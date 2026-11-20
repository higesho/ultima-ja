# 0・III〜VI・外伝2作の配布物に、窓の表示と東雲フォントの DLL を足して作り直す
#   公開中の zip（dist/<前の版>_backup に控える）を元にして、
#   起動設定に [sdl] [render] を足し、DOSBOX/opengl32.dll と DOSBOX/ultima_ja.ini を加え、説明書に説明を足す。
#   ほかのファイルは中身を変えない。dist の展開済みフォルダも同じ中身にそろえる。
# 使い方: python make_dist_more.py [mm] [--dry]     --dry は説明書の差分を見せるだけ
import os, sys, glob, shutil, zipfile, difflib, unicodedata

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
DLL = os.path.join(HERE, 'out', 'opengl32.dll')
INI = os.path.join(HERE, 'ultima_ja.ini')
README = 'はじめにお読みください.txt'
sys.path.insert(0, HERE)
from sim import add_view  # noqa: E402

# 作品のフォルダ、zip の名前、いまの版
GAMES = [
    ('Akalabeth - World of Doom', 'Akalabeth_JP.zip', 'v1.0'),
    ('Ultima 3', 'Ultima3_JP.zip', 'v1.0'),
    ('Ultima 4 - Quest of the Avatar', 'Ultima4_JP.zip', 'v1.1'),
    ('Ultima 5', 'Ultima5_JP.zip', 'v1.0'),
    ('Ultima 6', 'Ultima6_JP.zip', 'v1.0'),
    ('Martian Dreams', 'MartianDreams_JP.zip', 'v1.0'),
    ('The Savage Empire', 'SavageEmpire_JP.zip', 'v1.0'),
]
# マイト・アンド・マジック 1〜3（python make_dist_more.py mm）
GAMES_MM = [
    ('Might and Magic 1', 'MightAndMagic1_JP.zip', 'v1.0'),
    ('Might and Magic 2', 'MightAndMagic2_JP.zip', 'v1.0'),
    ('Might and Magic 3', 'MightAndMagic3_JP.zip', 'v1.0'),
]

VIEW = """■ 窓と字の形
  ・ゲームは窓で起動します。窓のふちをドラッグすると、大きさを自由に変えられます。
    最大化もできます。変えた大きさは次の起動でも使われます。
    Alt＋Enter で全画面と窓を切り替えられます。
  ・日本語の字の形は、東雲フォント（12ドット）と美咲フォント（8ドット）から選べます。
    最初は東雲フォントです。ゲーム中に F11 キーを押すと切り替わります。
  ・設定は DOSBOX フォルダの ultima_ja.ini で変えられます（窓の大きさ、縦横の比、広げ方など）。
  ・英字や数字、絵、全角の記号はゲームのままの形で、大きく広げて表示します。
"""
STEAM = "  ・Steam 版では、窓の表示と東雲フォントの動きを確かめていません。\n"
FONT_OLD = """■ フォントについて
  日本語の表示には「美咲フォント」（8×8ドット）を使っています。
    美咲フォント (c) 門真 なむ  https://littlelimit.net/misaki.htm
  美咲フォントは、改変の有無や商用・非商用を問わず、自由に利用・複製・再配布できる
  フリーソフトウエアです（無保証）。
"""
FONT_NEW = """■ フォントについて
  日本語の表示には「美咲フォント」（8×8ドット）と「東雲フォント」（12ドット）を使っています。
    美咲フォント (c) 門真 なむ  https://littlelimit.net/misaki.htm
    東雲フォント /efont/       http://openlab.ring.gr.jp/efont/shinonome/
  美咲フォントは、改変の有無や商用・非商用を問わず、自由に利用・複製・再配布できる
  フリーソフトウエアです（無保証）。
  東雲フォントはパブリックドメインで提供されているフォントです（無保証）。
"""


def width(s):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def section(lines, head):
    """head で始まる節の [始まり, 終わり) の行番号"""
    a = next(i for i, l in enumerate(lines) if l.startswith(head))
    b = next((i for i in range(a + 1, len(lines)) if lines[i].startswith('■')), len(lines))
    return a, b


