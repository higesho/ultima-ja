import sys, struct
from capstone import *
fn=sys.argv[1]; d=open(fn,'rb').read()
h=struct.unpack_from('<2s13H', d, 0); hdr=h[4]*16; ip=h[10]; cs=h[11]; nrel=h[3]; reloff=h[12]
rels=[struct.unpack_from('<HH',d,reloff+4*i) for i in range(nrel)]
img=d[hdr:]
print('relocs:', [(f"{s:04x}:{o:04x}", hex(struct.unpack_from('<H',img,s*16+o)[0])) for o,s in rels])
md=Cs(CS_ARCH_X86, CS_MODE_16)
start=cs*16+ip
for ins in md.disasm(img[start:start+120], ip):
    print(f"{cs:04x}:{ins.address:04x}  {ins.mnemonic} {ins.op_str}")
