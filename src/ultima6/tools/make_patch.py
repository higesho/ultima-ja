# 会話と本の日本語版（CONVERSE.JA / CONVERSE.JB / BOOK.JDT）を、元の CONVERSE.A / CONVERSE.B からの命令の並びにした
# パッチ U6JPMK.DAT を作る。配布物に原作のデータを入れないため（遊ぶ人の DOSBox で U6JPMK.COM が組み立てる）
# 使い方: python make_patch.py <ゲームのフォルダ> <組み立て済みの CONVERSE.A/B があるフォルダ> <出力 U6JPMK.DAT>
#
# U6JPMK.DAT の形（数はリトルエンディアン）
#   "U6JPMK01"、ファイルの数（16）
#   ファイルごと: 元の名前（12 バイト、0 埋め）、作る名前（12 バイト）、元の大きさ（32）、元のハッシュ h1, h2（16）、命令の数（16）、
#     作るファイルのハッシュ h1, h2（16）
#     命令 0: 写す       元の位置（32）、長さ（16）
#     命令 1: 書く       長さ（16）、バイト列
#     命令 2: 展開する   元の位置（32）、長さ（16）  元の項目（先頭 4 バイトが大きさの U6 の LZW）を展開して作業の場所に置く
#     命令 3: 展開から写す 位置（16）、長さ（16）
#   ハッシュ: h1 = rol(h1,1) + b、h2 = rol(h2 + b, 3)（どちらも 16 ビット、初めは 0）

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from u6fmt import lib, lzw  # noqa: E402

MIN_COPY = 4          # これより短い一致は写さずに書く
MAX_LEN = 0xF000


def rol16(x, n):
    return ((x << n) | (x >> (16 - n))) & 0xFFFF


def h12(bs):
    h1 = h2 = 0
    for b in bs:
        h1 = (rol16(h1, 1) + b) & 0xFFFF
        h2 = rol16((h2 + b) & 0xFFFF, 3)
    return h1, h2


def lib_offsets(data):
    """CONVERSE の索引（4 バイトの位置の並び）と、各項目の (位置, 長さ)"""
    items = lib(data, 4)
    n = len(items)
    offs = [struct.unpack_from("<I", data, 4 * i)[0] for i in range(n)]
    return [(o, len(it)) if it is not None else None for o, it in zip(offs, items)]


def diff_ops(src, dst, copy_op):
    """dst を src からの写し（copy_op(位置, 長さ)）と書く（("data", bytes)）で表す。
    前から順に、src のどこからでも最も長く一致する所を写す（順番が入れ替わった一致も拾うため。difflib は拾わない）"""
    idx = {}
    for i in range(len(src) - MIN_COPY + 1):
        idx.setdefault(src[i:i + MIN_COPY], []).append(i)
    ops = []
    lit = bytearray()
    i = 0
    while i < len(dst):
        best = (0, 0)
        for a in idx.get(dst[i:i + MIN_COPY], ()):
            n = MIN_COPY
            while i + n < len(dst) and a + n < len(src) and src[a + n] == dst[i + n]:
                n += 1
            if n > best[1]:
                best = (a, n)
        if best[1] >= MIN_COPY:
            if lit:
                ops.append(("data", bytes(lit)))
                lit = bytearray()
            ops.append(copy_op(best[0], best[1]))
            i += best[1]
        else:
            lit.append(dst[i])
            i += 1
    if lit:
        ops.append(("data", bytes(lit)))
    return ops