def fix_readme(text):
    t = text.replace('\r\n', '\n')
    if '■ 窓と字の形' in t: return t
    lines = t.split('\n')
    # 入っているファイル
    a, b = section(lines, '■ 入っているファイル')
    k = next(i for i in range(a, b) if lines[i].lstrip().startswith(README))
    col = width(lines[k][:lines[k].index('この文書')])
    ind = lines[k][:len(lines[k]) - len(lines[k].lstrip())]
    new = []
    for name, desc in (('DOSBOX\\opengl32.dll', '窓の大きさの変更と、東雲フォントでの表示'),
                       ('DOSBOX\\ultima_ja.ini', '表示の設定（メモ帳で書き換えられます）')):
        head = ind + name
        new.append(head + ' ' * max(2, col - width(head)) + desc)
    lines[k:k] = new
    # 導入のしかた: 「上書き」の行のあとに、DOSBOX フォルダのことを書く
    a, b = section(lines, '■ 導入のしかた')
    k = next(i for i in range(a, b) if '上書き' in lines[i])
    ind = ' ' * 5
    lines[k + 1:k + 1] = [ind + 'DOSBOX フォルダも、ゲームのフォルダの中の DOSBOX フォルダにコピーします',
                          ind + '（opengl32.dll と ultima_ja.ini が増えます）。']
    # 元に戻すには
    a, b = section(lines, '■ 元に戻すには')
    k = next((i for i in range(a, b) if lines[i].startswith('  ・セーブデータ')), None)
    if k is None:
        k = b
        while k > a + 1 and not lines[k - 1].strip(): k -= 1
    lines[k:k] = ['  ・DOSBOX フォルダに増えた opengl32.dll と ultima_ja.ini も削除してください。']
    t = '\n'.join(lines)
    # 窓と字の形
    view = VIEW + (STEAM if 'Steam' in t else '') + '\n'
    for h in ('■ 遊び方の注意', '■ 遊ぶときの注意', '■ 注意・既知の制限', '■ フォントについて'):
        if '\n' + h in t:
            t = t.replace('\n' + h, '\n' + view + h, 1)
            break
    else:
        raise RuntimeError('窓と字の形を入れる場所がない')
    assert FONT_OLD in t, 'フォントの節が違う'
    return t.replace(FONT_OLD, FONT_NEW)


def make(game, zname, ver, dry):
    dist = os.path.join(TOP, game, 'jp_work', 'dist')
    bak = os.path.join(dist, f'{ver}_backup')
    zips = [os.path.basename(p) for p in glob.glob(os.path.join(dist, '*.zip'))]
    if not dry:
        os.makedirs(bak, exist_ok=True)
        for z in zips:
            if not os.path.exists(os.path.join(bak, z)): shutil.copyfile(os.path.join(dist, z), os.path.join(bak, z))
    src_zip = os.path.join(bak if os.path.exists(os.path.join(bak, zname)) else dist, zname)
    entries = []
    with zipfile.ZipFile(src_zip) as z:
        for i in z.infolist():
            data = z.read(i)
            if i.filename.endswith('.conf'):
                data = add_view(data)
            elif i.filename == README:
                old = data.decode('utf-8-sig')
                new = fix_readme(old)
                if dry:
                    print('=====', game)
                    for l in difflib.unified_diff(old.replace('\r\n', '\n').split('\n'), new.split('\n'), lineterm='', n=0):
                        print(l)
                data = b'\xef\xbb\xbf' + new.replace('\n', '\r\n').encode('utf-8')
            entries.append((i.filename, data))
    if dry: return
    names = [n for n, _ in entries]
    k = names.index(README)
    entries[k:k] = [('DOSBOX/opengl32.dll', open(DLL, 'rb').read()), ('DOSBOX/ultima_ja.ini', open(INI, 'rb').read())]
    for z in zips:
        zpath = os.path.join(dist, z)
        tmp = zpath + '.tmp'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for n, d in entries: zf.writestr(n, d)
        os.replace(tmp, zpath)
        print('作成:', zpath, os.path.getsize(zpath), 'バイト')
    # 展開済みのフォルダもそろえる
    for d in glob.glob(os.path.join(dist, '*日本語化パッチ')):
        if not os.path.isdir(d): continue
        for n, data in entries:
            out = os.path.join(d, *n.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'wb').write(data)


if __name__ == '__main__':
    dry = '--dry' in sys.argv
    for g in (GAMES_MM if 'mm' in sys.argv else GAMES): make(*g, dry)
