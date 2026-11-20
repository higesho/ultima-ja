# 配布物に原作のデータが入っていないかを確かめる
# 使い方: python check_dist.py <ゲームの元のフォルダ> <調べるファイル...>
#   ゲームの元のファイル（AK.EXE と AK.DAT は展開した中身も）のどこかと、N バイト以上一致する並びを探す
#   空白・0・同じバイトの繰り返しなどの、ありふれた並びは数えない
import glob
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wdx, alldat

sys.stdout.reconfigure(encoding="utf-8")
N = 8
game = sys.argv[1]
targets = sys.argv[2:]
SKIP_EXT = {".COM", ".TXT", ".PDF", ".INI", ".INFO", ".SCRIPT", ".HASHDB", ".ICO", ".LNK",
            ".CONF", ".MSG", ".EXE_", ".DAT_"}
orig = []
for f in glob.glob(os.path.join(game, "*")):
    if os.path.isdir(f):
        continue
    ext = os.path.splitext(f)[1].upper()
    base = os.path.basename(f).upper()
    if ext in SKIP_EXT or base.startswith("UNINS") or base.startswith("GOG") or base.startswith("AKJP") or base == "AJ.DAT":
        continue
    orig.append(open(f, "rb").read())
    if base == "AK.EXE":
        orig.append(wdx.unpack_exe(orig[-1]))
    if base == "AK.DAT":
        orig.append(alldat.read_dat(f))


def boring(g):
    if max(g.count(b) for b in set(g)) >= N - 2:      # 同じバイトがほとんど（点の並びなど）
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
        g = d[i:i + N]
        if g in grams:
            j = i + N
            while j < len(d) and d[i:j + 1] in b"".join([]) or (j < len(d) and d[j - N + 1:j + 1] in grams):
                j += 1
            hits.append((i, d[i:j]))
            i = j
        else:
            i += 1
    print(f"{os.path.basename(t)}: 原作と {N} バイト以上一致する所 {len(hits)}")
    for off, s in hits:
        print(f"   {off:06x} {len(s):4d} {s[:40]!r}")
    bad += len(hits)
print("合計", bad)
sys.exit(1 if bad else 0)
