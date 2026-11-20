# 本体（DATA.OVL）の文字列で、訳す候補（data_cand.tsv）から漏れたものを探す（作業用）
# 使い方: python data_missing.py   （jp_work から）
#   プログラム（ULTIMA.EXE と *.OVL）の中の即値（mov 系の 16 ビット）と、DATA.OVL の中のワードの表を、
#   DS の位置として見て、そこから始まる英文が候補にない／候補の途中から始まるものを出す
#   出力: translation/work/data_missing.tsv（位置<TAB>元のバイト数<TAB>英文<TAB>理由）
import glob
import os
import re
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, "..", "game_test")
W = os.path.join(HERE, "..", "translation", "work")
D = open(os.path.join(G, "DATA.OVL"), "rb").read()
cand = {}
for line in open(os.path.join(W, "data_cand.tsv"), encoding="utf-8"):
    o, n, t = line.rstrip("\r\n").split("\t", 2)
    cand[int(o, 16)] = int(n)
inside = {}
for o, n in cand.items():
    for k in range(o + 1, o + n):
        inside[k] = o

refs = set()
for f in [os.path.join(G, "ULTIMA.EXE")] + glob.glob(os.path.join(G, "*.OVL")):
    d = open(f, "rb").read()
    if f.endswith("DATA.OVL"):
        for i in range(0, len(d) - 1, 1):
            refs.add(struct.unpack_from("<H", d, i)[0] + 0x10)
        continue
    for m in re.finditer(rb"[\xb8-\xbf\x68](..)", d, re.S):          # mov reg,imm16 / push imm16
        refs.add(struct.unpack_from("<H", m.group(1))[0] + 0x10)
    for m in re.finditer(rb"\xc7\x06..(..)|\xc7\x46.(..)", d, re.S):   # mov word [mem],imm16
        v = m.group(1) or m.group(2)
        refs.add(struct.unpack_from("<H", v)[0] + 0x10)

out = []
for r in sorted(refs):
    if r >= len(D) or r in cand or r >= 0xA400 or 0x104C <= r < 0x12BC:
        continue
    m = re.match(rb"[\x0a\x20-\x7e]{4,}(?=\x00)", D[r:])
    if not m:
        continue
    t = m.group().decode("latin1")
    if not re.search(r"[A-Za-z]{3}", t) or re.search(r"\.(DAT|OVL|NPC|TLK|OOL|GAM|16|4)$", t, re.I):
        continue
    words = re.findall(r"[A-Za-z]{3,}", t)
    if len(words) < 1:
        continue
    why = "途中から" if r in inside else "候補にない"
    if why == "途中から":
        # 候補の途中を指す（後ろの部分だけ別に使われる）。候補の訳で後ろが消えると、ここが壊れる
        pass
    out.append(f"{r - 0x10 + 0x10:05x}\t{len(m.group())}\t{t.replace(chr(10), chr(92) + 'n')}\t{why}"
               + (f"（候補 {inside[r]:05x}）" if r in inside else ""))
open(os.path.join(W, "data_missing.tsv"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print(len(out), "件 →", os.path.join(W, "data_missing.tsv"))
