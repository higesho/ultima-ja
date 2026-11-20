# 日本語版のファイルを組み立てる DOS のプログラム U5JPMK.COM を作る
# 使い方: python build_mk.py <出力 U5JPMK.COM>
#   U5JPMK.COM は、いまのドライブとフォルダにある U5JP.DAT（make_patch.py が作る）を読み、
#   ゲームの元のファイル（TOWNE.TLK など）から日本語版（TOWNE.TLJ など）を作る。
#   元のファイルの大きさかハッシュが違うときは作らず、古い日本語版があれば消す（ゲームは英語のまま動く）
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jpenc import fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

# ---- 変数（0x103 から）----
V = {}
_p = 0x103
for name, size in [("HDAT", 2), ("HSRC", 2), ("HDST", 2), ("NFILES", 2), ("NOPS", 2), ("SKIP", 1), ("OPT", 1),
                   ("OPLEN", 2), ("OPSTART", 2), ("H1", 2), ("H2", 2), ("SRCSEG", 2), ("DATSEG", 2),
                   ("HDR", 32), ("NAMEBUF", 14), ("BUF", 16)]:
    V[name] = _p
    _p += size
DATA_AT = (_p + 15) & ~15

MSGS = [("DATNAME", b"U5JP.DAT\0"),
        ("M_NODAT", b"U5JPMK: U5JP.DAT not found.\r\n$"),
        ("M_BAD", b"U5JPMK: U5JP.DAT is broken.\r\n$"),
        ("M_MEM", b"U5JPMK: not enough memory.\r\n$"),
        ("M_OK", b" ok\r\n$"),
        ("M_SKIP", b" skipped (game file differs; stays English)\r\n$"),
        ("M_HEAD", b"U5JPMK: $"),
        ("MAGIC", b"U5JPDAT1")]

