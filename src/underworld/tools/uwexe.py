"""UW.EXE / UW2.EXE（Borland C++、VROOMM オーバーレイ）の読み取りの共通部分。
  python uwexe.py uw1|uw2 info               スタブ（オーバーレイの入口）とセグメント表
  python uwexe.py uw1|uw2 dis SEG:OFF [n]    ルートの逆アセンブル（SEG はイメージ先頭からの段落）
  python uwexe.py uw1|uw2 odis STUB OFF [n]  オーバーレイの逆アセンブル
  python uwexe.py uw1|uw2 str TEXT           文字列の位置（イメージ内の段落:位置の候補）
  python uwexe.py uw1|uw2 ref LIN            その線形番地を即値として使う所（DGROUP の位置）"""
import sys, os, re, struct, capstone
SEGTAB = {'uw1': 0x5c1c0, 'uw2': 0x66750}   # ファイルの中のセグメント表（8 バイトずつ、先頭がセグメント）
HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = {'uw1': ('UW', 'UW.EXE'), 'uw2': ('UW2', 'UW2.EXE')}

class Exe:
    def __init__(self, game):
        d, f = GAMES[game]
        self.game = game
        self.path = os.path.join(HERE, '..', 'orig', d, f)
        self.d = open(self.path, 'rb').read()
        lastpg, pages = struct.unpack_from('<HH', self.d, 2)
        self.hdr = struct.unpack_from('<H', self.d, 8)[0] * 16
        self.end = (pages - 1) * 512 + (lastpg or 512)
        self.img = self.d[self.hdr:self.end]
        self.fbov = self.end
        self.ovdata = self.fbov + 0x10
        self.ss = struct.unpack_from('<H', self.d, 0x0e)[0]
        self.stubs = [p for p in range(0, len(self.img) // 16) if self.img[p * 16:p * 16 + 2] == b'\xcd\x3f'
                      and struct.unpack_from('<I', self.img, p * 16 + 4)[0] < len(self.d)]
        self.relocs = [struct.unpack_from('<HH', self.d, struct.unpack_from('<H', self.d, 0x18)[0] + i * 4)
                       for i in range(struct.unpack_from('<H', self.d, 6)[0])]
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)

    def stub(self, s):
        off, size, rsize, n = struct.unpack_from('<IHHH', self.img, s * 16 + 4)
        return off, size, rsize, n

    def ovcode(self, s):
        off, size, rsize, n = self.stub(s)
        return self.d[self.ovdata + off:self.ovdata + off + size]

    def dis_bytes(self, code, start, n, seg, base=0):
        out = []
        for i in self.md.disasm(code[start - base:start - base + n], start):
            b = code[i.address - base:i.address - base + i.size]
            out.append('%04x:%04x  %-18s %s %s' % (seg, i.address, b.hex(), i.mnemonic, i.op_str))
        return '\n'.join(out)

    def dis(self, seg, off, n=0x60):
        return self.dis_bytes(self.img, seg * 16 + off, n, seg, base=seg * 16) if False else \
            '\n'.join('%04x:%04x  %-18s %s %s' % (seg, i.address, self.img[seg * 16 + i.address:seg * 16 + i.address + i.size].hex(), i.mnemonic, i.op_str)
                      for i in self.md.disasm(self.img[seg * 16 + off:seg * 16 + off + n], off))

    def realseg(self, v):
        """オーバーレイの中の far 呼び出しのセグメント（セグメント表の番号×8）を本当のセグメントに"""
        return struct.unpack_from('<H', self.d, SEGTAB[self.game] + v)[0] if v % 8 == 0 and v < 0x800 else None

    def odis(self, s, off, n=0x60):
        c = self.ovcode(s)
        out = []
        for i in self.md.disasm(c[off:off + n], off):
            t = '%04x:%04x  %-18s %s %s' % (s, i.address, c[i.address:i.address + i.size].hex(), i.mnemonic, i.op_str)
            m = re.match(r'lcall (0x[0-9a-f]+), (0x[0-9a-f]+)', i.mnemonic + ' ' + i.op_str)
            if m and self.realseg(int(m.group(1), 16)) is not None:
                t += '    ; -> %04x:%s' % (self.realseg(int(m.group(1), 16)), m.group(2)[2:])
            out.append(t)
        return '\n'.join(out)

    def callers(self, seg, off):
        """far 呼び出し lcall SEG:OFF の呼び出し元（ルートとオーバーレイ）"""
        out = []
        pat = b'\x9a' + struct.pack('<HH', off, seg)
        i = self.img.find(pat)
        while i >= 0:
            out.append(('root', i)); i = self.img.find(pat, i + 1)
        idx = [v for v in range(0, 0x800, 8) if self.realseg(v) == seg]
        for s in self.stubs:
            c = self.ovcode(s)
            for v in idx:
                p = b'\x9a' + struct.pack('<HH', off, v); i = c.find(p)
                while i >= 0:
                    out.append(('ovl %04x' % s, i)); i = c.find(p, i + 1)
        return out

