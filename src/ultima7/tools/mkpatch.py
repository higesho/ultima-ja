# Exult のパッチフォルダの中身（配布する形）を作る
#   使い方: python mkpatch.py 出力フォルダ   （例: test\patch）
# 配布物に原作のプログラムやデータを入れないため、訳と自作のものだけを書く。
# 原作のファイルへの当てはめは、改造した Exult が起動時に行う。
# 作るもの:
#   usecode_ja.tsv  会話などの訳。1行「関数(16進)<TAB>位置<TAB>原文のCRC32(16進)<TAB>訳」
#   textmsg.txt     物の名前・短い文の訳（Exult の文字の形式。すべて訳してある）
#   npc_names.txt   NPC の名前の訳。1行「英語の名前のCRC32(16進)<TAB>訳」
#   exultmsg.txt    Exult のメッセージの訳（translation/exultmsg_ja.txt）
#   mainshp.flx     オープニングなどの文の訳と、日本語で描き直したメニューの絵だけ（ほかの項目は空）
#   endshape.flx    オープニングの後半の字幕を日本語で描いた絵だけ（ほかの項目は空。mkintro.py）
#   gumps.vga       能力の窓・持ち物の窓の英字を日本語に描き替えた絵だけ（ほかの項目は空。mkgumps.py）
#   jfont8.bin / jfont12.bin  日本語フォント（美咲・東雲。すでにあるものを使う）
import sys, os, shutil, zlib
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..')
STATIC = os.path.join(W, '..', 'STATIC')
TR = os.path.join(W, 'translation')
sys.path.insert(0, HERE)
from u7uc import unesc
from u7flex import read_flex, write_flex

def crc(b):
    return zlib.crc32(b) & 0xffffffff

