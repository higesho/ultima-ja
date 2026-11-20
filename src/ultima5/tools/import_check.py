# 手分けした訳（translation/work/out/*.tsv）を検査して、組み立て用の訳のファイルにまとめる
# 使い方: python import_check.py   （jp_work から）
#   出力: translation/tlk_ja.txt（会話）、translation/dat_ja.txt（店・物語・質問、story_test/misc_test の分も合わせる）、
#         translation/data_ja.txt（本体の文章）、translation/work/check.txt（問題の一覧）
#   問題のある行は「直すもの」として check.txt に出し、組み立てには使わない（英語のまま残る）
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_u5jp as B  # noqa: E402

TR = os.path.join(HERE, "..", "translation")
W = os.path.join(TR, "work")
BS = chr(92)
NL = BS + "n"
BAD = set("+<=>[]`{|}~_") | {BS}
problems = []


def bad_chars(t, allow=""):
    t = t.replace(NL, "")
    return sorted({c for c in t if c in BAD and c not in allow})


def width(t):
    return len(B.norm(t.replace(NL, "\n")))


def edges(t):
    """先頭と末尾の \\n と半角空白"""
    t = t.replace(NL, "\n")
    a = re.match(r"^[\n ]*", t).group()
    b = re.search(r"[\n ]*$", t).group()
    return a, b


def fix_edges(en, ja):
    """訳の先頭と末尾の \\n・空白を英文と同じにする（Write で行末の空白が消えることがあるため）"""
    ea, eb = edges(en)
    t = ja.replace(NL, "\n").strip("\n ")
    return (ea + t + eb).replace("\n", NL)


# ---------------- 会話 ----------------
src = {}
for f in glob.glob(os.path.join(W, "tlk", "tlk_*.tsv")):
    for line in open(f, encoding="utf-8"):
        if line.startswith("#"):
            continue
        p = line.rstrip("\r\n").split("\t")
        if len(p) == 5 and p[3] == "text":
            src[(p[0], int(p[1]), int(p[2]))] = p[4]
tlk_out, seen = [], set()
# 見直した組（out2）を先に使い、問題のある行や無い行は最初の訳（out）を使う
tlk_files = sorted(glob.glob(os.path.join(W, "out2", "tlk_*.tsv"))) + sorted(glob.glob(os.path.join(W, "out", "tlk_*.tsv")))
for f in tlk_files:
    tag = os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f)
    for n, line in enumerate(open(f, encoding="utf-8-sig"), 1):
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        p = line.split("\t")
        where = f"{tag}:{n}"
        if len(p) != 4 or not p[1].isdigit() or not p[2].isdigit():
            problems.append(f"{where} 列の数がちがう: {line[:60]}")
            continue
        key = (p[0], int(p[1]), int(p[2]))
        if key in seen:
            continue
        if key not in src:
            problems.append(f"{where} 入力にない欄: {key}")
            continue
        en, ja = src[key], p[3]
        if re.findall(r"\{..\}", en) != re.findall(r"\{..\}", ja):
            problems.append(f"{where} 命令がちがう {key}: 英 {re.findall(r'{..}', en)} / 訳 {re.findall(r'{..}', ja)}")
            continue
        e8 = [w for w in re.findall(r"\{8e\}(.*?)\{8e\}", en)]
        j8 = [w for w in re.findall(r"\{8e\}(.*?)\{8e\}", ja)]
        if [w for w in e8 if w != "PIGDOG"] != [j for j, e in zip(j8, e8) if e != "PIGDOG"]:
            problems.append(f"{where} {{8e}} の中の打つ言葉が変わった {key}: {e8} → {j8}")
            continue
        bc = bad_chars(re.sub(r"\{..\}", "", ja))
        if bc:
            problems.append(f"{where} 使えない記号 {bc} {key}")
            continue
        if en.count('"') != ja.count('"'):
            problems.append(f"{where} \" の数がちがう {key}（英 {en.count(chr(34))} / 訳 {ja.count(chr(34))}）: {ja[:40]}")
        seen.add(key)
        tlk_out.append(f"{p[0]}\t{p[1]}\t{p[2]}\t{ja}")
missing = sorted(set(src) - seen)
for k in missing:
    problems.append(f"会話 訳がない: {k}")
open(os.path.join(TR, "tlk_ja.txt"), "w", encoding="utf-8").write(
    "# 会話の訳（組み立て用。import_check.py が作る）\n" + "\n".join(tlk_out) + "\n")

# ---------------- 店・物語・質問など ----------------
dsrc = {}
for f in ["shoppe.tsv", "story.tsv", "question.tsv"]:
    for line in open(os.path.join(W, f), encoding="utf-8"):
        p = line.rstrip("\r\n").split("\t", 2)
        dsrc[(p[0], int(p[1]))] = p[2]
