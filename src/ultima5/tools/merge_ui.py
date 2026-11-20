# エンジンの表示の訳（translation/engine/out/*.tsv と extra.tsv）を確かめて、engine の i18n/ja/ui.json にまとめる
# 使い方: python merge_ui.py
#   確かめること: 英語が抜き出した表（ui_en.tsv）か extra.tsv にあること、{0} などの印が同じであること、
#   改行の数が同じであること、先頭と末尾の空白が同じであること
#   問題は translation/engine/merge_check.txt に書く（その行は ui.json に入れない）
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TE = os.path.join(HERE, "..", "translation", "engine")
OUT = os.path.join(HERE, "..", "engine", "web", "src", "i18n", "ja", "ui.json")
sys.stdout.reconfigure(encoding="utf-8")


def unesc(t):
    return t.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")


known = set()
for line in open(os.path.join(TE, "ui_en.tsv"), encoding="utf-8"):
    if line.strip():
        known.add(line.rstrip("\r\n").split("\t")[0])

ui, problems, keep, n = {}, [], 0, 0
files = sorted(glob.glob(os.path.join(TE, "out", "*.tsv"))) + [os.path.join(TE, "extra.tsv")]
for path in files:
    if not os.path.exists(path):
        continue
    extra = path.endswith("extra.tsv")
    for no, line in enumerate(open(path, encoding="utf-8-sig"), 1):
        line = line.rstrip("\r\n")
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            problems.append(f"{os.path.basename(path)}:{no}: タブがない: {line[:60]}")
            continue
        en, ja = line.split("\t", 1)
        ja = ja.split("\t")[0]
        n += 1
        if not extra and en not in known:
            problems.append(f"{os.path.basename(path)}:{no}: 抜き出した表にない英語: {en[:60]}")
            continue
        if ja == "KEEP":
            ui[unesc(en)] = "KEEP"
            keep += 1
            continue
        e, j = unesc(en), unesc(ja)
        if sorted(re.findall(r"\{\d+\}", e)) != sorted(re.findall(r"\{\d+\}", j)) and set(re.findall(r"\{\d+\}", e)) != set(re.findall(r"\{\d+\}", j)):
            problems.append(f"{os.path.basename(path)}:{no}: 印が違う: {en[:50]} → {ja[:50]}")
            continue
        if e.count("\n") != j.count("\n"):
            problems.append(f"{os.path.basename(path)}:{no}: 改行の数が違う: {en[:50]}")
        lead_e, lead_j = re.match(r"\s*", e).group(), re.match(r"\s*", j).group()
        if lead_e != lead_j:
            j = lead_e + j.lstrip()
        tail_e = re.search(r"\s*$", e).group()
        if not j.endswith(tail_e) or re.search(r"\s*$", j).group() != tail_e:
            j = j.rstrip() + tail_e
        ui[e] = j

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(ui, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
open(os.path.join(TE, "merge_check.txt"), "w", encoding="utf-8").write("\n".join(problems) + "\n")
print(f"行 {n}、辞書 {len(ui)}（KEEP {keep}）、問題 {len(problems)} → {OUT}")
for p in problems[:20]:
    print("  ", p)
