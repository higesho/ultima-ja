# Create / refresh translation tables: translation/<EXE>.tsv
# columns: off  kind  cap  en  ja
#   kind: M = movable (any length), F = fixed (ja must fit in cap bytes), - = do not translate
#   text escapes: \n = LF, \r = CR, \t = TAB, \\ = backslash
# Existing ja values are kept when the table is regenerated.
import sys, os, csv
sys.path.insert(0, os.path.dirname(__file__))
from strdb import build_db

def esc(s): return s.replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t')

NOTRANS_EXT = ('.bin', '.u1', '.exe', '.com')

def main(game_dir, out_dir, names):
    os.makedirs(out_dir, exist_ok=True)
    skip = set()
    sp = os.path.join(out_dir, 'skip.txt')
    if os.path.exists(sp):
        for line in open(sp, encoding='utf-8'):
            r = line.strip().split('	')
            if len(r) == 2 and not line.startswith('#'): skip.add((r[0] + '.EXE', r[1].lower()))
    for fn in names:
        e, db = build_db(os.path.join(game_dir, fn), fn)
        path = os.path.join(out_dir, fn.replace('.EXE', '') + '.tsv')
        old = {}
        if os.path.exists(path):
            for r in csv.reader(open(path, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
                if r and not r[0].startswith('#') and len(r) >= 5: old[r[0]] = r[4]
        rows = []
        for s in db:
            t = s['text'].decode('latin1')
            letters = sum(c.isalpha() for c in t)
            if letters < 2: continue
            low = t.lower()
            if low.endswith(NOTRANS_EXT) or '$' in t or low in ('tandy', 'rb', 'wb', 'out', 'com', 'exe'):
                kind = '-'
            else:
                kind = 'M' if s['movable'] else 'F'
            off = f"{s['off']:04x}"
            if (fn, off) in skip: kind = '-'
            rows.append([off, kind, str(s['cap']), esc(t), old.get(off, '')])
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('# off\tkind\tcap\ten\tja   (kind: M=長さ自由 F=cap以内 -=訳さない / \\n=改行)\n')
            for r in rows: f.write('\t'.join(r) + '\n')
        print(path, len(rows), 'rows')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
