# -*- coding: utf-8 -*-
"""訳の TSV から日本語化のファイルを組み立てる。

作るもの（出力先のゲームフォルダに書く）:
  USECODE/JUSECODE.FLX   英語版の usecode の文を訳に差し替えたもの（未訳は英文のまま）
  STATIC/EINTRO.SKF      オープニングの字幕を訳に差し替えたもの
  STATIC/U8FONTS.FLX     16番に漢字フォント（PixelMplus10）を足したもの
出力先が無ければ、英語版のフォルダを丸ごと写してから書く。

使い方: python -I tools/build_jp.py [出力先のゲームフォルダ]   （省略すると test/u8jp）
"""
import sys, os, glob, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u8uc import Usecode
from u8shape import read_flex, write_flex
from strdb import read_tsv, en_from_bytes, en_to_game, split_space
from jpenc import encode
import build_jpfont
from paginate import Layout

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GAME = os.path.normpath(os.path.join(ROOT, '..', 'ENGLISH'))
TR = os.path.join(ROOT, 'translation')
EMPTY = '{空}'      # ja にこう書くと、その文を空にする
FONT = 'ttf:' + os.path.join(ROOT, 'font', 'PixelMplus-20130602', 'PixelMplus-20130602', 'PixelMplus10-Regular.ttf') + ':10'


def with_spaces(en, ja):
    """英文の前後の空白を訳に付ける。ただし訳の端が日本語の字なら、その側には付けない
    （「よろしくな、 avatar。」のように空白が入ると、ScummVM がそこで行を折ってしまうため）。"""
    lead, core, trail = split_space(en)
    if ja and ord(ja[0]) >= 0x80:
        lead = ''
    if ja and ord(ja[-1]) >= 0x80:
        trail = ''
    return lead + ja + trail


def to_game(en, ja):
    """ゲーム用のバイト列にする。"""
    if not ja:
        return en_to_game(en)
    if ja == EMPTY:          # 日本語では要らない断片（複数の s など）
        return b''
    return encode(with_spaces(en, ja))


def load_tables():
    """{クラス番号: {英文: 訳}} と {字幕の項目: 訳}"""
    uc, skf = {}, {}
    for p in glob.glob(os.path.join(TR, 'usecode', '*.tsv')):
        for r in read_tsv(p):
            cid = int(r['key'].split(':')[0], 16)
            uc.setdefault(cid, {})[r['en']] = r['ja']
    for r in read_tsv(os.path.join(TR, 'intro.tsv')):
        skf[int(r['key'].split(':')[1])] = (r['en'], r['ja'])
    return uc, skf


# 文を表示する命令（intrinsic の番号）。本・巻物・墓碑・銘板はせりふの枠ではないのでページ分けを直さない
DOC_INTRINSICS = {0x6E, 0x6F, 0x70, 0x71}      # Book / Scroll / Grave / Plaque::read
BARK_INTRINSICS = {0x49, 0x4A}                 # Item::bark / Item::ask


def doc_strings(uc):
    """本などに出る文の (クラス番号, 英文) の集合。文の後で最初に呼ばれる表示の命令で見分ける。"""
    docs = set()
    for c in uc.classes():
        ins = c.ins
        for i, x in enumerate(ins):
            if x.op != 0x0D:
                continue
            for y in ins[i + 1:i + 80]:
                if y.op == 0x0F:
                    fid = y.raw[2] | (y.raw[3] << 8)
                    if fid in DOC_INTRINSICS:
                        docs.add((c.classid, en_from_bytes(x.text)))
                        break
                    if fid in BARK_INTRINSICS:
                        break
                if y.op in (0x50, 0x7A):
                    break
    return docs


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'test', 'u8jp')
    if not os.path.isdir(out):
        shutil.copytree(GAME, out)
        print('英語版を写しました →', out)
    uct, skft = load_tables()

    # フォント（ページ分けの計算に字の幅を使うので先に作る）
    fontflx = os.path.join(out, 'STATIC', 'U8FONTS.FLX')
    build_jpfont.build(os.path.join(GAME, 'STATIC', 'U8FONTS.FLX'), fontflx, FONT)
    lay = Layout(fontflx)

    # usecode
    uc = Usecode(os.path.join(GAME, 'USECODE', 'EUSECODE.FLX'))
    docs = doc_strings(uc)
    n_ja = n_en = 0
    n_fix = n_fail = n_widow = 0
    for c in uc.classes():
        tab = uct.get(c.classid, {})
        for s in c.strings():
            en = en_from_bytes(s.text)
            if not en.strip():
                continue
            ja = tab.get(en, '')
            if ja and ja != EMPTY and (c.classid, en) not in docs:
                # せりふ: 文の途中でページが分かれないように ~ を足す
                ja2, f, g = lay.fix(with_spaces(en, ja))
                ja2, w = lay.fix_widows(ja2)       # 最後の行が 1〜2 文字だけになるのを防ぐ
                n_fix += f
                n_fail += g
                n_widow += w
                s.text = encode(ja2)
            else:
                s.text = to_game(en, ja)
            if ja:
                n_ja += 1
            else:
                n_en += 1
    open(os.path.join(out, 'USECODE', 'JUSECODE.FLX'), 'wb').write(uc.build())
    print('usecode: 訳 %d 件、英文のまま %d 件' % (n_ja, n_en))
    print('ページ分け: 文の切れ目に直した %d か所、文の切れ目が見つからず直せなかった %d か所、'
          '最後の行が短すぎるのをならした %d か所（本などの %d 件は対象外）'
          % (n_fix, n_fail, n_widow, len(docs)))

    # 字幕
    raw = open(os.path.join(GAME, 'STATIC', 'EINTRO.SKF'), 'rb').read()
    ents = read_flex(raw)
    for k, (en, ja) in skft.items():
        e = ents[k]
        assert e[:4] == b'\x11\x00\x00\x00' and e[-1] == 0, k
        ents[k] = e[:6] + to_game(en, ja) + b'\x00'
    open(os.path.join(out, 'STATIC', 'EINTRO.SKF'), 'wb').write(write_flex(raw[:0x80], ents))
    print('字幕: 訳 %d / %d' % (sum(1 for v in skft.values() if v[1]), len(skft)))


main()
