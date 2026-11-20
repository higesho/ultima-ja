"""美咲 8x8 の形 → 東雲 12x12 の表 glyphs.h を作る（UW1・UW2 の訳に出てくる字＋かなと記号）。
形の作り方は Ultima 1/jp_work/gl/gen.py と同じ。python gen_glyphs.py"""
import os, sys, struct, collections

HERE = os.path.dirname(os.path.abspath(__file__))
U1GL = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'Ultima 1', 'jp_work', 'gl'))
sys.path.insert(0, U1GL)
import gen as u1gen  # noqa: E402  （load_bdf、load_shn、sjis_to_jis、MISAKI、SHN）

TEXTS = [os.path.join(HERE, '..', 'translation', 'uw1_ur_ja.tsv'),
         os.path.join(HERE, '..', 'translation', 'uw1_exe.tsv'),
         os.path.normpath(os.path.join(HERE, '..', '..', '..', 'Ultima Underworld 2', 'UnderworldRevisited',
                                       'Translation-ja', 'ja.strings.tsv'))]


def japanese(ch):
    o = ord(ch)
    return (0x3041 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0x3001 <= o <= 0x3002 or
            0x3005 <= o <= 0x3011 or o in (0x301C, 0x2026, 0x2025))


def main():
    mis = u1gen.load_bdf(u1gen.MISAKI)
    shn = u1gen.load_shn(u1gen.SHN)
    freq = collections.Counter()
    for p in TEXTS:
        if os.path.exists(p): freq.update(open(p, encoding='utf-8', errors='ignore').read())
        else: print('ない:', p)
    chars = set()
    for ch in list(freq):
        try: b = ch.encode('cp932')
        except UnicodeEncodeError: continue
        if len(b) == 2: chars.add(ch)
    for code in range(0x8140, 0x8397):
        try: ch = struct.pack('>H', code).decode('cp932')
        except UnicodeDecodeError: continue
        if len(ch) == 1: chars.add(ch)
    best, skipped = {}, []
    for ch in sorted(c for c in chars if japanese(c)):
        m = mis.get(ord(ch))
        s = shn.get(u1gen.sjis_to_jis(ch.encode('cp932')))
        if m is None or s is None or not any(m): skipped.append(ch); continue
        key = int.from_bytes(m, 'big')
        if key in best and freq[best[key][0]] >= freq[ch]: continue
        best[key] = (ch, s)
    items = sorted(best.items())
    out = ['/* gen_glyphs.py が作る。美咲 8x8 の形（上の行が上位バイト、左端が bit7）→ 東雲 12x12（左端が bit11） */',
           f'#define NGLYPH {len(items)}', 'static const GLYPH glyph_tab[NGLYPH] = {']
    for key, (ch, s) in items:
        out.append('    {0x%016XULL, {%s}, 0x%04X},' % (key, ','.join('0x%03X' % r for r in s), ord(ch)))
    out.append('};')
    open(os.path.join(HERE, 'glyphs.h'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('glyphs:', len(items), ' 字の形がない:', ''.join(skipped))


if __name__ == '__main__':
    main()
