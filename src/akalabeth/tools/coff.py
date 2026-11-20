import struct
class Coff:
    def __init__(s, data):
        s.d = bytearray(data)
        s.magic, s.nsec, _, s.symptr, s.nsym, s.opt, _ = struct.unpack_from('<HHIIIHH', data, 0)
        s.secs = []
        for i in range(s.nsec):
            h = data[20 + s.opt + 40*i: 20 + s.opt + 40*i + 40]
            name = h[:8].rstrip(b'\0').decode()
            pa, va, size, ptr = struct.unpack_from('<IIII', h, 8)
            s.secs.append((name, va, size, ptr, 20 + s.opt + 40*i))
        strtab_off = s.symptr + 18 * s.nsym
        s.syms = []
        i = 0
        while i < s.nsym:
            e = data[s.symptr + 18*i: s.symptr + 18*i + 18]
            if e[:4] == b'\0\0\0\0':
                o = struct.unpack_from('<I', e, 4)[0]
                j = data.index(b'\0', strtab_off + o)
                name = data[strtab_off + o: j].decode('latin1')
            else:
                name = e[:8].rstrip(b'\0').decode('latin1')
            val, sec, typ, cls, naux = struct.unpack_from('<IhHBB', e, 8)
            s.syms.append((name, val, sec, cls))
            i += 1 + naux
    def va2off(s, va):
        for n, v, size, ptr, _ in s.secs:
            if v <= va < v + size and ptr:
                return ptr + va - v
        return None
    def off2va(s, off):
        for n, v, size, ptr, _ in s.secs:
            if ptr and ptr <= off < ptr + size:
                return v + off - ptr
        return None
