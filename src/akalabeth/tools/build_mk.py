# 日本語版の本体 AKJP.EXE を遊ぶ人の所で組み立てる DOS のプログラム AKJPMK.COM を作る
#   python tools/build_mk.py <出力 AKJPMK.COM>
#
# AKJPMK.COM は、いまのフォルダの AKJP.PAT（make_patch.py が作る）と元の AK.EXE から AKJP.EXE を作る。
#   - 変えていないブロックは元の圧縮のまま写す
#   - 変えたブロックは展開し、元と同じか検算してから差分を当て、無圧縮（4KB そのまま）で書く
# AK.EXE の大きさや中身が違うときは作らない（古い AKJP.EXE も消す）。そのときは英語版で遊べる。
# 手本は make_patch.apply()。
import os, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

HEAD = 0x2a41          # WFSE の見出しの終わり（ここからブロックの表）
DATA = 0x0c00          # 変数と文字列の置き場（コードはこれより前）

V = {}
_p = DATA
for name, size in [('SEGA', 2), ('SEGP', 2), ('HPAT', 2), ('HIN', 2), ('HOUT', 2), ('PATLEN', 2),
                   ('SIZE', 4), ('USIZE', 4), ('NBLK', 2), ('NCHG', 2), ('TOTAL', 4), ('BASE', 2),
                   ('I', 2), ('OSTART', 4), ('OSIZE', 2), ('NSIZE', 2), ('CHGP', 2)]:
    V[name] = _p; _p += size
MSGS = [('PATNAME', b'AKJP.PAT\0'), ('EXENAME', b'AK.EXE\0'), ('OUTNAME', b'AKJP.EXE\0'),
        ('MAGIC', b'AKJPPAT1'),
        ('M_MEM', b'AKJPMK: not enough memory.\r\n$'),
        ('M_NOPAT', b'AKJPMK: AKJP.PAT not found.\r\n$'),
        ('M_BADPAT', b'AKJPMK: AKJP.PAT is broken.\r\n$'),
        ('M_NOEXE', b'AKJPMK: AK.EXE not found.\r\n$'),
        ('M_DIFF', b'AKJPMK: AK.EXE differs from the expected version. Japanese version not made.\r\n$'),
        ('M_IO', b'AKJPMK: file error.\r\n$'),
        ('M_OK', b'AKJPMK: AKJP.EXE ok\r\n$')]
for name, b in MSGS:
    V[name] = _p; _p += len(b)
V['CHG'] = (_p + 1) & ~1; _p = V['CHG'] + 2 * 1024
END = _p

