"""TALK.LZC の全員を U6 の構文で読み、読めない所をまとめる"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdfmt import entries
from u6conv import Script, build
from collections import Counter
d = open(sys.argv[1], 'rb').read()
t, es = entries(d)
ok = 0; errs = Counter(); same = 0; n = 0; seen = set()
for k, (o, f, r) in enumerate(es):
    if r is None or f != 0xe0 or k == 0 or o in seen: continue
    seen.add(o); n += 1
    try:
        s = Script(r)
    except Exception as e:
        errs[re.sub(r'0x[0-9a-f]+$', '', str(e))] += 1
        print(k, r[2:r.index(0xf1)], e)
    else:
        ok += 1
        if build(s) == r: same += 1
print('人数', n, '読めた', ok, '書き戻して一致', same)
for e, c in errs.most_common(20): print(c, e)
