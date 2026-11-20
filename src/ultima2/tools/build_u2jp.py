# ウルティマII 用の常駐プログラム U2JP.COM を作る
#   - INT 10h AH=09h（1文字を書く）を横取りして日本語を描く
#       CGA のグラフィック画面: 字の形を INT 1Fh のフォント表の 0xFE に写して BIOS に描かせる
#       文字画面: 字の形を縦2倍にして、表示側のフォント表の空き番号に読み込む（AX=1100h）
#   - 2バイトの組（リード＋トレイル）は、リードの位置を覚えておき、トレイルが来たら2マスまとめて描く
#   - 本体が起動直後に呼ぶ INT 10h AX=0001h（呼び出し元 0x4A22）を合図に、中身を照合してからメモリ上で書き換える
#   - 1文字関数の先頭の and al,7Fh（0x5007）を int 66h にする。文字列から来た文字だけ最上位ビットを残す
#   - 元より長い訳は、呼び出しを int 67h にして、常駐部の中の訳を書く
#   - 会話ファイル（TLK…）は、INT 21h AH=27h で読み込んだ直後に日本語の中身へ差し替える
# 使い方: python build_u2jp.py <ULTIMAII.EXE> <訳のファイル> <出力 U2JP.COM>
#   訳のファイル: 「位置（16進）<TAB>訳」または「TLKX03.0001<TAB>訳」。\n は改行
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import jpenc  # noqa: E402
from jpenc import Encoder, load_bdf, is_jp, fix16, FAR_JMP, FAR_CALL  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

# ウルティマII では1バイトが必ず1マスなので、日本語の字はどの英数字とも組にしてよい
jpenc.PAIR_ASCII = set(chr(c) for c in range(0x20, 0x7F))

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

PUTS = 0x4FDF                # 埋め込み文字列を書く関数
PUTC = 0x5003                # 1文字を書く関数
TRIGGER_IP = 0x4A22          # INT 10h AX=0001h の直後
SIG_OFF = 0x4FDF             # 照合に使う16バイト（書き換えない場所）
AND7F = 0x5007               # 24 7F = and al,7Fh
TALK_PUTC = 0x157B           # 会話・うわさを書く関数の中の call 0x53F4 → call PUTC に付け替える
# 0 区切りの文字列の表（終わりは最後の 0 の次）。番号で引くので、順番と件数は変えない
TABLES = [(0x4C60, 0x4F04),  # 地形、武器、防具、呪文、品物、能力、種族、職業
          (0x16BC, 0x1799),  # 酒場のうわさ
          (0x1B6A, 0x1D1D)]  # 謎かけの手がかり
# 文字画面に出る文字列（クレジット、メニュー、キャラクター作成、ディスクの案内、ステータス画面）
TEXT_KEYS = {0x0014E, 0x00161, 0x00190, 0x001A4, 0x001C7, 0x001ED, 0x00253, 0x0026A, 0x0027F, 0x00294,
             0x002F0, 0x00304, 0x0032B, 0x00357, 0x00381, 0x0549E, 0x054BF, 0x054F4, 0x0575B, 0x05788,
             0x057C9, 0x057F7, 0x05823, 0x05854, 0x0589E, 0x058CE, 0x058FD, 0x0592F, 0x007C6, 0x0546B,
             0x05489, 0x05A43, 0x0531E, 0x04583, 0x045C7, 0x045EC, 0x0460D, 0x04632, 0x04650, 0x04672,
             0x0474B, 0x04774, 0x047A5, 0x047CD, 0x047FD, 0x04825, 0x04856, 0x04884, 0x04889, 0x05069,
             0x05072}
INT66, INT67 = 0x66, 0x67
KEEP_HI = (0x4FFE, 0x50B0, TALK_PUTC + 3)   # 1文字関数の戻り先がこれなら最上位ビットを残す
TLK_SIZE = 256               # 会話ファイルは 256 バイト読み込まれる（DS:[0x476]）
STACK_SIZE = 512

# 文字画面で、日本語の字を読み込む番号（ゲームが文字画面で使わない番号）
# 0x01〜0x1F に読み込むと、そのあとの CGA 画面が崩れる（DOSBox の svga_s3 で確認）ので使わない
DYN = list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD)) + [0xFE, 0xFF]

# ---- 常駐部の変数（0x100 から）----
OLD10, LEAD, LEADPOS, DYNI, ATTR = 0x103, 0x107, 0x108, 0x10A, 0x10B
CURPOS, PA, PB = 0x10C, 0x10E, 0x110
OLD21, THUNK, OLDSS, OLDSP, INRELOC, RSTR = 0x112, 0x116, 0x11A, 0x11C, 0x11E, 0x11F
# ENABLED: 書き換えに成功したら 1（会話の差し替えもこのときだけ）。KEEPV1〜3: 最上位ビットを残す戻り先
# TRIEDCS: 書き換えを試したゲームのセグメント。FORCE: 試験用（1=必ず探す、2=見つからないふり）
ENABLED, KEEPV1, KEEPV2, KEEPV3, TRIEDCS, FORCE, RIDX, LISTN = (
    0x121, 0x122, 0x124, 0x126, 0x128, 0x12A, 0x12C, 0x12E)
# 見つけた場所: 文字列を書く関数、1文字を書く関数、表を引く関数、会話を書く所、3つの表
A_PUTS, A_PUTC, A_TABP, A_TALK, A_T0, A_T1, A_T2 = 0x130, 0x132, 0x134, 0x136, 0x138, 0x13A, 0x13C
CODE = 0x140

