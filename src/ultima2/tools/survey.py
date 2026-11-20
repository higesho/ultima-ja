# ULTIMAII.EXE と TLK ファイルの文章を集めて数える（調査用）
# 使い方: python survey.py <ゲームのフォルダ> <出力フォルダ>
import csv
import glob
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")
game, out = sys.argv[1], sys.argv[2]
d = open(os.path.join(game, "ULTIMAII.EXE"), "rb").read()
hdr = struct.unpack_from("<H", d, 8)[0] * 16
img = d[hdr:]

PUTS, PUTC, GOTO = 0x4FDF, 0x5003, 0x51EB


def calls_to(target):
    """call near（E8）で target を呼んでいる位置の一覧"""
    res = []
    for i in range(len(img) - 3):
        if img[i] == 0xE8:
            rel = struct.unpack_from("<h", img, i + 1)[0]
            if (i + 3 + rel) & 0xFFFF == target:
                res.append(i)
    return res


rows = []
# 1) call PUTS の直後に埋め込まれた文字列
for at in calls_to(PUTS):
    s = at + 3
    e = img.index(b"\0", s)
    rows.append(("EXE-inline", s, e - s, img[s:e]))

# 2) 0x4c60 の表（0 区切りの文字列の並び）
tab = 0x4C60
p = tab
for k in range(400):
    e = img.index(b"\0", p)
    if e == p and k > 0:
        break
    rows.append(("EXE-table4c60", p, e - p, img[p:e]))
    p = e + 1
    if any(b < 0x20 or b > 0x7E for b in img[p:p + 1]) and img[p:p + 1] != b"\0":
        break

# 3) TLK ファイル（最上位ビット付き、0x8D=改行、0 区切り）
for fn in sorted(glob.glob(os.path.join(game, "TLK*"))):
    t = open(fn, "rb").read()
    p = 0
    while p < len(t):
        e = t.find(b"\0", p)
        if e < 0:
            e = len(t)
        if e > p:
            rows.append((os.path.basename(fn), p, e - p, bytes(b & 0x7F for b in t[p:e])))
        p = e + 1

os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "strings_en.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["src", "off", "len", "text"])
    for src, off, n, b in rows:
        w.writerow([src, f"{off:05x}", n, b.decode("latin-1").replace("\r", "\\n")])

from collections import Counter
c = Counter()
nb = Counter()
for src, off, n, b in rows:
    k = "TLK" if src.startswith("TLK") else src
    c[k] += 1
    nb[k] += n
for k in c:
    print(f"{k}: {c[k]} 件, {nb[k]} バイト")
print("PUTC の呼び出し元:", [hex(x) for x in calls_to(PUTC)])
print("GOTO の呼び出し数:", len(calls_to(GOTO)))
