# 配布物に原作のデータが入っていないかを確かめる
# 使い方: python check_dist.py <ゲームの元のフォルダ> <調べるファイル...>
#   ゲームの元のファイルのどこかと、N バイト以上一致する並びを探す。圧縮されているもの（会話の各項目、LZW の .LZD など、
#   EXEPACK の GAME.EXE）は展開した中身とも比べる。LOOK.JZD は 9 ビットの符号に詰めてあるので、ほどいた中身も調べる
#   空白・0・同じバイトの繰り返しなどの、ありふれた並びは数えない
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from u6fmt import lib, lzw  # noqa: E402
from unexepack import unpack  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
N = 8
game = sys.argv[1]
targets = sys.argv[2:]
SKIP_EXT = {".COM", ".TXT", ".PDF", ".INI", ".INFO", ".SCRIPT", ".HASHDB", ".ICO", ".LNK", ".CONF", ".MSG",
            ".JA", ".JB", ".JZD", ".JDT"}
orig = []
for f in glob.glob(os.path.join(game, "*")):
    if os.path.isdir(f):
        continue
    ext = os.path.splitext(f)[1].upper()
    base = os.path.basename(f).upper()
    if ext in SKIP_EXT or base.startswith("UNINS") or base.startswith("GOG") or base.startswith("U6JP"):
        continue
    d = open(f, "rb").read()
    orig.append(bytes(d))
    if base in ("CONVERSE.A", "CONVERSE.B"):
        for it in lib(d, 4):
            if it and struct.unpack_from("<I", it)[0]:
                orig.append(bytes(lzw(it)[0]))
    elif ext in (".LZD",) or base in ("LZMAP",):
        try:
            orig.append(bytes(lzw(d)[0]))
        except Exception:
            pass
    elif base == "GAME.EXE":
        orig.append(bytes(unpack(f)[0]))


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


def scan(name, d):
    hits = []
    i = 0
    while i < len(d) - N + 1:
        if d[i:i + N] in grams:
            j = i + 1
            while j < len(d) - N + 1 and d[j:j + N] in grams:
                j += 1
            hits.append((i, d[i:j + N - 1]))
            i = j + N - 1
        else:
            i += 1
    print(f"{name}: 原作と {N} バイト以上一致する所 {len(hits)}")
    for off, s in hits[:40]:
        print(f"   {off:06x} {len(s):4d} {s[:48]!r}")
    return len(hits)


bad = 0
for t in targets:
    d = open(t, "rb").read()
    bad += scan(os.path.basename(t), d)
    if t.upper().endswith(".JZD"):
        bad += scan(os.path.basename(t) + "（展開）", lzw(d)[0])
print("合計", bad)
sys.exit(1 if bad else 0)
