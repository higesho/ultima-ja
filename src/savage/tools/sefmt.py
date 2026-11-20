"""Savage Empire の LZC 束: 先頭4バイト=全体の大きさ、続いて項目ごとに 3バイトの位置+1バイトの印。
印 1=U6 LZW、2=圧縮なし、0xFF=空(推測)"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from u6fmt import lzw
def lzc_entries(data):
    total = struct.unpack('<I', data[:4])[0]
    ents = []; i = 4; first = None
    while first is None or i < first:
        v = struct.unpack('<I', data[i:i+4])[0]
        off, fl = v & 0xFFFFFF, v >> 24
        if fl != 0xFF and (first is None or off < first): first = off
        ents.append((off, fl)); i += 4
    return total, ents
def lzc_items(data):
    total, ents = lzc_entries(data)
    offs = sorted(set(o for o, f in ents if f != 0xFF)) + [len(data)]
    out = []
    for o, f in ents:
        if f == 0xFF: out.append((f, None)); continue
        nxt = min(x for x in offs if x > o)
        raw = data[o:nxt]
        if f == 1:
            d, sz = lzw(raw); out.append((f, d))
        else:
            out.append((f, raw))
    return out
if __name__ == '__main__':
    for fn in sys.argv[1:]:
        data = open(fn, 'rb').read()
        total, ents = lzc_entries(data)
        items = lzc_items(data)
        print(fn, 'size', len(data), 'hdr', total, 'n', len(ents),
              'flags', {f: sum(1 for x, g in ents if g == f) for f in set(g for x, g in ents)})
        for k, (f, d) in enumerate(items[:6]):
            print('  ', k, f, None if d is None else (len(d), d[:40]))


def lzc_raw(data):
    """[(印, 束の中のバイト列そのまま or None)]（圧縮されたまま）"""
    total, ents = lzc_entries(data)
    offs = sorted(set(o for o, f in ents if f != 0xFF)) + [len(data)]
    out = []
    for o, f in ents:
        if f == 0xFF:
            out.append((f, None))
        else:
            out.append((f, data[o:min(x for x in offs if x > o)]))
    return out


def save_lzc(path, rows):
    """LZC 束を書く。rows: [(印, バイト列 or None)]。印 1 は圧縮済みのバイト列、2 は圧縮なし、0xFF は空"""
    n = len(rows)
    head = bytearray(4 + 4 * n)
    body = bytearray()
    base = len(head)
    for i, (f, b) in enumerate(rows):
        if f == 0xFF or b is None:
            # 元の束では空の項目も直前の位置を指している。位置は 0 でよいか未確認なので、次の項目の位置を入れておく
            struct.pack_into('<I', head, 4 + 4 * i, ((base + len(body)) & 0xFFFFFF) | 0xFF000000)
            continue
        struct.pack_into('<I', head, 4 + 4 * i, ((base + len(body)) & 0xFFFFFF) | (f << 24))
        body += b
    struct.pack_into('<I', head, 0, len(head) + len(body))
    open(path, 'wb').write(bytes(head + body))
