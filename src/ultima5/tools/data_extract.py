# DATA.OVL から、訳す候補の文字列を抜き出す（作業用）
# 使い方: python data_extract.py <DATA.OVL> <出力 tsv>
#   出力: 位置(16進)<TAB>元のバイト数<TAB>英文（\n は改行）
#   除くもの: 会話・店の辞書（0x104C〜0x12BC）、ファイル名、実行時ライブラリ（0xA400〜）、コードや表の雑音
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
D = open(sys.argv[1], "rb").read()
FILE_RE = re.compile(r"\.(DAT|OVL|NPC|TLK|OOL|GAM|BIT|PTH|CH|HCS|16|4|DRV|PCS|CBT|SAV)$", re.I)
SHORT_OK = {"a", "i", "no", "an", "of", "to", "in", "is", "it", "go", "up", "on", "ok", "yes"}
rows, dropped = [], {}
for m in re.finditer(rb"(?<=\x00)[\x0a\x20-\x7e]{2,}(?=\x00)", D):
    off, t = m.start(), m.group().decode("latin1")
    words = re.findall(r"[A-Za-z]+", t)
    why = None
    if 0x104C <= off < 0x12BC:
        why = "dict"
    elif FILE_RE.search(t.strip()):
        why = "file"
    elif off >= 0xA400:
        why = "rtl"
    elif not words or not any(len(w) >= 3 or w.lower() in SHORT_OK for w in words):
        why = "noise"
    elif re.search(r"[\[\]{}^`|~\\]", t) and len(words) < 2:
        why = "noise"
    if why:
        dropped[why] = dropped.get(why, 0) + 1
        continue
    rows.append((off, len(m.group()), t))
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for off, n, t in rows:
        f.write("%05x\t%d\t%s\n" % (off, n, t.replace("\n", "\\n")))
print("候補", len(rows), "件", sum(len(t) for *_, t in rows), "字 / 除いたもの", dropped)
