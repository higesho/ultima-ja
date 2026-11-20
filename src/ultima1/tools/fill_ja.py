# Merge translations into translation/<EXE>.tsv
# usage: python fill_ja.py <table.tsv> <ja_lines.txt>
#   ja_lines.txt: "off<TAB>japanese" per line (UTF-8), '#' comments; escapes as in the table
import sys
tsv, src = sys.argv[1:3]
ja = {}
for line in open(src, encoding='utf-8'):
    line = line.rstrip('\r\n')
    if not line or line.startswith('#'): continue
    off, t = line.split('\t', 1)
    ja[off.strip().lower().zfill(4)] = t
out = []; hit = set()
for line in open(tsv, encoding='utf-8'):
    line = line.rstrip('\r\n')
    if line and not line.startswith('#'):
        r = line.split('\t')
        if r[0] in ja:
            while len(r) < 5: r.append('')
            r[4] = ja[r[0]]; hit.add(r[0]); line = '\t'.join(r)
    out.append(line)
open(tsv, 'w', encoding='utf-8', newline='').write('\n'.join(out) + '\n')
miss = set(ja) - hit
print(f'{len(hit)} 件反映', ('/ 見つからない off: ' + ' '.join(sorted(miss))) if miss else '')
