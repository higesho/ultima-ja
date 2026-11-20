# 「英文 → 訳」の対応表から、位置ごとの訳のファイル（build_u2jp.py が読む形）を作る
# 使い方: python make_ja.py <en_all.tsv> <ja_map.tsv> <ja_override.tsv> <出力 ja.txt>
#   ja_map.tsv:      英文<TAB>訳（英文は en_all.tsv と同じ。\n は改行。前後の空白は無視して照合）
#   ja_override.tsv: キー<TAB>訳（場所によって訳を変えるとき。対応表より優先）
#   訳の先頭の {cN}: N マスの中で中央に寄せる（N を省くと元の長さ）
#   訳が「=」だけ: 英語のまま（最上位ビットだけ消す）。「{}」: 空にする
#   原文の末尾の空白は、訳の末尾に空白がなければ自動で引き継ぐ
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
en_path, map_path, ov_path, out_path = sys.argv[1:5]

# 文字画面（40桁）や、タイトルの下の行など、30マスを超えてよいもの
WIDE = set()


def load_pairs(path):
    res = {}
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            sys.exit(f"{path}:{n}: タブがありません: {line}")
        k, v = line.split("\t", 1)
        res[k.strip()] = v
    return res


rows = [l.rstrip("\n").split("\t") for l in open(en_path, encoding="utf-8")]
jmap = load_pairs(map_path)
ov = load_pairs(ov_path)
used = set()
out = []
missing = []
long_lines = []
for key, n, kind, en in rows:
    n = int(n)
    if key in ov:
        ja = ov[key]
    elif en.strip() in jmap:
        ja = jmap[en.strip()]
        used.add(en.strip())
    else:
        if re.search(r"[A-Za-z]{2,}", en):
            missing.append(f"{key}\t{en}")
        continue
    if ja == "=":
        continue
    if ja == "{}":
        ja = ""
    else:
        # 原文の末尾の空白は自動で引き継ぐ（訳の末尾に空白がない場合）
        trail = len(en) - len(en.rstrip(" "))
        if trail and not ja.endswith(" "):
            ja += " " * trail
    m = re.match(r"\{c(\d*)\}", ja)
    if m:
        width = int(m.group(1)) if m.group(1) else len(en)
        body = ja[m.end():]
        ja = " " * max(0, (width - len(body)) // 2) + body
    for line in ja.split("\\n"):
        if len(line) > 30 and kind in ("会話", "うわさ", "手がかり"):
            long_lines.append(f"{key}\t{len(line)}\t{line}")
    out.append(f"# {kind} {n}: {en}\n{key}\t{ja}\n")

open(out_path, "w", encoding="utf-8").write("".join(out))
print(f"{len(out)} 件を書き出しました")
if missing:
    print(f"訳がない英文 {len(missing)} 件:")
    print("\n".join(missing))
unused = [k for k in jmap if k not in used]
if unused:
    print(f"使われなかった対応 {len(unused)} 件:")
    print("\n".join(unused))
if long_lines:
    print("30マスを超える行:")
    print("\n".join(long_lines))
