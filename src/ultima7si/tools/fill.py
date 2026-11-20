# 「位置<TAB>訳」だけの下書きを、translation/usecode/XXXX.tsv の訳の列に入れる
#   使い方: python fill.py XXXX 下書きファイル
#   原文の @ ~ * の数が訳と合わないときは知らせる（入れはする）。
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from si_uc import unesc
fid, src = sys.argv[1].lower(), sys.argv[2]
path = os.path.join(here, '..', 'translation', 'usecode', f'{fid}.tsv')
ja = {}
for line in open(src, encoding='utf-8-sig'):
    line = line.rstrip('\r\n')
    if not line or line.startswith('#'):
        continue
    off, t = line.split('\t', 1)
    ja[int(off)] = t
out = []; used = set(); warn = []
for line in open(path, encoding='utf-8').read().split('\n'):
    if not line or line.startswith('#'):
        out.append(line); continue
    cols = line.split('\t')
    off = int(cols[0])
    if off in ja:
        en, t = unesc(cols[1]), unesc(ja[off])
        for ch in '@*':
            if en.count(ch) != t.count(ch):
                warn.append(f'{off}: 「{ch}」の数が違う（原文 {en.count(ch)}、訳 {t.count(ch)}）')
        if en.count('~') and not t.count('~'):
            warn.append(f'{off}: 原文にある ~ が訳にない')
        cols = cols[:2] + [ja[off]]; used.add(off)
    out.append('\t'.join(cols))
open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
miss = set(ja) - used
print(f'{fid}: {len(used)} 件を入れました' + (f'、位置が合わない: {sorted(miss)}' if miss else ''))
for w in warn:
    print('  注意', w)
