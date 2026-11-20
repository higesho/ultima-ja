"""文字列を参照する命令の後ろを短く表示する（表示位置を知るため）。"""
import sys, os, re, capstone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coff, refs
c = coff.Coff(open(sys.argv[1], 'rb').read())
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
targets = [int(x, 16) for x in sys.argv[2:]]
rf = refs.find_refs(c, set(targets))
skip = re.compile(r'(mov (e..|dword ptr \[ebp - 0x..\]), (e..|dword ptr \[0x52b..\]|dword ptr \[ebp - 0x..\])|push eax|add esp, .*|mov eax, eax|lea esi, \[esi.*|nop|mov esi, esi)$')
for t in targets:
    for rva, roff, kind in rf[t]:
        if not (0x1550 <= rva < 0x1a000) or kind == 'table': continue
        o = c.va2off(rva)
        seg = []
        for i in md.disasm(bytes(c.d[o:o + 260]), rva):
            s = i.mnemonic + ' ' + i.op_str
            if not skip.match(s): seg.append(s)
            if len(seg) > 26: break
        print('%x @%x: %s\n' % (t, rva, ' ; '.join(seg)))