# 探す場所（GOG 版での位置、長さ、見つけた場所を入れる変数）。番地や変数の部分は「何でもよい」にして探す
#   文字列を書く関数: +0x1F が1文字関数からの戻り先。1文字を書く関数: +4 が and al,7Fh
#   表を引く関数: +0x24 が1文字関数からの戻り先。会話を書く所: +0x17 が call、+0x1A が戻り先
ANCHORS = [(0x4FDF, 0x24, A_PUTS), (0x5003, 0x10, A_PUTC), (0x508C, 0x27, A_TABP), (0x1564, 0x1C, A_TALK)]
SEARCH_START, SEARCH_END = 0x100, 0xA000
LISTMAX = 600

# int 66h: 1文字関数の先頭。戻り先を見て、最上位ビットを消すか決める
RES66 = r'''
    cmp byte ptr cs:[{INRELOC}], 0
    jne i66_ret
    push bp
    mov bp, sp
    push bx
    mov bx, word ptr [bp+16]
    cmp bx, word ptr cs:[{KEEPV1}]
    je i66_keep
    cmp bx, word ptr cs:[{KEEPV2}]
    je i66_keep
    cmp bx, word ptr cs:[{KEEPV3}]
    je i66_keep
    and al, 0x7f
i66_keep:
    pop bx
    pop bp
i66_ret:
    iret
'''

# int 67h: 長い訳。戻り先（元の文字列の位置 -1）で表を引き、常駐部の中の訳を1文字ずつ書く
#   1文字関数は、元の文字列の場所に置いた中継（call PUTC; retf）を far call して呼ぶ
RES67 = r'''
    push bp
    mov bp, sp
    push ax
    push bx
    push si
    mov ax, word ptr [bp+2]
    mov si, {RELOC}
r_find:
    cmp word ptr cs:[si], 0
    je r_out
    cmp word ptr cs:[si], ax
    je r_found
    add si, 6
    jmp r_find
r_found:
    mov bx, word ptr cs:[si+2]
    mov word ptr [bp+2], bx
    inc ax
    mov word ptr cs:[{THUNK}], ax
    mov ax, word ptr [bp+4]
    mov word ptr cs:[{THUNK}+2], ax
    mov ax, word ptr cs:[si+4]
    mov word ptr cs:[{RSTR}], ax
    mov word ptr cs:[{OLDSS}], ss
    mov word ptr cs:[{OLDSP}], sp
    cli
    push cs
    pop ss
    mov sp, {STACKTOP}
    sti
    pusha
    mov dl, byte ptr [0x2e]
    mov dh, byte ptr [0x2f]
    mov ah, 2
    mov bh, 0
    pushf
    {call_old10}
    mov byte ptr cs:[{INRELOC}], 1
    mov si, word ptr cs:[{RSTR}]
r_loop:
    mov al, byte ptr cs:[si]
    or al, al
    jz r_end
    inc si
    push si
    {call_thunk}
    pop si
    jmp r_loop
r_end:
    mov byte ptr cs:[{INRELOC}], 0
    popa
    cli
    mov ss, word ptr cs:[{OLDSS}]
    mov sp, word ptr cs:[{OLDSP}]
    sti
r_out:
    pop si
    pop bx
    pop ax
    pop bp
    iret
'''

# INT 21h: AH=27h で TLK… を読んだら、読み込み先（DTA）を日本語の中身に差し替える
RES21 = r'''
    cmp ah, 0x27
    je i21_chk
i21_chain:
    {jmp_old21}
i21_chk:
    cmp byte ptr cs:[{ENABLED}], 0
    je i21_chain
    push si
    mov si, dx
    cmp word ptr [si+1], 0x4c54
    jne i21_no
    cmp byte ptr [si+3], 0x4b
    jne i21_no
    pop si
    pushf
    {call_old21}
    pusha
    push ds
    push es
    mov si, dx
    mov ax, word ptr [si+4]
    mov dl, byte ptr [si+6]
    push ax
    push dx
    mov ah, 0x2f
    pushf
    {call_old21}
    pop dx
    pop ax
    push cs
    pop ds
    mov si, {TLKTAB}
t_find:
    cmp byte ptr [si], 0
    je t_strip
    cmp word ptr [si], ax
    jne t_next
    cmp byte ptr [si+2], dl
    je t_found
t_next:
    add si, 5
    jmp t_find
t_found:
    mov si, word ptr [si+3]
    lodsw
    mov cx, ax
    mov di, bx
    cld
    rep movsb
    mov cx, {TLK_SIZE}
    sub cx, ax
    xor al, al
    rep stosb
    jmp t_done
t_strip:
    mov cx, {TLK_SIZE}
t_s:
    and byte ptr es:[bx], 0x7f
    inc bx
    loop t_s
t_done:
    pop es
    pop ds
    popa
    iret
i21_no:
    pop si
    jmp i21_chain
'''

