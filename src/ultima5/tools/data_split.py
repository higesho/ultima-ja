# 本体（DATA.OVL）の訳す候補を、英語のまま残すものを除いて組に分ける（作業用）
# 使い方: python data_split.py <data_cand.tsv> <出力フォルダ> <組の数>
#   出力: data_XX.tsv（位置<TAB>元のバイト数<TAB>英文）と data_keep.tsv（英語のまま残すもの）
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
src, outdir, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
# 英語のまま残す範囲（DATA.OVL の位置）
KEEP = [(0x0709, 0x08C9, "呪文の名前（唱える言葉）"),
        (0x0941, 0x09A0, "呪文の音節（打つ言葉）"),
        (0x09AE, 0x0A4C, "符号"),
        (0x0498, 0x04AF, "符号"),
        (0x0B98, 0x0BFE, "徳の名前と真言（祠で打つ言葉）"),
        (0x1AEE, 0x1AEF, "符号"),
        (0x0285F, 0x02860, ""),
        (0x030F2, 0x030F3, "符号"),
        (0x03280, 0x03281, "符号")]
rows = [l.rstrip("\n").split("\t", 2) for l in open(src, encoding="utf-8") if l.strip()]
keep, todo = [], []
for r in rows:
    off = int(r[0], 16)
    why = next((w for a, b, w in KEEP if a <= off < b), None)
    (keep if why is not None else todo).append(r + ([why] if why is not None else []))
os.makedirs(outdir, exist_ok=True)
open(os.path.join(outdir, "data_keep.tsv"), "w", encoding="utf-8").write(
    "".join("\t".join(r) + "\n" for r in keep))
per = (len(todo) + n - 1) // n
for i in range(n):
    part = todo[i * per:(i + 1) * per]
    open(os.path.join(outdir, f"data_{i:02d}.tsv"), "w", encoding="utf-8").write(
        "".join("\t".join(r) + "\n" for r in part))
print("訳す", len(todo), "件 / 英語のまま", len(keep), "件 / 組", n)
