# U7 の Flex 形式（TEXT.FLX、FONTS.VGA など）を読み書きする
import struct

def read_flex(path):
    """(先頭 0x80 バイト, [中身 or None, ...]) を返す"""
    d = open(path, 'rb').read()
    head = d[:0x80]
    cnt = struct.unpack_from('<I', d, 0x54)[0]
    ents = []
    for i in range(cnt):
        off, size = struct.unpack_from('<II', d, 0x80 + i * 8)
        ents.append(d[off:off + size] if size else None)
    return head, ents

def write_flex(path, head, ents):
    head = bytearray(head[:0x80].ljust(0x80, b'\0'))
    struct.pack_into('<I', head, 0x54, len(ents))
    table = bytearray()
    body = bytearray()
    pos = 0x80 + 8 * len(ents)
    for e in ents:
        if e:
            table += struct.pack('<II', pos + len(body), len(e))
            body += e
        else:
            table += struct.pack('<II', 0, 0)
    open(path, 'wb').write(bytes(head) + bytes(table) + bytes(body))
