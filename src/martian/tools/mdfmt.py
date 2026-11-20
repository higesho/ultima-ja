"""Martian Dreams の .LZC 束: 先頭4バイト=ファイル全体の大きさ、続いて 4バイトの項目表
(下位24ビット=位置, 上位8ビット=印)。印 0x20 = LZW(先頭4バイトが展開後の大きさ)。"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u6fmt import lzw

def entries(data):
    total = struct.unpack('<I', data[:4])[0]
    ents = []; i = 4; first = None
    while first is None or i < first:
        v = struct.unpack('<I', data[i:i+4])[0]
        off, flag = v & 0xFFFFFF, v >> 24
        ents.append((off, flag))
        if off and (first is None or off < first): first = off
        i += 4
    offs = sorted(set(o for o, f in ents if o)) + [len(data)]
    out = []
    for off, flag in ents:
        if not off: out.append((off, flag, None)); continue
        nxt = min(x for x in offs if x > off)
        out.append((off, flag, data[off:nxt]))
    return total, out

def item(off, flag, raw):
    if raw is None: return None
    if flag == 0x20:
        o, s = lzw(raw); return o
    return raw

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    t, es = entries(d)
    print('total', t, len(d), 'n', len(es))
    from collections import Counter
    print(Counter(f for _, f, _ in es))
    for k, (o, f, r) in enumerate(es[:int(sys.argv[2]) if len(sys.argv) > 2 else 8]):
        x = item(o, f, r)
        print(k, hex(o), hex(f), None if r is None else len(r), None if x is None else len(x), None if x is None else x[:60])


def pack(items):
    """[(印, 生のバイト列 or None)] から束を作る。空き（None）の項目は次の項目と同じ位置を指す（元の束と同じ）"""
    n = len(items)
    pos = 4 + 4 * n
    offs, body = [], bytearray()
    for flag, raw in items:
        if raw is None:
            offs.append(None)
        else:
            offs.append(pos + len(body))
            body += raw
    end = pos + len(body)
    for i in range(n - 1, -1, -1):
        if offs[i] is None:
            offs[i] = offs[i + 1] if i + 1 < n else end
    head = struct.pack('<I', end) + b''.join(struct.pack('<I', o | (f << 24)) for o, (f, _) in zip(offs, items))
    return head + bytes(body)


def raw_items(data):
    """[(印, 生のバイト列 or None)]（pack に戻すと元と同じになる形）"""
    t, es = entries(data)
    return [(f, None if f == 0xFF else r) for o, f, r in es]
