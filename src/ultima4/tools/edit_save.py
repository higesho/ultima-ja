# 試験用のセーブ（PARTY.SAV）を書き換える（試験用の写しにだけ使う）
# 使い方: python edit_save.py <元の PARTY.SAV> <出力> [項目=値 ...]
#   項目: x, y（世界地図の位置）、members（人数）、keys、gems、torches、gold、food（表示の100倍）、
#         runes、stones（8ビット、0xFF で全部）、items（16ビット）、lbintro（0 で王の最初の言葉が出る）、transport
# 位置などは xu4 の SaveGame の並びに合わせた（0x140 から食料、0x1D4 から x / y …）
import struct
import sys

FIELDS = {"food": (0x140, "<I"), "gold": (0x144, "<H"), "torches": (0x156, "<H"), "gems": (0x158, "<H"),
          "keys": (0x15A, "<H"), "sextants": (0x15C, "<H"), "items": (0x1D2, "<H"), "x": (0x1D4, "<B"),
          "y": (0x1D5, "<B"), "stones": (0x1D6, "<B"), "runes": (0x1D7, "<B"), "members": (0x1D8, "<H"),
          "transport": (0x1DA, "<H"), "lbintro": (0x1E4, "<H"),
          "lastmed": (0x1EA, "<H"), "moves": (0x04, "<I")}

src, dst = sys.argv[1], sys.argv[2]
b = bytearray(open(src, "rb").read())
for arg in sys.argv[3:]:
    k, v = arg.split("=")
    off, fmt = FIELDS[k]
    struct.pack_into(fmt, b, off, int(v, 0))
open(dst, "wb").write(b)
print(", ".join(f"{k}={struct.unpack_from(f, b, o)[0]}" for k, (o, f) in FIELDS.items()))