# INT 10h: 画面モードの切り替え（合図とフォント）と、1文字を書く（日本語）
RES = r'''
int10:
    cmp ah, 0
    je setmode
    cmp ah, 9
    je wchar
chain:
    {jmp_old}

setmode:
    push bp
    mov bp, sp
    cmp al, 1
    jne sm_call
    push ds
    push si
    lds si, dword ptr [bp+2]
    cmp word ptr [si-6], 0xb850
    jne sm_nt
    cmp word ptr [si-4], 0x0001
    jne sm_nt
    cmp word ptr [si-2], 0x10cd
    jne sm_nt
    mov si, ds
    cmp si, word ptr cs:[{TRIEDCS}]
    je sm_nt
    mov word ptr cs:[{TRIEDCS}], si
    pop si
    pop ds
    pusha
    push ds
    push es
    mov es, word ptr [bp+4]
    push cs
    pop ds
    mov word ptr [{OLDSS}], ss
    mov word ptr [{OLDSP}], sp
    cli
    push cs
    pop ss
    mov sp, {STACKTOP}
    sti
    call {PATCHALL}
    cli
    mov ss, word ptr cs:[{OLDSS}]
    mov sp, word ptr cs:[{OLDSP}]
    sti
    pop es
    pop ds
    popa
    jmp sm_call
sm_nt:
    pop si
    pop ds
sm_call:
    pop bp
    pushf
    {call_old}
    push ax
    push cx
    push di
    push ds
    push es
    xor ax, ax
    mov ds, ax
    cli
    mov word ptr [0x10c], {FONT}
    mov word ptr [0x10e], cs
    mov word ptr [0x7c], {FONT2}
    mov word ptr [0x7e], cs
    sti
    push cs
    pop es
    mov byte ptr cs:[{LEAD}], 0
    mov byte ptr cs:[{DYNI}], 0
    mov di, {SLOTGLY}
    mov cx, {NDYN}
    xor ax, ax
    cld
    rep stosw
    mov ax, 0x40
    mov ds, ax
    mov al, byte ptr [0x49]
    pop es
    pop ds
    pop di
    pop cx
    cmp al, 4
    pop ax
    jae sm_done
    call loadsingles
sm_done:
    iret

loadsingles:
    pusha
    push es
    push cs
    pop es
    mov si, {SINGLES}
    mov cx, {NSINGLE}
ls_loop:
    push cx
    mov dl, byte ptr cs:[si]
    xor dh, dh
    lea bp, [si+1]
    mov ax, 0x1100
    mov bx, 0x1000
    mov cx, 1
    pushf
    {call_old}
    add si, 17
    pop cx
    loop ls_loop
    pop es
    popa
    ret

wchar:
    cmp byte ptr cs:[{LEAD}], 0
    jne w_trail
    cmp al, 0x81
    jb chain
    cmp al, 0x9f
    jbe w_lead
    cmp al, 0xe0
    jb chain
    cmp al, 0xfc
    ja chain
w_lead:
    mov byte ptr cs:[{LEAD}], al
    push ax
    push bx
    push cx
    push dx
    mov ah, 3
    mov bh, 0
    pushf
    {call_old}
    mov word ptr cs:[{LEADPOS}], dx
    pop dx
    pop cx
    pop bx
    pop ax
    iret

w_trail:
    pusha
    push ds
    push es
    push cs
    pop ds
    push cs
    pop es
    mov byte ptr [{ATTR}], bl
    mov ah, byte ptr [{LEAD}]
    mov byte ptr [{LEAD}], 0
    mov si, {QMARK}
    mov word ptr [{PB}], 0
    cmp al, 0x40
    jb w_have
    mov cl, al
    mov al, ah
    sub al, 0x81
    cmp al, 0x1f
    jb w_leadok
    sub al, 0x40
w_leadok:
    mov bl, 0xc0
    mul bl
    sub cl, 0x40
    xor ch, ch
    add ax, cx
    cmp ax, word ptr [{NPAIRS}]
    jae w_have
    shl ax, 1
    shl ax, 1
    mov si, ax
    add si, {PAIRS}
    mov ax, word ptr [si+2]
    mov word ptr [{PB}], ax
    mov si, word ptr [si]
w_have:
    mov word ptr [{PA}], si
    mov ah, 3
    mov bh, 0
    pushf
    {call_old}
    mov word ptr [{CURPOS}], dx
    mov dx, word ptr [{LEADPOS}]
    mov si, word ptr [{PA}]
    call drawcell
    mov dx, word ptr [{CURPOS}]
    mov si, word ptr [{PB}]
    call drawcell
    mov dx, word ptr [{CURPOS}]
    mov ah, 2
    mov bh, 0
    pushf
    {call_old}
    pop es
    pop ds
    popa
    iret

drawcell:
    mov ah, 2
    mov bh, 0
    pushf
    {call_old}
    mov al, 0x20
    or si, si
    jz dc_write
    push ds
    mov ax, 0x40
    mov ds, ax
    mov al, byte ptr [0x49]
    pop ds
    cmp al, 4
    jb dc_text
    mov di, {SLOT}
    mov cx, 4
    cld
    rep movsw
    mov al, 0xfe
    jmp dc_write
dc_text:
    xor bx, bx
c_find:
    cmp bx, {NDYN2}
    jae c_miss
    cmp word ptr [bx+{SLOTGLY}], si
    je c_hit
    add bx, 2
    jmp c_find
c_hit:
    shr bx, 1
    mov al, byte ptr [bx+{DYNLIST}]
    jmp dc_write
c_miss:
    mov bl, byte ptr [{DYNI}]
    xor bh, bh
    mov al, bl
    inc al
    cmp al, {NDYN}
    jb c_ok
    xor al, al
c_ok:
    mov byte ptr [{DYNI}], al
    mov di, bx
    shl di, 1
    mov word ptr [di+{SLOTGLY}], si
    mov di, {BUF16}
    mov cx, 8
    cld
c_dbl:
    lodsb
    stosb
    stosb
    loop c_dbl
    mov al, byte ptr [bx+{DYNLIST}]
    push ax
    push dx
    mov dl, al
    xor dh, dh
    mov ax, 0x1100
    mov bx, 0x1000
    mov cx, 1
    mov bp, {BUF16}
    pushf
    {call_old}
    pop dx
    pop ax
dc_write:
    mov ah, 9
    mov bl, byte ptr [{ATTR}]
    mov bh, 0
    mov cx, 1
    pushf
    {call_old}
    ret
'''


