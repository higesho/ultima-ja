# 会話（*.TLK）を、訳す人向けの表に書き出す（作業用）
# 使い方: python tlk_extract.py <ゲームのフォルダ> <出力フォルダ> [1 組の字数の目安]
#   出力: tlk_XX.tsv（XX は組の番号）。1 行 1 欄:
#     ファイル<TAB>人<TAB>欄<TAB>種類<TAB>英文
#   種類: text（訳す）/ key（打つ言葉。訳さない）/ code（命令だけ。訳さない）
#   英文の中の {xx} は命令のバイト（そのまま残す）。{86} の後の 1 バイト、{85} の後の数字 3 つ、
#   台本の最後の @ も {xx} で書く
#   人ごとに「# 人 n: 名前 / 打つ言葉: ...」の見出し行をつける
import os
import re
import struct
import sys
import glob

sys.stdout.reconfigure(encoding="utf-8")
game, outdir = sys.argv[1], sys.argv[2]
chunk_chars = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
os.makedirs(outdir, exist_ok=True)

D = open(os.path.join(game, "DATA.OVL"), "rb").read()
words = []
i = 0x104C
while True:
    j = D.index(b"\0", i)
    w = D[i:j]
    if not re.fullmatch(rb"[A-Za-z',]+", w):
        break
    words.append(w.decode())
    i = j + 1
SKIP = {0x08, 0x1C, 0x32, 0x41, 0x43, 0x46, 0x48, 0x49, 0x4A, 0x4B}   # 辞書の番号の抜け（tlk_dump.py と同じ）


def word(c):
    k = c - 1 - sum(1 for s in SKIP if s < c)
    return words[k]


def show(field, last):
    """欄のバイト列を、訳す人に見せる文字列にする"""
    out = []
    i = 0
    while i < len(field):
        b = field[i]
        if 0x80 <= b <= 0x9F:
            out.append("{%02x}" % b)
            if b == 0x86 and i + 1 < len(field):          # 品物を渡す: 次の 1 バイトは品物の番号
                i += 1
                out.append("{%02x}" % field[i])
            elif b == 0x85:                                # 金: 次の数字 3 つ
                for _ in range(3):
                    if i + 1 < len(field) and 0xB0 <= field[i + 1] <= 0xB9:
                        i += 1
                        out.append("{%02x}" % field[i])
        elif b == 0xFE and i + 1 < len(field):            # 条件の命令: 次の 1 バイトは値（3 か所だけ）
            out.append("{fe}{%02x}" % field[i + 1])
            i += 1
        elif b >= 0xA0:
            if b == 0xFF or (last and i == len(field) - 1 and b == 0xC0):  # 0xFF と台本の最後の @ は命令として残す
                out.append("{c0}")
            else:
                out.append(chr(b & 0x7F))
        elif b == 0:
            pass
        else:
            out.append(" " + word(b) + " ")
        i += 1
    s = "".join(out)
    s = re.sub(r" {2,}", " ", s)
    s = re.sub(r" ([.,!?;:\"'])", r"\1", s)
    return s.strip(" ")


rows = []          # (ファイル, 人, 欄, 種類, 英文)
heads = {}         # (ファイル, 人) -> 見出し
for f in sorted(glob.glob(os.path.join(game, "*.TLK"))):
    name = os.path.basename(f).upper()
    d = open(f, "rb").read()
    n = struct.unpack_from("<H", d)[0]
    offs = [struct.unpack_from("<HH", d, 2 + 4 * k)[1] for k in range(n)] + [len(d)]
    for k in range(n):
        fields = d[offs[k]:offs[k + 1]].split(b"\0")
        texts = [show(fl, idx == len(fields) - 1) for idx, fl in enumerate(fields)]
        keys = []
        for idx, t in enumerate(texts):
            plain = re.sub(r"\{..\}", "", t).strip()
            if not plain:
                kind = "code"
            elif idx >= 5 and re.fullmatch(r"[a-z]{1,4}", plain) and "{" not in t.replace("{87}", ""):
                kind = "key"
                if len(plain) > 1:
                    keys.append(plain)
            else:
                kind = "text"
            rows.append((name, k, idx, kind, t))
        nm = re.sub(r"\{..\}", "", texts[0]).strip(' "')
        heads[(name, k)] = f"# 人 {k}: {nm} / 打つ言葉: {' '.join(dict.fromkeys(keys))}"

# 人の切れ目で、字数の目安ごとに組に分ける
groups, cur, size, last = [], [], 0, None
for r in rows:
    key = (r[0], r[1])
    if key != last and size >= chunk_chars:
        groups.append(cur)
        cur, size = [], 0
    if key != last:
        cur.append(heads[key])
        last = key
    cur.append("\t".join(map(str, r)))
    if r[3] == "text":
        size += len(r[4])
groups.append(cur)
for gi, g in enumerate(groups):
    open(os.path.join(outdir, f"tlk_{gi:02d}.tsv"), "w", encoding="utf-8").write("\n".join(g) + "\n")
total = sum(len(r[4]) for r in rows if r[3] == "text")
print(f"欄 {len(rows)}（訳す {sum(1 for r in rows if r[3] == 'text')}）、英文 約 {total} 字、組 {len(groups)}")
