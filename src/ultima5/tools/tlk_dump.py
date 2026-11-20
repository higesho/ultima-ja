# 会話ファイル（*.TLK）を辞書で展開して、テキストに書き出す（調査用）
# 使い方: python tlk_dump.py <ゲームのフォルダ> <出力フォルダ>
#
# - TLK: 先頭 2 バイト = 人数 n、続いて (人の番号, 位置) が n 組。各人の台本は次の人の位置まで
# - 0xA0 以上: 文字（下位 7 ビット）。0x00: 区切り
# - 0x01〜0x7F: 辞書の単語（DATA.OVL の 0x104C から、0 区切り）。番号の割り当てに抜けがある（下の SKIP）
# - 0x80〜0x9F: 台本の命令（0x81 名前、0x87 または、0x8D 改行、0x86 品物を渡す＋番号 など）
import os
import re
import struct
import sys
import glob
import collections

sys.stdout.reconfigure(encoding="utf-8")
game, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)

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

# 0x86（品物を渡す）の引数として出てくる値。単語の番号には使われていない（仮説。ゲームの展開処理で確かめる）
SKIP = {0x08, 0x1C, 0x32, 0x41, 0x43, 0x46, 0x48, 0x49, 0x4A, 0x4B}


def word(c):
    if c in SKIP:
        return "<%02x>" % c
    k = c - 1 - sum(1 for s in SKIP if s < c)
    return words[k] if k < len(words) else "<?%02x>" % c


total = 0
for f in sorted(glob.glob(os.path.join(game, "*.TLK"))):
    d = open(f, "rb").read()
    n = struct.unpack_from("<H", d)[0]
    offs = [struct.unpack_from("<HH", d, 2 + 4 * k)[1] for k in range(n)] + [len(d)]
    res = []
    for k, (a, b) in enumerate(zip(offs, offs[1:])):
        res.append("\n===== %d =====\n" % k)
        for x in d[a:b]:
            if x >= 0xA0:
                res.append(chr(x & 0x7F))
            elif x == 0:
                res.append("\n")
            elif x < 0x80:
                res.append(" " + word(x) + " ")
            else:
                res.append("{%02x}" % x)
    s = re.sub(" +", " ", "".join(res))
    name = os.path.basename(f)
    open(os.path.join(out, name + ".txt"), "w", encoding="utf-8").write(s)
    plain = re.sub(r"\{..\}|<..>|=====.*=====", "", s)
    total += len(plain)
    print(f"{name:13s} 人数 {n:3d}  ファイル {len(d):6d} バイト  展開後 約 {len(plain):6d} 字")
print("合計 約", total, "字")
