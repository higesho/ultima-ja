# Extract null-terminated strings from data segment of Ultima I DOS EXEs, with code references.
import sys, struct, re, csv, os
from capstone import *
DS = {'ULTIMA.EXE':0x3ed,'OUT.EXE':0xd48,'SPACE.EXE':0x72d,'MONDAIN.EXE':0x597,'GEN.EXE':0x426}
out = sys.argv[1]
rows=[]
md=Cs(CS_ARCH_X86, CS_MODE_16); md.detail=False
for fn,ds in DS.items():
    d=open(fn,'rb').read(); hdr=struct.unpack_from('<H',d,8)[0]*16; img=d[hdr:]
    base=ds*16; data=img[base:]; code=img[:base]
    # immediates in code: collect all 16-bit immediate operands / displacement values
    imms={}
    for ins in md.disasm_lite(code,0) if False else []: pass
    # linear sweep is unreliable; instead pattern search for common opcodes with imm16
    for m in re.finditer(rb'[\xb8-\xbf]..', code, re.S):   # mov r16, imm16
        v=struct.unpack_from('<H',code,m.start()+1)[0]; imms.setdefault(v,[]).append(m.start())
    for m in re.finditer(rb'\xc7[\x06\x46\x86]', code):     # mov word [..], imm16
        ln={0x06:4,0x46:3,0x86:4}[code[m.start()+1]]
        p=m.start()+2+(ln-2)
        if p+2<=len(code): v=struct.unpack_from('<H',code,p)[0]; imms.setdefault(v,[]).append(m.start())
    for m in re.finditer(rb'[\x05\x3d]..', code): pass
    for m in re.finditer(rb'([\x20-\x7e\r\n]{2,})\x00', data):
        s=m.group(1); off=m.start(1)
        # skip strings that are tails of longer strings (preceded by printable char)
        if off>0 and 0x20<=data[off-1]<=0x7e: continue
        letters=sum(c.isalpha() for c in s.decode('latin1'))
        if letters<2: continue
        refs=imms.get(off,[])
        rows.append([fn,f"{hdr+base+off:#07x}",f"{off:#06x}",len(s),len(refs),' '.join(f"{r:#06x}" for r in refs[:4]),s.decode('latin1').replace('\r','\r').replace('\n','\n')])
with open(out,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['file','file_off','ds_off','len','nrefs','code_refs','text']); w.writerows(rows)
from collections import Counter
c=Counter(r[0] for r in rows); print(c, 'total',len(rows))
print('with refs:', sum(1 for r in rows if r[4]>0), ' bytes:', sum(r[3] for r in rows))
