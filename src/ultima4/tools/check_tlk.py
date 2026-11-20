# 会話の訳を作業ファイルと照らして確かめる（目安の検査。正確な長さは組み立てで確かめる）
# 使い方: python check_tlk.py <作業ファイル translation/work/tlk_<町>.txt> <訳のファイル>
# 調べること: 項目の抜け、書き方の間違い、1人分の長さの目安（訳の字数＋区切り ≦ 訳に使える目安）、
#             16マスを越える英数字の続き（改行できない）
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
work, ja = sys.argv[1], sys.argv[2]
FIELDS = ["name", "pronoun", "look", "job", "health", "kw1", "kw2", "question", "yes", "no"]
room = {}
en = {}
for line in open(work, encoding="utf-8"):
    m = re.match(r"# (\w+#\d\d) .*訳に使える目安 (\d+) バイト", line)
    if m:
        room[m.group(1)] = int(m.group(2))
    elif "\t" in line and not line.startswith("#"):
        k, t = line.rstrip("\n").split("\t", 1)
        en[k] = t
tr = {}
bad = 0
for no, line in enumerate(open(ja, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    if not line.strip() or line.startswith("#"):
        continue
    if "\t" not in line:
        print(f"{no}行目: タブがありません: {line}")
        bad += 1
        continue
    k, t = line.split("\t", 1)
    if k not in en:
        print(f"{no}行目: 作業ファイルにない項目: {k}")
        bad += 1
        continue
    if not t.strip():
        print(f"{k}: 訳が空です")
        bad += 1
    tr[k] = t.replace("\\n", "\n")
people = sorted({k.split(".")[0] for k in en})
for p in people:
    got = [f for f in FIELDS if f"{p}.{f}" in tr]
    if got and len(got) < len(FIELDS):
        print(f"{p}: 項目が足りません（{', '.join(f for f in FIELDS if f not in got)}）")
        bad += 1
    if got:
        n = sum(len(tr[f"{p}.{f}"]) + 1 for f in got)
        if n > room[p]:
            print(f"{p}: 長すぎる目安 {n} / {room[p]} バイト（縮めてください）")
            bad += 1
        elif n > room[p] - 15:
            print(f"{p}: （注意）上限に近い {n} / {room[p]} バイト")
    for f in got:
        for run in re.findall(r"[\x21-\x7e]+", tr[f"{p}.{f}"]):
            if len(run) > 16:
                print(f"{p}.{f}: 16マスを越える英数字の続き（空白で区切る）: {run}")
                bad += 1
done = sum(1 for p in people if f"{p}.name" in tr)
print(f"訳した人 {done} / {len(people)}、問題 {bad} 件")
