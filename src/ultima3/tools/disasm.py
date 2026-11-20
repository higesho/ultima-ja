# .COM / .BIN を逆アセンブルする（調査用）
# 使い方: python dis.py <ファイル> <開始(16進, 0x100 基準のオフセット)> <バイト数> [基準(16進, 既定 100)]
import sys
import capstone

sys.stdout.reconfigure(encoding="utf-8")
d = open(sys.argv[1], "rb").read()
base = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x100
start = int(sys.argv[2], 16)
n = int(sys.argv[3])
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
for ins in md.disasm(d[start - base:start - base + n], start):
    print(f"{ins.address:05x}: {ins.bytes.hex():16s} {ins.mnemonic} {ins.op_str}")
