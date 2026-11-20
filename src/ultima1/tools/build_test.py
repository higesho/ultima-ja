# Build JPTEST.COM: sets a graphics mode, prints Japanese text via INT 10h AH=0Eh, waits for a key.
# usage: python build_test.py <out.com> <mode hex> <lines.txt (UTF-8)>
import sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

out, mode, txt = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
lines = [l.rstrip('\n') for l in open(txt, encoding='utf-8')]
data = b''
for i, l in enumerate(lines):
    data += bytes([2 + i * 2, 1, 9 + i % 6]) + l.encode('cp932') + b'\0'   # row, col, color, text
data += b'\xff'

SRC = '''
    mov ax, {MODE}
    int 0x10
    mov si, {DATA}
next:
    lodsb
    cmp al, 0xff
    je wait
    mov dh, al
    lodsb
    mov dl, al
    lodsb
    mov bl, al
    mov ah, 2
    mov bh, 0
    int 0x10
putc:
    lodsb
    or al, al
    jz next
    mov ah, 0x0e
    int 0x10
    jmp putc
wait:
    xor ax, ax
    int 0x16
    mov ax, 3
    int 0x10
    mov ax, 0x4c00
    int 0x21
'''
ks = Ks(KS_ARCH_X86, KS_MODE_16)
code = bytes(ks.asm(SRC.format(MODE=mode, DATA=0x9000), 0x100)[0])
code = bytes(ks.asm(SRC.format(MODE=mode, DATA=0x100 + len(code)), 0x100)[0])
open(out, 'wb').write(code + data)
print(out, len(code) + len(data), 'bytes')
