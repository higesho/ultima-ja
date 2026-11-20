# 固有名の書き方の揺れを洗い出す（作業用）
# 使い方: python names_check.py   （jp_work から）
#   英文の大文字で始まる語（4字以上）ごとに、同じ行の訳に出るカタカナの語を数え、
#   いちばん多い書き方と似ているのに違う書き方（1〜2字違い）を出す
import collections
import difflib
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(HERE, "..", "translation")


def read(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or "\t" not in line:
            continue
        k, v = line.rstrip("\n").split("\t", 1)
        d[k] = v
    return d


pairs = []
for f in sorted(glob.glob(os.path.join(T, "conv_en", "*.tsv"))):
    en = read(f)
    ja = read(f.replace("conv_en", "conv_ja"))
    for k, e in en.items():
        if k in ja and ":k" not in k:
            pairs.append((k, e, ja[k]))
for name in ("book", "look", "game", "gam2", "u", "end"):
    en = read(os.path.join(T, "other_en", name + ".tsv"))
    ja = read(os.path.join(T, "other_ja", name + ".tsv"))
    for k, e in en.items():
        if k in ja:
            pairs.append((k, e, ja[k]))

KATA = re.compile(r"[ァ-ヶー・]{2,}")
words = collections.defaultdict(collections.Counter)
where = collections.defaultdict(list)
for k, e, j in pairs:
    toks = set(KATA.findall(j.replace("@", "")))
    for w in set(re.findall(r"\b[A-Z][a-z]{3,}\b", e)):
        for t in toks:
            words[w][t] += 1
            where[(w, t)].append(k)
for w, c in sorted(words.items()):
    if sum(c.values()) < 2:
        continue
    top, n = c.most_common(1)[0]
    if n < 2:
        continue
    for t, m in c.items():
        if t == top or m > n:
            continue
        r = difflib.SequenceMatcher(None, top.replace("・", ""), t.replace("・", "")).ratio()
        if 0.6 <= r < 1 and abs(len(t) - len(top)) <= 2:
            print(f"{w}: {top}（{n}） ← {t}（{m}）  {' '.join(where[(w, t)][:6])}")
