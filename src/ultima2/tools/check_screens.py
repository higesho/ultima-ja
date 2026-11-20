# 文字画面ごとに、組の字（読み込みが要る字）の数を数える。1画面 62 字まで
# 使い方: python check_screens.py <ja.txt> <U2JP_enc.json>
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 62
LEADS = list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD))


def table_keys(start, end):
    return [k for k in TABLE_ORDER if start <= int(k, 16) < end]


SCREENS = {
    "クレジット": ["0014e", "00161", "00190", "001a4", "001c7", "001ed"],
    "タイトルのメニュー": ["00253", "0026a", "0027f", "00294", "002ad", "002d8", "002f0", "00304", "0032b",
                    "00357", "00381"],
    "キャラクター作成": ["0549e", "054bf", "054f4", "0575b", "05788", "057c9", "057f7", "05823", "05854",
                  "0589e", "058ce", "058fd", "0592f"],
    "ディスクの案内": ["007c6", "0546b", "05489", "05a43", "0531e"],
    # ステータス画面: 見出しと、表の能力値・種族・職業・武器・防具・呪文・品物を全部（最悪の場合）
    "ステータス画面": ["04583", "045c7", "045ec", "0460d", "04632", "04650", "04672", "0474b", "04774",
                "047a5", "047cd", "047fd", "04825", "04856", "04884", "04889", "05069", "05072",
                "TABLE:04d53-04f04"],
}

tr = {}
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        continue
    k, _, v = line.partition("\t")
    tr[k] = v.replace("\\n", "\r")
TABLE_ORDER = [k for k in tr if "." not in k and 0x4C60 <= int(k, 16) < 0x4F04]
data = json.load(open(sys.argv[2], encoding="utf-8"))
enc = {t: bytes.fromhex(h) for t, h in data["encoded"].items()}
pairs = data["pairs"]


def glyphs_of(b):
    g = set()
    i = 0
    while i < len(b):
        c = b[i]
        if c in LEADS and i + 1 < len(b):
            idx = LEADS.index(c) * 0xC0 + (b[i + 1] - 0x40)
            a, bb = pairs[idx]
            for x in (a, bb):
                if x is not None:
                    g.add(x)
            i += 2
        else:
            i += 1
    return g


bad = False
for name, keys in SCREENS.items():
    allk = []
    for k in keys:
        if k.startswith("TABLE:"):
            a, e = k[6:].split("-")
            allk += [x for x in TABLE_ORDER if int(a, 16) <= int(x, 16) < int(e, 16)]
        else:
            allk.append(k)
    g = set()
    for k in allk:
        if k in tr and tr[k] in enc:
            g |= glyphs_of(enc[tr[k]])
    mark = "OK" if len(g) <= LIMIT else "多すぎる"
    bad |= len(g) > LIMIT
    print(f"{name}: {len(g)} 字 {mark}  {''.join(sorted(x for x in g if ord(x) > 0x7e))}")
sys.exit(1 if bad else 0)
