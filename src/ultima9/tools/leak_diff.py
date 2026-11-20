# -*- coding: utf-8 -*-
"""u9probe の集計2つ（または3つ以上）を比べて、生きている確保が増えた呼び出し元を並べる。
使い方: python leak_diff.py <前.txt> <後.txt> [さらに後.txt ...] [--top N]
3つ以上渡すと、毎回増えている（単調増加の）呼び出し元に印を付ける。
"""
import sys


def load(path):
    d = {}
    for line in open(path):
        if line.startswith('#'):
            continue
        f = line.split()
        key = (int(f[1]), f[5], f[6], f[7])          # 種類と3段の呼び出し元
        d[key] = (int(f[2]), int(f[3]), int(f[4]))   # 件数, バイト, 累計
    return d


args = [a for a in sys.argv[1:] if not a.startswith('--')]
top = int(sys.argv[sys.argv.index('--top') + 1]) if '--top' in sys.argv else 25
if '--top' in sys.argv:
    args.remove(str(top))
snaps = [load(p) for p in args]
first, last = snaps[0], snaps[-1]
rows = []
for k in set(first) | set(last):
    c0, b0, t0 = first.get(k, (0, 0, 0))
    c1, b1, t1 = last.get(k, (0, 0, 0))
    mono = all(snaps[i].get(k, (0, 0, 0))[0] <= snaps[i + 1].get(k, (0, 0, 0))[0] for i in range(len(snaps) - 1))
    rows.append((b1 - b0, c1 - c0, t1 - t0, c1, b1, mono, k))
rows.sort(reverse=True)
print('バイト増  件数増  確保回数  残り件数  残りバイト  単調  種類 呼び出し元')
for db, dc, dt, c1, b1, mono, k in rows[:top]:
    print('%9d %7d %9d %8d %11d   %s   %s  %s %s %s' % (db, dc, dt, c1, b1, '○' if mono and dc > 0 else ' ',
                                                    'VA' if k[0] else 'ヒープ', k[1], k[2], k[3]))
print('合計: バイト %+d, 件数 %+d' % (sum(r[0] for r in rows), sum(r[1] for r in rows)))