dat_out = []
for f in ["shoppe_00.tsv", "shoppe_01.tsv", "story.tsv", "question.tsv"]:
    path = os.path.join(W, "out", f)
    if not os.path.exists(path):
        problems.append(f"{f} がまだない")
        continue
    for n, line in enumerate(open(path, encoding="utf-8-sig"), 1):
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        p = line.split("\t", 2)
        where = f"{f}:{n}"
        if len(p) != 3 or not p[1].isdigit() or (p[0], int(p[1])) not in dsrc:
            problems.append(f"{where} 形がちがう: {line[:60]}")
            continue
        en, ja = dsrc[(p[0], int(p[1]))], p[2]
        ja = fix_edges(en, ja)
        allow = "{" if p[0] != "SHOPPE.DAT" else ""
        bc = bad_chars(ja, allow)
        if bc:
            problems.append(f"{where} 使えない記号 {bc}")
            continue
        sym = "#$%&*@^" if p[0] == "SHOPPE.DAT" else "{"
        if sorted(c for c in en if c in sym) != sorted(c for c in ja if c in sym):
            problems.append(f"{where} 記号の数がちがう（{sym}）: 英 {en[:40]} / 訳 {ja[:40]}")
            continue
        if en.count(NL) != ja.count(NL):
            problems.append(f"{where} 改行の数がちがう（英 {en.count(NL)} / 訳 {ja.count(NL)}）")
        dat_out.append(f"{p[0]}\t{p[1]}\t{ja}")
# 自分で訳した分（story_test / misc_test）と手で直した分（dat_fix、後ろほど優先）も、末尾の空白をそろえて合わせる
for f in ["story_test.txt", "misc_test.txt", "dat_fix.txt"]:
    if not os.path.exists(os.path.join(TR, f)):
        continue
    for line in open(os.path.join(TR, f), encoding="utf-8"):
        line = line.rstrip("\r\n")
        if not line or line.startswith("#"):
            continue
        p = line.split("\t", 2)
        if p[0] in ("STORY.DAT", "QUESTION.DAT", "MISCMSG.DAT", "KARMA.DAT", "ENDMSG.DAT", "END.DAT"):
            parts = open(os.path.join(HERE, "..", "game_test", p[0]), "rb").read().split(b"\0")
            en = parts[int(p[1])].decode("latin1").replace("\n", NL)
            p[2] = fix_edges(en, p[2])
        dat_out.append("\t".join(p))
open(os.path.join(TR, "dat_ja.txt"), "w", encoding="utf-8").write(
    "# 店・物語・質問・看板・調べるなどの訳（組み立て用。import_check.py が作る）\n" + "\n".join(dat_out) + "\n")

# ---------------- 本体の文章 ----------------
asrc = {}
for f in glob.glob(os.path.join(W, "data_0*.tsv")):
    for line in open(f, encoding="utf-8"):
        p = line.rstrip("\r\n").split("\t", 2)
        asrc[p[0]] = (int(p[1]), p[2])
data_out, keep = [], 0
for f in sorted(glob.glob(os.path.join(W, "out", "data_*.tsv"))):
    for n, line in enumerate(open(f, encoding="utf-8-sig"), 1):
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        p = line.split("\t", 1)
        where = f"{os.path.basename(f)}:{n}"
        if len(p) != 2 or p[0] not in asrc:
            problems.append(f"{where} 形がちがう: {line[:60]}")
            continue
        nbytes, en = asrc[p[0]]
        ja = p[1]
        if ja.strip() == "KEEP":
            keep += 1
            continue
        ja = fix_edges(en, ja)
        bc = bad_chars(ja)
        if bc:
            problems.append(f"{where} 使えない記号 {bc}: {ja}")
            continue
        if sorted(c for c in en if c in "#$%&*@^") != sorted(c for c in ja if c in "#$%&*@^"):
            problems.append(f"{where} 記号の数がちがう: 英 {en} / 訳 {ja}")
            continue
        if nbytes < 3 and len(B.Enc([ja]).encode(ja.replace(NL, "\n"))) > nbytes:
            problems.append(f"{where} 元が {nbytes} バイトで入らない: {en} → {ja}")
            continue
        if NL not in en and " " not in en.strip() or len(en) <= 12:
            if width(ja) > nbytes:
                problems.append(f"{where} 幅が元より広い（{width(ja)} > {nbytes}）: {en} → {ja}")
        data_out.append(f"{p[0]}\t{ja}")
# 手で直した訳（translation/data_fix.txt: 位置<TAB>訳、KEEP なら英語のまま）で上書きする
fixp = os.path.join(TR, "data_fix.txt")
if os.path.exists(fixp):
    fixes = {}
    for line in open(fixp, encoding="utf-8"):
        line = line.rstrip("\r\n")
        if line and not line.startswith("#"):
            k, v = line.split("\t", 1)
            fixes[k] = v
    data_out = [l for l in data_out if l.split("\t", 1)[0] not in fixes]
    data_out += [f"{k}\t{v}" for k, v in fixes.items() if v != "KEEP"]
open(os.path.join(TR, "data_ja.txt"), "w", encoding="utf-8").write(
    "# 本体（DATA.OVL）の訳（組み立て用。import_check.py が作る）\n" + "\n".join(data_out) + "\n")

open(os.path.join(W, "check.txt"), "w", encoding="utf-8").write("\n".join(problems) + "\n")
print(f"会話 {len(tlk_out)} / {len(src)}、店など {len(dat_out)}、本体 {len(data_out)}（KEEP {keep}）、問題 {len(problems)} 件 → work/check.txt")
