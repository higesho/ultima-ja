# U7 のシェイプ（絵）を読み書きする
# シェイプ: 全体の長さ(4) 各フレームの位置(4×n) フレーム…
# フレーム: xright(2) xleft(2) yabove(2) ybelow(2) RLE のスキャンライン（0 で終わり）
#   スキャンライン: 長さ(2、下位1ビットが RLE の印) x(2) y(2)（原点からの相対位置） データ
import struct

def read_shape(data):
    """[(xleft, yabove, w, h, {(x,y): 色})]（x, y は左上を 0 とする）"""
    first = struct.unpack_from('<I', data, 4)[0]
    n = (first - 4) // 4
    frames = []
    for f in range(n):
        o = struct.unpack_from('<I', data, 4 + 4 * f)[0]
        xr, xl, ya, yb = struct.unpack_from('<hhhh', data, o)
        p = o + 8; pix = {}
        while True:
            bl = struct.unpack_from('<H', data, p)[0]; p += 2
            if bl == 0:
                break
            x, y = struct.unpack_from('<hh', data, p); p += 4
            cnt = bl >> 1
            if bl & 1 == 0:
                for i in range(cnt):
                    pix[(x + i + xl, y + ya)] = data[p + i]
                p += cnt
            else:
                while cnt > 0:
                    b = data[p]; p += 1; c = b >> 1
                    if b & 1:
                        v = data[p]; p += 1
                        for i in range(c):
                            pix[(x + i + xl, y + ya)] = v
                    else:
                        for i in range(c):
                            pix[(x + i + xl, y + ya)] = data[p + i]
                        p += c
                    x += c; cnt -= c
        frames.append((xl, ya, xl + xr + 1, ya + yb + 1, pix))
    return frames

def encode_frame(xl, ya, w, h, pix):
    """pix: {(x,y): 色}（左上を 0 とする）。RLE は使わず、そのままの並びで書く"""
    out = bytearray(struct.pack('<hhhh', w - xl - 1, xl, ya, h - ya - 1))
    for y in range(h):
        x = 0
        while x < w:
            if (x, y) not in pix:
                x += 1; continue
            run = []
            while x + len(run) < w and (x + len(run), y) in pix and len(run) < 0x7FFF:
                run.append(pix[(x + len(run), y)])
            out += struct.pack('<Hhh', len(run) << 1, x - xl, y - ya) + bytes(run)
            x += len(run)
    out += b'\0\0'
    return bytes(out)

def write_shape(frames):
    """frames: [(xl, ya, w, h, pix)]"""
    blobs = [encode_frame(*f) for f in frames]
    head = 4 + 4 * len(blobs)
    offs = []; pos = head
    for b in blobs:
        offs.append(pos); pos += len(b)
    return struct.pack('<I', pos) + b''.join(struct.pack('<I', o) for o in offs) + b''.join(blobs)
