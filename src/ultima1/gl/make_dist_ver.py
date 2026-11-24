# 前の版の配布物に、作り直した opengl32.dll（配布版）を入れて、新しい版の zip を作る（2026-11-24）
#   前の版の zip（<作品>/jp_work/prev_release/<zip>）を元にして、
#   DOSBOX/opengl32.dll を build.bat で作った配布版（out\opengl32.dll か out\<作品>\opengl32.dll）に差し替え、
#   説明書に「■ 更新履歴」を足す。ほかのファイルは中身も順番も変えない。
#   dist の zip（同じ中身の別名の zip も）と、展開済みのフォルダを作り直す。
#   release/<タグ>-<新しい版>.md も、前の版の文に「## <新しい版> で変わったこと」を足して作る。
# 使い方: python make_dist_ver.py [作品のキー ...]   （省くと 9 作すべて）
import os, sys, glob, zipfile, re

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
README = 'はじめにお読みください.txt'
DATE = '2026-11-24'
NOTE = ('ウイルス対策ソフトに誤検知されにくいよう、配布版に不要だった試験用のコードを外し、'
        'DLL にバージョン情報を入れました。訳文は前の版と同じです。')
NOTE_TXT = ['ウイルス対策ソフトに誤検知されにくいよう、配布版に不要だった試験用のコードを外し、',
            'DLL にバージョン情報を入れました。訳文は前の版と同じです。']

# キー、作品のフォルダ、zip の名前、新しい版
GAMES = [
    ('akalabeth', 'Akalabeth - World of Doom', 'Akalabeth_JP.zip', 'v1.2'),
    ('ultima1', 'Ultima 1', 'Ultima1_JP.zip', 'v1.4'),
    ('ultima2', 'Ultima 2', 'Ultima2_JP.zip', 'v1.2'),
    ('ultima3', 'Ultima 3', 'Ultima3_JP.zip', 'v1.2'),
    ('ultima4', 'Ultima 4 - Quest of the Avatar', 'Ultima4_JP.zip', 'v1.3'),
    ('ultima5', 'Ultima 5', 'Ultima5_JP.zip', 'v1.2'),
    ('ultima6', 'Ultima 6', 'Ultima6_JP.zip', 'v1.3'),
    ('martian', 'Martian Dreams', 'MartianDreams_JP.zip', 'v1.3'),
    ('savage', 'The Savage Empire', 'SavageEmpire_JP.zip', 'v1.2'),
]


def dll_of(key):
    return os.path.join(HERE, 'out', 'opengl32.dll') if key == 'ultima1' else os.path.join(HERE, 'out', key, 'opengl32.dll')


def add_history(text, ver, lines):
    """説明書（改行は \n）の「■ 最新版・ほかの作品」の前に「■ 更新履歴」を足す（もうあれば、その先頭に足す）"""
    entry = [f'  {ver}（{DATE}）'] + ['    ' + l for l in lines]
    ls = text.split('\n')
    if any(l.startswith('■ 更新履歴') for l in ls):
        k = next(i for i, l in enumerate(ls) if l.startswith('■ 更新履歴'))
        ls[k + 1:k + 1] = entry
    else:
        k = next(i for i, l in enumerate(ls) if l.startswith('■ 最新版'))
        ls[k:k] = ['■ 更新履歴'] + entry + ['']
    return '\n'.join(ls)


def fix_readme(key, data, ver):
    t = data.decode('utf-8-sig').replace('\r\n', '\n')
    assert f'{ver}（{DATE}）' not in t
    if key == 'ultima1':
        # Where Are We? の節: 起動設定は v1.3 と同じなので、版の番号だけ新しくする
        assert t.count('この版（v1.3）') == 1
        t = t.replace('この版（v1.3）', f'この版（{ver}）')
    t = add_history(t, ver, NOTE_TXT)
    return b'\xef\xbb\xbf' + t.replace('\n', '\r\n').encode('utf-8')


def notes(key, game, ver):
    rel = os.path.join(TOP, game, 'jp_work', 'release')
    out = os.path.join(rel, f'{key}-{ver}.md')
    olds = sorted(glob.glob(os.path.join(rel, f'{key}-v*.md')),
                  key=lambda p: [int(x) for x in re.findall(r'v(\d+)\.(\d+)', p)[-1]])
    olds = [p for p in olds if p != out]
    t = open(olds[-1], encoding='utf-8').read().replace('\r\n', '\n')
    sec = f'## {ver} で変わったこと\n\n- {NOTE}\n\n'
    k = t.index('\n## ') + 1
    t = t[:k] + sec + t[k:]
    open(out, 'w', encoding='utf-8', newline='\n').write(t)
    print('リリースの文:', out, '（元:', os.path.basename(olds[-1]) + '）')


def make(key, game, zname, ver):
    jp = os.path.join(TOP, game, 'jp_work')
    dist = os.path.join(jp, 'dist')
    src = os.path.join(jp, 'prev_release', zname)
    dll = open(dll_of(key), 'rb').read()
    entries = []
    with zipfile.ZipFile(src) as z:
        for i in z.infolist():
            data = z.read(i)
            if i.filename == 'DOSBOX/opengl32.dll':
                data = dll
            elif i.filename == README:
                data = fix_readme(key, data, ver)
            entries.append((i.filename, data))
    names = [n for n, _ in entries]
    assert 'DOSBOX/opengl32.dll' in names and README in names, names
    zips = sorted(os.path.basename(p) for p in glob.glob(os.path.join(dist, '*.zip')))
    assert zname in zips, zips
    for zn in zips:
        zpath = os.path.join(dist, zn)
        tmp = zpath + '.tmp'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for n, d in entries: zf.writestr(n, d)
        os.replace(tmp, zpath)
        print('作成:', zpath, os.path.getsize(zpath), 'バイト')
    for d in glob.glob(os.path.join(dist, '*日本語化パッチ')):
        if not os.path.isdir(d): continue
        for n, data in entries:
            out = os.path.join(d, *n.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'wb').write(data)
    notes(key, game, ver)


if __name__ == '__main__':
    want = sys.argv[1:]
    for g in GAMES:
        if not want or g[0] in want: make(*g)
