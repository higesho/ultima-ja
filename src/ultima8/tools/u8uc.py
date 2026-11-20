# -*- coding: utf-8 -*-
"""ウルティマVIII の usecode（EUSECODE.FLX）を読み書きする道具。

- Flex ファイル: 0x54 に項目数、0x80 から (位置, 大きさ) の表。0 番・1 番はクラス以外。
- クラス（項目 2 以降）: 先頭 12 バイトの見出し (a, 大きさ, c)。a と c は「大きさ＋決まった数」。
  その後ろがコード領域（基準位置 0x0C）。コード領域の先頭 128 バイトはイベント表（32 個×4 バイト）、
  命令は 0x80 から始まる。
- 文字列は 0x0D 命令: 0D 長さ(2) 文字列 00
- 位置を持つ命令:
    相対: 51/52 (rel16 は命令の直後から)、75/76 (4 バイト目の rel16、命令の直後から)
    絶対: 11 call (クラス, 位置)、57 spawn (クラス, 位置)、58 spawn inline (クラス, 位置, 差分)
"""
import struct

# 命令の長さ（オペコードも含む）。0x0D は可変。
OPLEN = {
    0x00: 2, 0x01: 2, 0x02: 2, 0x03: 3, 0x08: 1, 0x09: 4, 0x0A: 2, 0x0B: 3,
    0x0C: 5, 0x0E: 3, 0x0F: 4, 0x11: 5, 0x12: 1, 0x13: 1, 0x14: 1, 0x15: 1,
    0x16: 1, 0x17: 1, 0x19: 2, 0x1A: 2, 0x1B: 2, 0x1C: 1, 0x1D: 1, 0x1E: 1,
    0x1F: 1, 0x20: 1, 0x21: 1, 0x22: 1, 0x23: 1, 0x24: 1, 0x25: 1, 0x26: 1,
    0x28: 1, 0x29: 1, 0x2A: 1, 0x2B: 1, 0x2C: 1, 0x2D: 1, 0x2E: 1, 0x2F: 1,
    0x30: 1, 0x31: 1, 0x32: 1, 0x33: 1, 0x34: 1, 0x35: 1, 0x36: 1, 0x37: 1,
    0x38: 3, 0x39: 1, 0x3A: 1, 0x3B: 1, 0x3C: 1, 0x3D: 1, 0x3E: 2, 0x3F: 2,
    0x40: 2, 0x41: 2, 0x42: 3, 0x43: 2, 0x44: 3, 0x45: 3, 0x4B: 2, 0x4C: 2,
    0x4D: 2, 0x4E: 4, 0x4F: 4, 0x50: 1, 0x51: 3, 0x52: 3, 0x53: 1, 0x54: 3,
    0x57: 7, 0x58: 9, 0x59: 1, 0x5A: 2, 0x5B: 3, 0x5C: 12, 0x5D: 1, 0x5E: 1,
    0x5F: 1, 0x60: 1, 0x61: 1, 0x62: 2, 0x63: 2, 0x64: 2, 0x65: 2, 0x66: 2,
    0x67: 2, 0x69: 2, 0x6B: 1, 0x6C: 3, 0x6D: 1, 0x6E: 2, 0x6F: 2, 0x70: 4,
    0x73: 1, 0x74: 2, 0x75: 5, 0x76: 5, 0x77: 1, 0x78: 1, 0x79: 1, 0x7A: 1,
}

CODE_BASE = 0x0C      # クラスの先頭からコード領域まで
CODE_START = 0x80     # コード領域の中で命令が始まる位置（イベント表の後ろ）
NUM_EVENTS = 32


class Ins:
    """命令ひとつ。pos はコード領域の中の位置。raw は命令のバイト列。"""
    __slots__ = ('pos', 'op', 'raw', 'text')

    def __init__(self, pos, raw):
        self.pos = pos
        self.op = raw[0]
        self.raw = bytes(raw)
        self.text = None   # 0x0D のときの文字列（bytes）。差し替えるときはここを変える

    def rel_target(self):
        """相対ジャンプの行き先（コード領域の位置）。無ければ None。"""
        if self.op in (0x51, 0x52):
            rel = struct.unpack_from('<h', self.raw, 1)[0]
        elif self.op in (0x75, 0x76):
            rel = struct.unpack_from('<h', self.raw, 3)[0]
        else:
            return None
        return (self.pos + len(self.raw) + rel) & 0xFFFF


class UClass:
    def __init__(self, index, data):
        self.index = index            # Flex の項目番号（クラス番号＋2）
        self.hdr = struct.unpack_from('<3I', data, 0)
        assert self.hdr[1] == len(data), (index, self.hdr, len(data))
        code = data[CODE_BASE:]
        self.events = list(struct.unpack_from('<%dI' % NUM_EVENTS, code, 0))
        self.ins = []
        p = CODE_START
        while p < len(code):
            op = code[p]
            if op == 0x0D:
                ln = struct.unpack_from('<H', code, p + 1)[0]
                n = 3 + ln + 1
                assert code[p + n - 1] == 0, ('0D の終わりが 0 でない', index, hex(p))
                ins = Ins(p, code[p:p + n])
                ins.text = bytes(code[p + 3:p + 3 + ln])
            else:
                if op not in OPLEN:
                    raise ValueError('知らない命令 %02X (項目 %d, 位置 %04X)' % (op, index, p))
                n = OPLEN[op]
                ins = Ins(p, code[p:p + n])
            self.ins.append(ins)
            p += n
        assert p == len(code), ('コードの終わりがずれた', index, p, len(code))
        self.code_len = len(code)

    @property
    def classid(self):
        return self.index - 2

    def strings(self):
        return [i for i in self.ins if i.op == 0x0D]


