# -*- coding: utf-8 -*-
"""ウルティマVIII の shape（絵・フォント）と Flex を読み書きする道具。

shape の形:
  見出し 6 バイト: 不明 4 バイト（フォントでは最大の幅・高さ）、フレーム数 2
  フレーム表 6 バイト×数: 位置 3、不明 1、長さ 2
  フレーム: 不明 8、圧縮 1、空き 1、幅 2、高さ 2、xoff 2、yoff 2、
            行の位置 2×高さ（その値が置かれた場所からの距離）、RLE
  RLE（圧縮なし）: 行ごとに「飛ばす数, 描く数, 色…」を繰り返し、x が幅に達したら次の行
"""
import struct


class Frame:
    def __init__(self, w, h, xoff, yoff, pixels, unk=b'\x00' * 8):
        self.w, self.h, self.xoff, self.yoff = w, h, xoff, yoff
        self.pixels = pixels          # 行ごとのリスト。None は透明
        self.unk = unk


def read_flex(data):
    n = struct.unpack_from('<I', data, 0x54)[0]
    out = []
    for i in range(n):
        o, sz = struct.unpack_from('<II', data, 0x80 + i * 8)
        out.append(data[o:o + sz] if sz else b'')
    return out


def write_flex(head, entries):
    """head は元のファイルの先頭 0x80 バイト。項目数は entries に合わせて書き直す。"""
    head = bytearray(head[:0x80])
    n = len(entries)
    struct.pack_into('<I', head, 0x54, n)
    table = bytearray(n * 8)
    body = bytearray()
    pos = 0x80 + n * 8
    for i, e in enumerate(entries):
        if e:
            struct.pack_into('<II', table, i * 8, pos, len(e))
            body += e
            pos += len(e)
    return bytes(head) + bytes(table) + bytes(body)


def read_shape(data):
    hdr = data[:4]
    n = struct.unpack_from('<H', data, 4)[0]
    frames = []
    for i in range(n):
        b = data[6 + i * 6:12 + i * 6]
        off = b[0] | (b[1] << 8) | (b[2] << 16)
        ln = struct.unpack_from('<H', b, 4)[0]
        f = data[off:off + ln]
        unk = f[:8]
        comp = f[8]
        w, h, xo, yo = struct.unpack_from('<hhhh', f, 10)
        rows = []
        for y in range(h):
            lo = struct.unpack_from('<H', f, 18 + y * 2)[0]
            p = 18 + y * 2 + lo
            row = [None] * w
            x = 0
            while True:
                x += f[p]; p += 1
                if x >= w:
                    break
                dl = f[p]; p += 1
                t = 0
                if comp:
                    t = dl & 1
                    dl >>= 1
                for k in range(dl):
                    row[x + k] = f[p]
                    if not t:
                        p += 1
                x += dl
                if t:
                    p += 1
                if x >= w:
                    break
            rows.append(row)
        frames.append(Frame(w, h, xo, yo, rows, unk))
    return hdr, frames


def encode_frame(fr):
    """圧縮なしで1フレームを作る。"""
    rle_rows = []
    for row in fr.pixels:
        r = bytearray()
        x = 0
        w = fr.w
        while x < w:
            s = x
            while x < w and row[x] is None:
                x += 1
            skip = x - s
            if x >= w:
                # 残りは透明。x を幅以上にして行を終える
                r.append(min(skip, 255) if skip else 0)
                if skip == 0:
                    pass
                break
            # 飛ばす数は 255 まで
            while skip > 255:
                r += bytes([255, 0])
                skip -= 255
            r.append(skip)
            s = x
            while x < w and row[x] is not None and x - s < 255:
                x += 1
            r.append(x - s)
            r += bytes(row[s:x])
        rle_rows.append(bytes(r))
    h = fr.h
    head = bytearray(fr.unk) + bytes([0, 0]) + struct.pack('<hhhh', fr.w, h, fr.xoff, fr.yoff)
    offs = bytearray()
    pos = 0
    for y in range(h):
        offs += struct.pack('<H', pos + (h - y) * 2)
        pos += len(rle_rows[y])
    return bytes(head) + bytes(offs) + b''.join(rle_rows)


def write_shape(hdr4, frames):
    n = len(frames)
    datas = [encode_frame(f) for f in frames]
    out = bytearray(hdr4[:4]) + struct.pack('<H', n)
    table = bytearray(n * 6)
    pos = 6 + n * 6
    body = bytearray()
    for i, d in enumerate(datas):
        table[i * 6:i * 6 + 3] = bytes([pos & 0xFF, (pos >> 8) & 0xFF, (pos >> 16) & 0xFF])
        struct.pack_into('<H', table, i * 6 + 4, len(d))
        body += d
        pos += len(d)
    assert pos < (1 << 24)
    return bytes(out + table + body)
