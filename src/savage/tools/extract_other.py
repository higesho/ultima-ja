"""会話以外の英文を書き出す（翻訳用。SE 用に直した。本は無く、物の名前は LOOK.LZC）。
  translation/other_en/book.tsv   本・看板など（BOOK.DAT、128件）  番号 book:000
  translation/other_en/look.tsv   物の名前（LOOK.LZD）             番号 look:0001（タイルの番号、16進）
  translation/other_en/game.tsv   本編 GAME.EXE のデータの文字列   番号 game:0a8c（データの中の位置）
  translation/other_en/u.tsv      タイトル・導入・キャラクター作成 U.EXE  番号 u:1234（イメージの中の位置）
  translation/other_en/end.tsv    エンディング END.EXE             番号 end:1234
使い方: python extract_other.py <ゲームのフォルダ> <出力のフォルダ>
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from conv_text import esc  # noqa: E402

DGROUP = 0x2FA6
SEG2 = 0x2F65     # DGROUP の手前の、文字列だけのセグメント
SKIP = re.compile(rb'(?i)(\.(cga|ega|hrc|tga|vga|shp|drv|m|bmp|lzd|ptr|exe|dat|u6|ch|set|pal|lbm|int|bin)$'
                  rb'|^savegame|^lzobjblk|^lzdngblk|^objblk|^objlist|^tileflag|^basetile|^chunks$|^map$|^schedule$'
                  rb'|^portrait|^converse|^config|^u6pal|^tileindx|^maptiles|^objtiles|^masktype|^animdata|^dither'
                  rb'|^Turbo-C|^Null pointer|^Divide error|^Abnormal program|^\(null\)|^print scanf|^Floating point'
                  rb'|^MS Run-Time)')


def strings_in(img, lo, hi, min_letters=2):
    """lo〜hi の中の、0 で終わる表示用らしい文字列: [(位置, bytes)]"""
    out = []
    for m in re.finditer(rb'[\x20-\x7e\n]{2,}(?=\0)', img[lo:hi]):
        s = m.group()
        p = lo + m.start()
        if p > 0 and img[p - 1] not in (0,) and not (0x80 <= img[p - 1]):
            # 前が 0 でない（別の文字列の後半）ものは、前が表示できない値のときだけ取る
            if 0x20 <= img[p - 1] <= 0x7e or img[p - 1] == 0x0a:
                continue
        if len(re.findall(rb'[A-Za-z]', s)) < min_letters or SKIP.search(s.strip()):
            continue
        if not re.search(rb'[a-z]{3}|[A-Z][a-z]{2}|[A-Z]{4}', s):   # コードの一部が文字に見えたもの（DD-A など）を外す
            continue
        out.append((p, s))
    return out


def write(path, head, rows):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(head)
        for key, b in rows:
            f.write(f"{key}\t{esc(b)}\n")
    print(f"{path}: {len(rows)} 件")


def main(gamedir, outdir):
    os.makedirs(outdir, exist_ok=True)
    from sefmt import lzc_items
    # 物の名前（LOOK.LZC の 0 番、圧縮なし）
    raw = lzc_items(open(os.path.join(gamedir, 'LOOK.LZC'), 'rb').read())[0][1]
    rows = []
    p = 0
    while p + 2 < len(raw):
        tile = struct.unpack_from('<H', raw, p)[0]
        p += 2
        e = raw.find(bytes([0]), p)
        if e < 0:
            break
        if re.search(rb'[A-Za-z]{2}', raw[p:e]):
            rows.append((f"look:{tile:04x}", raw[p:e]))
        p = e + 1
    write(os.path.join(outdir, 'look.tsv'),
          "# 物の名前（LOOK.LZC）。番号はタイルの番号（16進）\n", rows)
    # 本編
    exe = open(os.path.join(gamedir, 'GAME.EXE'), 'rb').read()
    img = exe[struct.unpack_from('<H', exe, 8)[0] * 16:]
    ds = DGROUP * 16
    rows = [(f"game:{p - ds:04x}", s) for p, s in strings_in(img, ds, len(img))]
    write(os.path.join(outdir, 'game.tsv'),
          "# 本編 GAME.EXE の文字列。訳は元の英語の字数以内（全角も半角も1字）。%s %d などはそのまま残す\n", rows)
    # 本編の途中の場面 MIDGAME1〜5.LZC の文（項目ごとに 0 終わりの1文。*END* はページの終わりの印なので外す）
    rows = []
    for n in range(1, 6):
        for i, (f, b) in enumerate(lzc_items(open(os.path.join(gamedir, f'MIDGAME{n}.LZC'), 'rb').read())):
            if b and b.endswith(bytes([0])) and re.fullmatch(rb'[\x20-\x7e\n]+', b[:-1]) and b[:-1] != b'*END*':
                rows.append((f"mid{n}:{i:02d}", b[:-1]))
    write(os.path.join(outdir, 'midgame.tsv'),
          "# 本編の途中の場面（MIDGAME1〜5.LZC）。番号は mid<場面>:<項目>。長さの決まりはない（画面の下の欄に出る）\n", rows)
    # DGROUP の手前の、文字列だけのセグメント 0x2F65（戦闘・操作の短いメッセージ。初めは書き出し漏れていた）
    s2 = SEG2 * 16
    rows = [(f"game2:{p - s2:04x}", s) for p, s in strings_in(img, s2, ds)]
    write(os.path.join(outdir, 'game2.tsv'),
          "# 本編 GAME.EXE のセグメント 0x2F65 の文字列（番号はセグメントの中の位置）。決まりは game.tsv と同じ\n", rows)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(sys.argv[1], sys.argv[2])
