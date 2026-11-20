# SE の絵（U6 の形の絵）を読む・書く道具
#   束（TITLE.LZC などの1項目）: 先頭 4 バイト = 大きさ、続いて 4 バイトずつ各絵の位置（最初の絵の位置 - 4 が表の長さ）
#   絵: +0 右の幅、+2 hotx（左の幅）、+4 hoty（上の高さ）、+6 下の高さ（幅 = 右 + hotx + 1、高さ = hoty + 下 + 1）。
#       続いて「点の数 n（2バイト）、x（符号つき）、y（符号つき）」の並び、n = 0 で終わり。
#       n の最下位ビットが 0 なら n/2 点をそのまま、1 なら n/2 点を小分けに: 1 バイト m の最下位ビットが 1 なら m/2 点を同じ色、0 なら m/2 点をそのまま
#   使い方: python seshape.py <LZC> <出力フォルダ>    各絵を PNG に（パレットは SEPAL の先頭）
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sefmt import lzc_items  # noqa: E402


def sub_items(d):
    """束の中の各絵のバイト列。束でなければ None"""
    if len(d) < 8:
        return None
    size, first = struct.unpack_from("<2I", d)
    if size != len(d) or first < 8 or first % 4 or first > len(d):
        return None
    offs = [struct.unpack_from("<I", d, 4 + 4 * i)[0] for i in range(first // 4 - 1)]
    if offs != sorted(offs) or offs[-1] > len(d):
        return None
    ends = offs[1:] + [len(d)]
    return [d[a:b] for a, b in zip(offs, ends)]


def decode(s):
    """絵 → (幅, 高さ, hotx, hoty, 点の辞書 {(x, y): 色})"""
    rw, hx, hy, bh = struct.unpack_from("<4H", s)
    w, h = hx + rw + 1, hy + bh + 1
    px = {}
    p = 8
    while True:
        n, = struct.unpack_from("<H", s, p)
        if n == 0:
            break
        x, y = struct.unpack_from("<2h", s, p + 2)
        p += 6
        X, Y = hx + x, hy + y
        if not n & 1:
            for i in range(n >> 1):
                px[(X + i, Y)] = s[p + i]
            p += n >> 1
        else:
            j = 0
            while j < n >> 1:
                m = s[p]
                p += 1
                if m & 1:
                    for i in range(m >> 1):
                        px[(X + j + i, Y)] = s[p]
                    p += 1
                else:
                    for i in range(m >> 1):
                        px[(X + j + i, Y)] = s[p + i]
                    p += m >> 1
                j += m >> 1
    return w, h, hx, hy, px


def encode(w, h, hx, hy, px):
    """点の辞書 → 絵（行ごとに、つながった点を1つの並びにする。同じ色が 4 点以上続けば小分けで縮める）"""
    out = bytearray(struct.pack("<4H", w - hx - 1, hx, hy, h - hy - 1))
    for y in range(h):
        xs = sorted(x for (x, yy) in px if yy == y)
        runs = []
        for x in xs:
            if runs and runs[-1][1] == x:
                runs[-1][1] = x + 1
            else:
                runs.append([x, x + 1])
        for a, b in runs:
            while a < b:
                n = min(b - a, 0x3FFF)
                row = [px[(a + i, y)] for i in range(n)]
                packed = bytearray()
                i = 0
                lit = []

                def flush():
                    while lit:
                        k = min(len(lit), 127)
                        packed.append(k << 1)
                        packed.extend(lit[:k])
                        del lit[:k]
                while i < n:
                    r = 1
                    while i + r < n and r < 127 and row[i + r] == row[i]:
                        r += 1
                    if r >= 3:
                        flush()
                        packed += bytes([r << 1 | 1, row[i]])
                    else:
                        lit.extend(row[i:i + r])
                    i += r
                flush()
                if len(packed) < n:
                    out += struct.pack("<H2h", n << 1 | 1, a - hx, y - hy) + packed
                else:
                    out += struct.pack("<H2h", n << 1, a - hx, y - hy) + bytes(row)
                a += n
    out += b"\0\0"
    return bytes(out)


def pack_items(items):
    head = 4 + 4 * len(items)
    offs, body = [], bytearray()
    for s in items:
        offs.append(head + len(body))
        body += s
    return struct.pack("<I", head + len(body)) + b"".join(struct.pack("<I", o) for o in offs) + bytes(body)


def palette(path):
    p = open(path, "rb").read()[:768]
    return [min(255, c * 4 + c // 16) for c in p]


def to_png(w, h, px, pal, path):
    from PIL import Image
    im = Image.new("P", (w, h), 0)
    im.putpalette(pal)
    for (x, y), c in px.items():
        if 0 <= x < w and 0 <= y < h:
            im.putpixel((x, y), c)
    im.save(path)


if __name__ == "__main__":
    lzc, outdir = sys.argv[1], sys.argv[2]
    pal = palette(os.path.join(os.path.dirname(lzc), "SEPAL"))
    os.makedirs(outdir, exist_ok=True)
    for i, (_, d) in enumerate(lzc_items(open(lzc, "rb").read())):
        subs = sub_items(d)
        if subs is None:
            print(i, "束ではない", len(d))
            continue
        for j, s in enumerate(subs):
            try:
                w, h, hx, hy, px = decode(s)
            except Exception as e:  # noqa: BLE001
                print(i, j, "読めない", e)
                continue
            to_png(w, h, px, pal, os.path.join(outdir, f"{i:02d}_{j:02d}.png"))
            if encode(w, h, hx, hy, px) != s:
                print(i, j, f"{w}x{h} 書き戻しが元と違う（中身は同じ）")
            else:
                print(i, j, f"{w}x{h}")
