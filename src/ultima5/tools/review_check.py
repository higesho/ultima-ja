# 訳の見直し用の検査（作業用）
# 使い方: python review_check.py   （jp_work から）
#   出力: translation/work/review/
#     8e.txt       {8e}…{8e}（打つ言葉の強調）の中身が英語のまま残っていない欄
#     hint.txt     人ごとの打つ言葉で、英文に出ているのに訳に「(XXXX)」の添え字がないもの
#     names.txt    英語の固有名ごとに、訳で使われたカタカナの候補（表記ゆれの洗い出し）
import collections
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "..", "translation", "work")
OUT = os.path.join(W, "review")
os.makedirs(OUT, exist_ok=True)

en, heads = {}, {}
for f in glob.glob(os.path.join(W, "tlk", "tlk_*.tsv")):
    for line in open(f, encoding="utf-8"):
        line = line.rstrip("\r\n")
        if line.startswith("# 人"):
            cur = line
            continue
        p = line.split("\t")
        if len(p) == 5:
            if p[3] == "text":
                en[(p[0], int(p[1]), int(p[2]))] = p[4]
            heads[(p[0], int(p[1]))] = cur
ja = {}
for line in open(os.path.join(HERE, "..", "translation", "tlk_ja.txt"), encoding="utf-8"):
    p = line.rstrip("\r\n").split("\t")
    if len(p) == 4:
        ja[(p[0], int(p[1]), int(p[2]))] = p[3]

# 1. {8e} の中身
out = []
for k, e in sorted(en.items()):
    words = re.findall(r"\{8e\}(.*?)\{8e\}", e)
    jw = re.findall(r"\{8e\}(.*?)\{8e\}", ja.get(k, ""))
    if [w for w in words if w != "PIGDOG"] != [w for w, ew in zip(jw, words) if ew != "PIGDOG"]:
        out.append(f"{k[0]}\t{k[1]}\t{k[2]}\t英: {words}\t訳: {jw}")
open(os.path.join(OUT, "8e.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
n8e = len(out)

# 2. 打つ言葉の添え字
out = []
by_npc = collections.defaultdict(list)
for k in en:
    by_npc[(k[0], k[1])].append(k)
for npc, keys in sorted(by_npc.items()):
    m = re.search(r"打つ言葉: (.*)$", heads.get(npc, ""))
    kws = m.group(1).split() if m else []
    jall = "".join(ja.get(k, "") for k in keys)
    eall = " ".join(en[k] for k in keys)
    for kw in kws:
        if kw in ("name", "job", "bye", "y", "n"):
            continue
        appears = re.search(r"\b" + re.escape(kw), eall, re.I)
        hinted = re.search(r"\(" + re.escape(kw.upper()) + r"[A-Z]*\)", jall)
        if appears and not hinted:
            out.append(f"{npc[0]}\t{npc[1]}\t{kw.upper()}\t{heads[npc][2:40]}")
open(os.path.join(OUT, "hint.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
nhint = len(out)

# 3. 固有名の表記ゆれ（会話）: 英文の大文字で始まる語と、訳のカタカナ語の、同じ欄に出る回数で対応をとる
KATA = re.compile(r"[ァ-ヴー・]{2,}")
cooc = collections.defaultdict(collections.Counter)
ecount = collections.Counter()
STOP = {"The", "Thou", "Thy", "Thee", "I", "A", "An", "It", "He", "She", "We", "They", "Yes", "No", "If", "But",
        "And", "Ah", "Oh", "My", "Well", "What", "Then", "This", "That", "There", "Tis", "In", "Of", "For", "To",
        "Lord", "Lady", "Sir", "Avatar", "Good", "Ye", "Aye", "Nay"}
for k, e in en.items():
    j = ja.get(k, "")
    names = set(w for w in re.findall(r"\b[A-Z][a-z']{2,}\b", re.sub(r"\{..\}", " ", e)) if w not in STOP)
    katas = set(KATA.findall(j))
    for n in names:
        ecount[n] += 1
        for kt in katas:
            cooc[n][kt] += 1
out = []
for n, c in sorted(ecount.items(), key=lambda x: -x[1]):
    if c < 2:
        continue
    cands = [(kt, v) for kt, v in cooc[n].most_common(6) if v >= max(2, c * 0.25)]
    if len(cands) >= 2:
        out.append(f"{n}（{c}欄）\t" + "  ".join(f"{kt}:{v}" for kt, v in cands))
open(os.path.join(OUT, "names.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"{{8e}} の中身が違う {n8e} 欄、添え字がない打つ言葉 {nhint} 件、表記ゆれの候補 {len(out)} 語 → {OUT}")
