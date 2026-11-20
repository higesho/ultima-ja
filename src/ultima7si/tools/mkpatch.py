# サーペントアイルの Exult のパッチフォルダの中身（配布する形）を作る
#   使い方: python mkpatch.py 出力フォルダ   （例: test\patch）
# 配布物に原作のプログラムやデータを入れないため、訳と自作のものだけを書く（BG の mkpatch.py と同じ形）。
# 原作のファイルへの当てはめは、改造した Exult（BG 側でビルドしたもの）が起動時に行う。
# 作るもの:
#   usecode_ja.tsv  会話などの訳。1行「関数(16進)<TAB>位置<TAB>原文のCRC32(16進)<TAB>訳」（訳が原文と同じ行は入れない）
#   textmsg.txt     物の名前・ひとこと・そのほかの名前の訳（Exult の文字の形式。中身のある項目はすべて訳してある）
#   npc_names.txt   NPC の名前の訳。1行「英語の名前のCRC32(16進)<TAB>訳」
#   exultmsg.txt    Exult のメッセージの訳（BG の訳に、SI の字幕の訳を重ねる）
#   mainshp.flx     スタッフ一覧・名言集の訳と、日本語で描き直したメニューの絵だけ（ほかの項目は空）
#   gumps.vga       ステータスの窓と戦闘の窓の見出しを日本語にした絵だけ（mkgumps.py。原作の絵は写さず形と色番号から描き直す。ほかの項目は空）
#   jfont8.bin / jfont12.bin  日本語フォント（BG のパッチから写す）
import sys, os, re, shutil, zlib
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.normpath(os.path.join(HERE, '..'))
STATIC = os.path.join(W, '..', 'STATIC')
TR = os.path.join(W, 'translation')
BG = os.path.normpath(os.path.join(W, '..', '..', 'Ultima 7', 'jp_work'))   # 読むだけ
sys.path.insert(0, HERE)
from si_uc import unesc
from u7flex import read_flex, write_flex

def crc(b):
    return zlib.crc32(b) & 0xffffffff

