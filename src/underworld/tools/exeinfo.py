"""MZ ヘッダと Borland のオーバーレイ（FBOV）の位置、気になる文字列の場所を出す: python exeinfo.py UW.EXE"""
import sys, struct, re
d = open(sys.argv[1], 'rb').read()
lastpg, pages, nrel, hdrpar, minalloc, maxalloc, ss, sp, ck, ip, cs, relofs = struct.unpack('<11H H', d[2:26])
size = (pages - 1) * 512 + (lastpg or 512)
print(f'file {len(d):#x}  image end {size:#x}  header {hdrpar*16:#x}  relocs {nrel}  CS:IP {cs:04x}:{ip:04x}  SS:SP {ss:04x}:{sp:04x}  min/max {minalloc:#x}/{maxalloc:#x}')
i = d.find(b'FBOV')
print('FBOV at', hex(i) if i >= 0 else None)
if i >= 0:
    print('FBOV header', d[i:i+16].hex(' '))
for pat in [rb'(?i)strings\.pak', rb'(?i)font[0-9a-z]*\.sys', rb'(?i)\.ark', rb'(?i)borland', rb'(?i)turbo', rb'(?i)copyright[^\0]{0,60}', rb'(?i)ems|xms', rb'(?i)not enough memory[^\0]{0,40}']:
    for m in re.finditer(pat, d):
        print(f'{m.start():#08x} {m.group()[:70]!r}')