if __name__ == '__main__':
    e = Exe(sys.argv[1]); cmd = sys.argv[2]
    if cmd == 'info':
        print(f'image {len(e.img):#x}  FBOV {e.fbov:#x}  stubs {len(e.stubs)}  SS {e.ss:#x}')
        segs = sorted(set(s for o, s in e.relocs))
        print('reloc target segs (first 10):', [hex(s) for s in segs[:10]], '... count', len(segs))
        tot = 0
        for s in e.stubs:
            off, size, rsize, n = e.stub(s); tot += size
            print('stub %04x  file %06x  code %04x  reloc %04x  entries %d' % (s, e.ovdata + off, size, rsize, n))
        print('overlay code total', hex(tot))
    elif cmd == 'dis':
        s, o = sys.argv[3].split(':'); print(e.dis(int(s, 16), int(o, 16), int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x60))
    elif cmd == 'odis':
        print(e.odis(int(sys.argv[3], 16), int(sys.argv[4], 16), int(sys.argv[5], 16) if len(sys.argv) > 5 else 0x60))
    elif cmd == 'str':
        t = sys.argv[3].encode(); i = e.img.find(t)
        while i >= 0:
            print(f'image {i:#07x}'); i = e.img.find(t, i + 1)

DG = {'uw1': 0x5aac, 'uw2': 0x65e9}

def code_seg_of(e, lin):
    """ルートのコードで、線形番地を含みそうなセグメント（再配置の先のセグメントのうち、それ以下で最大のもの）"""
    segs = sorted(set(s for o, s in e.relocs))
    best = 0
    for s in segs:
        if s * 16 <= lin: best = s
    return best

def find_imm(e, game, val):
    """値 val を即値に持つ命令（mov r16,imm / push imm / mov [m],imm / cmp）を、ルートとオーバーレイから探す"""
    pat = struct.pack('<H', val)
    hits = []
    dg = DG[game] * 16
    i = e.img.find(pat)
    while 0 <= i < dg:
        for back in (1, 2, 3, 4):
            st = i - back
            if st < 0: continue
            ins = next(e.md.disasm(e.img[st:st + 8], 0), None)
            if ins and ins.size == back + 2 and ('%#x' % val) in ins.op_str:
                seg = code_seg_of(e, st)
                hits.append(('root', '%04x:%04x' % (seg, st - seg * 16), ins.mnemonic + ' ' + ins.op_str)); break
        i = e.img.find(pat, i + 1)
    for s in e.stubs:
        c = e.ovcode(s)
        i = c.find(pat)
        while i >= 0:
            for back in (1, 2, 3, 4):
                st = i - back
                if st < 0: continue
                ins = next(e.md.disasm(c[st:st + 8], st), None)
                if ins and ins.size == back + 2 and ('%#x' % val) in ins.op_str:
                    hits.append(('ovl', '%04x:%04x' % (s, st), ins.mnemonic + ' ' + ins.op_str)); break
            i = c.find(pat, i + 1)
    return hits

if __name__ == '__main__' and sys.argv[2] in ('ref', 'dstr'):
    e = Exe(sys.argv[1]); g = sys.argv[1]
    if sys.argv[2] == 'dstr':      # DGROUP の文字列を探して、その位置を使う所
        t = sys.argv[3].encode(); dg = DG[g] * 16
        i = e.img.find(t, dg)
        while i >= 0:
            off = i - dg
            print(f'DS:{off:04x} {e.img[i:i+30].split(bytes(1))[0]!r}')
            for h in find_imm(e, g, off): print('   ', *h)
            i = e.img.find(t, i + 1)
    else:
        for h in find_imm(e, g, int(sys.argv[3], 16)): print(*h)

def entry(e, seg, off):
    """lcall SEG:OFF がオーバーレイのスタブなら、オーバーレイの中の位置を返す"""
    if seg in e.stubs and e.img[seg * 16 + off:seg * 16 + off + 2] == b'\xcd\x3f':
        return struct.unpack_from('<H', e.img, seg * 16 + off + 2)[0]
    return None

if __name__ == '__main__' and sys.argv[2] == 'call':   # call SEG:OFF [n]: スタブなら中身を、そうでなければルートを逆アセンブル
    e = Exe(sys.argv[1]); s, o = (int(x, 16) for x in sys.argv[3].split(':')); n = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x80
    t = entry(e, s, o)
    print(e.odis(s, t, n) if t is not None else e.dis(s, o, n))
