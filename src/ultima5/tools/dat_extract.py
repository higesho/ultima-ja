# 店・物語・質問などの文章ファイルを、訳す人向けの表に書き出す（作業用）
# 使い方: python dat_extract.py <ゲームのフォルダ> <出力 tsv> <ファイル名> [すでに訳した番号を除く訳のファイル...]
#   出力: ファイル<TAB>何番目の文字列か<TAB>英文（\n は改行）
#   SHOPPE.DAT の 0x80 以上は辞書の単語（DS:0x23EA の表）に戻す
import os
import re
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")
game, out, name = sys.argv[1], sys.argv[2], sys.argv[3].upper()
done = set()
for p in sys.argv[4:]:
    for line in open(p, encoding="utf-8"):
        if line.startswith(name + "\t"):
            done.add(int(line.split("\t")[1]))
D = open(os.path.join(game, "DATA.OVL"), "rb").read()


def word(b):
    p = struct.unpack_from("<H", D, 0x23EA + 0x10 + 2 * b)[0]
    return D[p + 0x10:D.index(b"\0", p + 0x10)].decode("latin1")


rows = []
for k, s in enumerate(open(os.path.join(game, name), "rb").read().split(b"\0")):
    if not s or k in done:
        continue
    t = "".join((" " + word(b) + " ") if b >= 0x80 else chr(b) for b in s)
    t = re.sub(r" {2,}", " ", t).replace(" \n", "\n")
    if not re.search(r"[A-Za-z]{2}", t):
        continue
    rows.append(f"{name}\t{k}\t" + t.replace("\n", "\\n"))
open(out, "w", encoding="utf-8").write("\n".join(rows) + "\n")
print(name, len(rows), "件", sum(len(r) for r in rows), "字")
