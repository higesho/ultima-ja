# 会話の日本語版を組み立てる DOS のプログラム U6JPMK.COM を作る（U5 の U5JPMK を元に、LZW の展開と 64KB を超えるファイルに対応）
# 使い方: python build_mk.py <出力 U6JPMK.COM>
#   U6JPMK.COM は、いまのドライブとフォルダにある U6JPMK.DAT（make_patch.py が作る）を読み、
#   ゲームの元のファイル（CONVERSE.A/B）から日本語版（CONVERSE.JA/JB）を作る。
#   元のファイルの大きさかハッシュが違うとき、または作ったファイルのハッシュが合わないときは日本語版を消す（その会話は英語のまま動く）
#
# U6JPMK.DAT の形は make_patch.py を見る。ファイルの見出しは 38 バイト:
#   元の名前 12、作る名前 12、元の大きさ 4、元の h1 2、元の h2 2、命令の数 2、作るファイルの h1 2、h2 2
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jpenc import fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

V = {}
_p = 0x103
for name, size in [("HDAT", 2), ("HSRC", 2), ("HDST", 2), ("NFILES", 2), ("NOPS", 2), ("SKIP", 1), ("OPT", 1),
                   ("ARG", 6), ("H1", 2), ("H2", 2), ("D1", 2), ("D2", 2), ("REM", 4),
                   ("DICSEG", 2), ("PKSEG", 2), ("UBSEG", 2), ("DATSEG", 2),
                   ("INLEN", 2), ("BITOFF", 2), ("BITS", 2), ("NEXT", 2), ("PREV", 2), ("FIRST", 2),
                   ("HDR", 38), ("NAMEBUF", 14), ("BUF", 16)]:
    V[name] = _p
    _p += size
DATA_AT = (_p + 15) & ~15
DIC_P, DIC_S, DIC_STK = 0x8000, 0xA000, 0xC000      # 展開の辞書（展開先と同じセグメントの後ろ半分）

MSGS = [("DATNAME", b"U6JPMK.DAT\0"),
        ("M_NODAT", b"U6JPMK: U6JPMK.DAT not found.\r\n$"),
        ("M_BAD", b"U6JPMK: U6JPMK.DAT is broken.\r\n$"),
        ("M_MEM", b"U6JPMK: not enough memory.\r\n$"),
        ("M_OK", b" ok\r\n$"),
        ("M_SKIP", b" skipped (game file differs; stays English)\r\n$"),
        ("M_FAIL", b" failed (stays English)\r\n$"),
        ("M_HEAD", b"U6JPMK: $"),
        ("MAGIC", b"U6JPMK01")]

