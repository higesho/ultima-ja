# 配布物に原作のデータが入っていないかを確かめる（U5 の check_dist.py に LZW の項目の展開を足した）
# 使い方: python check_dist.py <ゲームの元のフォルダ（MARTIAN）> <調べるファイル...>
#   ゲームの元のファイル（*.LZC は項目を展開したものも）のどこかと、N バイト以上一致する並びを探す
#   0・空白・同じバイトの繰り返しなどの、ありふれた並びは数えない
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mdfmt  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
N = 8
game = sys.argv[1]
targets = sys.argv[2:]
orig = []
for f in glob.glob(os.path.join(game, "*")):
    if os.path.isdir(f):
        continue
    base = os.path.basename(f).upper()
    if base.startswith("MDJP") or base.endswith(".LZJ"):
        continue
    d = open(f, "rb").read()
    orig.append(d)
    if base.endswith(".LZC"):
        try:
            orig += [mdfmt.item(*e) or b"" for e in mdfmt.entries(d)[1]]
        except Exception:  # noqa: BLE001
            pass


def boring(g):
    if max(g.count(b) for b in set(g)) >= N - 2:
        return True
    return len(set(g)) <= 2 or g.count(0) >= N // 2 or g.count(0x20) >= N - 2 or g.count(0xFF) >= N // 2


grams = set()
for d in orig:
    for i in range(len(d) - N + 1):
        g = d[i:i + N]
        if not boring(g):
            grams.add(g)
bad = 0
for t in targets:
    d = open(t, "rb").read()
    hits = []
    i = 0
    while i < len(d) - N + 1:
        if d[i:i + N] in grams:
            j = i + N
            while j < len(d) and d[j - N + 1:j + 1] in grams:
                j += 1
            hits.append((i, d[i:j]))
            i = j
        else:
            i += 1
    print(f"{os.path.basename(t)}: 原作と {N} バイト以上一致する所 {len(hits)}（{sum(len(s) for _, s in hits)} バイト）")
    for off, s in (hits if os.environ.get("ALL") else hits[:20]):
        print(f"   {off:06x} {len(s):4d} {s[:40]!r}")
    bad += len(hits)
print("合計", bad)
sys.exit(1 if bad else 0)
