# 訳す対象の英文を全部、キーと長さつきで一覧にする
# 使い方: python list_en.py <ULTIMAII.EXE> <出力.tsv>
import importlib.util
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("b", os.path.join(here, "build_u2jp.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

exe, out = sys.argv[1], sys.argv[2]
game = os.path.dirname(os.path.abspath(exe))
d = open(exe, "rb").read()
img = d[512:]


def show(bs):
    return bytes(x & 0x7F for x in bs).decode("latin-1").replace("\r", "\\n").replace("\n", "\\n")


rows = []
for off, n in sorted(b.inline_strings(img).items()):
    rows.append((f"{off:05x}", n, "文字列", show(img[off:off + n])))
for (a, e), name in zip(b.TABLES, ["表", "うわさ", "手がかり"]):
    for p, n in b.table_strings(img, a, e):
        if n:
            rows.append((f"{p:05x}", n, name, show(img[p:p + n])))
for fn in sorted(os.listdir(game)):
    if fn.startswith("TLK"):
        data = open(os.path.join(game, fn), "rb").read()
        for p, t in b.tlk_entries(data):
            rows.append((f"{fn}.{p:04x}", len(t), "会話", show(t)))
with open(out, "w", encoding="utf-8") as f:
    for r in rows:
        f.write("\t".join(map(str, r)) + "\n")
print(len(rows), "件")
