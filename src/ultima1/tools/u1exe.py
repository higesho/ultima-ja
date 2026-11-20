# Shared analysis of Ultima I DOS executables: strings and the places that point at them.
import struct, re
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from capstone.x86 import X86_OP_IMM, X86_OP_REG, X86_OP_MEM

DS = {'ULTIMA.EXE': 0x3ed, 'OUT.EXE': 0xd48, 'SPACE.EXE': 0x72d, 'MONDAIN.EXE': 0x597, 'GEN.EXE': 0x426}
# end of the C data area that holds initialized strings (offset in DS); found by the startup code
# (bytes after this are BSS etc.). None = whole rest of the file image.

class Exe:
    def __init__(self, path, name):
        self.name = name
        self.raw = bytearray(open(path, 'rb').read())
        self.hdr = struct.unpack_from('<H', self.raw, 8)[0] * 16
        self.ds = DS[name]
        self.dbase = self.hdr + self.ds * 16          # file offset of DS:0000
        self.code_end = self.ds * 16                   # code = image[0:ds*16] (segment 0)
        self.data_len = len(self.raw) - self.dbase

    def data(self):
        return bytes(self.raw[self.dbase:])

    def code(self):
        return bytes(self.raw[self.hdr:self.hdr + self.code_end])

    def strings(self, minletters=2):
        """null-terminated printable runs in the data segment -> list of (off, bytes)"""
        out = []
        data = self.data()
        for m in re.finditer(rb'([\x20-\x7e\r\n]{2,})\x00', data):
            s, off = m.group(1), m.start(1)
            if off > 0 and 0x20 <= data[off - 1] <= 0x7e: continue
            if sum(chr(c).isalpha() for c in s) < minletters: continue
            out.append((off, s))
        return out

    def code_imm_refs(self):
        """linear-sweep disassembly; returns {imm_value: [(insn_addr, imm_file_offset, kind)]}
        kind: 'arg'  = mov reg,imm followed by push reg (function argument)
              'mov'  = other mov reg/mem, imm
              'other'= imm in other instructions (cmp/add/...) -- not treated as pointers"""
        md = Cs(CS_ARCH_X86, CS_MODE_16); md.detail = True
        code = self.code()
        ins = []; pos = 0; self.gaps = []
        while pos < len(code):
            n0 = len(ins)
            for i in md.disasm(code[pos:], pos):
                ins.append(i)
            if len(ins) > n0:
                pos = ins[-1].address + ins[-1].size
            if pos < len(code):
                self.gaps.append(pos); pos += 1
        refs = {}
        for k, i in enumerate(ins):
            for op in i.operands:
                if op.type != X86_OP_IMM or op.size != 2: continue
                v = op.imm & 0xffff
                # locate imm bytes: last 2 bytes of the instruction for mov r16,imm / mov m16,imm
                ioff = i.address + i.size - 2
                if struct.unpack_from('<H', code, ioff)[0] != v: continue
                if i.mnemonic == 'mov':
                    nxt = ins[k + 1] if k + 1 < len(ins) else None
                    dst = i.operands[0]
                    if dst.type == X86_OP_REG and nxt and nxt.mnemonic == 'push' and \
                            nxt.operands[0].type == X86_OP_REG and nxt.operands[0].reg == dst.reg:
                        kind = 'arg'
                    else:
                        kind = 'mov'
                else:
                    kind = 'other'
                refs.setdefault(v, []).append((i.address, self.hdr + ioff, kind))
        self.sweep_end = ins[-1].address + ins[-1].size if ins else 0
        return refs
