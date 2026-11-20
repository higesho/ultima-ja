"""Allegro 2.2 のデータファイル（slh! = LZSS 圧縮）を読み書きする。"""
import struct

def lzss_unpack(src):
    N, F, TH = 4096, 18, 2
    buf = bytearray(N)
    r = N - F
    out = bytearray(); i = 0; flags = 0
    while i < len(src):
        flags >>= 1
        if not (flags & 0x100):
            flags = src[i] | 0xff00; i += 1
            if i >= len(src): break
        if flags & 1:
            c = src[i]; i += 1
            out.append(c); buf[r] = c; r = (r + 1) & (N - 1)
        else:
            if i + 1 >= len(src): break
            a, b = src[i], src[i + 1]; i += 2
            a |= (b & 0xf0) << 4; b = (b & 0x0f) + TH
            for k in range(b + 1):
                c = buf[(a + k) & (N - 1)]
                out.append(c); buf[r] = c; r = (r + 1) & (N - 1)
    return bytes(out)

def read_dat(path):
    d = open(path, 'rb').read()
    if d[:4] == b'slh!':
        d = lzss_unpack(d[4:])
    elif d[:4] == b'slh.':
        d = d[4:]
    return d
