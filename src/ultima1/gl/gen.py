# opengl32.dll（代わり）の組み立てに使う表を作る
#   exports.h  … 本物の opengl32.dll の関数を、そのまま本物へつなぐための表
#   glyphs.h   … 美咲フォント 8x8 の形 → 東雲フォント 12x12 の形
#   build.bat  … 組み立て（Shift-JIS で保存する）
import os, sys, struct, collections
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
U1 = os.path.normpath(os.path.join(HERE, '..'))
U2 = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'Ultima 2', 'jp_work'))
sys.path.insert(0, os.path.join(U1, 'tools'))
from jpenc import load_bdf  # noqa: E402

MISAKI = os.path.join(U1, 'font', 'dl', 'misaki_gothic_2nd.bdf')
SHN = os.path.join(U1, 'font', 'shinonome_dl', 'shinonome-0.9.11', 'bdf', 'shnmk12.bdf')
SYS_GL = r'C:\Windows\SysWOW64\opengl32.dll'

# 自分で中身を書く関数（それ以外は本物へそのままつなぐ）
HOOKS = {
    'glGetString': 4, 'glTexImage2D': 36, 'glTexSubImage2D': 36, 'glNewList': 8, 'glEndList': 0,
    'glTexCoord2f': 8, 'glCallList': 4,
}


def gen_exports():
    pe = pefile.PE(SYS_GL, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    names = [e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name]
    for h in HOOKS:
        assert h in names, h
    out = ['/* gen.py が作る。手で直さない */', f'#define NREAL {len(names)}',
           'static const char *real_names[NREAL] = {']
    out += [f'    "{n}",' for n in names] + ['};']
    for i, n in enumerate(names):
        out.append(f'#define IX_{n} {i}')
    for i, n in enumerate(names):
        if n in HOOKS:
            out.append(f'#pragma comment(linker, "/EXPORT:{n}=_hk_{n}@{HOOKS[n]}")')
        else:
            out.append(f'__declspec(naked) void st_{n}(void) {{ __asm jmp dword ptr [g_real + {4 * i}] }}')
            out.append(f'#pragma comment(linker, "/EXPORT:{n}=_st_{n}")')
    open(os.path.join(HERE, 'exports.h'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('exports:', len(names))


def load_shn(path):
    """東雲 12px の BDF。戻り値: JIS コード → 12 行（各行 12 ビット、左端が bit11）"""
    g = {}; cur = None; rows = None; bbx = None; asc = 10
    for line in open(path, encoding='latin1'):
        t = line.split()
        if not t: continue
        if t[0] == 'FONT_ASCENT': asc = int(t[1])
        elif t[0] == 'ENCODING': cur = int(t[1])
        elif t[0] == 'BBX': bbx = list(map(int, t[1:5]))
        elif t[0] == 'BITMAP': rows = []
        elif t[0] == 'ENDCHAR':
            w, h, xo, yo = bbx
            r12 = [0] * 12; top = asc - (yo + h)
            for i, r in enumerate(rows):
                y = top + i
                v = int(r, 16) << (16 - 4 * len(r)) if len(r) < 4 else int(r[:4], 16)
                if 0 <= y < 12: r12[y] = (v >> (4 + xo)) & 0xFFF
            g[cur] = r12; rows = None
        elif rows is not None: rows.append(t[0])
    return g


def sjis_to_jis(b):
    s1, s2 = b[0], b[1]
    if s1 >= 0xE0: s1 -= 0x40
    j1 = (s1 - 0x81) * 2 + 0x21
    if s2 >= 0x9F:
        j1 += 1; j2 = s2 - 0x7E
    else:
        j2 = s2 - 0x1F - (1 if s2 >= 0x80 else 0)
    return (j1 << 8) | j2


def gen_glyphs():
    mis = load_bdf(MISAKI)
    shn = load_shn(SHN)
    freq = collections.Counter()
    # 美咲フォントで日本語を出している作品すべての訳から、字を集める
    games = ['Ultima 1', 'Ultima 2', 'Akalabeth - World of Doom', 'Ultima 3', 'Ultima 4 - Quest of the Avatar',
             'Ultima 5', 'Ultima 6', 'Martian Dreams', 'The Savage Empire',
             'Might and Magic 1', 'Might and Magic 2', 'Might and Magic 3']
    top = os.path.normpath(os.path.join(U1, '..', '..'))
    for g in games:
        root = os.path.join(top, g, 'jp_work', 'translation')
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if fn.endswith(('.tsv', '.txt', '.json', '.csv')):
                    freq.update(open(os.path.join(dp, fn), encoding='utf-8', errors='ignore').read())
    # 訳に出てくる全角の字に、かなと記号をすべて足す
    chars = set()
    for ch in list(freq):
        try: b = ch.encode('cp932')
        except UnicodeEncodeError: continue
        if len(b) == 2: chars.add(ch)
    for code in range(0x8140, 0x8397):
        try: ch = struct.pack('>H', code).decode('cp932')
        except UnicodeDecodeError: continue
        if len(ch) == 1: chars.add(ch)
    best = {}
    skipped = []

    def japanese(ch):
        # かな・漢字と、日本語の句読点・かっこだけ（全角の英数字や記号は、ゲームの英字と同じ形のことがある）
        o = ord(ch)
        return (0x3041 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0x3001 <= o <= 0x3002 or
                0x3005 <= o <= 0x3011 or o in (0x301C, 0x2026, 0x2025))
    for ch in sorted(c for c in chars if japanese(c)):
        m = mis.get(ord(ch))
        jis = sjis_to_jis(ch.encode('cp932'))
        s = shn.get(jis)
        if m is None or s is None or not any(m): skipped.append(ch); continue
        key = int.from_bytes(m, 'big')
        if key in best and freq[best[key][0]] >= freq[ch]: continue
        best[key] = (ch, s)
    items = sorted(best.items())
    out = ['/* gen.py が作る。美咲 8x8 の形（上の行が上位バイト、左端が bit7）→ 東雲 12x12（左端が bit11） */',
           f'#define NGLYPH {len(items)}', 'static const GLYPH glyph_tab[NGLYPH] = {']
    for key, (ch, s) in items:
        out.append('    {0x%016XULL, {%s}, 0x%04X},' % (key, ','.join('0x%03X' % r for r in s), ord(ch)))
    out.append('};')
    open(os.path.join(HERE, 'glyphs.h'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('glyphs:', len(items), ' 形が同じで省いた字:', len(chars) - len(items) - len(skipped),
          ' 字の形がない:', ''.join(skipped))


def gen_bat():
    bat = r'''@echo off
rem opengl32.dll（代わり）を組み立てる。gen.py が作る。
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
if not exist out mkdir out
cl /nologo /utf-8 /D_CRT_SECURE_NO_WARNINGS /O2 /LD /MT /W3 gl_proxy.c /link /OUT:out\opengl32.dll user32.lib gdi32.lib kernel32.lib || exit /b 1
del gl_proxy.obj gl_proxy.exp gl_proxy.lib out\opengl32.exp out\opengl32.lib 2>nul
'''
    open(os.path.join(HERE, 'build.bat'), 'w', encoding='cp932', newline='\r\n').write(bat)


if __name__ == '__main__':
    gen_exports(); gen_glyphs(); gen_bat()
