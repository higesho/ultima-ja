"""Martian Dreams GAME.EXE（ロードイメージ build/GAME_img.bin）の逆アセンブル補助。
  python mddis.py dis SEG:OFF [バイト数16進]       逆アセンブル（SEG は段落、イメージ先頭が 0）
  python mddis.py imm 値16進 [値16進...]           mov/push/cmp の即値として値を使う所を探す（ルートのコード）
  python mddis.py far SEG:OFF                      far call の呼び出し元
  python mddis.py near SEG:OFF                     同じセグメント内の near call の呼び出し元
"""
import sys, os, struct, re
import capstone
HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, '..', 'build', 'GAME_img.bin')
DG = 0x2fab
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
img = open(IMG, 'rb').read()
CODE_END = 0x2bb4 * 16          # 0x2bb4 からはデータ（far data、オーバーレイの入口、DGROUP）

def segtab():
    d = open(os.path.join(HERE, '..', '..', 'MARTIAN', 'GAME.EXE'), 'rb').read()
    out = []
    for i in range(0x66):
        out.append(struct.unpack('<4H', d[0x325c0 + i * 8:0x325c0 + i * 8 + 8]))
    return out
SEGS = segtab()
CODESEGS = sorted(set(s for s, mx, fl, mn in SEGS if fl in (1, 3)))

def seg_of(lin):
    best = None
    for s, mx, fl, mn in SEGS:
        if fl == 1 and s * 16 <= lin < s * 16 + mx + 1:
            best = s
    return best

def dis(seg, off, n=0x80):
    base = seg * 16
    out = []
    for i in md.disasm(img[base + off:base + off + n], off):
        b = img[base + i.address:base + i.address + i.size]
        extra = ''
        if b[0] == 0x9a:
            o = int.from_bytes(b[1:3], 'little'); s = int.from_bytes(b[3:5], 'little')
            extra = '  ; far %04x:%04x' % (s, o)
        out.append('%05x %04x:%04x  %-20s %s %s%s' % (base + i.address, seg, i.address, b.hex(), i.mnemonic, i.op_str, extra))
    return '\n'.join(out)

def far_callers(seg, off):
    pat = b'\x9a' + struct.pack('<HH', off, seg)
    return [m.start() for m in re.finditer(re.escape(pat), img[:CODE_END])]

def near_callers(seg, off):
    base = seg * 16; hs = []
    for i in range(base, min(CODE_END, base + 0x10000) - 3):
        if img[i] == 0xe8 and (i + 3 - base + struct.unpack('<h', img[i + 1:i + 3])[0]) & 0xffff == off:
            hs.append(i)
    return hs

def func_start(lin):
    p = lin
    while p > 0 and img[p:p + 3] != b'\x55\x8b\xec': p -= 1
    return p

def fmt(lin):
    s = seg_of(lin)
    return '%05x (%04x:%04x) func %05x' % (lin, s or 0, lin - (s or 0) * 16, func_start(lin))

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dis':
        s, o = (int(x, 16) for x in sys.argv[2].split(':'))
        print(dis(s, o, int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x80))
    elif cmd == 'imm':
        for v in sys.argv[2:]:
            v = int(v, 16); w = struct.pack('<H', v)
            for pre in (b'\xb8', b'\xbb', b'\xb9', b'\xba', b'\xbe', b'\xbf', b'\x68', b'\x3d'):
                for m in re.finditer(re.escape(pre + w), img[:CODE_END]):
                    print('%04x' % v, pre.hex(), fmt(m.start()))
    elif cmd == 'far':
        s, o = (int(x, 16) for x in sys.argv[2].split(':'))
        for h in far_callers(s, o): print(fmt(h))
    elif cmd == 'near':
        s, o = (int(x, 16) for x in sys.argv[2].split(':'))
        for h in near_callers(s, o): print(fmt(h))
