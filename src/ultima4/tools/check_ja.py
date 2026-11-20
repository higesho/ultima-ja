# 訳のファイルを元表と照らして確かめる（目安の検査）
# 使い方: python check_ja.py <作業ファイル translation/work/xxx.tsv> <訳のファイル>
#   訳のファイル: 1行に「id<TAB>訳」。改行は \n と書く。訳さない行は書かない
# 調べること: 抜け、id の間違い、長さの目安（字数＋2 ≦ 最大バイト）、前後の \n と空白が英語と同じか、
#             TITLE の1行が38マス以内か、行数が英語以下か
import sys

sys.stdout.reconfigure(encoding="utf-8")
work, ja = sys.argv[1], sys.argv[2]
rows = {}
for line in open(work, encoding="utf-8"):
    if line.startswith("#"):
        continue
    i, n, k, en, ex = line.rstrip("\n").split("\t")
    rows[i] = (int(n), k, en.replace("\\n", "\n"))
tr = {}
bad = 0
for no, line in enumerate(open(ja, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        continue
    if "\t" not in line:
        print(f"{no}行目: タブがありません: {line}")
        bad += 1
        continue
    i, t = line.split("\t", 1)
    tr[i] = t.replace("\\n", "\n")


def edge(s):
    a = len(s) - len(s.lstrip("\n "))
    b = len(s) - len(s.rstrip("\n "))
    return (s[:a], s[len(s) - b:] if b else "")


for i, t in tr.items():
    if i not in rows:
        print(f"{i}: 元表にない id")
        bad += 1
        continue
    n, k, en = rows[i]
    if k != "text":
        print(f"{i}: 訳さない行（keep）です")
        bad += 1
        continue
    if len(t) > n:
        print(f"{i}: 長すぎる {len(t)}字 / 最大 {n} バイト: {t!r}")
        bad += 1
    elif n >= 10 and len(t) + 2 > n:
        print(f"{i}: （注意）上限ぎりぎり {len(t)}字 / 最大 {n} バイト。少し縮めると安全: {t!r}")
    if edge(t) != edge(en):
        print(f"{i}: 前後の改行・空白が英語と違う 英{edge(en)!r} 訳{edge(t)!r}")
        bad += 1
    if i.startswith("T:"):
        for ln in t.split("\n"):
            if len(ln) > 38:
                print(f"{i}: 38マスを越える行 {len(ln)}: {ln}")
                bad += 1
        if t.count("\n") > en.count("\n"):
            print(f"{i}: 行数が英語より多い（英 {en.count(chr(10)) + 1} 行、訳 {t.count(chr(10)) + 1} 行）")
            bad += 1
missing = [i for i, (n, k, en) in rows.items() if k == "text" and i not in tr]
print(f"訳 {len(tr)} 件、抜け {len(missing)} 件、問題 {bad} 件")
if missing:
    print("抜け:", " ".join(missing[:40]), "…" if len(missing) > 40 else "")
