# 会話ファイルの差し替えを確かめる試験プログラム TLKTEST.COM を作る
# FCB で TLK… を開き、AH=27h で 256 バイト読んで、TLKOUT.BIN に書き出す
# 使い方: python tlktest.py <ファイル名（TLKX03 など）> <出力 .COM>
import sys
import struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

name, out = sys.argv[1], sys.argv[2]
src = '''
    mov ah, 0x0f
    mov dx, {FCB}
    int 0x21
    mov ah, 0x1a
    mov dx, {BUF}
    int 0x21
    mov word ptr [{FCB}+14], 1
    mov cx, 256
    mov dx, {FCB}
    mov ah, 0x27
    int 0x21
    mov ah, 0x10
    mov dx, {FCB}
    int 0x21
    mov ah, 0x3c
    xor cx, cx
    mov dx, {FN}
    int 0x21
    mov bx, ax
    mov ah, 0x40
    mov cx, 256
    mov dx, {BUF}
    int 0x21
    mov ah, 0x3e
    int 0x21
    mov ax, 0x4c00
    int 0x21
'''
ks = Ks(KS_ARCH_X86, KS_MODE_16)
code = bytes(ks.asm(src.format(FCB=0x9000, BUF=0x9000, FN=0x9000), 0x100)[0])
fcb = 0x100 + len(code)
fn = fcb + 37
buf = fn + 11
code2 = bytes(ks.asm(src.format(FCB=fcb, BUF=buf, FN=fn), 0x100)[0])
assert len(code2) == len(code)
fcbdata = b"\0" + name.ljust(8).encode() + b"   " + bytes(25)
open(out, "wb").write(code2 + fcbdata + b"TLKOUT.BIN\0")
print(out, len(code2) + 37 + 11)