SRC = r'''
start:
    mov ax, cs
    add ax, 0x1000
    mov word ptr [{SEGA}], ax
    add ax, 0x1000
    mov word ptr [{SEGP}], ax
    add ax, 0x1000
    cmp ax, word ptr [2]
    jbe mem_ok
    mov dx, {M_MEM}
    jmp die
mem_ok:
    mov word ptr [{HOUT}], 0
; ---- AKJP.PAT を読む
    mov ax, 0x3d00
    mov dx, {PATNAME}
    int 0x21
    jnc pat_open
    mov dx, {M_NOPAT}
    jmp die
pat_open:
    mov bx, ax
    mov ah, 0x3f
    mov cx, 0xfff0
    xor dx, dx
    mov si, word ptr [{SEGP}]
    call dos_seg
    jc bad_pat
    mov word ptr [{PATLEN}], ax
    mov ah, 0x3e
    int 0x21
    mov es, word ptr [{SEGP}]
    xor di, di
    mov si, {MAGIC}
    mov cx, 8
    cld
    repe cmpsb
    jne bad_pat
    mov eax, dword ptr es:[8]
    mov dword ptr [{SIZE}], eax
    mov eax, dword ptr es:[12]
    mov dword ptr [{USIZE}], eax
    mov ax, word ptr es:[16]
    mov word ptr [{NBLK}], ax
    cmp ax, 1024
    ja bad_pat
    or ax, ax
    jz bad_pat
    mov ax, word ptr es:[18]
    mov word ptr [{NCHG}], ax
; ---- 変えたブロックの表 CHG[i] = PAT の中の位置（0 = 変えていない）
    push es
    push ds
    pop es
    mov di, {CHG}
    mov cx, 1024
    xor ax, ax
    rep stosw
    pop es
    mov si, 20
    mov cx, word ptr [{NCHG}]
    jcxz chg_done
chg_loop:
    lea ax, [si + 6]
    cmp ax, word ptr [{PATLEN}]
    ja bad_pat
    mov bx, word ptr es:[si]
    cmp bx, word ptr [{NBLK}]
    jae bad_pat
    shl bx, 1
    mov word ptr [{CHG} + bx], si
    mov dx, word ptr es:[si + 4]
    add si, 6
rec_skip:
    or dx, dx
    jz rec_done
    xor ax, ax
    mov al, byte ptr es:[si + 2]
    add si, 3
    add si, ax
    jc bad_pat
    cmp si, word ptr [{PATLEN}]
    ja bad_pat
    dec dx
    jmp rec_skip
rec_done:
    loop chg_loop
chg_done:
; ---- AK.EXE を開いて確かめる
    mov ax, 0x3d00
    mov dx, {EXENAME}
    int 0x21
    jnc exe_open
    mov dx, {M_NOEXE}
    jmp fail
exe_open:
    mov word ptr [{HIN}], ax
    mov bx, ax
    mov ax, 0x4202
    xor cx, cx
    xor dx, dx
    int 0x21
    jc io_err
    cmp ax, word ptr [{SIZE}]
    jne differs
    cmp dx, word ptr [{SIZE} + 2]
    jne differs
    mov ax, 0x4200
    xor cx, cx
    xor dx, dx
    int 0x21
    jc io_err
    mov cx, word ptr [{NBLK}]
    shl cx, 2
    add cx, {HEAD}
    mov word ptr [{BASE}], cx
    mov ah, 0x3f
    xor dx, dx
    mov si, word ptr [{SEGA}]
    call dos_seg
    jc io_err
    cmp ax, word ptr [{BASE}]
    jne differs
    mov es, word ptr [{SEGA}]
    cmp dword ptr es:[{WFSE}], 0x45534657
    jne differs
    mov eax, dword ptr es:[{WFSE} + 8]
    cmp eax, dword ptr [{USIZE}]
    jne differs
    mov eax, dword ptr es:[{WFSE} + 4]
    mov dword ptr [{TOTAL}], eax
; ---- 新しい表（SEGA:0x3000）と全体の大きさ
    xor edx, edx
    xor si, si
tab_loop:
    call blkinfo
    jc differs
    mov bx, si
    shl bx, 2
    mov dword ptr es:[0x3000 + bx], edx
    movzx eax, word ptr [{OSIZE}]
    cmp word ptr [{CHGP}], 0
    je tab_old
    movzx eax, word ptr [{NSIZE}]
tab_old:
    add edx, eax
    inc si
    cmp si, word ptr [{NBLK}]
    jb tab_loop
    movzx eax, word ptr [{NBLK}]
    shl eax, 2
    add eax, 0x20
    add eax, edx
    mov dword ptr es:[{WFSE} + 4], eax
; ---- AKJP.EXE を作る
    mov ah, 0x3c
    xor cx, cx
    mov dx, {OUTNAME}
    int 0x21
    jc io_err
    mov word ptr [{HOUT}], ax
    mov bx, ax
    mov ah, 0x40
    mov cx, {HEAD}
    xor dx, dx
    mov si, word ptr [{SEGA}]
    call dos_seg
    jc io_err
    mov ah, 0x40
    mov cx, word ptr [{NBLK}]
    shl cx, 2
    mov dx, 0x3000
    call dos_seg
    jc io_err
; ---- ブロックを順に
    mov word ptr [{I}], 0
blk_loop:
    mov si, word ptr [{I}]
    mov es, word ptr [{SEGA}]
    call blkinfo
    jc differs
    cmp word ptr [{OSIZE}], 0x1000
    ja differs
    mov eax, dword ptr [{OSTART}]
    movzx ecx, word ptr [{BASE}]
    add eax, ecx
    mov dx, ax
    shr eax, 16
    mov cx, ax
    mov bx, word ptr [{HIN}]
    mov ax, 0x4200
    int 0x21
    jc io_err
    mov ah, 0x3f
    mov cx, word ptr [{OSIZE}]
    mov dx, 0x4000
    mov si, word ptr [{SEGA}]
    call dos_seg
    jc io_err
    cmp ax, word ptr [{OSIZE}]
    jne differs
    cmp word ptr [{CHGP}], 0
    jne blk_change
    mov bx, word ptr [{HOUT}]
    mov ah, 0x40
    mov cx, word ptr [{OSIZE}]
    mov dx, 0x4000
    call dos_seg
    jc io_err
    jmp blk_next
blk_change:
    push ds
    mov ax, word ptr [{SEGA}]
    mov bx, word ptr [{NSIZE}]
    mov cx, word ptr [{OSIZE}]
    mov ds, ax
    mov es, ax
    mov si, 0x4000
    mov di, 0x6000
    cmp cx, bx
    jne blk_unpack
    cld
    rep movsb
    jmp blk_unpacked
blk_unpack:
    call decomp
blk_unpacked:
    mov si, 0x6000
    mov cx, bx
    xor ax, ax
ck_loop:
    rol ax, 1
    add al, byte ptr [si]
    adc ah, 0
    inc si
    loop ck_loop
    pop ds
    mov es, word ptr [{SEGP}]
    mov si, word ptr [{CHGP}]
    cmp ax, word ptr es:[si + 2]
    jne differs
    mov dx, word ptr es:[si + 4]
    add si, 6
    push ds
    mov ax, word ptr [{SEGA}]
    mov es, ax
    mov ds, word ptr [{SEGP}]
ap_loop:
    or dx, dx
    jz ap_done
    mov di, word ptr [si]
    add di, 0x6000
    xor cx, cx
    mov cl, byte ptr [si + 2]
    add si, 3
    cld
    rep movsb
    dec dx
    jmp ap_loop
ap_done:
    pop ds
    mov bx, word ptr [{HOUT}]
    mov ah, 0x40
    mov cx, word ptr [{NSIZE}]
    mov dx, 0x6000
    mov si, word ptr [{SEGA}]
    call dos_seg
    jc io_err
blk_next:
    inc word ptr [{I}]
    mov ax, word ptr [{I}]
    cmp ax, word ptr [{NBLK}]
    jb blk_loop
; ---- おわり
    mov bx, word ptr [{HOUT}]
    mov ah, 0x3e
    int 0x21
    mov bx, word ptr [{HIN}]
    mov ah, 0x3e
    int 0x21
    mov dx, {M_OK}
    mov ah, 9
    int 0x21
    mov ax, 0x4c00
    int 0x21

bad_pat:
    mov dx, {M_BADPAT}
    jmp fail
io_err:
    mov dx, {M_IO}
    jmp fail
differs:
    mov dx, {M_DIFF}
fail:
    push cs
    pop ds
    mov ah, 9
    int 0x21
    mov bx, word ptr [{HOUT}]
    or bx, bx
    jz fail_del
    mov ah, 0x3e
    int 0x21
fail_del:
    mov ah, 0x41
    mov dx, {OUTNAME}
    int 0x21
    mov ax, 0x4c01
    int 0x21
die:
    mov ah, 9
    int 0x21
    mov ax, 0x4c01
    int 0x21

; DOS の読み書き（ah, bx, cx, dx はそのまま）を、データの区画 si で行う
dos_seg:
    push ds
    mov ds, si
    int 0x21
    pop ds
    ret

; ブロック si の情報: OSTART, OSIZE, NSIZE, CHGP（es = SEGA、edx は壊さない）
blkinfo:
    push edx
    mov bx, si
    shl bx, 2
    mov eax, dword ptr es:[{HEAD} + bx]
    mov dword ptr [{OSTART}], eax
    lea ax, [si + 1]
    cmp ax, word ptr [{NBLK}]
    jb bi_mid
    mov ecx, dword ptr [{TOTAL}]
    movzx edx, word ptr [{NBLK}]
    shl edx, 2
    add edx, 0x20
    sub ecx, edx
    mov edx, dword ptr [{USIZE}]
    and dx, 0xfff
    jnz bi_n
    mov dx, 0x1000
    jmp bi_n
bi_mid:
    mov ecx, dword ptr es:[{HEAD} + 4 + bx]
    mov dx, 0x1000
bi_n:
    mov word ptr [{NSIZE}], dx
    sub ecx, dword ptr [{OSTART}]
    jb bi_bad
    cmp ecx, 0x1000
    ja bi_bad
    mov word ptr [{OSIZE}], cx
    mov bx, si
    shl bx, 1
    mov ax, word ptr [{CHG} + bx]
    mov word ptr [{CHGP}], ax
    pop edx
    clc
    ret
bi_bad:
    pop edx
    stc
    ret

; WDOSX の展開（ds:si → es:di、bx バイト）。AK.EXE の先頭の展開処理と同じ
decomp:
    push bp
    push bx
    cld
    mov dl, 0x80
    add bx, di
    movsb
d_lit_after:
    mov dh, 0x80
d_loop:
    cmp di, bx
    jae d_end
    call getbit
    jnc d_lit
    mov ax, 1
    mov cx, ax
d_g1:
    call getbit
    adc cx, cx
    call getbit
    jc d_g1
d_g2:
    call getbit
    adc ax, ax
    call getbit
    jc d_g2
    add dh, dh
    sbb ax, 2
    jb d_rep
    or ax, 0x400
d_b6:
    call getbit
    adc ax, ax
    jnc d_b6
    inc ax
    cmp ax, 0x781
    sbb cx, -1
    mov bp, ax
d_rep:
    mov ax, bp
    push si
    mov si, di
    sub si, ax
    rep movsb
    pop si
    jmp d_loop
d_lit:
    movsb
    jmp d_lit_after
d_end:
    pop bx
    pop bp
    ret
getbit:
    add dl, dl
    jnz gb_ret
    mov dl, byte ptr [si]
    inc si
    adc dl, dl
gb_ret:
    ret
'''


def build():
    v = dict(V); v['HEAD'] = HEAD; v['WFSE'] = 0x2a21
    src = SRC.format(**v)
    src = '\n'.join(l.split(';')[0] for l in src.split('\n'))   # 日本語の注釈は除く
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    code, _ = ks.asm(src, 0x100)
    code = bytes(code)
    if 0x100 + len(code) > DATA:
        raise SystemExit('コードが長すぎる: %d' % len(code))
    last = max(V[name] + len(b) for name, b in MSGS)
    img = bytearray(code) + bytes(last - 0x100 - len(code))
    for name, b in MSGS:
        img[V[name] - 0x100:V[name] - 0x100 + len(b)] = b
    # CHG などの変数は 0 でよいので、文字列の後ろまでで切る
    last = max(V[name] + len(b) for name, b in MSGS)
    return bytes(img[:last - 0x100])


if __name__ == '__main__':
    com = build()
    assert END < 0xfff0
    open(sys.argv[1], 'wb').write(com)
    print('AKJPMK.COM %d バイト' % len(com))
