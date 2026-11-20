# Apply translation/<EXE>.tsv to copies of the game, and build the matching JPFONT.COM.
#  - Japanese text is encoded with jpenc (1 byte = 1 cell)
#  - a translation that fits in its original slot is written in place
#  - a longer one (movable strings only) is moved into free space and every pointer to it is updated
#    free space = unused tail of translated movable strings + whole slots of moved strings
# usage: python apply_translation.py <game_dir> <translation_dir> <out_dir> [font.bdf]
import sys, os, re, struct, shutil, glob
sys.path.insert(0, os.path.dirname(__file__))
from strdb import build_db
from jpenc import Encoder, build_tsr, load_bdf

EXES = ('ULTIMA.EXE', 'GEN.EXE', 'OUT.EXE', 'SPACE.EXE', 'MONDAIN.EXE')
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BDF = os.path.join(HERE, '..', 'font', 'dl', 'misaki_gothic_2nd.bdf')

def unesc(s):
    out = []; i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]; out.append({'n': '\n', 'r': '\r', 't': '\t', '\\': '\\'}.get(n, '\\' + n)); i += 2
        else:
            out.append(c); i += 1
    return ''.join(out)

def layout(ja):
    """{cN}text = center in N cells (spaces both sides), {CN} = center (leading spaces only),
    {wN}text = pad with trailing spaces to N cells, {rN}text = right-align in N cells"""
    m = re.match(r'\{([cCwr])(\d+)\}', ja)
    if not m: return ja
    k, n = m.group(1), int(m.group(2)); t = ja[m.end():]
    gap = max(0, n - len(t))
    if k == 'c': return ' ' * (gap // 2) + t + ' ' * (gap - gap // 2)
    if k == 'C': return ' ' * (gap // 2) + t
    if k == 'w': return t + ' ' * gap
    return ' ' * gap + t

def load_tsv(path):
    rows = {}
    for ln, line in enumerate(open(path, encoding='utf-8'), 1):
        line = line.rstrip('\r\n')
        if not line or line.startswith('#'): continue
        r = line.split('\t')
        if len(r) < 5 or r[4] == '' or r[1] == '-': continue
        en, ja = unesc(r[3]), layout(unesc(r[4]))
        # keep the original's trailing spaces (text is often joined after it); editors tend to strip them
        tail = len(en) - len(en.rstrip(' '))
        if tail and ja and not ja.endswith(' '): ja += ' ' * tail
        rows[int(r[0], 16)] = (ln, r[1], en, ja)
    return rows

def apply(e, db, tr, enc, out_dir, fn, report):
    raw = e.raw
    byoff = {s['off']: s for s in db}
    errors = 0; free = []; moves = []
    for off, (ln, kind, en, ja) in sorted(tr.items()):
        s = byoff.get(off)
        if s is None or s['text'].decode('latin1') != en:
            print(f'  {fn} {ln}行目: 原文が一致しません ({off:04x})'); errors += 1; continue
        b = enc.encode(ja)
        cap = s['cap']; p = e.dbase + off
        if len(b) <= cap:
            raw[p:p + cap] = b + b'\0' * (cap - len(b))
            if s['movable'] and cap > len(b): free.append((off + len(b) + 1, off + cap + 1))
        elif s['movable']:
            raw[p:p + cap] = b'\0' * cap
            free.append((off, off + cap + 1)); moves.append((s, b, ja))
        else:
            print(f'  {fn} {ln}行目: {len(b)}バイトで長すぎます（固定文字列は{cap}バイトまで）: {ja}'); errors += 1
    free.sort(); merged = []
    for a, b2 in free:
        if merged and a <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], b2)
        else: merged.append([a, b2])
    total_free = sum(b2 - a for a, b2 in merged)
    for s, b, ja in sorted(moves, key=lambda m: -len(m[1])):
        size = len(b) + 1
        fit = [r for r in merged if r[1] - r[0] >= size]
        if not fit:
            print(f'  {fn}: 空き領域が足りません: {ja!r} ({size}バイト)'); errors += 1; continue
        r = min(fit, key=lambda r: r[1] - r[0])
        new = r[0]; r[0] += size
        raw[e.dbase + new:e.dbase + new + size] = b + b'\0'
        for fo in s['refs']:
            assert struct.unpack_from('<H', raw, fo)[0] == s['off']
            struct.pack_into('<H', raw, fo, new)
    left = sum(b2 - a for a, b2 in merged)
    open(os.path.join(out_dir, fn), 'wb').write(raw)
    report.append(f'{fn}: 訳 {len(tr)}件, 移動 {len(moves)}件, 空き {total_free}バイト中 残り {left}バイト, エラー {errors}')
    return errors

def main(game_dir, tdir, out_dir, bdf=DEFAULT_BDF):
    os.makedirs(out_dir, exist_ok=True)
    for pat in ('*.EXE', '*.BIN', 'CASTLE.*'):
        for f in glob.glob(os.path.join(game_dir, pat)):
            if os.path.basename(f).lower() != 'unins000.exe': shutil.copy2(f, out_dir)
    work = []
    for fn in EXES:
        tsv = os.path.join(tdir, fn.replace('.EXE', '') + '.tsv')
        if not os.path.exists(tsv): continue
        e, db = build_db(os.path.join(game_dir, fn), fn)
        work.append((fn, e, db, load_tsv(tsv)))
    enc = Encoder([ja for *_, tr in work for (_, _, _, ja) in tr.values()])
    report = []; err = 0
    for fn, e, db, tr in work:
        err += apply(e, db, tr, enc, out_dir, fn, report)
    info = build_tsr(enc, load_bdf(bdf), os.path.join(out_dir, 'JPFONT.COM'))
    print('\n'.join(report))
    print(f"JPFONT.COM: {info['size']}バイト（常駐 {info['resident']}）, 1バイト文字 {len(enc.single)}, "
          f"2文字組 {info['pairs']}, 字形 {info['glyphs']}")
    if info['missing']: print('  フォントにない文字:', info['missing']); err += 1
    return err

if __name__ == '__main__':
    sys.exit(1 if main(*sys.argv[1:]) else 0)