class Usecode:
    def __init__(self, path):
        d = open(path, 'rb').read()
        self.head = d[:0x80]
        n = struct.unpack_from('<I', d, 0x54)[0]
        self.entries = []      # bytes か UClass か None（空）
        for i in range(n):
            o, sz = struct.unpack_from('<II', d, 0x80 + i * 8)
            if sz == 0:
                self.entries.append(None)
            elif i < 2:
                self.entries.append(d[o:o + sz])
            else:
                self.entries.append(UClass(i, d[o:o + sz]))
        self.raw = d

    def classes(self):
        return [e for e in self.entries if isinstance(e, UClass)]

    def by_classid(self, cid):
        e = self.entries[cid + 2] if 0 <= cid + 2 < len(self.entries) else None
        return e if isinstance(e, UClass) else None

    # ---- 組み直し ----
    def build(self):
        """命令の並び（文字列の差し替え後）から Flex を作り直す。位置を全部直す。"""
        classes = self.classes()
        # 1. 新しい命令の大きさと位置を決める
        newpos = {}   # classid -> {古い位置: 新しい位置}
        newraw = {}
        for c in classes:
            m = {}
            p = CODE_START
            sizes = []
            for ins in c.ins:
                m[ins.pos] = p
                if ins.op == 0x0D:
                    n = 3 + len(ins.text) + 1
                else:
                    n = len(ins.raw)
                sizes.append(n)
                p += n
            m[c.code_len] = p      # コードの終わり
            newpos[c.classid] = m
            newraw[c.classid] = sizes

        def mp(cid, off, where):
            m = newpos.get(cid)
            if m is None:
                raise ValueError('無いクラス %04X を指している (%s)' % (cid, where))
            if off not in m:
                raise ValueError('命令の頭でない位置 %04X:%04X を指している (%s)' % (cid, off, where))
            return m[off]

        # 2. 命令を書き出す
        out = []
        for c in classes:
            cid = c.classid
            m = newpos[cid]
            buf = bytearray()
            ev = []
            for e in c.events:
                ev.append(mp(cid, e, 'イベント表 %04X' % cid) if e else 0)
            buf += struct.pack('<%dI' % NUM_EVENTS, *ev)
            for ins in c.ins:
                where = '%04X:%04X' % (cid, ins.pos)
                op = ins.op
                if op == 0x0D:
                    r = bytearray([0x0D]) + struct.pack('<H', len(ins.text)) + ins.text + b'\x00'
                else:
                    r = bytearray(ins.raw)
                    tgt = ins.rel_target()
                    if tgt is not None:
                        np_ = m[ins.pos]
                        nt = mp(cid, tgt, where)
                        # 16 ビットで回り込む（ゲーム側も 16 ビットで足す）
                        rel = (nt - (np_ + len(r))) & 0xFFFF
                        struct.pack_into('<H', r, 1 if op in (0x51, 0x52) else 3, rel)
                    elif op == 0x11:
                        tc, to = struct.unpack_from('<HH', r, 1)
                        struct.pack_into('<H', r, 3, mp(tc, to, where))
                    elif op == 0x57:
                        tc, to = struct.unpack_from('<HH', r, 3)
                        struct.pack_into('<H', r, 5, mp(tc, to, where))
                    elif op == 0x58:
                        tc, to, dl = struct.unpack_from('<HHH', r, 1)
                        no = mp(tc, to, where)
                        nt = mp(tc, (to + dl) & 0xFFFF, where)
                        struct.pack_into('<HH', r, 3, no, nt - no)
                assert m[ins.pos] == len(buf), where
                buf += r
            assert len(buf) == m[c.code_len]
            size = CODE_BASE + len(buf)
            if size > 0xFFFF:
                raise ValueError('クラス %04X が 64KB を超えた' % cid)
            a, s, cc = c.hdr
            hdr = struct.pack('<3I', a - s + size, size, cc - s + size)
            out.append((c.index, hdr + bytes(buf)))

        # 3. Flex にまとめる（元の並び順を保つ）
        data = {}
        for i, e in enumerate(self.entries):
            if isinstance(e, (bytes, bytearray)):
                data[i] = e
        for i, b in out:
            data[i] = b
        n = len(self.entries)
        # 元のファイルと同じ順に置く（元の位置の順）
        order = sorted(data.keys(), key=lambda i: struct.unpack_from('<I', self.raw, 0x80 + i * 8)[0])
        table = bytearray(self.raw[0x80:0x80 + n * 8])   # 空の項目は元の値のまま
        body = bytearray()
        first = struct.unpack_from('<I', self.raw, 0x80 + order[0] * 8)[0] if order else 0x80 + n * 8
        pad = self.raw[0x80 + n * 8:first]     # 表と最初の項目の間（元のまま）
        pos = 0x80 + n * 8 + len(pad)
        for i in order:
            struct.pack_into('<II', table, i * 8, pos, len(data[i]))
            body += data[i]
            pos += len(data[i])
        return bytes(self.head) + bytes(table) + bytes(pad) + bytes(body)
