# 会話（TLK）の訳の作業ファイルを作る
# 使い方: python make_tlk_work.py   → translation/work/tlk_<町>.txt と translation/work/tlk_keywords.txt
#   作業ファイル: tlk_ja.txt と同じ書き方（町#番号.項目<TAB>英文）。人ごとに、打つ言葉と、
#   訳に使える目安のバイト数（288 − 先頭3 − 打つ言葉 − 区切り）をコメントで書く
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, "..", "..")
OUT = os.path.join(HERE, "..", "translation", "work")
FIELDS = ["name", "pronoun", "look", "job", "health", "kw1", "kw2", "question", "yes", "no"]
os.makedirs(OUT, exist_ok=True)

allkeys = {}
for path in sorted(glob.glob(os.path.join(GAME, "*.TLK"))):
    town = os.path.basename(path)[:-4]
    d = open(path, "rb").read()
    lines = [f"# {town}.TLK の会話（英文）。訳は同じ行の形で「町#番号.項目<TAB>訳」と書く\n"]
    for i in range(len(d) // 288):
        r = d[i * 288:(i + 1) * 288]
        parts = [p.decode("latin1") for p in r[3:].split(b"\0")[:12]]
        keys = parts[10:12]
        room = 288 - 3 - sum(len(k) + 1 for k in keys) - 10
        en_len = sum(len(p) for p in parts[:10])
        allkeys.setdefault(town, []).append((i + 1, parts[0].replace("\n", " "), keys))
        lines.append(f"\n# {town}#{i + 1:02d}  打つ言葉: {keys[0].strip()} / {keys[1].strip()}"
                     f"  （質問は {['仕事', '体調', '言葉1', '言葉2'][r[0] - 3] if 3 <= r[0] <= 6 else 'なし'} の後）"
                     f"  訳に使える目安 {room} バイト（英語は {en_len}）\n")
        for f, p in zip(FIELDS, parts[:10]):
            lines.append(f"{town}#{i + 1:02d}.{f}\t{p.replace(chr(10), chr(92) + 'n')}\n")
    open(os.path.join(OUT, f"tlk_{town}.txt"), "w", encoding="utf-8", newline="\n").writelines(lines)

with open(os.path.join(OUT, "tlk_keywords.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write("# 町ごとの、人の名前と打つ言葉（先頭4文字で照合）。訳の中でこれらの言葉に当たる語には英語を添える\n")
    for town, people in allkeys.items():
        f.write(f"\n## {town}\n")
        for n, name, keys in people:
            f.write(f"{n:2d} {name:28s} {keys[0].strip():5s} {keys[1].strip()}\n")
print("作りました:", ", ".join(sorted(allkeys)))
