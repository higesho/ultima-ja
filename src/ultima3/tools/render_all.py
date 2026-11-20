# 全訳を、常駐部と同じ字の形・同じ解読の仕方で絵にする（確認用）
#   1) 符号化したバイト列を、常駐部と同じ規則（1バイトの字・2字の組・ゲームのフォントの英数字）で解読し、元の訳と一致するか調べる
#   2) メッセージ欄と同じく 16 マスで折り返して、全訳を一覧の絵（test/all_*.png）にする
# 使い方: python render_all.py <ゲームのフォルダ> <U3JP_enc.json> <出力の頭（例 test/all）>
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jpenc import load_bdf, is_jp  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
game, encp, outp = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
j = json.load(open(encp, encoding="utf-8"))
glyphs = load_bdf(os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf"))
charset = open(os.path.join(game, "CHARSET.ULT"), "rb").read()
single = {v: k for k, v in j["single"].items()}
pairs = j["pairs"]
nlead = j["nlead"]
LEADS = list(range(0x80, 0x80 + nlead))


def decode(b):
    """→ [(字, 種類)]  種類: 'a' 英数字（ゲームのフォント）/ 'j' 日本語 / 'b' 空白 / 'n' 改行"""
    out = []
    i = 0
    while i < len(b):
        x = b[i]
        if x == 0x0A:
            out.append(("\n", "n"))
        elif x < 0x80:
            out.append((chr(x), "a"))
        elif x in LEADS:
            idx = (x - 0x80) * 128 + (b[i + 1] - 0x80)
            a, c = pairs[idx]
            for ch in (a, c):
                if ch is None:
                    out.append((" ", "b"))
                else:
                    out.append((ch, "j" if is_jp(ch) else "a"))
            i += 1
        else:
            out.append((single[x], "j"))
        i += 1
    return out


def cell_img(ch, kind):
    im = Image.new("L", (8, 8), 0)
    px = im.load()
    if kind == "j":
        g = glyphs.get(ord(ch), bytes(8))
        for y in range(8):
            for x in range(8):
                if g[y] & (0x80 >> x):
                    px[x, y] = 255
    elif kind == "a":
        c = ord(ch) & 0x7F
        g = charset[c * 16:c * 16 + 16]
        order = [0, 2, 4, 6, 1, 3, 5, 7]
        for k in range(8):
            w = (g[2 * k] << 8) | g[2 * k + 1]
            for x in range(8):
                v = (w >> (14 - 2 * x)) & 3
                px[x, order[k]] = (0, 90, 170, 255)[v]
    return im


# 1) 解読して元の訳と一致するか
tr = {}
for line in open(os.path.join(HERE, "..", "translation", "ja.txt"), encoding="utf-8"):
    line = line.rstrip("\n")
    if line and not line.startswith("#") and "\t" in line:
        k, t = line.split("\t", 1)
        for a in ("{c}", "{r}", "{l.}", "{l}"):
            if t.startswith(a):
                t = t[len(a):]
        tr[k] = t.replace("\\n", "\n").replace("{10}", "\x10").replace("{11}", "\x11")
bad = 0
for k, h in j["encoded"].items():
    dec = "".join(ch for ch, kind in decode(bytes.fromhex(h)) if kind != "b")
    if dec.replace(" ", "").replace(".", "") != tr[k].replace(" ", "").replace(".", ""):
        bad += 1
        print("一致しない:", k, repr(dec), repr(tr[k]))
blanks = sum(1 for k, h in j["encoded"].items() for ch, kind in decode(bytes.fromhex(h)) if kind == "b")
print(f"解読: {len(j['encoded'])} 件、一致しないもの {bad} 件、組の空白 {blanks} マス")

# 2) 16 マスで折り返して並べる
W = 16
blocks = []
for k in sorted(j["encoded"]):
    cells = decode(bytes.fromhex(j["encoded"][k]))
    lines = [[]]
    for ch, kind in cells:
        if kind == "n":
            lines.append([])
            continue
        if len(lines[-1]) >= W:
            lines.append([])
        lines[-1].append((ch, kind))
    blocks.append((k, lines))
COLS, ROWS = 6, 48
SC = 2
pages = []
cur = []
col = 0
row = 0
for k, lines in blocks:
    need = len(lines) + 2
    if row + need > ROWS:
        col += 1
        row = 0
        if col >= COLS:
            pages.append(cur)
            cur = []
            col = 0
    cur.append((col, row, k, lines))
    row += need
pages.append(cur)
for n, page in enumerate(pages):
    im = Image.new("L", (COLS * (W + 2) * 8, ROWS * 8), 0)
    for col, row, k, lines in page:
        x0 = col * (W + 2) * 8
        for i, ch in enumerate(k[:W]):
            im.paste(cell_img(ch, "a").point(lambda v: v // 2), (x0 + i * 8, row * 8))
        for li, cl in enumerate(lines):
            for ci, (ch, kind) in enumerate(cl):
                im.paste(cell_img(ch, kind), (x0 + ci * 8, (row + 1 + li) * 8))
    im = im.resize((im.width * SC, im.height * SC), Image.NEAREST)
    im.save(f"{outp}_{n + 1}.png")
print(f"絵: {len(pages)} 枚（{outp}_1.png …）")