SRC = r'''
start:
    mov ax, cs
    add ax, 0x1000
    mov word ptr [{PKSEG}], ax
    add ax, 0x1000
    mov word ptr [{UBSEG}], ax
    add ax, 0x1000
    mov word ptr [{DATSEG}], ax
    add ax, 0x1000
    cmp ax, word ptr [2]
    jbe mem_ok
    mov dx, {M_MEM}
    jmp die
mem_ok:
    mov word ptr [{HDST}], 0
    mov ax, 0x3d00
    mov dx, {DATNAME}
    int 0x21
    jnc dat_ok
    mov dx, {M_NODAT}
    jmp die
dat_ok:
    mov word ptr [{HDAT}], ax
    mov dx, {BUF}
    mov cx, 10
    call rd_dat
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
    jne fl_1
    jmp done
fl_1:
    dec word ptr [{NFILES}]
    mov dx, {HDR}
    mov cx, 38
    call rd_dat
    jc bad
    mov ax, word ptr [{HDR}+32]
    mov word ptr [{NOPS}], ax
    mov byte ptr [{SKIP}], 1
    mov word ptr [{D1}], 0
    mov word ptr [{D2}], 0
    mov si, {HDR}+12
    call put_name
    mov si, {HDR}
    call copy_name
    mov ax, 0x3d00
    mov dx, {NAMEBUF}
    int 0x21
    jc f_noskip
    mov word ptr [{HSRC}], ax
    call src_hash
    jc f_noskip
    mov ax, word ptr [{H1}]
    cmp ax, word ptr [{HDR}+28]
    jne f_noskip
    mov ax, word ptr [{H2}]
    cmp ax, word ptr [{HDR}+30]
    jne f_noskip
    mov si, {HDR}+12
    call copy_name
    mov ah, 0x3c
    xor cx, cx
    mov dx, {NAMEBUF}
    int 0x21
    jc f_noskip
    mov word ptr [{HDST}], ax
    mov byte ptr [{SKIP}], 0
    jmp ops
f_noskip:
    call del_dst
ops:
    cmp word ptr [{NOPS}], 0
    jne op_1
    jmp f_end
op_1:
    dec word ptr [{NOPS}]
    mov dx, {OPT}
    mov cx, 1
    call rd_dat
    jc bad
    mov al, byte ptr [{OPT}]
    cmp al, 1
    je op_data
    cmp al, 3
    je op_ucopy
    cmp al, 2
    ja bad
    mov dx, {ARG}
    mov cx, 6
    call rd_dat
    jc bad
    cmp byte ptr [{SKIP}], 0
    jne ops
    call src_read
    jc fail
    cmp byte ptr [{OPT}], 0
    jne op_unpack
    mov ax, word ptr [{DATSEG}]
    xor dx, dx
    mov cx, word ptr [{ARG}+4]
    call wr
    jc fail
    jmp ops
op_unpack:
    call unlzw
    jmp ops
op_ucopy:
    mov dx, {ARG}
    mov cx, 4
    call rd_dat
    jc bad
    cmp byte ptr [{SKIP}], 0
    jne ops
    mov ax, word ptr [{UBSEG}]
    mov dx, word ptr [{ARG}]
    mov cx, word ptr [{ARG}+2]
    call wr
    jc fail
    jmp ops
op_data:
    mov dx, {ARG}
    mov cx, 2
    call rd_dat
    jc bad
    mov cx, word ptr [{ARG}]
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
    je od_w
    jmp ops
od_w:
    mov ax, word ptr [{DATSEG}]
    xor dx, dx
    call wr
    jc fail
    jmp ops
fail:
    call close_src
    call del_dst
    mov dx, {M_FAIL}
    jmp bad_end
f_end:
    call close_src
    cmp byte ptr [{SKIP}], 0
    jne f_msk
    mov bx, word ptr [{HDST}]
    mov ah, 0x3e
    int 0x21
    mov word ptr [{HDST}], 0
    mov ax, word ptr [{D1}]
    cmp ax, word ptr [{HDR}+34]
    jne f_bad
    mov ax, word ptr [{D2}]
    cmp ax, word ptr [{HDR}+36]
    jne f_bad
    mov dx, {M_OK}
    jmp f_msg
f_bad:
    call del_dst
    mov dx, {M_FAIL}
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
    call close_src
    call del_dst
    mov dx, {M_BAD}
bad_end:
die:
    mov ah, 9
    int 0x21
    mov ax, 0x4c01
    int 0x21

close_src:
    mov bx, word ptr [{HSRC}]
    or bx, bx
    jz cs_x
    mov ah, 0x3e
    int 0x21
    mov word ptr [{HSRC}], 0
cs_x:
    ret

; 作りかけの日本語版を閉じて消す（名前は見出しの作る名前）
del_dst:
    mov bx, word ptr [{HDST}]
    or bx, bx
    jz dd_1
    mov ah, 0x3e
    int 0x21
    mov word ptr [{HDST}], 0
dd_1:
    mov si, {HDR}+12
    call copy_name
    mov ah, 0x41
    mov dx, {NAMEBUF}
    int 0x21
    mov byte ptr [{SKIP}], 1
    ret

; 元のファイル全体の大きさとハッシュ（CF=1 なら大きさが違う）
src_hash:
    mov word ptr [{H1}], 0
    mov word ptr [{H2}], 0
    mov ax, word ptr [{HDR}+24]
    mov word ptr [{REM}], ax
    mov ax, word ptr [{HDR}+26]
    mov word ptr [{REM}+2], ax
sh_l:
    mov bx, word ptr [{HSRC}]
    push ds
    mov ax, word ptr [{DATSEG}]
    mov ds, ax
    xor dx, dx
    mov cx, 0x8000
    mov ah, 0x3f
    int 0x21
    pop ds
    jc sh_bad
    or ax, ax
    jz sh_end
    sub word ptr [{REM}], ax
    sbb word ptr [{REM}+2], 0
    jb sh_bad
    mov cx, ax
    push ds
    mov bx, word ptr [{H1}]
    mov dx, word ptr [{H2}]
    mov ax, word ptr [{DATSEG}]
    mov ds, ax
    xor si, si
    call hash
    pop ds
    mov word ptr [{H1}], bx
    mov word ptr [{H2}], dx
    jmp sh_l
sh_end:
    mov ax, word ptr [{REM}]
    or ax, word ptr [{REM}+2]
    jnz sh_bad
    clc
    ret
sh_bad:
    stc
    ret

; DS:SI から CX バイトをハッシュ（BX=h1, DX=h2）
hash:
    jcxz h_x
h_l:
    lodsb
    xor ah, ah
    rol bx, 1
    add bx, ax
    add dx, ax
    rol dx, 1
    rol dx, 1
    rol dx, 1
    loop h_l
h_x:
    ret

; 元のファイルの ARG の位置から ARG+4 の長さを読む（命令 0 は DATSEG、命令 2 は PKSEG に）
src_read:
    mov bx, word ptr [{HSRC}]
    mov dx, word ptr [{ARG}]
    mov cx, word ptr [{ARG}+2]
    mov ax, 0x4200
    int 0x21
    jc sr_x
    mov ax, word ptr [{DATSEG}]
    cmp byte ptr [{OPT}], 0
    je sr_1
    mov ax, word ptr [{PKSEG}]
sr_1:
    mov cx, word ptr [{ARG}+4]
    mov word ptr [{INLEN}], cx
    push ds
    mov ds, ax
    xor dx, dx
    mov ah, 0x3f
    int 0x21
    jc sr_p
    mov bx, word ptr cs:[{ARG}+4]
    mov word ptr [bx], 0
    mov word ptr [bx+2], 0
    cmp ax, cx
    pop ds
    je sr_ok
    stc
    ret
sr_p:
    pop ds
sr_x:
    ret
sr_ok:
    clc
    ret

; AX:DX から CX バイトを日本語版に書く（ハッシュも取る）
wr:
    jcxz wr_ok
    push ax
    push cx
    push dx
    push ds
    mov bx, word ptr [{D1}]
    mov si, dx
    mov dx, word ptr [{D2}]
    mov ds, ax
    call hash
    pop ds
    mov word ptr [{D1}], bx
    mov word ptr [{D2}], dx
    pop dx
    pop cx
    pop ax
    mov bx, word ptr [{HDST}]
    push ds
    mov ds, ax
    mov ah, 0x40
    int 0x21
    pop ds
    jc wr_x
    cmp ax, cx
    jne wr_bad
wr_ok:
    clc
    ret
wr_bad:
    stc
wr_x:
    ret

; U6 の LZW を展開: PKSEG:0 からの INLEN バイト（先頭 4 バイトは大きさ）→ UBSEG:0
unlzw:
    push ds
    push es
    mov ax, word ptr [{PKSEG}]
    mov ds, ax
    mov ax, word ptr cs:[{UBSEG}]
    mov es, ax
    mov si, 4
    mov word ptr cs:[{BITOFF}], 0
    mov word ptr cs:[{BITS}], 9
    mov word ptr cs:[{NEXT}], 0x102
    mov word ptr cs:[{PREV}], 0xffff
    xor di, di
    cld
ul_loop:
    cmp si, word ptr cs:[{INLEN}]
    jb ul_get
    jmp ul_end
ul_get:
    mov ax, word ptr [si]
    mov dl, byte ptr [si+2]
    mov cx, word ptr cs:[{BITOFF}]
    jcxz ul_g1
ul_sh:
    shr dl, 1
    rcr ax, 1
    loop ul_sh
ul_g1:
    mov cx, word ptr cs:[{BITS}]
    mov bx, 1
    shl bx, cl
    dec bx
    and ax, bx
    add cx, word ptr cs:[{BITOFF}]
    mov bx, cx
    and bx, 7
    mov word ptr cs:[{BITOFF}], bx
    shr cx, 1
    shr cx, 1
    shr cx, 1
    add si, cx
    cmp ax, 0x100
    jne ul_n1
    mov word ptr cs:[{BITS}], 9
    mov word ptr cs:[{NEXT}], 0x102
    mov word ptr cs:[{PREV}], 0xffff
    jmp ul_loop
ul_n1:
    cmp ax, 0x101
    jne ul_n1b
    jmp ul_end
ul_n1b:
    cmp word ptr cs:[{PREV}], 0xffff
    jne ul_n2
    stosb
    mov word ptr cs:[{PREV}], ax
    mov byte ptr cs:[{FIRST}], al
    jmp ul_loop
ul_n2:
    cmp ax, word ptr cs:[{NEXT}]
    jb ul_known
    ja ul_end
    push ax
    mov ax, word ptr cs:[{PREV}]
    call ul_out
    mov al, byte ptr cs:[{FIRST}]
    stosb
    pop ax
    jmp ul_add
ul_known:
    call ul_out
ul_add:
    mov bx, word ptr cs:[{NEXT}]
    cmp bx, 4096
    jae ul_skp
    mov dx, word ptr cs:[{PREV}]
    shl bx, 1
    mov word ptr es:[bx+{DIC_P}], dx
    shr bx, 1
    mov dl, byte ptr cs:[{FIRST}]
    mov byte ptr es:[bx+{DIC_S}], dl
ul_skp:
    inc word ptr cs:[{NEXT}]
    mov word ptr cs:[{PREV}], ax
    mov cx, word ptr cs:[{BITS}]
    cmp cx, 12
    jae ul_lp
    mov bx, 1
    shl bx, cl
    cmp word ptr cs:[{NEXT}], bx
    jb ul_lp
    inc word ptr cs:[{BITS}]
ul_lp:
    jmp ul_loop
ul_end:
    pop es
    pop ds
    ret

; AX の符号の文字列を ES:DI に書く（AX は変えない。最初の字を FIRST に）
ul_out:
    push ax
    push bx
    push cx
    push dx
    mov dx, {DIC_STK}
ulo_l:
    cmp ax, 0x100
    jb ulo_e
    mov bx, ax
    mov cl, byte ptr es:[bx+{DIC_S}]
    dec dx
    mov bx, dx
    mov byte ptr es:[bx], cl
    mov bx, ax
    shl bx, 1
    mov ax, word ptr es:[bx+{DIC_P}]
    jmp ulo_l
ulo_e:
    mov byte ptr cs:[{FIRST}], al
    stosb
    mov bx, dx
ulo_p:
    cmp bx, {DIC_STK}
    jae ulo_x
    mov al, byte ptr es:[bx]
    stosb
    inc bx
    jmp ulo_p
ulo_x:
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; U6JPMK.DAT から CX バイトを DS:DX へ読む（足りなければ CF=1）
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

; 「U6JPMK: 名前」を出す
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
    sys.stdout.reconfigure(encoding="utf-8")
    kw = dict(V, DIC_P=DIC_P, DIC_S=DIC_S, DIC_STK=DIC_STK)
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
