"""GAME.EXE の Borland オーバーレイ (FBOV) を取り出す。
  python mdovl.py list                 一覧
  python mdovl.py dis STUB OFF [n]     オーバーレイ STUB（段落）を 0 番地から逆アセンブル
各スタブ: +4 位置(FBOV データ先頭 0x422c0 から), +8 コードの大きさ, +0xA 再配置の大きさ, +0xC 入口の数"""
import sys, os, struct, capstone
HERE = os.path.dirname(os.path.abspath(__file__))
EXE = open(os.path.join(HERE, '..', '..', 'MARTIAN', 'GAME.EXE'), 'rb').read()
FBOV = 0x422b0
DATA = FBOV + 0x10
IMG = EXE[0x3400:FBOV]
STUBS = [0x2f52, 0x2f55, 0x2f58, 0x2f5b, 0x2f5f, 0x2f63, 0x2f68, 0x2f6e, 0x2f72, 0x2f75, 0x2f7c, 0x2f80,
         0x2f83, 0x2f88, 0x2f8d, 0x2f98, 0x2fa1]

def stub(s):
    b = IMG[s * 16:s * 16 + 0x20]
    off, size, rsize, n = struct.unpack_from('<IHHH', b, 4)
    return off, size, rsize, n

def code(s):
    off, size, rsize, n = stub(s)
    return EXE[DATA + off:DATA + off + size]

def find_file_off(fo):
    for s in STUBS:
        off, size, rsize, n = stub(s)
        if DATA + off <= fo < DATA + off + size:
            return s, fo - DATA - off
    return None

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
def dis(s, start, n=0x80):
    c = code(s)
    out = []
    for i in md.disasm(c[start:start + n], start):
        b = c[i.address:i.address + i.size]
        out.append('%04x:%04x  %-20s %s %s' % (s, i.address, b.hex(), i.mnemonic, i.op_str))
    return '\n'.join(out)

if __name__ == '__main__':
    if sys.argv[1] == 'list':
        for s in STUBS:
            off, size, rsize, n = stub(s)
            print('%04x file %06x size %04x reloc %04x entries %d' % (s, DATA + off, size, rsize, n))
    elif sys.argv[1] == 'dis':
        print(dis(int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x80))
    elif sys.argv[1] == 'where':
        print(find_file_off(int(sys.argv[2], 16)))
