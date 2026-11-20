# 試験用プログラム LOADTEST.COM を作る
#   ゲームと同じく FCB の一括読み込み（AH=14h）でファイルを「別のセグメントの 0x100」に読み込み、
#   そのセグメント全体（64KB）を OUT.BIN に書き出す。常駐部の書き換えが効いたかを Python で調べるため
# 使い方: python loadtest.py <出力 LOADTEST.COM>
#   DOS で: LOADTEST <ファイル名> <DTA の番地(16進4桁)>   例: LOADTEST EXODUS.BIN 0100
import sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

SRC = r'''
    mov ax, cs
    add ax, 0x1000
    mov es, ax
    ; 64KB をゼロにする
    xor di, di
    xor ax, ax
    mov cx, 0x8000
    cld
    rep stosw
    ; コマンドラインの名前を FCB（ES:005C）に
    mov si, 0x81
skip:
    lodsb
    cmp al, 0x20
    je skip
    dec si
    mov di, 0x5c
    mov ax, 0x2900
    push ds
    push es
    ; DS:SI = コマンドライン, ES:DI = FCB
    int 0x21
    pop es
    pop ds
    ; 名前の後ろの DTA の番地（16進4桁）
find:
    lodsb
    cmp al, 0x20
    jne find
    xor bx, bx
    mov cx, 4
hex:
    lodsb
    sub al, 0x30
    cmp al, 10
    jb dig
    sub al, 7
dig:
    shl bx, 4
    or bl, al
    loop hex
    push es
    pop ds
    mov dx, bx
    mov ah, 0x1a
    int 0x21
    mov dx, 0x5c
    mov ah, 0x0f
    int 0x21
    mov ax, word ptr [0x6c]
    mov word ptr [0x6a], ax
    mov word ptr [0x68], 0
    mov byte ptr [0x7c], 0
    mov ah, 0x14
    int 0x21
    mov ah, 0x10
    int 0x21
    ; OUT.BIN に 64KB を書く（ファイル名は自分の CS 側）
    push cs
    pop ds
    mov dx, offset_name
    mov ah, 0x3c
    xor cx, cx
    int 0x21
    mov bx, ax
    push es
    pop ds
    xor dx, dx
    mov cx, 0x8000
    mov ah, 0x40
    int 0x21
    mov dx, 0x8000
    mov cx, 0x8000
    mov ah, 0x40
    int 0x21
    mov ah, 0x3e
    int 0x21
    mov ax, 0x4c00
    int 0x21
offset_name:
'''
src = "\n".join(l.split(";")[0] for l in SRC.split("\n"))
enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src.replace("offset_name", "0x9999", 1).replace("offset_name:", "") , 0x100)
n = len(enc)
enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src.replace("mov dx, offset_name", f"mov dx, {0x100 + n}").replace("offset_name:", ""), 0x100)
assert len(enc) == n
open(sys.argv[1], "wb").write(bytes(enc) + b"OUT.BIN\0")
print(len(enc) + 8, "bytes")
