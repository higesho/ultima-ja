# 会話の見直し用の入力を作る（作業用）
# 使い方: python review_prepare.py   （jp_work から）
#   出力: translation/work/review/tlk_XX.tsv（tlk_extract の組と同じ分け方）
#     人ごとの見出し「# 人 n: 名前 / 打つ言葉: ...」の次に「# 添え字がない: ...」（あれば）
#     欄の行: ファイル<TAB>人<TAB>欄<TAB>英文<TAB>いまの訳（text の欄だけ）
import collections
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "..", "translation", "work")
R = os.path.join(W, "review")
ja = {}
for line in open(os.path.join(HERE, "..", "translation", "tlk_ja.txt"), encoding="utf-8"):
    p = line.rstrip("\r\n").split("\t")
    if len(p) == 4:
        ja[(p[0], p[1], p[2])] = p[3]
missing = collections.defaultdict(list)
for line in open(os.path.join(R, "hint.txt"), encoding="utf-8"):
    p = line.rstrip("\r\n").split("\t")
    if len(p) >= 3:
        missing[(p[0], p[1])].append(p[2])
for f in sorted(glob.glob(os.path.join(W, "tlk", "tlk_*.tsv"))):
    out = []
    for line in open(f, encoding="utf-8"):
        line = line.rstrip("\r\n")
        if line.startswith("# 人"):
            out.append(line)
            continue
        p = line.split("\t")
        if len(p) != 5:
            continue
        if p[2] == "0":
            m = missing.get((p[0], p[1]))
            if m:
                out.append("# 添え字がない: " + " ".join(m))
        if p[3] == "text":
            out.append("\t".join([p[0], p[1], p[2], p[4], ja.get((p[0], p[1], p[2]), "")]))
    open(os.path.join(R, os.path.basename(f)), "w", encoding="utf-8").write("\n".join(out) + "\n")
print("書き出し:", R)
