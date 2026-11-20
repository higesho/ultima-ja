# 町の地図で、歩ける所（床・草原・やぶ）だけを通る道順を矢印キーで出す（試験用）
# 使い方: python path.py <町のファイル> <開始 x,y> <目的 x,y>
import sys
from collections import deque

d = open(sys.argv[1], "rb").read()
sx, sy = map(int, sys.argv[2].split(","))
gx, gy = map(int, sys.argv[3].split(","))
OK = {0x04, 0x08, 0x0C, 0x20}          # 草原・やぶ・森・床
prev = {(sx, sy): None}
q = deque([(sx, sy)])
while q:
    x, y = q.popleft()
    if (x, y) == (gx, gy):
        break
    for dx, dy, k in ((1, 0, "»"), (-1, 0, "«"), (0, 1, "↓"), (0, -1, "↑")):
        n = (x + dx, y + dy)
        if 0 <= n[0] < 64 and 0 <= n[1] < 64 and n not in prev and d[n[1] * 64 + n[0]] in OK:
            prev[n] = ((x, y), k)
            q.append(n)
keys = []
p = (gx, gy)
while prev.get(p):
    p, k = prev[p]
    keys.append(k)
print("".join(reversed(keys)))