# patch_all: ES = ゲームのセグメント、DS = 常駐部。場所を全部見つけてから書き換える。1つでも見つからなければ何もしない
#   元のバイト列は持たない（配布物に原作のデータを入れないため）。代わりにハッシュ値（h1, h2）で照合する
#   探す場所の表 ANCH（16バイトずつ）: GOG 版の位置、長さ、「何でもよい」の印（0=なし）、
#     絞り込みに使う 8 バイトの位置（「何でもよい」を含まない所）と、その 8 バイトの合計、全体の h1, h2、見つけた場所を入れる変数
#   GOG 版の位置で全部合えばそれを使う。合わなければ、8 バイトの合計を少しずつ更新しながら1回走査し、
#   合計が合う所だけハッシュ値を計算して、全部の探し物をまとめて探す（QBITS: 合計の下位バイトの早見表）
#   文字列の表 STRS（14バイトずつ）: GOG 版の位置、長さ、英文の h1, h2、書き込む中身、種類（0=その場所 1=長い訳）、
#                                     同じ英文の何番目か、見つけた場所
#   表の書き込み TABAP（6バイトずつ）: 見つけた場所の変数、書き込む中身、長さ
RESP = r'''
patch_all:
    cld
    mov byte ptr [{ENABLED}], 0
    mov word ptr [{LISTN}], 0xffff
    call anch_all
    jc pa_fail
    mov si, {STRS}
    mov cx, {NSTR}
pa_str:
    push cx
    push si
    call str_locate
    pop si
    pop cx
    jc pa_fail
    add si, 14
    dec cx
    jnz pa_str

    mov di, word ptr [{A_PUTC}]
    mov word ptr es:[di+4], 0x66cd
    mov di, word ptr [{A_TALK}]
    add di, 0x17
    mov ax, word ptr [{A_PUTC}]
    sub ax, di
    sub ax, 3
    mov word ptr es:[di+1], ax
    mov ax, word ptr [{A_PUTS}]
    add ax, 0x1f
    mov word ptr [{KEEPV1}], ax
    mov ax, word ptr [{A_TABP}]
    add ax, 0x24
    mov word ptr [{KEEPV2}], ax
    mov ax, word ptr [{A_TALK}]
    add ax, 0x1a
    mov word ptr [{KEEPV3}], ax

    mov word ptr [{RIDX}], {RELOC}
    mov si, {STRS}
    mov cx, {NSTR}
ap_s:
    push cx
    push si
    mov di, word ptr [si+12]
    cmp byte ptr [si+10], 0
    jne ap_rel
    mov cx, word ptr [si+2]
    inc cx
    mov si, word ptr [si+8]
    rep movsb
    jmp ap_sn
ap_rel:
    mov bx, word ptr [{RIDX}]
    lea ax, [di-1]
    mov word ptr [bx], ax
    mov ax, di
    add ax, word ptr [si+2]
    inc ax
    mov word ptr [bx+2], ax
    mov ax, word ptr [si+8]
    mov word ptr [bx+4], ax
    add bx, 6
    mov word ptr [{RIDX}], bx
    mov word ptr es:[di-3], 0x67cd
    mov byte ptr es:[di-1], 0x90
    mov byte ptr es:[di], 0xe8
    mov ax, word ptr [{A_PUTC}]
    sub ax, di
    sub ax, 3
    mov word ptr es:[di+1], ax
    mov byte ptr es:[di+3], 0xcb
ap_sn:
    pop si
    pop cx
    add si, 14
    dec cx
    jnz ap_s

    mov si, {TABAP}
    mov cx, {NTAB}
ap_t:
    push cx
    push si
    mov bx, word ptr [si]
    mov di, word ptr [bx]
    mov cx, word ptr [si+4]
    mov si, word ptr [si+2]
    rep movsb
    pop si
    pop cx
    add si, 6
    dec cx
    jnz ap_t
    mov byte ptr [{ENABLED}], 1
pa_fail:
    ret

anch_all:
    test byte ptr [{FORCE}], 2
    jnz aa_fail
    test byte ptr [{FORCE}], 1
    jnz aa_scan
    mov si, {ANCH}
    mov cx, {NANCH}
aa_f:
    mov di, word ptr [si]
    call mcmp
    jne aa_scan
    mov bx, word ptr [si+14]
    mov word ptr [bx], di
    add si, 16
    dec cx
    jnz aa_f
    clc
    ret
aa_scan:
    mov si, {ANCH}
    mov cx, {NANCH}
aa_clr:
    mov bx, word ptr [si+14]
    mov word ptr [bx], 0xffff
    add si, 16
    dec cx
    jnz aa_clr
    mov di, {SSTART}
    xor bp, bp
    mov cx, 8
    xor ah, ah
aa_init:
    mov al, byte ptr es:[di]
    add bp, ax
    inc di
    dec cx
    jnz aa_init
    mov di, {SSTART}
aa_loop:
    mov ax, bp
    xor ah, ah
    mov bx, ax
    shr bx, 1
    shr bx, 1
    shr bx, 1
    and al, 7
    mov cl, al
    mov al, 1
    shl al, cl
    test byte ptr [bx+{QBITS}], al
    jz aa_roll
    mov si, {ANCH}
    mov cx, {NANCH}
aa_each:
    mov bx, word ptr [si+14]
    cmp word ptr [bx], 0xffff
    jne aa_next
    cmp bp, word ptr [si+8]
    jne aa_next
    push di
    sub di, word ptr [si+6]
    call mcmp
    jne aa_nomatch
    mov word ptr [bx], di
aa_nomatch:
    pop di
aa_next:
    add si, 16
    dec cx
    jnz aa_each
aa_roll:
    xor ah, ah
    mov al, byte ptr es:[di]
    sub bp, ax
    mov al, byte ptr es:[di+8]
    add bp, ax
    inc di
    cmp di, {SEND}
    jb aa_loop
    mov si, {ANCH}
    mov cx, {NANCH}
aa_chk:
    mov bx, word ptr [si+14]
    cmp word ptr [bx], 0xffff
    je aa_fail
    add si, 16
    dec cx
    jnz aa_chk
    clc
    ret
aa_fail:
    stc
    ret

mcmp:
    push bx
    push cx
    push dx
    mov bx, word ptr [si+4]
    mov cx, word ptr [si+2]
    call hash
    cmp dx, word ptr [si+10]
    jne mc_out
    cmp ax, word ptr [si+12]
mc_out:
    pop dx
    pop cx
    pop bx
    ret

hash:
    push di
    push cx
    push bx
    push si
    xor dx, dx
    xor si, si
hs_l:
    mov al, byte ptr es:[di]
    or bx, bx
    jz hs_nm
    and al, byte ptr [bx]
    inc bx
hs_nm:
    xor ah, ah
    rol dx, 1
    add dx, ax
    add si, ax
    rol si, 3
    inc di
    dec cx
    jnz hs_l
    mov ax, si
    pop si
    pop bx
    pop cx
    pop di
    ret

str_locate:
    test byte ptr [{FORCE}], 1
    jnz sl_list
    mov di, word ptr [si]
    call str_check
    je sl_ok
sl_list:
    cmp word ptr [{LISTN}], 0xffff
    jne sl_have
    call build_list
sl_have:
    xor dx, dx
    mov bx, {LIST}
    mov cx, word ptr [{LISTN}]
    or cx, cx
    jz sl_fail
sl_l:
    mov di, word ptr [bx]
    call str_check
    jne sl_next
    cmp dl, byte ptr [si+11]
    je sl_ok
    inc dl
sl_next:
    add bx, 2
    dec cx
    jnz sl_l
sl_fail:
    stc
    ret
sl_ok:
    mov word ptr [si+12], di
    clc
    ret

str_check:
    push bx
    push cx
    push dx
    push ax
    push di
    cmp byte ptr es:[di-3], 0xe8
    jne sc_out
    mov ax, word ptr es:[di-2]
    add ax, di
    cmp ax, word ptr [{A_PUTS}]
    jne sc_out
    mov bx, di
    add bx, word ptr [si+2]
    cmp byte ptr es:[bx], 0
    jne sc_out
    mov cx, word ptr [si+2]
    xor bx, bx
    call hash
    cmp dx, word ptr [si+4]
    jne sc_out
    cmp ax, word ptr [si+6]
sc_out:
    pop di
    pop ax
    pop dx
    pop cx
    pop bx
    ret

build_list:
    push si
    push bx
    push di
    push ax
    mov word ptr [{LISTN}], 0
    mov bx, {LIST}
    mov di, {SSTART3}
bl_l:
    cmp byte ptr es:[di-3], 0xe8
    jne bl_n
    mov ax, word ptr es:[di-2]
    add ax, di
    cmp ax, word ptr [{A_PUTS}]
    jne bl_n
    cmp word ptr [{LISTN}], {LISTMAX}
    jae bl_n
    mov word ptr [bx], di
    add bx, 2
    inc word ptr [{LISTN}]
bl_n:
    inc di
    cmp di, {SEND}
    jb bl_l
    pop ax
    pop di
    pop bx
    pop si
    ret
'''