def make_usecode(out):
    n = nf = 0
    with open(os.path.join(out, 'usecode_ja.tsv'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('# 会話などの訳。関数(16進)\t位置\t原文のCRC32(16進)\t訳\n')
        for name in sorted(os.listdir(os.path.join(TR, 'usecode'))):
            fid = int(name[:4], 16); any_ = False
            for line in open(os.path.join(TR, 'usecode', name), encoding='utf-8'):
                c = line.rstrip('\n').split('\t')
                if line.startswith('#') or len(c) < 3 or not c[2]:
                    continue
                en = unesc(c[1]).encode('latin-1')
                w.write(f'{fid:04x}\t{c[0]}\t{crc(en):08x}\t{c[2]}\n')
                n += 1; any_ = True
            nf += any_
    print(f'{out}\\usecode_ja.tsv: 関数 {nf}、文字列 {n} 件')

def make_text(out):
    # TEXT.FLX の並び（BG）: 0〜0x3FF 物の名前、0x400〜0x4FF 短い文、0x500〜 そのほかの名前
    shapes, msgs, misc = [], [], []
    for line in open(os.path.join(TR, 'text_flx.tsv'), encoding='utf-8'):
        c = line.rstrip('\n').split('\t')
        if line.startswith('#') or len(c) < 3 or not c[2]:
            continue
        i = int(c[0]); ja = unesc(c[2])
        if '\n' in ja:
            sys.exit(f'TEXT {i}: 訳に改行があります')
        (shapes if i < 0x400 else msgs if i < 0x500 else misc).append((i if i < 0x400 else i - 0x400 if i < 0x500 else i - 0x500, ja))
    with open(os.path.join(out, 'textmsg.txt'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('# 物の名前・短い文の訳（Exult の text.msg の形式）\n')
        for sect, rows in (('shapes', shapes), ('msgs', msgs), ('miscnames', misc)):
            w.write(f'%%section {sect}\n')
            for i, ja in rows:
                w.write(f'{i:#x}:{ja}\n')
            w.write('%%endsection\n')
    print(f'{out}\\textmsg.txt: 物の名前 {len(shapes)}、短い文 {len(msgs)}、そのほか {len(misc)}')

def make_names(out):
    table = {}
    for line in open(os.path.join(TR, '固有名詞.tsv'), encoding='utf-8-sig'):
        c = line.rstrip('\r\n').split('\t')
        if not line.startswith('#') and len(c) >= 2 and c[1]:
            table.setdefault(c[0], c[1])
    names = [l.strip() for l in open(os.path.join(TR, 'npc_names_en.txt'), encoding='utf-8') if l.strip()]
    n = 0; missing = []
    with open(os.path.join(out, 'npc_names.txt'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('# NPC の名前の訳。英語の名前のCRC32(16進)\t訳\n')
        for name in names:
            if name == 'Avatar':
                continue
            if name in table:
                w.write(f'{crc(name.encode("latin-1")):08x}\t{table[name]}\n'); n += 1
            else:
                missing.append(name)
    print(f'{out}\\npc_names.txt: {n} 人' + (f'（一覧に無い名前: {" / ".join(missing)}）' if missing else ''))

def make_mainshp(out):
    from mkmenu import make_menu_shapes, MENU
    head, orig = read_flex(os.path.join(STATIC, 'MAINSHP.FLX'))
    # 元の絵から作り直したメニューの絵（色だけ元の絵から取る。字は日本語フォントで描く）
    work = list(orig)
    make_menu_shapes(work, os.path.join(out, 'jfont8.bin'))
    ents = [None] * len(orig)    # 空の項目は元のファイルから読まれる
    for idx in MENU:
        ents[idx] = work[idx]
    for name in sorted(os.listdir(os.path.join(TR, 'mainshp'))):
        if name.endswith('_ja.txt'):
            data = open(os.path.join(TR, 'mainshp', name), 'rb').read()
            ents[int(name[:2], 16)] = data[3:] if data.startswith(b'\xef\xbb\xbf') else data
    title = 'Ultima VII Japanese patch'.encode('ascii').ljust(0x50, b'\0')
    newhead = title + head[0x50:0x80]
    write_flex(os.path.join(out, 'mainshp.flx'), newhead, ents)
    print(f'{out}\\mainshp.flx: {sum(e is not None for e in ents)} 項目（ほかは空）')

def make_endshape(out):
    from mkintro import make_intro_shapes
    head, orig = read_flex(os.path.join(STATIC, 'ENDSHAPE.FLX'))
    ents = [None] * len(orig)    # 空の項目は元のファイルから読まれる
    for idx, data in make_intro_shapes().items():
        assert orig[idx], idx
        ents[idx] = data
    title = 'Ultima VII Japanese patch'.encode('ascii').ljust(0x50, b'\0')
    write_flex(os.path.join(out, 'endshape.flx'), title + head[0x50:0x80], ents)
    print(f'{out}\\endshape.flx: {sum(e is not None for e in ents)} 項目（ほかは空）')

def make_gumps(out):
    from mkgumps import make_gump_shapes
    head, orig = read_flex(os.path.join(STATIC, 'GUMPS.VGA'))
    ents = [None] * len(orig)    # 空の項目は元のファイルから読まれる
    for idx, data in make_gump_shapes(orig, os.path.join(out, 'jfont8.bin')).items():
        ents[idx] = data
    title = 'Ultima VII Japanese patch'.encode('ascii').ljust(0x50, b'\0')
    write_flex(os.path.join(out, 'gumps.vga'), title + head[0x50:0x80], ents)
    print(f'{out}\\gumps.vga: {sum(e is not None for e in ents)} 項目（ほかは空）')

def main(out):
    os.makedirs(out, exist_ok=True)
    # 前の形（原作を写したもの）が残っていたら消す
    for old in ('usecode', 'text.flx'):
        p = os.path.join(out, old)
        if os.path.exists(p):
            os.remove(p); print(f'{p}: 前の形のファイルを消しました')
    make_usecode(out)
    make_text(out)
    make_names(out)
    shutil.copyfile(os.path.join(TR, 'exultmsg_ja.txt'), os.path.join(out, 'exultmsg.txt'))
    print(f'{out}\\exultmsg.txt: 写しました')
    make_mainshp(out)
    make_endshape(out)
    make_gumps(out)

if __name__ == '__main__':
    main(sys.argv[1])
