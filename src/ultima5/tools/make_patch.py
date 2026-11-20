# 日本語版のファイル（*.TLJ / *.DAJ）を、元のファイルからの「写す」と「訳を書く」の並びにした
# パッチ U5JP.DAT を作る。配布物に原作のデータを入れないため（遊ぶ人の DOSBox で U5JPMK.COM が組み立てる）
# 使い方: python make_patch.py <ゲームのフォルダ（組み立て済みの TLJ/DAJ がある）> <出力 U5JP.DAT>
#
# U5JP.DAT の形（数はすべて 16 ビット、リトルエンディアン）
#   "U5JPDAT1"、ファイルの数
#   ファイルごと: 元の名前（12 バイト、0 埋め）、作る名前（12 バイト）、元の大きさ、元のハッシュ h1, h2、命令の数
#     命令: 0x00 写す（元の位置、長さ）／ 0x01 書く（長さ、バイト列）
#   ハッシュ: h1 = rol(h1,1) + b、h2 = rol(h2 + b, 3)（どちらも 16 ビット、初めは 0）
import difflib
import glob
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")
MIN_COPY = 4          # これより短い一致は写さずに書く（訳の中の偶然の一致を拾わないため）


def rol16(x, n):
    return ((x << n) | (x >> (16 - n))) & 0xFFFF


def h12(bs):
    h1 = h2 = 0
    for b in bs:
        h1 = (rol16(h1, 1) + b) & 0xFFFF
        h2 = rol16((h2 + b) & 0xFFFF, 3)
    return h1, h2


def ops_for(src, dst):
    sm = difflib.SequenceMatcher(None, src, dst, autojunk=False)
    ops = []
    for a, b, size in sm.get_matching_blocks():
        pass
    pos = 0
    for a, b, size in sm.get_matching_blocks():
        if size < MIN_COPY:
            continue
        if b > pos:
            ops.append(("data", dst[pos:b]))
        ops.append(("copy", a, size))
        pos = b + size
    if pos < len(dst):
        ops.append(("data", dst[pos:]))
    # 確かめ
    out = bytearray()
    for op in ops:
        out += src[op[1]:op[1] + op[2]] if op[0] == "copy" else op[1]
    assert bytes(out) == dst
    return ops


def main(game, outpath):
    pairs = []
    for dst in sorted(glob.glob(os.path.join(game, "*.TLJ")) + glob.glob(os.path.join(game, "*.DAJ"))):
        base = os.path.basename(dst)
        srcname = base[:-1] + ("K" if base.endswith(".TLJ") else "T")
        pairs.append((srcname, base))
    blob = bytearray(b"U5JPDAT1" + struct.pack("<H", len(pairs)))
    total_data = total_copy = 0
    for srcname, dstname in pairs:
        src = open(os.path.join(game, srcname), "rb").read()
        dst = open(os.path.join(game, dstname), "rb").read()
        ops = ops_for(src, dst)
        h1, h2 = h12(src)
        blob += srcname.encode().ljust(12, b"\0") + dstname.encode().ljust(12, b"\0")
        blob += struct.pack("<HHHH", len(src), h1, h2, len(ops))
        for op in ops:
            if op[0] == "copy":
                blob += struct.pack("<BHH", 0, op[1], op[2])
                total_copy += op[2]
            else:
                blob += struct.pack("<BH", 1, len(op[1])) + op[1]
                total_data += len(op[1])
        print(f"{dstname:13s} 元 {len(src):6d} → {len(dst):6d}  写す {sum(o[2] for o in ops if o[0]=='copy'):6d}  "
              f"書く {sum(len(o[1]) for o in ops if o[0]=='data'):6d}  命令 {len(ops)}")
    open(outpath, "wb").write(blob)
    print(f"書き出し: {outpath} {len(blob)} バイト（写す {total_copy}、書く {total_data}）")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
