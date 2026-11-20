# 日本語版のファイルを組み立てる DOS のプログラム MDJPMK.COM を作る
# 使い方: python build_mk.py <出力 MDJPMK.COM>
#   MDJPMK.COM は、いまのドライブとフォルダにある MDJP.PAT（make_patch.py が作る）を読み、
#   （組み立て済みの印 MDJPMK.OK の版が同じで、作るファイルが全部決まった大きさなら何もしない）
#   ゲームの元のファイル（TALK.LZC など）から日本語版（TALK.LZJ など）を作る。
#   元のファイルの大きさかハッシュが違うときは作らず、古い日本語版があれば消す（その部分は英語のまま動く）
#   U5 の U5JPMK.COM と同じ作りに、32 ビットの位置、出力のため込み、U6 の LZW の展開を足した
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jpenc import fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

# ---- 変数（0x103 から）----
V = {}
_p = 0x103
for name, size in [("HDAT", 2), ("HSRC", 2), ("HDST", 2), ("NFILES", 2), ("NOPS", 2), ("SKIP", 1), ("OPT", 1),
                   ("OPLEN", 2), ("ARGS", 8), ("H1", 2), ("H2", 2), ("SZLO", 2), ("SZHI", 2),
                   ("OUTSEG", 2), ("INSEG", 2), ("DICTSEG", 2), ("CMPSEG", 2), ("DECSEG", 2),
                   ("OUTPOS", 2), ("DECLEN", 2), ("BITPOS", 2), ("NBITS", 2), ("CBITS", 2), ("NEXT", 2),
                   ("PREV", 2), ("CUR", 2), ("FIRST", 1),
                   ("PATSEG", 2), ("PBPOS", 2), ("PBLEN", 2), ("PRN", 2), ("SKIPPED", 1), ("NCHK", 2),
                   ("STAMP", 8), ("BUF2", 8), ("FTAB", 16 * 24),
                   ("HDR", 34), ("NAMEBUF", 14), ("BUF", 16)]:
    V[name] = _p
    _p += size
DATA_AT = (_p + 15) & ~15

MSGS = [("DATNAME", b"MDJP.PAT\0"),
        ("M_NODAT", b"MDJPMK: MDJP.PAT not found.\r\n$"),
        ("M_BAD", b"MDJPMK: MDJP.PAT is broken.\r\n$"),
        ("M_MEM", b"MDJPMK: not enough memory.\r\n$"),
        ("M_OK", b" ok\r\n$"),
        ("M_SKIP", b" skipped (game file differs; stays English)\r\n$"),
        ("M_HEAD", b"MDJPMK: $"),
        ("M_DONE", b"MDJPMK: ok (already built)\r\n$"),
        ("OKNAME", b"MDJPMK.OK\0"),
        ("MAGIC", b"MDJPPAT2")]

