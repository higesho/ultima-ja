# 訳す文字列の一覧（translation/en_all.tsv）を作る
#   列: キー、表示の種類、英文
#   表示の種類: MSG = メッセージ欄（16 マス、自動で折り返す）、POS = 決まった位置、TAB = 番地の表、TALK = 会話
# 使い方: python list_en.py <ゲームのフォルダ>
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import u3data  # noqa: E402
import build_u3jp  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
game = sys.argv[1]
MSGF = {"E": {0x26A9}, "B": set()}
rows = []
for tag in ("B", "E"):
    r = u3data.collect(game, tag)
    d = r["data"]
    for a, s in sorted(r["units"].items()):
        kinds = set()
        for ins in r["code"].get(a, []):
            # lea si の後ろ 12 バイト以内の call の行き先
            for k in range(ins + 4, ins + 16):
                if d[k - 0x100] == 0xE8:
                    t = (k + 3 + struct.unpack_from("<h", d, k - 0x100 + 1)[0]) & 0xFFFF
                    kinds.add("MSG" if t in MSGF[tag] else "POS")
                    break
        if r["tab"].get(a):
            kinds.add("TAB")
        rows.append((f"{tag}.{a:04x}", "/".join(sorted(kinds)), u3data.show(s)))
for fn in sorted(os.listdir(game)):
    if not fn.upper().endswith(".ULT"):
        continue
    data = open(os.path.join(game, fn), "rb").read()
    if len(data) not in build_u3jp.TALK_FILES:
        continue
    toff, ents = build_u3jp.talk_entries(data)
    for k, t, p in ents:
        rows.append((f"{fn.upper()[:-4]}.{k}", "TALK", u3data.show(t)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "translation", "en_all.tsv")
with open(out, "w", encoding="utf-8") as f:
    for row in rows:
        f.write("\t".join(row) + "\n")
print(len(rows), "件")