INIT = r'''
    mov si, 0x81
    mov cl, byte ptr [0x80]
    xor ch, ch
    or cx, cx
    jz i_done
i_l:
    lodsb
    cmp al, 0x2f
    jne i_n
    mov al, byte ptr [si]
    and al, 0xdf
    cmp al, 0x53
    jne i_x
    or byte ptr [{FORCE}], 1
i_x:
    cmp al, 0x58
    jne i_n
    or byte ptr [{FORCE}], 2
i_n:
    dec cx
    jnz i_l
i_done:
    push ds
    mov ax, 0x1130
    mov bh, 3
    int 0x10
    push es
    pop ds
    mov si, bp
    push cs
    pop es
    mov di, {FONT}
    mov cx, 0x200
    cld
    rep movsw
    pop ds
    mov ax, 0x3510
    int 0x21
    mov word ptr [{OLD10}], bx
    mov word ptr [{OLD10}+2], es
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21}+2], es
    mov ax, 0x2510
    mov dx, {E10}
    int 0x21
    mov ax, 0x2521
    mov dx, {E21}
    int 0x21
    mov ax, 0x2566
    mov dx, {E66}
    int 0x21
    mov ax, 0x2567
    mov dx, {E67}
    int 0x21
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''


def asm(src, addr, kw):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src.format(**kw), addr)
    return fix16(bytes(enc), addr)


def read_translation(path):
    """{位置(int) または 'TLKX03.0001': 訳}"""
    tr = {}
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        key, _, text = line.partition("\t")
        text = text.replace("\\n", "\r")
        if "." in key:
            name, _, off = key.partition(".")
            tr[f"{name.upper()}.{int(off, 16):04x}"] = text
        else:
            tr[int(key, 16)] = text
    return tr


def inline_strings(img):
    """call PUTS の直後の文字列 → {位置: 長さ}"""
    res = {}
    for i in range(len(img) - 3):
        if img[i] == 0xE8 and (i + 3 + struct.unpack_from("<h", img, i + 1)[0]) & 0xFFFF == PUTS:
            s = i + 3
            res[s] = img.index(b"\0", s) - s
    return res


def table_strings(img, start, end):
    res = []
    p = start
    while p < end:
        e = img.index(b"\0", p)
        res.append((p, e - p))
        p = e + 1
    return res


def tlk_entries(data):
    """会話ファイル → [(位置, バイト列)]。先頭は 0、そのあと 0 区切り"""
    last = max(i for i, b in enumerate(data[:TLK_SIZE]) if b) if any(data[:TLK_SIZE]) else 0
    res = []
    p = 1
    while p <= last:
        e = data.index(b"\0", p) if b"\0" in data[p:last + 1] else last + 1
        res.append((p, data[p:e]))
        p = e + 1
    return res


def anchor_pattern(img, off, n):
    """off から n バイトの並び。call/jmp の相対番地とメモリの番地（disp）は「何でもよい」にする → (バイト列, 印)"""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.detail = True
    pat = bytes(img[off:off + n])
    mask = bytearray(b"\xff" * n)
    for ins in md.disasm(pat, off):
        rel = ins.address - off
        if ins.bytes[0] in (0xE8, 0xE9):
            mask[rel + 1:rel + 3] = b"\0\0"
        if ins.disp_size == 2:
            mask[rel + ins.disp_offset:rel + ins.disp_offset + 2] = b"\0\0"
    return pat, bytes(mask)


QLEN = 8     # 探すとき、まず先頭のこのバイト数のハッシュ値で絞り込む


def h12(bs, mask=None):
    """常駐部の hash と同じ計算。h1 = rol(h1,1) + b、h2 = rol(h2 + b, 3)（16ビット）"""
    h1 = h2 = 0
    for i, x in enumerate(bs):
        if mask is not None:
            x &= mask[i]
        h1 = (((h1 << 1) | (h1 >> 15)) + x) & 0xFFFF
        h2 = (h2 + x) & 0xFFFF
        h2 = ((h2 << 3) | (h2 >> 13)) & 0xFFFF
    return h1, h2


def quick_off(mask, n):
    """「何でもよい」を含まない QLEN バイトが始まる位置"""
    for q in range(0, n - QLEN + 1):
        if mask is None or all(mask[q:q + QLEN]):
            return q
    raise RuntimeError("絞り込みに使える 8 バイトがありません")


def sim_scan(img, anchors):
    """常駐部の anch_all（探す方）と同じ探し方（試験用）。{GOG 版の位置: 見つかった位置}"""
    found = {}
    info = []
    for off, pat, mask, var in anchors:
        q = quick_off(mask, len(pat))
        info.append((off, q, sum(pat[q:q + QLEN]) & 0xFFFF, h12(pat, mask), len(pat), mask))
    for p in range(SEARCH_START, SEARCH_END):
        qs = sum(img[p:p + QLEN]) & 0xFFFF
        for off, q, qsum, fh, n, mask in info:
            if off in found or qs != qsum:
                continue
            c = p - q
            if h12(img[c:c + n], mask) == fh:
                found[off] = c
    return found

def main(exe, trfile, out):
    game = os.path.dirname(os.path.abspath(exe))
    d = open(exe, "rb").read()
    hdr = struct.unpack_from("<H", d, 8)[0] * 16
    orig = bytes(d[hdr:])
    tr = read_translation(trfile)
    inl = inline_strings(orig)
    tabs = [table_strings(orig, a, b) for a, b in TABLES]
    tabpos = {p for t in tabs for p, _ in t}
    for key in tr:
        if isinstance(key, int) and key not in inl and key not in tabpos:
            sys.exit(f"{key:05x} は文字列の先頭ではありません")

    enc = Encoder([t for t in tr.values()])
    # 1バイトで書ける字は、文字画面（1画面 62 字まで読み込める）に出る字を優先して選ぶ
    from collections import Counter
    freq = Counter()
    for k, t in tr.items():
        w = 1000 if (isinstance(k, int) and (k in TEXT_KEYS or TABLES[0][0] <= k < TABLES[0][1])) else 1
        for ch in t:
            if is_jp(ch):
                freq[ch] += w
    top = sorted(freq, key=lambda c: (-freq[c], c))[:len(jpenc.SINGLE_CODES)]
    enc.single = {ch: jpenc.SINGLE_CODES[i] for i, ch in enumerate(top)}
    # 確認用に、訳ごとの符号化の結果を覚えておく（出力の横に _enc.json で書き出す）
    encoded = {}
    _encode = enc.encode

    def enc_rec(t):
        b = _encode(t)
        encoded[t] = b.hex()
        return b
    enc.encode = enc_rec
    errors = []

    # 埋め込み文字列の記録: (GOG 版の位置, 長さ, 英文, 書き込む中身, 種類, 同じ英文の何番目か)
    #   収まる訳: 訳＋0＋NOP（戻り先は 0 の次なので、NOP を通って元の続きへ進む）
    #   長い訳: 呼び出しを int 67h にして、元の場所には中継（call PUTC; retf）を置く（常駐部が書き込むときに作る）
    #   訳していないもの: 最上位ビットを消す（0x8D の改行など）
    seen = Counter()
    strs = []
    for off in sorted(inl):
        n = inl[off]
        text = orig[off:off + n]
        occ = seen[text]
        seen[text] += 1
        if off in tr:
            b = enc.encode(tr[off])
            if len(b) <= n:
                strs.append((off, n, text, b + b"\0" + b"\x90" * (n - len(b)), 0, occ))
            elif n >= 3:
                strs.append((off, n, text, b + b"\0", 1, occ))
            else:
                errors.append(f"{off:05x}: 元が {n} バイトなので長い訳は入りません  {tr[off]}")
        elif any(x >= 0x80 for x in text):
            strs.append((off, n, text, bytes(x & 0x7F for x in text) + b"\0", 0, occ))
        if occ > 255:
            errors.append(f"{off:05x}: 同じ英文が多すぎます")

    # 表: 順番と件数を保ったまま詰め直す。訳していないものは最上位ビットを消す
    tabnew = []
    for (start, end), tab in zip(TABLES, tabs):
        buf = bytearray()
        for p, n in tab:
            buf += (enc.encode(tr[p]) if p in tr else bytes(x & 0x7F for x in orig[p:p + n])) + b"\0"
        room = end - start
        if len(buf) > room:
            errors.append(f"表 {start:05x}: {len(buf)} バイト > {room}")
        tabnew.append(bytes(buf + b"\0" * (room - len(buf))))

    # 会話ファイル
    tlk = {}
    names = sorted({k.split(".")[0] for k in tr if isinstance(k, str)})
    for name in names:
        data = open(os.path.join(game, name), "rb").read()
        ents = tlk_entries(data)
        known = {f"{name}.{p:04x}" for p, _ in ents}
        for k in tr:
            if isinstance(k, str) and k.startswith(name + ".") and k not in known:
                errors.append(f"{k} は会話の先頭ではありません")
        body = b"\0" + b"\0".join(enc.encode(tr[f"{name}.{p:04x}"]) if f"{name}.{p:04x}" in tr
                                  else bytes(x & 0x7F for x in t) for p, t in ents) + b"\0"
        if len(body) > TLK_SIZE:
            errors.append(f"{name}: {len(body)} バイト > {TLK_SIZE}")
        if not (len(name) == 6 and name.startswith("TLK")):
            errors.append(f"{name}: 会話ファイルの名前は TLK と3文字")
        tlk[name] = body

    # 探す場所（関数）と、3つの表。GOG 版で、探し方どおりに元の場所が見つかることを確かめる
    anchors = []
    for off, n, var in ANCHORS:
        pat, mask = anchor_pattern(orig, off, n)
        anchors.append((off, pat, mask, var))
    for (start, end), var in zip(TABLES, (A_T0, A_T1, A_T2)):
        anchors.append((start, orig[start:end], None, var))
    got = sim_scan(orig, anchors)
    for off, pat, mask, var in anchors:
        if got.get(off) != off:
            errors.append(f"探す場所 {off:05x} が、探す方で正しく見つかりません（{got.get(off)}）")
    assert orig[0x5007:0x5009] == b"\x24\x7f"
    assert orig[0x157B] == 0xE8 and (0x157E + struct.unpack_from("<h", orig, 0x157C)[0]) == 0x53F4
    assert orig[0x4A1C:0x4A22] == b"\x50\xb8\x01\x00\xcd\x10"

    # 探す方で、文字列ごとに「同じ長さ・同じハッシュ値」の何番目かが、元の位置と一致すること
    order = sorted(inl)
    for off, n, text, new, kind, occ in strs:
        hit = [o for o in order if inl[o] == n and h12(orig[o:o + n]) == h12(text)]
        if hit.index(off) != occ:
            errors.append(f"{off:05x}: ハッシュ値で探すと別の文字列と区別できません")

    if errors:
        print("\n".join(errors))
        sys.exit("入らない訳があります")

    glyphs = load_bdf(BDF)
    missing = set()
    pool = {}
    for (a, b) in enc.pairs:
        for x in (a, b):
            if x is not None and is_jp(x):
                k = x if ord(x) in glyphs else "？"
                if ord(x) not in glyphs:
                    missing.add(x)
                pool.setdefault(k, len(pool))

    qmark = bytes([0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00])
    names10 = ["FONT", "FONT2", "SLOT", "SLOTGLY", "SINGLES", "QMARK", "NPAIRS", "PAIRS",
               "DYNLIST", "BUF16", "RELOC", "STACKTOP", "TLKTAB", "PATCHALL", "ANCH", "STRS", "TABAP", "LIST",
               "QBITS"]
    nreloc = sum(1 for s in strs if s[4] == 1)
    base = dict(jmp_old=FAR_JMP(OLD10), call_old=FAR_CALL(OLD10), call_old10=FAR_CALL(OLD10),
                jmp_old21=FAR_JMP(OLD21), call_old21=FAR_CALL(OLD21), call_thunk=FAR_CALL(THUNK),
                LEAD=LEAD, LEADPOS=LEADPOS, DYNI=DYNI, ATTR=ATTR, CURPOS=CURPOS, PA=PA, PB=PB,
                THUNK=THUNK, OLDSS=OLDSS, OLDSP=OLDSP, INRELOC=INRELOC, RSTR=RSTR, TLK_SIZE=TLK_SIZE,
                ENABLED=ENABLED, KEEPV1=KEEPV1, KEEPV2=KEEPV2, KEEPV3=KEEPV3, TRIEDCS=TRIEDCS, FORCE=FORCE,
                RIDX=RIDX, LISTN=LISTN, A_PUTS=A_PUTS, A_PUTC=A_PUTC, A_TABP=A_TABP, A_TALK=A_TALK,
                NANCH=len(anchors), NSTR=len(strs), NTAB=len(TABLES), LISTMAX=LISTMAX, QLEN=QLEN,
                SSTART=SEARCH_START, SSTART3=SEARCH_START + 3, SEND=SEARCH_END,
                NDYN=len(DYN), NDYN2=len(DYN) * 2, NSINGLE=len(enc.single))

    def build(lay):
        kw = dict(base)
        kw.update({k: lay.get(k, 0x9000) for k in names10})
        blocks = []
        p = CODE
        ent = {}
        for name, src in (("E66", RES66), ("E67", RES67), ("E21", RES21), ("E10", RES), ("EP", RESP)):
            ent[name] = p
            code = asm(src, p, kw)
            blocks.append(code)
            p += len(code)
        return b"".join(blocks), ent, p

    code0, ent0, p = build({})

    lay = {"PATCHALL": ent0["EP"]}
    lay["QMARK"] = p; p += 8
    lay["BUF16"] = p; p += 16
    lay["DYNLIST"] = p; p += len(DYN)
    lay["SLOTGLY"] = p; p += 2 * len(DYN)
    p = (p + 15) & ~15
    lay["FONT"] = p; lay["FONT2"] = p + 0x400; lay["SLOT"] = p + 0xFE * 8; p += 2048
    lay["NPAIRS"] = p; p += 2
    lay["PAIRS"] = p; p += 4 * len(enc.pairs)
    lay["GLY"] = p; p += 8 * len(pool)
    lay["SINGLES"] = p; p += 17 * len(enc.single)
    # 探す場所の表と並び
    lay["ANCH"] = p; p += 16 * len(anchors)
    lay["QBITS"] = p; p += 32
    anch_tab = bytearray()
    anch_blob = bytearray()
    qbits = bytearray(32)
    for off, pat, mask, var in anchors:
        q = quick_off(mask, len(pat))
        qsum = sum(pat[q:q + QLEN]) & 0xFFFF
        qbits[(qsum & 0xFF) >> 3] |= 1 << (qsum & 7)
        f1, f2 = h12(pat, mask)
        mptr = 0
        if mask is not None:
            mptr = p + len(anch_blob)
            anch_blob += mask
        anch_tab += struct.pack("<HHHHHHHH", off, len(pat), mptr, q, qsum, f1, f2, var)
    p += len(anch_blob)
    # 文字列の表と、英文・書き込む中身
    lay["STRS"] = p; p += 14 * len(strs)
    str_tab = bytearray()
    str_blob = bytearray()
    for off, n, text, new, kind, occ in strs:
        h1, h2 = h12(text)
        pn = p + len(str_blob)
        str_blob += new
        str_tab += struct.pack("<HHHHHBBH", off, n, h1, h2, pn, kind, occ, 0)
    p += len(str_blob)
    # 表の書き込み
    lay["TABAP"] = p; p += 6 * len(TABLES)
    tab_ap = bytearray()
    tab_blob = bytearray()
    for (start, end), var, new in zip(TABLES, (A_T0, A_T1, A_T2), tabnew):
        tab_ap += struct.pack("<HHH", var, p + len(tab_blob), len(new))
        tab_blob += new
    p += len(tab_blob)
    # 長い訳の表（書き換えのときに常駐部が作る）、文字列を書く関数の呼び出し元の一覧（探すとき用）
    lay["RELOC"] = p; p += 6 * nreloc + 2
    lay["LIST"] = p; p += 2 * LISTMAX
    lay["TLKTAB"] = p; p += 5 * len(tlk) + 1
    tbase = p
    tblob = bytearray()
    ttab = bytearray()
    for name, body in sorted(tlk.items()):
        ttab += name[3:6].encode("ascii") + struct.pack("<H", tbase + len(tblob))
        tblob += struct.pack("<H", len(body)) + body
    p += len(tblob)
    p = (p + 1) & ~1
    p += STACK_SIZE
    lay["STACKTOP"] = p
    resident_end = p
    if resident_end > 0xF000:
        sys.exit("常駐部が大きすぎます")

    code, ent, p2 = build(lay)
    assert len(code) == len(code0) and ent == ent0

    def ptr(ch):
        if ch is None:
            return 0
        if not is_jp(ch):
            return lay["FONT"] + ord(ch) * 8
        k = ch if ord(ch) in glyphs else "？"
        return lay["GLY"] + 8 * pool[k]

    pairs = bytearray()
    for (a, b), idx in sorted(enc.pairs.items(), key=lambda kv: kv[1]):
        pairs += struct.pack("<HH", ptr(a), ptr(b))
    upper = bytearray(1024)
    singles = bytearray()
    for ch, c in enc.single.items():
        g = glyphs.get(ord(ch))
        if g is None:
            missing.add(ch)
            g = qmark
        upper[(c - 0x80) * 8:(c - 0x80) * 8 + 8] = g
        singles += bytes([c]) + bytes(x for r in g for x in (r, r))

    msg = "U2JP: Ultima II Japanese patch loaded\r\n$".encode()
    ikw = dict(OLD10=OLD10, OLD21=OLD21, FORCE=FORCE, FONT=lay["FONT"], MSG=0x9000,
               PARAS=(resident_end + 15) // 16, **ent)
    init = asm(INIT, resident_end, ikw)
    ikw["MSG"] = resident_end + len(init)
    init2 = asm(INIT, resident_end, ikw)
    assert len(init2) == len(init)

    com = bytearray(b"\xe9" + struct.pack("<H", (resident_end - 0x103) & 0xFFFF))
    com += bytes(CODE - 0x103)
    com += code
    assert 0x100 + len(com) == lay["QMARK"]
    com += qmark + bytes(16) + bytes(DYN) + bytes(2 * len(DYN))
    com += bytes(lay["FONT"] - 0x100 - len(com))
    com += bytes(1024) + upper
    com += struct.pack("<H", len(enc.pairs)) + pairs
    for k in sorted(pool, key=lambda k: pool[k]):
        com += glyphs[ord(k)]
    com += singles
    assert 0x100 + len(com) == lay["ANCH"]
    com += anch_tab + qbits + anch_blob
    assert 0x100 + len(com) == lay["STRS"]
    com += str_tab + str_blob
    assert 0x100 + len(com) == lay["TABAP"]
    com += tab_ap + tab_blob
    assert 0x100 + len(com) == lay["RELOC"]
    com += bytes(6 * nreloc + 2) + bytes(2 * LISTMAX)
    assert 0x100 + len(com) == lay["TLKTAB"]
    com += ttab + b"\0" + tblob
    com += bytes(resident_end - 0x100 - len(com))
    assert 0x100 + len(com) == resident_end
    com += init2 + msg
    open(out, "wb").write(com)
    import json
    pairs_list = [list(k) for k, _ in sorted(enc.pairs.items(), key=lambda kv: kv[1])]
    with open(os.path.splitext(out)[0] + "_enc.json", "w", encoding="utf-8") as f:
        json.dump({"encoded": encoded, "pairs": pairs_list, "single": enc.single}, f, ensure_ascii=False)
    print(f"{out}: {len(com)} バイト（常駐 {resident_end - 0x100}）、1バイトの字 {len(enc.single)}、"
          f"組 {len(enc.pairs)}、字の形 {len(pool)}、文字列 {len(strs)}（長い訳 {nreloc}）、"
          f"探す場所 {len(anchors)}、会話 {len(tlk)} ファイル")
    if missing:
        print("フォントにない字:", "".join(sorted(missing)))


if __name__ == "__main__":
    main(*sys.argv[1:4])
