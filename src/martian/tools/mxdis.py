"""MARTIAN.EXE（導入・キャラクター作成・エンディング）の逆アセンブル補助。
  python mxdis.py dis 位置16進 [バイト数16進]      ロードイメージの位置から逆アセンブル（SEG:OFF でもよい）
  python mxdis.py far SEG:OFF                     far call の呼び出し元
  python mxdis.py find 16進の並び                   バイトの並びを探す
  python mxdis.py imm 値16進                        即値として使う所（mov/push/cmp）
"""
import sys, os, struct, re
import capstone
HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, '..', '..', 'MARTIAN', 'MARTIAN.EXE')
d = open(EXE, 'rb').read()
HDR = struct.unpack('<H', d[8:10])[0] * 16
img = d[HDR:]
nrel, relo = struct.unpack('<H', d[6:8])[0], struct.unpack('<H', d[0x18:0x1a])[0]
RELOCS = [struct.unpack('<HH', d[relo + 4 * i:relo + 4 * i + 4]) for i in range(nrel)]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)


def lin(a):
    if ':' in a:
        s, o = a.split(':')
        return int(s, 16) * 16 + int(o, 16)
    return int(a, 16)


def dis(start, n=0x80, seg=None):
    if seg is None:
        seg = start >> 4
    off = start - seg * 16
    for ins in md.disasm(img[start:start + n], off):
        print(f"{seg:04X}:{ins.address:04X}  {ins.bytes.hex():<16} {ins.mnemonic} {ins.op_str}")


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dis':
        a = sys.argv[2]
        n = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x80
        if ':' in a:
            s = int(a.split(':')[0], 16)
            dis(lin(a), n, s)
        else:
            dis(lin(a), n)
    elif cmd == 'far':
        s, o = [int(x, 16) for x in sys.argv[2].split(':')]
        pat = b'\x9a' + struct.pack('<HH', o, s)
        for m in re.finditer(re.escape(pat), img):
            print(hex(m.start()))
    elif cmd == 'find':
        pat = bytes.fromhex(sys.argv[2])
        for m in re.finditer(re.escape(pat), img):
            print(hex(m.start()))
    elif cmd == 'imm':
        v = int(sys.argv[2], 16)
        b = struct.pack('<H', v)
        for m in re.finditer(re.escape(b), img):
            print(hex(m.start()), img[max(0, m.start() - 3):m.start() + 2].hex())
