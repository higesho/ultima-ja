# Copy translations between tables: rows whose English text is identical get the same Japanese,
# unless the target row already has a translation.
# usage: python share_ja.py <target.tsv> <source.tsv>...
import sys

def read(path):
    return open(path, encoding='utf-8').read().split('\n')

target, sources = sys.argv[1], sys.argv[2:]
known = {}
for s in sources:
    for line in read(s):
        r = line.split('\t')
        if line.startswith('#') or len(r) < 5 or not r[4]: continue
        known.setdefault(r[3], r[4])
out = []; n = 0
for line in read(target):
    r = line.split('\t')
    if not line.startswith('#') and len(r) >= 5 and r[1] != '-' and not r[4] and r[3] in known:
        r[4] = known[r[3]]; line = '\t'.join(r); n += 1
    out.append(line)
open(target, 'w', encoding='utf-8', newline='').write('\n'.join(out))
print(f'{n} 件を共有')
