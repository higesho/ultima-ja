# 日本語版の TALK.LZC・LOOK.LZC・CREATE.LZC を、元のファイルからの「写す」と「書く」の並びにした
# パッチ MDJP.PAT を作る。配布物に原作のデータを入れないため（遊ぶ人の DOSBox で MDJPMK.COM が *.LZJ を組み立てる）
# 使い方: python make_patch.py <ゲームのフォルダ> <組み立て済みのフォルダ（build/conv）> <出力 MDJP.PAT>
#
# MDJP.PAT の形（数はリトルエンディアン）
#   "MDJPPAT2"、ファイルの数（2）、版の印（8。この後ろ全体のハッシュと大きさ）
#   作るファイルの一覧: 作る名前（12）、作る大きさ（4）をファイルの数だけ（組み立て済みかを早く確かめるため）
#   ファイルごと: 元の名前（12 バイト、0 埋め）、作る名前（12）、元の大きさ（4）、元のハッシュ h1, h2（各 2）、命令の数（2）
#     命令 0: 元のファイルから写す（位置 4、長さ 4）
#     命令 1: 書く（長さ 2、バイト列）
#     命令 2: 元のファイルの LZW の項目を展開する（位置 4、長さ 2）。以後の命令 3 はこの展開した中身から写す
#     命令 3: 展開した中身から写す（位置 2、長さ 2）
#   ハッシュ: h1 = rol(h1,1) + b、h2 = rol(h2 + b, 3)（どちらも 16 ビット、初めは 0）
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mdfmt  # noqa: E402
from u6fmt import lzw  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
FILES = [("TALK.LZC", "TALK.LZJ"), ("LOOK.LZC", "LOOK.LZJ"), ("MDTEXT.LZC", "MDTEXT.LZJ"), ("SCENETXT.LZC", "SCENETXT.LZJ")] +     [(f"MIDGAME{c}.LZC", f"MIDGAME{c}.LZJ") for c in "123456789ABCD"]
K = 4                 # 見出しの長さ
MIN_D, MIN_F = 5, 5  # 写す一致の最短（原作の文字列を「書く」に残さないよう短くても写す）
MAXDATA = 0xF000      # 1 つの書く命令の最大


def rol16(x, n):
    return ((x << n) | (x >> (16 - n))) & 0xFFFF


def h12(bs):
    h1 = h2 = 0
    for b in bs:
        h1 = (rol16(h1, 1) + b) & 0xFFFF
        h2 = rol16((h2 + b) & 0xFFFF, 3)
    return h1, h2


def items_with_pos(data):
    """[(位置, 印, 生のバイト列)]（空は (None, 0xFF, None)）"""
    total, ents = mdfmt.entries(data)
    return [(None, f, None) if f == 0xFF or r is None else (o, f, r) for o, f, r in ents]


def match_ops(src, dst, minlen):
    """dst を src からの写す (位置, 長さ) と書く bytes の並びにする（K バイトの見出しで探して前へ伸ばす）"""
    index = {}
    for i in range(len(src) - K + 1):
        index.setdefault(src[i:i + K], []).append(i)
    ops = []
    lit = bytearray()
    p = 0
    while p < len(dst):
        best = (0, 0)
        for i in index.get(dst[p:p + K], [])[:64]:
            n = K
            while p + n < len(dst) and i + n < len(src) and src[i + n] == dst[p + n]:
                n += 1
            if n > best[1]:
                best = (i, n)
        if best[1] >= minlen:
            if lit:
                ops.append(("data", bytes(lit)))
                lit = bytearray()
            ops.append(("copy", best[0], best[1]))
            p += best[1]
        else:
            lit.append(dst[p])
            p += 1
    if lit:
        ops.append(("data", bytes(lit)))
    out = bytearray()
    for op in ops:
        out += src[op[1]:op[1] + op[2]] if op[0] == "copy" else op[1]
    assert bytes(out) == dst
    return ops


def file_ops(src, dst):
    """元の LZC と新しい LZC から命令の並び"""
    s_items = items_with_pos(src)
    d_items = items_with_pos(dst)
    assert len(s_items) == len(d_items)
    ops = [("data", dst[:d_items[0][0] if d_items[0][0] else min(o for o, f, b in d_items if o)])]
    # 新しい束の中身は、見出しのあとに項目が並んだもの（save_lzc の形）
    body_start = len(ops[0][1])
    pos = body_start
    for (so, sf, sb), (do, df, db) in zip(s_items, d_items):
        if db is None:
            continue
        assert do == pos, (do, pos)
        pos += len(db)
        if sb is not None and db == sb:
            ops.append(("fcopy", so, len(sb)))          # 変えていない項目はそのまま写す
            continue
        if sf == 0x20:          # MD の LZW の印
            dec, _ = lzw(sb)
            ops.append(("unz", so, len(sb)))
            for op in match_ops(dec, db, MIN_D):
                ops.append(("dcopy", op[1], op[2]) if op[0] == "copy" else op)
        else:
            base = so if sb is not None else 0
            for op in match_ops(sb or b"", db, MIN_F):
                ops.append(("fcopy", base + op[1], op[2]) if op[0] == "copy" else op)
    assert pos == len(dst)
    return ops


def encode_ops(ops):
    out = bytearray()
    n = 0
    for op in ops:
        if op[0] == "data":
            for i in range(0, len(op[1]), MAXDATA):
                part = op[1][i:i + MAXDATA]
                out += struct.pack("<BH", 1, len(part)) + part
                n += 1
        elif op[0] == "fcopy":
            out += struct.pack("<BII", 0, op[1], op[2])
            n += 1
        elif op[0] == "unz":
            assert op[2] < 0xFFF0
            out += struct.pack("<BIH", 2, op[1], op[2])
            n += 1
        else:
            out += struct.pack("<BHH", 3, op[1], op[2])
            n += 1
    return n, bytes(out)


def apply_ops(src, ops):
    """確かめ用: 命令を実行して新しいファイルを作る"""
    out = bytearray()
    dec = b""
    for op in ops:
        if op[0] == "data":
            out += op[1]
        elif op[0] == "fcopy":
            out += src[op[1]:op[1] + op[2]]
        elif op[0] == "unz":
            dec, _ = lzw(src[op[1]:op[1] + op[2]])
        else:
            out += dec[op[1]:op[1] + op[2]]
    return bytes(out)


def main(game, built, outpath):
    blob = bytearray()
    table = bytearray()
    for srcname, dstname in FILES:
        src = open(os.path.join(game, srcname), "rb").read()
        dst = open(os.path.join(built, srcname), "rb").read()
        ops = file_ops(src, dst)
        assert apply_ops(src, ops) == dst
        n, body = encode_ops(ops)
        h1, h2 = h12(src)
        blob += srcname.encode().ljust(12, b"\0") + dstname.encode().ljust(12, b"\0")
        blob += struct.pack("<IHHH", len(src), h1, h2, n) + body
        table += dstname.encode().ljust(12, b"\0") + struct.pack("<I", len(dst))
        data = sum(len(o[1]) for o in ops if o[0] == "data")
        print(f"{dstname:11s} 元 {len(src):7d} → {len(dst):7d}  書く {data:7d}  命令 {n}")
    rest = bytes(table + blob)
    stamp = struct.pack("<HHI", *h12(rest), len(rest))
    open(outpath, "wb").write(b"MDJPPAT2" + struct.pack("<H", len(FILES)) + stamp + rest)
    blob = rest
    print(f"書き出し: {outpath} {len(blob)} バイト")


if __name__ == "__main__":
    main(*sys.argv[1:4])
