# ULTIMAII.EXE を逆アセンブルする（調査用）
# 使い方: python dis.py <EXE> <開始(イメージ内の位置, 16進)> <バイト数>
import sys
import struct
import capstone

sys.stdout.reconfigure(encoding="utf-8")
d = open(sys.argv[1], "rb").read()
hdr = struct.unpack_from("<H", d, 8)[0] * 16
img = d[hdr:]
start = int(sys.argv[2], 16)
n = int(sys.argv[3])
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
for ins in md.disasm(img[start:start + n], start):
    print(f"{ins.address:05x}: {ins.bytes.hex():16s} {ins.mnemonic} {ins.op_str}")