SRC = r'''
start:
    mov ax, cs
    add ax, 0x1000
    mov word ptr [{SRCSEG}], ax
    add ax, 0x1000
    mov word ptr [{DATSEG}], ax
    add ax, 0x1000
    cmp ax, word ptr [2]
    jbe mem_ok
    mov dx, {M_MEM}
    jmp die
mem_ok:
    mov ax, 0x3d00
    mov dx, {DATNAME}
    int 0x21
    jnc dat_ok
    mov dx, {M_NODAT}
    jmp die
dat_ok:
    mov word ptr [{HDAT}], ax
    mov cx, 10
    call rd_buf
    jc bad
    mov si, {BUF}
    mov di, {MAGIC}
    mov cx, 8
    push ds
    pop es
    cld
    repe cmpsb
    jne bad
    mov ax, word ptr [{BUF}+8]
    mov word ptr [{NFILES}], ax
file_loop:
    cmp word ptr [{NFILES}], 0
    je done
    dec word ptr [{NFILES}]
    mov dx, {HDR}
    mov cx, 32
    call rd_dat
    jc bad
    mov ax, word ptr [{HDR}+30]
    mov word ptr [{NOPS}], ax
    mov byte ptr [{SKIP}], 0
    ; 作る名前を見せる
    mov si, {HDR}+12
    call put_name
    ; 元のファイルを読む
    mov si, {HDR}
    call copy_name
    mov ax, 0x3d00
    mov dx, {NAMEBUF}
    int 0x21
    jc f_skip
    mov word ptr [{HSRC}], ax
    mov bx, ax
    push ds
    mov ax, word ptr [{SRCSEG}]
    mov ds, ax
    xor dx, dx
    mov cx, 0xffff
    mov ah, 0x3f
    int 0x21
    pop ds
    pushf
    push ax
    mov bx, word ptr [{HSRC}]
    mov ah, 0x3e
    int 0x21
    pop ax
    popf
    jc f_skip
    cmp ax, word ptr [{HDR}+24]
    jne f_skip
    ; ハッシュ
    mov cx, ax
    xor bx, bx
    xor dx, dx
    xor si, si
    push ds
    mov ax, word ptr [{SRCSEG}]
    mov ds, ax
    jcxz h_end
h_loop:
    lodsb
    xor ah, ah
    rol bx, 1
    add bx, ax
    add dx, ax
    rol dx, 1
    rol dx, 1
    rol dx, 1
    loop h_loop
h_end:
    pop ds
    cmp bx, word ptr [{HDR}+26]
    jne f_skip
    cmp dx, word ptr [{HDR}+28]
    jne f_skip
    ; 日本語版を作る
    mov si, {HDR}+12
    call copy_name
    mov ah, 0x3c
    xor cx, cx
    mov dx, {NAMEBUF}
    int 0x21
    jc f_skip
    mov word ptr [{HDST}], ax
    jmp ops
f_skip:
    mov byte ptr [{SKIP}], 1
    mov si, {HDR}+12
    call copy_name
    mov ah, 0x41
    mov dx, {NAMEBUF}
    int 0x21
ops:
    cmp word ptr [{NOPS}], 0
    je f_end
    dec word ptr [{NOPS}]
    mov dx, {OPT}
    mov cx, 1
    call rd_dat
    jc bad
    cmp byte ptr [{OPT}], 0
    jne op_data
    mov dx, {OPSTART}
    mov cx, 4
    call rd_dat
    jc bad
    cmp byte ptr [{SKIP}], 0
    jne ops
    mov bx, word ptr [{HDST}]
    mov dx, word ptr [{OPSTART}]
    mov cx, word ptr [{OPSTART}+2]
    push ds
    mov ax, word ptr [{SRCSEG}]
    mov ds, ax
    mov ah, 0x40
    int 0x21
    pop ds
    jc bad
    jmp ops
op_data:
    mov dx, {OPLEN}
    mov cx, 2
    call rd_dat
    jc bad
d_loop:
    mov cx, word ptr [{OPLEN}]
    or cx, cx
    je ops
    cmp cx, 0xf000
    jbe d_n
    mov cx, 0xf000
d_n:
    sub word ptr [{OPLEN}], cx
    push cx
    mov bx, word ptr [{HDAT}]
    push ds
    mov ax, word ptr [{DATSEG}]
    mov ds, ax
    xor dx, dx
    mov ah, 0x3f
    int 0x21
    pop ds
    pop cx
    jc bad
    cmp ax, cx
    jne bad
    cmp byte ptr [{SKIP}], 0
    jne d_loop
    mov bx, word ptr [{HDST}]
    push ds
    mov ax, word ptr [{DATSEG}]
    mov ds, ax
    xor dx, dx
    mov ah, 0x40
    int 0x21
    pop ds
    jc bad
    jmp d_loop
f_end:
    cmp byte ptr [{SKIP}], 0
    jne f_msk
    mov bx, word ptr [{HDST}]
    mov ah, 0x3e
    int 0x21
    mov dx, {M_OK}
    jmp f_msg
f_msk:
    mov dx, {M_SKIP}
f_msg:
    mov ah, 9
    int 0x21
    jmp file_loop
done:
    mov bx, word ptr [{HDAT}]
    mov ah, 0x3e
    int 0x21
    mov ax, 0x4c00
    int 0x21
bad:
    mov dx, {M_BAD}
die:
    mov ah, 9
    int 0x21
    mov ax, 0x4c01
    int 0x21

; U5JP.DAT から CX バイトを DS:DX へ読む（足りなければ CF=1）
rd_dat:
    push cx
    mov bx, word ptr [{HDAT}]
    mov ah, 0x3f
    int 0x21
    pop cx
    jc rd_ret
    cmp ax, cx
    je rd_ret
    stc
rd_ret:
    ret
rd_buf:
    mov dx, {BUF}
    jmp rd_dat

; SI の 12 バイトの名前を NAMEBUF に写して 0 で終える
copy_name:
    push ds
    pop es
    mov di, {NAMEBUF}
    mov cx, 12
    cld
    rep movsb
    mov byte ptr [di], 0
    ret

; 「U5JPMK: 名前」を出す
put_name:
    push si
    mov dx, {M_HEAD}
    mov ah, 9
    int 0x21
    pop si
    mov cx, 12
pn_loop:
    lodsb
    or al, al
    je pn_ret
    mov dl, al
    mov ah, 2
    push cx
    push si
    int 0x21
    pop si
    pop cx
    loop pn_loop
pn_ret:
    ret
'''


def asm(src, addr, kw):
    s = "\n".join(line.split(";")[0] for line in src.format(**kw).splitlines())
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(s, addr)
    return fix16(bytes(enc), addr)


def main(out):
    kw = dict(V)
    p = DATA_AT
    for name, blob in MSGS:
        kw[name] = p
        p += len(blob)
    code_at = (p + 15) & ~15
    code = asm(SRC, code_at, kw)
    img = bytearray(b"\xe9" + struct.pack("<H", (code_at - 0x103) & 0xFFFF))
    img += bytes(DATA_AT - 0x100 - len(img))
    for name, blob in MSGS:
        img += blob
    img += bytes(code_at - 0x100 - len(img))
    img += code
    open(out, "wb").write(img)
    print("書き出し:", out, len(img), "バイト")


if __name__ == "__main__":
    main(sys.argv[1])
