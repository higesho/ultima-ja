"""WDOSX 0.97 の圧縮（ビット列 LZ）を展開する。"""
import struct, sys

def unpack(src, pos, outlen=None, first_literal=True):
    out = bytearray()
    st = {'dl': 0x80, 'pos': pos}
    def bit():
        dl = st['dl'] << 1
        if dl & 0xff == 0:
            b = src[st['pos']]; st['pos'] += 1
            dl = (b << 1) | 1
        st['dl'] = dl & 0xff
        return (dl >> 8) & 1
    def gamma(v):
        while True:
            v = v * 2 + bit()
            if not bit():
                return v
    out.append(src[st['pos']]); st['pos'] += 1
    after_lit = True
    bp = 0
    while outlen is None or len(out) < outlen:
        if st['pos'] >= len(src):
            break
        if not bit():
            out.append(src[st['pos']]); st['pos'] += 1
            after_lit = True
            continue
        cx = gamma(1)
        ax = gamma(1)
        ax -= 2 + (1 if after_lit else 0)
        after_lit = False
        if ax < 0:
            off = bp
        else:
            ax = ((ax << 6) & 0xffff)
            for _ in range(6):
                ax = (ax & ~0x3f) | (ax & 0x3f)
            # 6 ビット読む
            v = (ax >> 6)
            v6 = 0
            for _ in range(6):
                v6 = v6 * 2 + bit()
            ax = (((v << 6) | v6) & 0xffff) + 1
            if ax >= 0x781:
                cx += 1
            bp = ax
            off = ax
        for _ in range(cx):
            out.append(out[-off])
    return bytes(out), st['pos']


class BitWriter:
    """展開側の読み方（8 ビット単位のタグ列がバイト列に挟まる）に合わせて書く。"""
    def __init__(self):
        self.out = bytearray(); self.tagpos = None; self.nbits = 8
    def bit(self, b):
        if self.nbits == 8:
            self.tagpos = len(self.out); self.out.append(0); self.nbits = 0
        if b:
            self.out[self.tagpos] |= 0x80 >> self.nbits
        self.nbits += 1
    def byte(self, b):
        self.out.append(b)
    def gamma(self, v):
        assert v >= 2
        bits = bin(v)[3:]
        for i, ch in enumerate(bits):
            self.bit(int(ch))
            self.bit(1 if i < len(bits) - 1 else 0)


def pack_block(data):
    """1 ブロックを圧縮する（貪欲法）。"""
    w = BitWriter()
    n = len(data)
    w.byte(data[0])
    after_lit = True
    heads = {}
    def add(i):
        if i + 3 <= n:
            heads.setdefault(data[i:i + 3], []).append(i)
    add(0)
    i = 1
    while i < n:
        best_len, best_off = 0, 0
        cands = heads.get(data[i:i + 3], [])
        for j in reversed(cands[-64:]):
            off = i - j
            L = 0
            while i + L < n and data[j + L] == data[i + L]:
                L += 1
            need = 3 if off >= 0x781 else 2
            if L >= need and L > best_len:
                best_len, best_off = L, off
        if best_len >= 3 or (best_len == 2 and best_off < 0x781):
            off, L = best_off, best_len
            w.bit(1)
            w.gamma(L - 1 if off >= 0x781 else L)
            hi = (off - 1) >> 6
            w.gamma(hi + 2 + (1 if after_lit else 0))
            lo = (off - 1) & 0x3f
            for k in range(5, -1, -1):
                w.bit((lo >> k) & 1)
            after_lit = False
            for k in range(L):
                add(i + k)
            i += L
        else:
            w.bit(0); w.byte(data[i]); after_lit = True
            add(i); i += 1
    return bytes(w.out)


WFSE_AT = 0x2a21

def unpack_exe(exe):
    """AK.EXE から本体 COFF を取り出す。"""
    import struct
    assert exe[WFSE_AT:WFSE_AT + 4] == b'WFSE'
    total, usize = struct.unpack_from('<II', exe, WFSE_AT + 4)
    nblk = (usize + 0xfff) // 0x1000
    tab = [struct.unpack_from('<I', exe, WFSE_AT + 0x20 + 4 * i)[0] for i in range(nblk)]
    base = WFSE_AT + 0x20 + 4 * nblk
    ends = tab[1:] + [total - 0x20 - 4 * nblk]
    out = bytearray()
    for i in range(nblk):
        n = min(0x1000, usize - len(out))
        if ends[i] - tab[i] == n:          # 無圧縮のブロック
            out += exe[base + tab[i]:base + ends[i]]
            continue
        o, p = unpack(exe, base + tab[i], n)
        out += o
    return bytes(out)


def pack_exe(exe, coff):
    """AK.EXE の WFSE 部分を、新しい COFF で作り直す。"""
    import struct
    head = bytearray(exe[:WFSE_AT + 0x20])
    nblk = (len(coff) + 0xfff) // 0x1000
    blocks = []
    for i in range(nblk):
        raw = coff[i * 0x1000:(i + 1) * 0x1000]
        b = pack_block(raw)
        blocks.append(b if len(b) < len(raw) else raw)   # 縮まないブロックは無圧縮（WDOSX はそのまま写す）
    tab = bytearray(); pos = 0
    for b in blocks:
        tab += struct.pack('<I', pos); pos += len(b)
    body = tab + b''.join(blocks)
    struct.pack_into('<II', head, WFSE_AT + 4, 0x20 + len(body), len(coff))
    return bytes(head) + bytes(body)