SRC = r'''
start:
    mov ax, cs
    add ax, 0x1000
    mov word ptr [{OUTSEG}], ax
    add ax, 0x1000
    mov word ptr [{INSEG}], ax
    add ax, 0x1000
    mov word ptr [{DICTSEG}], ax
    add ax, 0x1000
    mov word ptr [{CMPSEG}], ax
    add ax, 0x1000
    mov word ptr [{DECSEG}], ax
    add ax, 0x1000
    mov word ptr [{PATSEG}], ax
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
    mov word ptr [{PBPOS}], 0
    mov word ptr [{PBLEN}], 0
    mov dx, {BUF}
    mov cx, 18
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
    cmp ax, 24
    ja bad
    mov word ptr [{NFILES}], ax
    mov si, {BUF}+10
    mov di, {STAMP}
    mov cx, 8
    rep movsb
    mov cx, word ptr [{NFILES}]
    shl cx, 1
    shl cx, 1
    shl cx, 1
    shl cx, 1
    mov dx, {FTAB}
    call rd_dat
    jc bad
    ; 組み立て済みか: 印のファイルの版が同じで、作るファイルが全部、決まった大きさであれば何もしない
    mov ax, 0x3d00
    mov dx, {OKNAME}
    int 0x21
    jc full
    mov bx, ax
    mov ah, 0x3f
    mov cx, 8
    mov dx, {BUF2}
    int 0x21
    pushf
    push ax
    mov ah, 0x3e
    int 0x21
    pop ax
    popf
    jc full
    cmp ax, 8
    jne full
    mov si, {BUF2}
    mov di, {STAMP}
    mov cx, 8
    push ds
    pop es
    cld
    repe cmpsb
    jne full
    mov ax, word ptr [{NFILES}]
    mov word ptr [{NCHK}], ax
    mov si, {FTAB}
qc_l:
    cmp word ptr [{NCHK}], 0
    je qc_ok
    dec word ptr [{NCHK}]
    push si
    call copy_name
    pop si
    mov ax, 0x3d00
    mov dx, {NAMEBUF}
    int 0x21
    jc full
    mov bx, ax
    mov ax, 0x4202
    xor cx, cx
    xor dx, dx
    int 0x21
    pushf
    push ax
    push dx
    mov ah, 0x3e
    int 0x21
    pop dx
    pop ax
    popf
    jc full
    cmp ax, word ptr [si+12]
    jne full
    cmp dx, word ptr [si+14]
    jne full
    add si, 16
    jmp qc_l
qc_ok:
    mov dx, {M_DONE}
    mov ah, 9
    int 0x21
    jmp done_x
full:
    mov byte ptr [{SKIPPED}], 0
    mov ah, 0x41
    mov dx, {OKNAME}
    int 0x21
file_loop:
    cmp word ptr [{NFILES}], 0
    jne fl_more
    jmp done
fl_more:
    dec word ptr [{NFILES}]
    mov dx, {HDR}
    mov cx, 34
    call rd_dat
    jc bad
    mov ax, word ptr [{HDR}+32]
    mov word ptr [{NOPS}], ax
    mov byte ptr [{SKIP}], 0
    mov word ptr [{OUTPOS}], 0
    mov word ptr [{DECLEN}], 0
    mov si, {HDR}+12
    call put_name
    ; 元のファイルを開いて、大きさとハッシュを確かめる
    mov si, {HDR}
    call copy_name
    mov ax, 0x3d00
    mov dx, {NAMEBUF}
    int 0x21
    jc f_skip
    mov word ptr [{HSRC}], ax
    xor ax, ax
    mov word ptr [{SZLO}], ax
    mov word ptr [{SZHI}], ax
    mov word ptr [{H1}], ax
    mov word ptr [{H2}], ax
hs_loop:
    mov bx, word ptr [{HSRC}]
    mov cx, 0xf000
    mov ax, word ptr [{INSEG}]
    push ds
    mov ds, ax
    xor dx, dx
    mov ah, 0x3f
    int 0x21
    pop ds
    jc f_skipc
    or ax, ax
    jz hs_end
    add word ptr [{SZLO}], ax
    adc word ptr [{SZHI}], 0
    mov cx, ax
    mov bx, word ptr [{H1}]
    mov dx, word ptr [{H2}]
    mov ax, word ptr [{INSEG}]
    push ds
    mov ds, ax
    xor si, si
    cld
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
    pop ds
    mov word ptr [{H1}], bx
    mov word ptr [{H2}], dx
    jmp hs_loop
hs_end:
    mov ax, word ptr [{SZLO}]
    cmp ax, word ptr [{HDR}+24]
    jne f_skipc
    mov ax, word ptr [{SZHI}]
    cmp ax, word ptr [{HDR}+26]
    jne f_skipc
    mov ax, word ptr [{H1}]
    cmp ax, word ptr [{HDR}+28]
    jne f_skipc
    mov ax, word ptr [{H2}]
    cmp ax, word ptr [{HDR}+30]
    jne f_skipc
    ; 日本語版を作る
    mov si, {HDR}+12
    call copy_name
    mov ah, 0x3c
    xor cx, cx
    mov dx, {NAMEBUF}
    int 0x21
    jc f_skipc
    mov word ptr [{HDST}], ax
    jmp ops
f_skipc:
    mov bx, word ptr [{HSRC}]
    mov ah, 0x3e
    int 0x21
f_skip:
    mov byte ptr [{SKIP}], 1
    mov byte ptr [{SKIPPED}], 1
    mov si, {HDR}+12
    call copy_name
    mov ah, 0x41
    mov dx, {NAMEBUF}
    int 0x21
ops:
    cmp word ptr [{NOPS}], 0
    jne ops_more
    jmp f_end
ops_more:
    dec word ptr [{NOPS}]
    mov dx, {OPT}
    mov cx, 1
    call rd_dat
    jc bad
    mov al, byte ptr [{OPT}]
    cmp al, 0
    je op_f
    cmp al, 1
    je op_d
    cmp al, 2
    je op_z
    cmp al, 3
    jne bad
    jmp op_c

; 0: 元のファイルから写す（位置 4、長さ 4）
op_f:
    mov dx, {ARGS}
    mov cx, 8
    call rd_dat
    jc bad
    cmp byte ptr [{SKIP}], 0
    jne ops
    call seek_src
of_l:
    mov ax, word ptr [{ARGS}+4]
    or ax, word ptr [{ARGS}+6]
    jz ops
    mov cx, 0xf000
    cmp word ptr [{ARGS}+6], 0
    jne of_n
    cmp word ptr [{ARGS}+4], cx
    jae of_n
    mov cx, word ptr [{ARGS}+4]
of_n:
    sub word ptr [{ARGS}+4], cx
    sbb word ptr [{ARGS}+6], 0
    mov bx, word ptr [{HSRC}]
    call rd_seg
    mov ax, word ptr [{INSEG}]
    xor si, si
    call put
    jmp of_l

; 1: 書く（長さ 2、バイト列）
op_d:
    mov dx, {OPLEN}
    mov cx, 2
    call rd_dat
    jc bad
    mov cx, word ptr [{OPLEN}]
    cmp cx, 0xf000
    ja bad
    mov es, word ptr [{INSEG}]
    xor di, di
    call pat_read
    jc bad
    mov cx, word ptr [{OPLEN}]
    cmp byte ptr [{SKIP}], 0
    jne ops
    mov ax, word ptr [{INSEG}]
    xor si, si
    call put
    jmp ops

; 2: LZW の項目を展開する（位置 4、長さ 2）
op_z:
    mov dx, {ARGS}
    mov cx, 6
    call rd_dat
    jc bad
    cmp byte ptr [{SKIP}], 0
    jne ops
    mov cx, word ptr [{ARGS}+4]
    cmp cx, 0x1f00
    ja bad
    call seek_src
    mov bx, word ptr [{HSRC}]
    mov ax, word ptr [{CMPSEG}]
    push ds
    mov ds, ax
    xor dx, dx
    mov ah, 0x3f
    push cx
    int 0x21
    pop cx
    pop ds
    jc bad
    cmp ax, cx
    jne bad
    mov ax, word ptr [{CMPSEG}]
    mov es, ax
    mov di, cx
    mov word ptr es:[di], 0
    mov word ptr es:[di+2], 0
    shl cx, 1
    shl cx, 1
    shl cx, 1
    mov word ptr [{NBITS}], cx
    call lzw
    jc bad
    jmp ops

; 3: 展開した中身から写す（位置 2、長さ 2）
op_c:
    mov dx, {ARGS}
    mov cx, 4
    call rd_dat
    jc bad
    cmp byte ptr [{SKIP}], 0
    je oc_go
    jmp ops
oc_go:
    mov si, word ptr [{ARGS}]
    mov cx, word ptr [{ARGS}+2]
    mov ax, si
    add ax, cx
    jc bad
    cmp ax, word ptr [{DECLEN}]
    ja bad
    mov ax, word ptr [{DECSEG}]
    call put
    jmp ops

f_end:
    cmp byte ptr [{SKIP}], 0
    jne f_msk
    call flush
    mov bx, word ptr [{HDST}]
    mov ah, 0x3e
    int 0x21
    mov bx, word ptr [{HSRC}]
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
    cmp byte ptr [{SKIPPED}], 0
    jne done_x
    mov ah, 0x3c
    xor cx, cx
    mov dx, {OKNAME}
    int 0x21
    jc done_x
    mov bx, ax
    mov ah, 0x40
    mov cx, 8
    mov dx, {STAMP}
    int 0x21
    mov ah, 0x3e
    int 0x21
done_x:
    mov bx, word ptr [{HDAT}]
    mov ah, 0x3e
    int 0x21
    mov ax, 0x4c00
    int 0x21
bad:
    mov dx, {M_BAD}
die:
    push cs
    pop ds
    mov ah, 9
    int 0x21
    mov ax, 0x4c01
    int 0x21

; MDJP.PAT から CX バイトを DS:DX へ読む（足りなければ CF=1）
rd_dat:
    push ds
    pop es
    mov di, dx
    jmp pat_read

; MDJP.PAT から CX バイトを ES:DI へ読む（PATSEG に 0xF000 バイトずつまとめて読んでおく。足りなければ CF=1）
pat_read:
    push si
pr_l:
    jcxz pr_ok
    mov ax, word ptr [{PBLEN}]
    sub ax, word ptr [{PBPOS}]
    jnz pr_have
    push cx
    push di
    push es
    mov bx, word ptr [{HDAT}]
    mov cx, 0xf000
    mov ax, word ptr [{PATSEG}]
    push ds
    mov ds, ax
    xor dx, dx
    mov ah, 0x3f
    int 0x21
    pop ds
    pop es
    pop di
    pop cx
    jc pr_bad
    mov word ptr [{PBLEN}], ax
    mov word ptr [{PBPOS}], 0
    or ax, ax
    jz pr_bad
pr_have:
    cmp ax, cx
    jbe pr_n
    mov ax, cx
pr_n:
    mov word ptr [{PRN}], ax
    push cx
    mov cx, ax
    mov si, word ptr [{PBPOS}]
    add word ptr [{PBPOS}], ax
    mov ax, word ptr [{PATSEG}]
    push ds
    mov ds, ax
    cld
    rep movsb
    pop ds
    pop cx
    sub cx, word ptr [{PRN}]
    jmp pr_l
pr_ok:
    pop si
    clc
    ret
pr_bad:
    pop si
    stc
    ret

; ハンドル BX から CX バイトを INSEG:0 へ読む（足りなければ終わる）
rd_seg:
    mov ax, word ptr [{INSEG}]
    push ds
    mov ds, ax
    xor dx, dx
    mov ah, 0x3f
    push cx
    int 0x21
    pop cx
    pop ds
    jc bad
    cmp ax, cx
    jne bad
    ret

; 元のファイルを ARGS の位置（4 バイト）へ
seek_src:
    push cx
    mov ax, 0x4200
    mov bx, word ptr [{HSRC}]
    mov dx, word ptr [{ARGS}]
    mov cx, word ptr [{ARGS}+2]
    int 0x21
    pop cx
    jc bad
    ret

; AX:SI から CX バイトを出力にためる（あふれそうなら先に書き出す）
put:
    jcxz p_ret
    push ax
    mov dx, word ptr [{OUTPOS}]
    add dx, cx
    jc p_fl
    cmp dx, 0xf000
    jbe p_cp
p_fl:
    call flush
p_cp:
    pop ax
    mov di, word ptr [{OUTPOS}]
    add word ptr [{OUTPOS}], cx
    mov es, word ptr [{OUTSEG}]
    push ds
    mov ds, ax
    cld
    rep movsb
    pop ds
p_ret:
    ret

flush:
    push cx
    push si
    mov cx, word ptr [{OUTPOS}]
    jcxz fl_x
    mov bx, word ptr [{HDST}]
    mov ax, word ptr [{OUTSEG}]
    push ds
    mov ds, ax
    xor dx, dx
    mov ah, 0x40
    push cx
    int 0x21
    pop cx
    pop ds
    jc bad
    cmp ax, cx
    jne bad
    mov word ptr [{OUTPOS}], 0
fl_x:
    pop si
    pop cx
    ret

; ---- U6 の LZW の展開: CMPSEG:0（先頭 4 バイトは大きさ）→ DECSEG:0、長さは DECLEN ----
;   符号は 9 ビットから 12 ビット、下位のビットから。0x100 = 初めから、0x101 = 終わり
;   表は DICTSEG: 0〜0x1FFF 前の符号（2 バイト）、0x2000〜0x2FFF 足す字、0x3000〜0x3FFF 字を逆に積む所
lzw:
    mov word ptr [{BITPOS}], 32
    mov word ptr [{DECLEN}], 0
lz_reset:
    mov word ptr [{CBITS}], 9
    mov word ptr [{NEXT}], 258
    mov word ptr [{PREV}], 0xffff
lz_loop:
    mov ax, word ptr [{BITPOS}]
    add ax, word ptr [{CBITS}]
    jc lz_end
    cmp ax, word ptr [{NBITS}]
    ja lz_end
    call getcode
    cmp ax, 0x100
    je lz_reset
    cmp ax, 0x101
    je lz_end
    mov word ptr [{CUR}], ax
    cmp word ptr [{PREV}], 0xffff
    jne lz_2
    cmp ax, 0x100
    jae lz_bad
    call outbyte
    jc lz_bad
    jmp lz_next
lz_2:
    cmp ax, word ptr [{NEXT}]
    ja lz_bad
    je lz_kwk
    call emit
    jc lz_bad
    jmp lz_add
lz_kwk:
    mov ax, word ptr [{PREV}]
    call emit
    jc lz_bad
    mov al, byte ptr [{FIRST}]
    call outbyte
    jc lz_bad
lz_add:
    mov bx, word ptr [{NEXT}]
    cmp bx, 4096
    jae lz_inc
    mov es, word ptr [{DICTSEG}]
    mov al, byte ptr [{FIRST}]
    mov byte ptr es:[bx+0x2000], al
    shl bx, 1
    mov ax, word ptr [{PREV}]
    mov word ptr es:[bx], ax
lz_inc:
    inc word ptr [{NEXT}]
    mov cx, word ptr [{CBITS}]
    cmp cx, 12
    jae lz_next
    mov dx, 1
    shl dx, cl
    cmp word ptr [{NEXT}], dx
    jb lz_next
    inc word ptr [{CBITS}]
lz_next:
    mov ax, word ptr [{CUR}]
    mov word ptr [{PREV}], ax
    jmp lz_loop
lz_end:
    clc
    ret
lz_bad:
    stc
    ret

getcode:
    mov ax, word ptr [{BITPOS}]
    mov bx, ax
    shr bx, 1
    shr bx, 1
    shr bx, 1
    mov cl, al
    and cl, 7
    mov es, word ptr [{CMPSEG}]
    mov ax, word ptr es:[bx]
    mov dl, byte ptr es:[bx+2]
    xor ch, ch
    jcxz gc_m
gc_s:
    shr dl, 1
    rcr ax, 1
    loop gc_s
gc_m:
    mov cx, word ptr [{CBITS}]
    mov dx, 1
    shl dx, cl
    dec dx
    and ax, dx
    add word ptr [{BITPOS}], cx
    ret

outbyte:
    mov di, word ptr [{DECLEN}]
    cmp di, 0xfff0
    jae ob_bad
    mov es, word ptr [{DECSEG}]
    mov byte ptr es:[di], al
    inc word ptr [{DECLEN}]
    clc
    ret
ob_bad:
    stc
    ret

emit:
    mov es, word ptr [{DICTSEG}]
    mov di, 0x4000
em_l:
    cmp ax, 0x100
    jb em_r
    cmp ax, 4096
    jae em_bad
    cmp di, 0x3001
    jb em_bad
    mov bx, ax
    mov dl, byte ptr es:[bx+0x2000]
    dec di
    mov byte ptr es:[di], dl
    shl bx, 1
    mov ax, word ptr es:[bx]
    jmp em_l
em_r:
    dec di
    mov byte ptr es:[di], al
    mov byte ptr [{FIRST}], al
    mov cx, 0x4000
    sub cx, di
    mov ax, word ptr [{DECLEN}]
    add ax, cx
    jc em_bad
    cmp ax, 0xfff0
    ja em_bad
    mov si, di
    mov di, word ptr [{DECLEN}]
    mov word ptr [{DECLEN}], ax
    mov ax, word ptr [{DECSEG}]
    push ds
    push es
    pop ds
    mov es, ax
    cld
    rep movsb
    pop ds
    clc
    ret
em_bad:
    stc
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

; 「MDJPMK: 名前」を出す
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
