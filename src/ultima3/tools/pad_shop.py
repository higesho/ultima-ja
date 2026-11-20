# 店の品物一覧の行を、価格が 15 マス目で終わるようにそろえる
import re
import sys

W = 15
KEYS = ("E.9d0e", "E.9d7a", "E.9d8c", "E.9dec", "E.9e60", "E.9eb0", "E.a3b3")
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().split("\n")
for i, l in enumerate(lines):
    key, _, t = l.partition("\t")
    if key not in KEYS:
        continue
    parts = t.split("\\n")
    for j, s in enumerate(parts):
        m = re.match(r"^(\s*[A-Z]?:?\s*\S+?)\s*(\d+gp)$", s)
        if m:
            name, price = m.group(1), m.group(2)
            parts[j] = name + " " * max(1, W - len(name) - len(price)) + price
    lines[i] = key + "\t" + "\\n".join(parts)
    print(ascii(lines[i]))
open(p, "w", encoding="utf-8").write("\n".join(lines))