def make_usecode(out):
    n = nf = same = 0
    with open(os.path.join(out, 'usecode_ja.tsv'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('# 会話などの訳（サーペントアイル）。関数(16進)\t位置\t原文のCRC32(16進)\t訳\n')
        for name in sorted(os.listdir(os.path.join(TR, 'usecode'))):
            if not re.fullmatch(r'[0-9a-f]{4}\.tsv', name):
                continue
            fid = int(name[:4], 16); any_ = False
            for line in open(os.path.join(TR, 'usecode', name), encoding='utf-8'):
                c = line.rstrip('\n').split('\t')
                if line.startswith('#') or len(c) < 3 or not c[2]:
                    continue
                if c[2] == c[1]:
                    same += 1; continue      # 英語のまま残す行（看板など）
                en = unesc(c[1]).encode('latin-1')
                w.write(f'{fid:04x}\t{c[0]}\t{crc(en):08x}\t{c[2]}\n')
                n += 1; any_ = True
            nf += any_
    print(f'usecode_ja.tsv: 関数 {nf}、文字列 {n} 件（英語のまま残す {same} 件は入れない）')

def make_text(out):
    # TEXT.FLX の並び: 0〜0x3FF 物の名前、0x400〜0x4FF ひとこと、0x500〜0x685 そのほかの名前（Exult は 0x686 から先を読まない）
    shapes, msgs, misc = [], [], []
    for line in open(os.path.join(TR, 'text_ja.tsv'), encoding='utf-8-sig'):
        c = line.rstrip('\r\n').split('\t', 1)
        if line.startswith('#') or len(c) < 2 or not c[1]:
            continue
        i = int(c[0], 0); ja = c[1]
        if '\n' in ja or i >= 0x686:
            sys.exit(f'TEXT {i}: 改行があるか、番号が範囲の外です')
        (shapes if i < 0x400 else msgs if i < 0x500 else misc).append((i if i < 0x400 else i - 0x400 if i < 0x500 else i - 0x500, ja))
    with open(os.path.join(out, 'textmsg.txt'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('# 物の名前・ひとこと・そのほかの名前の訳（サーペントアイル。Exult の text.msg の形式）\n')
        for sect, rows in (('shapes', shapes), ('msgs', msgs), ('miscnames', misc)):
            w.write(f'%%section {sect}\n')
            for i, ja in sorted(rows):
                w.write(f'{i:#x}:{ja}\n')
            w.write('%%endsection\n')
    print(f'textmsg.txt: 物の名前 {len(shapes)}、ひとこと {len(msgs)}、そのほか {len(misc)}')

def name_table():
    """英語の名前 → 訳。優先: npc_names_extra.tsv > SI の用語集 > BG の固有名詞.tsv"""
    table = {}
    def add(e, j):
        e = re.sub(r'（.*?）|\(.*?\)', '', e).strip(); j = re.sub(r'（.*?）|\(.*?\)', '', j).strip()
        if e and j and not re.search('[A-Za-z]', j):
            table.setdefault(e, j)
    for line in open(os.path.join(TR, 'npc_names_extra.tsv'), encoding='utf-8-sig'):
        c = line.rstrip('\r\n').split('\t')
        if not line.startswith('#') and len(c) >= 2:
            add(c[0], c[1])
    for line in open(os.path.join(TR, '用語集.md'), encoding='utf-8'):
        if line.startswith('|') and not line.startswith('|---'):
            c = [x.strip() for x in line.strip().strip('|').split('|')]
            if len(c) >= 2:
                es = [x.strip() for x in c[0].split('/')]; js = [x.strip() for x in c[1].split('/')]
                if len(es) == len(js):
                    for e, j in zip(es, js):
                        add(e, j)
        for m in re.finditer(r"([A-Z][A-Za-z'\-]+(?: [A-Z][A-Za-z'\-]+)*) ([ァ-ヶー・]+)", line):
            add(m.group(1), m.group(2))
        for m in re.finditer(r"([ァ-ヶー・]+)（([A-Z][A-Za-z'\- ]+)）", line):
            add(m.group(2), m.group(1))
    for line in open(os.path.join(BG, 'translation', '固有名詞.tsv'), encoding='utf-8-sig'):
        c = line.rstrip('\r\n').split('\t')
        if not line.startswith('#') and len(c) >= 2 and c[1]:
            add(c[0], c[1])
    return table

def make_names(out):
    table = name_table()
    names = [l.strip() for l in open(os.path.join(TR, 'npc_names_en.txt'), encoding='utf-8') if l.strip()]
    n = 0; missing = []
    with open(os.path.join(out, 'npc_names.txt'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('# NPC の名前の訳（サーペントアイル）。英語の名前のCRC32(16進)\t訳\n')
        for name in names:
            if name == 'Avatar':
                continue
            if name in table:
                w.write(f'{crc(name.encode("latin-1")):08x}\t{table[name]}\n'); n += 1
            else:
                missing.append(name)
    print(f'npc_names.txt: {n} 人（訳のない名前の断片など: {" / ".join(missing)}）')

def make_exultmsg(out):
    # BG の訳（Exult のメニューなど）を土台にし、SI の字幕の訳で同じ番号を上書きする
    si = {}
    for line in open(os.path.join(TR, 'exultmsg_si_ja.txt'), encoding='utf-8-sig'):
        m = re.match(r'(0x[0-9A-Fa-f]+):(.*)$', line.rstrip('\r\n'))
        if m:
            si[int(m.group(1), 16)] = line.rstrip('\r\n')
    out_lines = []; used = set()
    for line in open(os.path.join(BG, 'translation', 'exultmsg_ja.txt'), encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        m = re.match(r'(0x[0-9A-Fa-f]+):', line)
        if m and int(m.group(1), 16) in si:
            k = int(m.group(1), 16); out_lines.append(si[k]); used.add(k)
        else:
            out_lines.append(line)
    rest = [si[k] for k in sorted(si) if k not in used]
    if rest:
        sys.exit(f'exultmsg: BG の訳にない番号があります: {[hex(k) for k in sorted(si) if k not in used]}')
    with open(os.path.join(out, 'exultmsg.txt'), 'w', encoding='utf-8', newline='\n') as w:
        w.write('\n'.join(out_lines) + '\n')
    print(f'exultmsg.txt: {len(out_lines)} 行（SI の字幕 {len(used)} 行を重ねた）')

def make_mainshp(out):
    from mkmenu import make_menu_shapes, MENU
    head, orig = read_flex(os.path.join(STATIC, 'MAINSHP.FLX'))
    work = list(orig)
    make_menu_shapes(work, os.path.join(out, 'jfont8.bin'), pal=orig[26])   # 26 番はメニューのパレット
    ents = [None] * len(orig)    # 空の項目は元のファイルから読まれる
    for idx in MENU:
        ents[idx] = work[idx]
    for name in sorted(os.listdir(os.path.join(TR, 'mainshp'))):
        if name.endswith('_ja.txt'):
            data = open(os.path.join(TR, 'mainshp', name), 'rb').read()
            ents[int(name[:2], 16)] = data[3:] if data.startswith(b'\xef\xbb\xbf') else data
    title = 'Ultima VII Serpent Isle Japanese patch'.encode('ascii').ljust(0x50, b'\0')
    write_flex(os.path.join(out, 'mainshp.flx'), title + head[0x50:0x80], ents)
    print(f'mainshp.flx: {sum(e is not None for e in ents)} 項目（ほかは空）')

def main(out):
    os.makedirs(out, exist_ok=True)
    # 前の形（原作を写したもの）が残っていたら消す
    for old in ('usecode', 'text.flx'):
        p = os.path.join(out, old)
        if os.path.exists(p):
            os.remove(p); print(f'{old}: 前の形のファイルを消しました')
    for f in ('jfont8.bin', 'jfont12.bin'):
        shutil.copyfile(os.path.join(BG, 'test', 'patch', f), os.path.join(out, f))
    make_usecode(out)
    make_text(out)
    make_names(out)
    make_exultmsg(out)
    make_mainshp(out)
    from mkgumps import make_gumps
    print(f'gumps.vga: {make_gumps(out, os.path.join(out, "jfont8.bin"))} 個の絵（ほかは空）')

if __name__ == '__main__':
    main(sys.argv[1])
