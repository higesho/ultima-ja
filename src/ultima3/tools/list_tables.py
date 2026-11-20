# 番地の表の候補を一覧にする（tables.txt で採否を決めるため）
# 使い方: python list_tables.py <ゲームのフォルダ>
import sys
import u3data

sys.stdout.reconfigure(encoding="utf-8")
for tag in ("B", "E"):
    r = u3data.collect(sys.argv[1], tag)
    d, inside = r["data"], r["inside"]
    for start, vals in r["runs"]:
        heads = sum(1 for v in vals if inside[v][0] == v)
        txt = " / ".join(u3data.show(d[v - 0x100:inside[v][1] - 0x100])[:14] for v in vals[:6])
        print(f"{tag} {start:04x} n={len(vals)} heads={heads}  {txt}")
