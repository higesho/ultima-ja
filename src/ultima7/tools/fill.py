# 「位置<TAB>訳」だけのファイルの訳を、translation/usecode/XXXX.tsv の訳の列に入れる
#   使い方: python fill.py XXXX 訳だけのファイル
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
here = os.path.dirname(os.path.abspath(__file__))
fid, src = sys.argv[1], sys.argv[2]
path = os.path.join(here, '..', 'translation', 'usecode', f'{fid}.tsv')
ja = {}
for line in open(src, encoding='utf-8-sig'):
    line = line.rstrip('\r\n')
    if not line or line.startswith('#'):
        continue
    off, t = line.split('\t', 1)
    ja[int(off)] = t
out = []; used = set()
for line in open(path, encoding='utf-8').read().split('\n'):
    if not line or line.startswith('#'):
        out.append(line); continue
    cols = line.split('\t')
    off = int(cols[0])
    if off in ja:
        cols = cols[:2] + [ja[off]]; used.add(off)
    out.append('\t'.join(cols))
open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
miss = set(ja) - used
print(f'{fid}: {len(used)} 件を入れました' + (f'、位置が合わない: {sorted(miss)}' if miss else ''))