def file_ops(src, dst):
    """元の CONVERSE と日本語版の CONVERSE を、項目ごとに命令にする"""
    so = lib_offsets(src)
    do = lib_offsets(dst)
    assert len(so) == len(do)
    ops = [("data", dst[:4 * len(do)])]                       # 索引（新しい位置の並び）
    for k, (s, d) in enumerate(zip(so, do)):
        if d is None:
            continue
        sit = src[s[0]:s[0] + s[1]]
        dit = dst[d[0]:d[0] + d[1]]
        if sit == dit:
            ops.append(("copy", s[0], s[1]))                    # 変えていない項目
            continue
        assert dit[:4] == b"\0\0\0\0"                          # 変えた項目は圧縮なし
        ops.append(("data", b"\0\0\0\0"))
        if struct.unpack_from("<I", sit, 0)[0] == 0:          # 元も圧縮なし
            base = sit[4:]
            ops += diff_ops(base, dit[4:], lambda a, n, o=s[0]: ("copy", o + 4 + a, n))
        else:
            base, _ = lzw(sit)
            assert len(base) <= 0x8000, k            # 組み立て器は展開先の後ろ半分に辞書を置く
            ops.append(("unpack", s[0], s[1]))
            ops += diff_ops(base, dit[4:], lambda a, n: ("ucopy", a, n))
    # 長い書く・写すを分ける
    out = []
    for op in ops:
        if op[0] == "data":
            for i in range(0, len(op[1]), MAX_LEN):
                out.append(("data", op[1][i:i + MAX_LEN]))
        elif op[0] == "copy":
            for i in range(0, op[2], MAX_LEN):
                out.append(("copy", op[1] + i, min(MAX_LEN, op[2] - i)))
        else:
            out.append(op)
    # 確かめ
    got = bytearray()
    ubuf = b""
    for op in out:
        if op[0] == "copy":
            got += src[op[1]:op[1] + op[2]]
        elif op[0] == "data":
            got += op[1]
        elif op[0] == "unpack":
            ubuf, _ = lzw(src[op[1]:op[1] + op[2]])
        else:
            got += ubuf[op[1]:op[1] + op[2]]
    assert bytes(got) == dst
    return out


def main(game, built, outpath):
    sys.stdout.reconfigure(encoding="utf-8")
    # (元の名前, 作る名前, 組み立て済みのファイルの名前)。本は圧縮なしなので、ファイル全体を元からの写しと書くで表す
    pairs = [("CONVERSE.A", "CONVERSE.JA", "CONVERSE.A"), ("CONVERSE.B", "CONVERSE.JB", "CONVERSE.B"),
             ("BOOK.DAT", "BOOK.JDT", "BOOK.JDT")]
    blob = bytearray(b"U6JPMK01" + struct.pack("<H", len(pairs)))
    for srcname, dstname, builtname in pairs:
        src = open(os.path.join(game, srcname), "rb").read()
        dst = open(os.path.join(built, builtname), "rb").read()
        if srcname.startswith("CONVERSE"):
            ops = file_ops(src, dst)
        else:
            ops = []
            for op in diff_ops(src, dst, lambda a, n: ("copy", a, n)):
                if op[0] == "data":
                    ops += [("data", op[1][i:i + MAX_LEN]) for i in range(0, len(op[1]), MAX_LEN)]
                else:
                    ops.append(op)
        h1, h2 = h12(src)
        blob += srcname.encode().ljust(12, b"\0") + dstname.encode().ljust(12, b"\0")
        blob += struct.pack("<IHHHHH", len(src), h1, h2, len(ops), *h12(dst))
        n = {"copy": 0, "data": 0, "unpack": 0, "ucopy": 0}
        for op in ops:
            if op[0] == "copy":
                blob += struct.pack("<BIH", 0, op[1], op[2])
                n["copy"] += op[2]
            elif op[0] == "data":
                blob += struct.pack("<BH", 1, len(op[1])) + op[1]
                n["data"] += len(op[1])
            elif op[0] == "unpack":
                blob += struct.pack("<BIH", 2, op[1], op[2])
                n["unpack"] += 1
            else:
                blob += struct.pack("<BHH", 3, op[1], op[2])
                n["ucopy"] += op[2]
        print(f"{dstname:12s} 元 {len(src):6d} → {len(dst):6d}  写す {n['copy']:6d}  展開 {n['unpack']:3d} 項目、"
              f"展開から写す {n['ucopy']:6d}  書く {n['data']:6d}  命令 {len(ops)}")
    open(outpath, "wb").write(blob)
    print(f"書き出し: {outpath} {len(blob)} バイト")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
