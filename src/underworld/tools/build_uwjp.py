"""Ultima Underworld（UW1）の常駐部 UWJP.COM と、日本語の文字列のファイル UWJP.DAT を作る。
  python build_uwjp.py <訳 ブロック TAB 番号 TAB 訳（UR の書式、番号は 1 から）> <出力フォルダ>

常駐部（INT 21h と INT 66h を横取り）:
  AH=3Dh で DATA\\strings.pak を開いたとき（DS = 本編の DGROUP）、照合してから本編のコードを書き換える（B = DS - 0x5AAC）:
    1. 文字列を取り出す関数 B+32A8:0604 を getstr への far jmp に。訳があれば UWJP.DAT から読んで本編の輪（B+56DD:[09DA]）に書いて返す。
       なければ元の関数の続き（0607 の sub sp,12h から）へ戻る
    2. 大文字・小文字にする関数（32A8:082E、0871）の mov al,es:[bx] ＋ cbw を movzx に（0x80 以上の字を符号拡張して表を引かないように）
    3. 絵の部品（B+0090）の文字列を描く入口の表 5A78〜5A8A（7 個の jmp）と幅を測る 4C45 を INT 66h に。
       INT 66h は、文字列（部品のデータの DS:SI）の日本語の 2 バイトの字を、その行で使っていない字の番号 1 つに置き換え、
       その番号の字の絵を美咲フォントの字に書き換えてから、元の行き先へ戻る。書き換えた字の絵は、次に呼ばれたときに元に戻す
    4. 巻物に出す文を 49 バイトずつに切る所（B+3603:0389 の strrchr(s,' ')）を breakfind に。空白がないとき、日本語の字の途中で切らない
  AH=3Dh で font5x6p.sys を開いたとき: その後の読み込み（頭 12 バイト、字の絵）で、高さ 6 の字を高さ 8 にして渡す（上に 2 行足す）。
    巻物の行の高さが 8 になり、美咲フォント（8×8）の字が入る
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uwjpenc import load_bdf, Encoder, fix16, add_breaks
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

sys.stdout.reconfigure(encoding='utf-8')

# 作品ごとの番地（UW2 は UW1 と同じ作りで、場所だけ違う。絵の部品のデータの変数は 2 ずれている）
GAMES = {
    'uw1': dict(DG=0x5AAC, SEG_STR=0x32A8, GS=0x604, SEG_RING=0x56DD, RINGIDX=0x9DA, CASE1=0x82E, CASE2=0x871,
                SEG_LIB=0x90, SEG_LIBDS=0x3963, WFAR=0x4DCB, SEG_CHUNK=0x3603, CHUNK=0x389, CHUNKW=0x5D9A,
                L_H=0x4D0C, L_RB=0x4D0E, L_TAB=0x4D16, L_W1=0x2D3A, L_W2=0x2D3C,
                LIB_ENTRIES=[0x5A78, 0x5A7B, 0x5A7E, 0x5A81, 0x5A84, 0x5A87, 0x5A8A],
                SINGLES=[0x87, 0x88, 0x8a, 0x93, 0x94, 0x95, 0x96, 0x97, 0x99, 0xb1, 0xb2, 0xb8, 0xbe],
                NAME='UWJP', EXE_TSV='uw1_exe.tsv', EN_TSV='uw1_en.tsv', TITLE='Ultima Underworld',
                # 名札（会話の画面の上の、相手と自分の名前）。描く far 関数 0090:4CED が呼び出し側の SS:SP を CS:4C70・4C72 に取っておく
                PLATE=dict(SAVSS=0x4C70, SAVSP=0x4C72, SITES=[(0x4B2, 0x90, 0xC5), (0x57E, 0x30, 0xC5)])),
    'uw2': dict(DG=0x65E9, SEG_STR=0x3265, GS=0x601, SEG_RING=0x617D, RINGIDX=0x8F2, CASE1=0x82B, CASE2=0x86E,
                SEG_LIB=0x85, SEG_LIBDS=0x370D, WFAR=0x454B, SEG_CHUNK=0x342C, CHUNK=0x23F, CHUNKW=0x3F9A,
                L_H=0x4D0E, L_RB=0x4D10, L_TAB=0x4D18, L_W1=0x2D3C, L_W2=0x2D3E,
                LIB_ENTRIES=[0x527E, 0x5281, 0x5284, 0x5287, 0x528A, 0x528D, 0x5290],
                SINGLES=[0x82, 0x84, 0x86, 0x88, 0x8a, 0x8c, 0x8e, 0x90, 0x94, 0x97, 0x9a, 0x9b, 0x9e, 0xa1, 0xa4, 0xa7,
                         0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xad, 0xae, 0xb0, 0xb9, 0xba, 0xbb, 0xbc, 0xbd],
                NAME='UW2JP', EXE_TSV='uw2_exe.tsv', EN_TSV='uw2_en.tsv', TITLE='Ultima Underworld II',
                # 名札（会話の画面の、話し相手と自分の名前）: 描く far 関数 0085:446D が呼び出し側の SS:SP を
                # 部品の CS:43F0・43F2 に取っておくので、そこから戻り先を見る。高さ 6 のフォントを 8 に広げた分（上に 2 行）
                # 字が下へずれて枠からはみ出すので、この呼び出しだけ 2 行上に描く（y は下から数える）
                PLATE=dict(SAVSS=0x43F0, SAVSP=0x43F2, SITES=[(0x40E, None, 0xC5), (0x44D, 0x47, 0x81), (0x1B8B, 0x47, 0x81)]),
                # 話し手が替わるとき、名札を四角（0085:4D3C、引数 x1 y1 x2 y2、y は下から）で消してから描く。
                # 英語の 6 行・幅 82 の範囲なので、上にずらした行と長い日本語の名前が残る。4D51 の mov ax,[bp+6] を
                # int 66h にして、この呼び出し（戻り先 1B69）だけ y1 を 1 上に、x2 を枠の内側の右端にする
                FILL=dict(OFF=0x4D51, RET=0x1B69, ARGS=(0x47, 0x81, 0x98, 0x7C), Y1=0x82, X2=0xA2)),
}
G = GAMES['uw1']
DG = G['DG']
# 変数（COM の中の番地）
V = dict(OLD21=0x110, OLD66=0x114, GBASE=0x118, DGSEG=0x11A, LIBSEG=0x11C, LIBDS=0x11E, RINGSEG=0x120, DATH=0x122,
         FONTH=0x124, FONTST=0x126, FONTGEN=0x128, NBAK=0x12A, BAKGEN=0x12C, NBLOCKS=0x12E, ORIGCONT=0x130,
         NSLOT=0x134, WSLOT=0x136, CANJP=0x138, CAND=0x13A, LOGP=0x13C, STRIDE=0x146, FPAD=0x148, FOLD=0x14A, FNEW=0x14C, JPW=0x14E, WPREV=0x144, OLD33=0xAA0, MSEQ=0xAA4, MSTATE=0xAA6, MX=0xAA8, MY=0xAAA, MBTN=0xAAC, MTIMER=0xAAE, MPOLL=0xAB0, INDOS=0xAB2, MBUF=0xAC0, RDBUF=0x140, DATNAME=0x150,
         PRESENT=0x1A0, SLOTCODE=0x220, SLOTID=0x2A0, BAKSLOT=0x2E0, STACKTOP=0xD20)
CODE = 0xD20
# 字の番号の候補（その行に出てこないものから使う）: 制御文字 → 使われにくい記号 → 数字・英字
CANDS = [ord(c) for c in '`^_@#$%&*+<=>[]' + chr(92) + ';:"0123456789/()-,.!?' + "'"] + list(range(ord('A'), ord('Z') + 1)) + list(range(ord('a'), ord('z') + 1))   # 部品は 0x20〜0x7A の外の字を ? で描くので、その範囲だけ
# 1 バイトで書く字（UW1 の文字の種類の表 DS:1D81〜 で値が 0 のバイト）
SINGLES = [0x87, 0x88, 0x8a, 0x93, 0x94, 0x95, 0x96, 0x97, 0x99, 0xb1, 0xb2, 0xb8, 0xbe]
LIB_ENTRIES = [0x5A78, 0x5A7B, 0x5A7E, 0x5A81, 0x5A84, 0x5A87, 0x5A8A]


def fjmp(a): return f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"
def fcall(a): return f".byte 0x2e,0xff,0x1e,{a & 0xff},{a >> 8}"


RES = r"""
; ======================================================== INT 21h
int21:
    cmp ah, 0x3d
    je o21
    cmp ah, 0x3f
    je r21
c21:
    {JMP_OLD21}

; ---- 開く
o21:
    push di
    mov di, {PAT_STR}
    call name_ends
    jc o21_str
    mov di, {PAT_FNT}
    call name_ends
    jc o21_font
    pop di
    jmp c21
o21_str:
    pop di
    inc word ptr cs:[0xae6]
    call patch_game
    jmp c21
o21_font:
    pop di
    inc word ptr cs:[0xaea]
    inc word ptr cs:[{FONTGEN}]
    pushf
    {CALL_OLD21}
    jc o21_ret
    mov word ptr cs:[{FONTH}], ax
    mov word ptr cs:[{FONTST}], 1
    clc
o21_ret:
    retf 2

; ---- 読む: フォントの頭（12 バイト）を見て、高さ 6・7 のフォントを高さ 8 に広げる（1 行 1 バイトと 2 バイト）
;   頭: +2 1 字のバイト数、+6 高さ、+8 1 行のバイト数、+10 最大の幅。字の絵は 1 字（1 字のバイト数＋幅 1）× 128
r21:
    cmp bx, word ptr cs:[{FONTH}]
    jne c21
    cmp word ptr cs:[{FONTST}], 1
    jne r21_glyphs
    pushf
    {CALL_OLD21}
    jc r21_ret
    cmp ax, 12
    jne r21_off
    push bx
    push cx
    mov bx, dx
    mov cx, word ptr [bx+6]
    cmp cx, 6
    jb r21_skip
    cmp cx, {FMAXH}
    ja r21_skip
    mov ax, word ptr [bx+8]
    cmp ax, 1
    je r21_rb
    cmp ax, 2
    jne r21_skip
r21_rb:
    ; 上に足すバイト数 = (8 - 高さ) × 1 行のバイト数、元の 1 字 = 1 字のバイト数 + 1、新しい 1 字 = 8 × 1 行のバイト数 + 1
    push dx
    neg cx
    add cx, 8
    mul cx
    mov word ptr cs:[{FPAD}], ax
    mov ax, word ptr [bx+2]
    inc ax
    mov word ptr cs:[{FOLD}], ax
    mov ax, word ptr [bx+8]
    shl ax, 3
    mov word ptr [bx+2], ax
    inc ax
    mov word ptr cs:[{FNEW}], ax
    pop dx
    inc word ptr cs:[0xaec]
    mov word ptr [bx+6], 8
    cmp word ptr [bx+10], 8
    jae r21_mw
    mov word ptr [bx+10], 8
r21_mw:
    mov word ptr cs:[{FONTST}], 2
    pop cx
    pop bx
    mov ax, 12
    clc
    retf 2
r21_skip:
    pop cx
    pop bx
    mov ax, 12
r21_off:
    ; フォントでなかった（12 バイトの読み込みでない）ときは、読めたバイト数をそのまま返す
    mov word ptr cs:[{FONTH}], 0xffff
    clc
r21_ret:
    retf 2
r21_glyphs:
    ; 字の絵: 元の 128 字を FONTBUF に読み、1 字ずつ上に FPAD バイトの 0 を足して渡す
    push si
    push di
    push cx
    push dx
    push ds
    push es
    mov word ptr cs:[{FONTH}], 0xffff
    mov ax, ds
    mov es, ax
    mov di, dx
    push cs
    pop ds
    mov dx, {FONTBUF}
    mov ax, word ptr [{FOLD}]
    shl ax, 7
    mov cx, ax
    mov ah, 0x3f
    pushf
    {CALL_OLD21}
    jc r21g_err
    mov si, {FONTBUF}
    mov dx, 128
    inc word ptr cs:[0xaee]
r21g_l:
    mov cx, word ptr [{FPAD}]
    xor al, al
    rep stosb
    mov cx, word ptr [{FOLD}]
    rep movsb
    dec dx
    jnz r21g_l
    mov ax, word ptr cs:[{FNEW}]
    shl ax, 7
    pop es
    pop ds
    pop dx
    pop cx
    pop di
    pop si
    clc
    retf 2
r21g_err:
    pop es
    pop ds
    pop dx
    pop cx
    pop di
    pop si
    retf 2

; ---- 調べる用: 開いた名前の終わり 15 字と AH を 16 バイトずつ輪に記録（CS:0B20〜0D1F、32 件）
log_open:
    push ax
    push cx
    push si
    push di
    push es
    mov cl, ah
    push cs
    pop es
    mov di, word ptr cs:[{LOGP}]
    and di, 0x1f0
    add di, 0xb20
    mov si, dx
lo_e:
    cmp byte ptr [si], 0
    je lo_e2
    inc si
    jmp lo_e
lo_e2:
    mov ax, si
    sub ax, dx
    cmp ax, 15
    jbe lo_s
    mov ax, 15
lo_s:
    sub si, ax
    mov al, cl
    stosb
    mov cx, 15
lo_c:
    lodsb
    stosb
    or al, al
    jz lo_z
    loop lo_c
    jmp lo_d
lo_z:
    dec cx
    xor al, al
    rep stosb
lo_d:
    add word ptr cs:[{LOGP}], 16
    pop es
    pop di
    pop si
    pop cx
    pop ax
    ret

; ---- DS:DX の名前が CS:DI の名前（大文字、0 終わり）で終わるか。終わるなら CF=1
name_ends:
    push ax
    push bx
    push si
    push cx
    mov si, dx
ne_end:
    cmp byte ptr [si], 0
    je ne_e2
    inc si
    jmp ne_end
ne_e2:
    mov bx, di
ne_pl:
    cmp byte ptr cs:[bx], 0
    je ne_p2
    inc bx
    jmp ne_pl
ne_p2:
    mov cx, bx
    sub cx, di
    mov ax, si
    sub ax, dx
    cmp ax, cx
    jb ne_no
    sub si, cx
ne_cmp:
    jcxz ne_yes
    mov al, byte ptr [si]
    cmp al, 0x61
    jb ne_c1
    cmp al, 0x7a
    ja ne_c1
    sub al, 0x20
ne_c1:
    cmp al, byte ptr cs:[di]
    jne ne_no2
    inc si
    inc di
    dec cx
    jmp ne_cmp
ne_yes:
    pop cx
    pop si
    pop bx
    pop ax
    stc
    ret
ne_no2:
ne_no:
    pop cx
    pop si
    pop bx
    pop ax
    clc
    ret

; ---- 本編を書き換える（DS = 本編の DGROUP）
patch_game:
    ; 常駐部の中からは int 21h を呼ばない（後から入る常駐プログラム（GOG 版の cdwedge）が、
    ; 呼ばれるたびにレジスタを 1 か所に保存して再試行に使うため、入れ子で呼ぶと壊れる）
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push es
    push bx
    mov ah, 0x62
    pushf
    {CALL_OLD21}
    lea ax, [bx+0x10]
    pop bx
    cmp ax, word ptr cs:[{GBASE}]
    je pg_done
    mov bx, ax
    add ax, {SEG_STR}
    mov es, ax
    cmp word ptr es:[{GS}], 0x8b55
    jne pg_done
    cmp word ptr es:[{GS2}], 0x83ec
    jne pg_done
    cmp word ptr es:[{CASE1}], 0x8a26
    jne pg_done
    cmp word ptr es:[{CASE2}], 0x8a26
    jne pg_done
    mov ax, bx
    add ax, {SEG_LIB}
    mov es, ax
    cmp word ptr es:[{WFAR}], 0x8b55
    jne pg_done
    cmp word ptr es:[{WFAR2}], 0x57ec
    jne pg_done
    mov ax, bx
    add ax, {SEG_CHUNK}
    mov es, ax
    cmp word ptr es:[{CHUNK}], {CHUNKW}
    jne pg_done
    ; ---- 照合できた
    inc word ptr cs:[0xae8]
    mov word ptr cs:[{GBASE}], bx
    lea ax, [bx+{DG}]
    mov word ptr cs:[{DGSEG}], ax
    lea ax, [bx+{SEG_LIB}]
    mov word ptr cs:[{LIBSEG}], ax
    lea ax, [bx+{SEG_LIBDS}]
    mov word ptr cs:[{LIBDS}], ax
    lea ax, [bx+{SEG_RING}]
    mov word ptr cs:[{RINGSEG}], ax
    lea ax, [bx+{SEG_STR}]
    mov word ptr cs:[{ORIGCONT}+2], ax
    mov word ptr cs:[{ORIGCONT}], {GSC}
    ; 0. 本編の EXE の中の文字列（DGROUP）を訳に（表: 位置 u16、長さ u8、中身。位置 0xFFFF で終わり）
    mov es, word ptr cs:[{DGSEG}]
    mov si, {EXESTR}
pg_ex:
    mov di, word ptr cs:[si]
    cmp di, 0xffff
    je pg_ex_end
    mov cl, byte ptr cs:[si+2]
    xor ch, ch
    add si, 3
pg_ex_c:
    mov al, byte ptr cs:[si]
    stosb
    inc si
    loop pg_ex_c
    jmp pg_ex
pg_ex_end:
    lea ax, [bx+{SEG_STR}]
    ; 1. getstr
    mov es, ax
    mov byte ptr es:[{GS}], 0xea
    mov word ptr es:[{GS1}], {getstr}
    mov word ptr es:[{GS3}], cs
    ; 2. 大文字・小文字: mov al,es:[bx] + cbw -> movzx ax, byte ptr es:[bx]
    mov word ptr es:[{CASE1}], 0x0f26
    mov word ptr es:[{CASE1B}], 0x07b6
    mov word ptr es:[{CASE2}], 0x0f26
    mov word ptr es:[{CASE2B}], 0x07b6
    ; 3. 絵の部品
    mov ax, word ptr cs:[{LIBSEG}]
    mov es, ax
    mov si, {LIBTAB}
    mov cx, 7
pg_lib:
    mov di, word ptr cs:[si]
    mov byte ptr es:[di], 0xcd
    mov byte ptr es:[di+1], 0x66
    mov byte ptr es:[di+2], 0x90
    add si, 4
    loop pg_lib
    mov byte ptr es:[{WFAR}], 0xea
    mov word ptr es:[{WFAR1}], {width_far}
    mov word ptr es:[{WFAR3}], cs
{FILLPATCH}
    ; 4. 49 バイトに切る所
    lea ax, [bx+{SEG_CHUNK}]
    mov es, ax
    mov word ptr es:[{CHUNK1}], {breakfind}
    mov word ptr es:[{CHUNK3}], cs
    ; UWJP.DAT を開く（本編のプロセスで）
    cmp word ptr cs:[{DATH}], 0xffff
    jne pg_done
    push ds
    push cs
    pop ds
    mov dx, {DATNAME}
    mov ax, 0x3d40
    pushf
    {CALL_OLD21}
    pop ds
    jc pg_done
    mov word ptr cs:[{DATH}], ax
pg_done:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ======================================================== 文字列を1つ取り出す（本編の 32A8:0604 の代わり）
getstr:
    push bp
    mov bp, sp
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    push cs
    pop ds
    inc word ptr cs:[0xae0]
    ; 調べる用: 'G' ブロック 番号 を輪に記録
    mov di, word ptr [{LOGP}]
    and di, 0x1f0
    add di, 0xb20
    mov byte ptr [di], 0x47
    mov ax, word ptr [bp+6]
    mov word ptr [di+1], ax
    mov ax, word ptr [bp+8]
    mov word ptr [di+3], ax
    add word ptr [{LOGP}], 16
    cmp word ptr [{DATH}], 0xffff
    je gs_orig
    mov ax, word ptr [bp+6]
    mov si, {BLOCKTAB}
    mov cx, word ptr [{NBLOCKS}]
    jcxz gs_orig
gs_find:
    cmp word ptr [si], ax
    je gs_found
    add si, 8
    loop gs_find
    jmp gs_orig
gs_found:
    mov ax, word ptr [bp+8]
    cmp ax, word ptr [si+2]
    jae gs_orig
    xor dx, dx
    shl ax, 1
    rcl dx, 1
    shl ax, 1
    rcl dx, 1
    add ax, word ptr [si+4]
    adc dx, word ptr [si+6]
    mov cx, dx
    mov dx, ax
    mov bx, word ptr [{DATH}]
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc gs_orig
    mov ah, 0x3f
    mov cx, 4
    mov dx, {RDBUF}
    pushf
    {CALL_OLD21}
    jc gs_orig
    cmp ax, 4
    jne gs_orig
    mov dx, word ptr [{RDBUF}]
    mov cx, word ptr [{RDBUF}+2]
    mov ax, dx
    or ax, cx
    jz gs_orig
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc gs_orig
    mov es, word ptr [{DGSEG}]
    mov di, word ptr es:[{RINGIDX}]
    mov ds, word ptr cs:[{RINGSEG}]
    mov dx, di
    mov cx, 0x200
    mov ah, 0x3f
    pushf
    {CALL_OLD21}
    mov byte ptr [di+0x1ff], 0
    jnc gs_ok
    mov byte ptr [di], 0
gs_ok:
    add word ptr es:[{RINGIDX}], 0x200
    cmp word ptr es:[{RINGIDX}], 0xfff
    jle gs_ok2
    mov word ptr es:[{RINGIDX}], 0
gs_ok2:
    mov dx, ds
    mov ax, di
    pop es
    pop ds
    pop di
    pop si
    add sp, 2
    pop cx
    pop bx
    pop bp
    retf
gs_orig:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    sub sp, 0x12
    {JMP_ORIG}

; ======================================================== 49 バイトに切る所（strrchr(s, ' ') の代わり、DS = SS）
breakfind:
    push bp
    mov bp, sp
    push si
    push bx
    mov si, word ptr [bp+6]
    xor bx, bx
bf_l1:
    lodsb
    or al, al
    jz bf_e1
    cmp al, 0x20
    jne bf_l1
    lea bx, [si-1]
    jmp bf_l1
bf_e1:
    mov ax, bx
    or ax, ax
    jnz bf_done
    mov si, word ptr [bp+6]
bf_l2:
    mov al, byte ptr [si]
    or al, al
    jz bf_none
    cmp al, 0xc0
    jb bf_one
    cmp byte ptr [si+1], 0
    je bf_dang
    add si, 2
    jmp bf_l2
bf_one:
    inc si
    jmp bf_l2
bf_dang:
    mov ax, si
    jmp bf_done
bf_none:
    xor ax, ax
bf_done:
    pop bx
    pop si
    pop bp
    retf

; ======================================================== 幅を測る far 関数（部品の 0090:4DCB の代わり、引数 far 文字列）
; 英数字は部品のフォントの幅、日本語の 2 バイトは 8、途中で切れた日本語は 255（折り返しがその手前で切るように）
width_far:
    push bp
    mov bp, sp
    push bx
    push cx
    push si
    push di
    push ds
    push es
    les si, dword ptr [bp+6]
    mov ds, word ptr cs:[{LIBDS}]
    mov word ptr cs:[{JPW}], 8
    cmp word ptr [{L_RB}], 2
    jne wf_j8
    cmp word ptr [{L_H}], 15
    jb wf_j8
    mov word ptr cs:[{JPW}], 16
wf_j8:
    mov bx, word ptr [{L_W1}]
    mov cx, word ptr [{L_W2}]
    shl bx, cl
    xor dx, dx
    mov cx, 0x84
    mov word ptr cs:[{WPREV}], 2
wf_l:
    mov al, byte ptr es:[si]
    or al, al
    jz wf_end
    inc si
    cmp al, 0x80
    jae wf_jp
    cmp al, 0x20
    jne wf_asc
    ; 空白: 前が日本語か頭、後ろが日本語か終わり、そのどちらかが日本語なら幅 0（折り返しの切れ目）
    mov ah, byte ptr es:[si]
    cmp word ptr cs:[{WPREV}], 0
    je wf_asc
    cmp ah, 0x80
    jae wf_next
    or ah, ah
    jnz wf_asc
    cmp word ptr cs:[{WPREV}], 1
    je wf_next
wf_asc:
    mov word ptr cs:[{WPREV}], 0
    xor ah, ah
    mov di, ax
    shl di, 1
    mov di, word ptr [di+{L_TAB}]
    mov al, byte ptr [di+bx]
    xor ah, ah
    add dx, ax
    jmp wf_next
wf_jp:
    mov word ptr cs:[{WPREV}], 1
    xor ah, ah
    mov di, ax
    mov ah, byte ptr cs:[{CTAB}+di]
    cmp al, 0xc0
    jae wf_lead
    cmp ah, 0xff
    je wf_wide
    cmp ah, 0x80
    jb wf_wide
    add dx, word ptr cs:[{JPW}]
    jmp wf_next
wf_lead:
    mov al, byte ptr es:[si]
    xor ah, ah
    mov di, ax
    cmp byte ptr cs:[{CTAB}+di], 0x40
    jae wf_wide
    inc si
    add dx, word ptr cs:[{JPW}]
    jmp wf_next
wf_wide:
    add dx, 255
wf_next:
    loop wf_l
wf_end:
    mov ax, dx
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop bx
    pop bp
    retf

; ======================================================== INT 66h（絵の部品の文字列の入口）
int66:
    inc word ptr cs:[0xae4]
    push bp
    mov bp, sp
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov bx, word ptr [bp+2]
{FILLCHK}
i66_tab:
    push si
    mov si, {LIBTAB}
    mov cx, 7
i66_tl:
    mov ax, word ptr cs:[si]
    add ax, 2
    cmp ax, bx
    je i66_tf
    add si, 4
    loop i66_tl
    pop si
    jmp i66_out
i66_tf:
    mov ax, word ptr cs:[si+2]
    mov word ptr [bp+2], ax
    pop si
i66_go:
    call plate_fix
    call transform
i66_out:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    pop bp
    iret

{PLATEFIX}
{FILLFIX}
; ---- 調べる用: 文字列 DS:SI の頭 15 バイトを輪に記録（1 バイト目は戻り先の下位）
log_str:
    push ax
    push cx
    push si
    push di
    push es
    push cs
    pop es
    mov di, word ptr cs:[{LOGP}]
    and di, 0x1f0
    add di, 0xb20
    mov al, byte ptr [{L_H}]
    mov ah, byte ptr [{L_RB}]
    shl ah, 4
    or al, ah
    stosb
    mov cx, 15
    rep movsb
    add word ptr cs:[{LOGP}], 16
    pop es
    pop di
    pop si
    pop cx
    pop ax
    ret

; ---- 文字列 DS:SI の日本語を、その行で使っていない字の番号に置き換え、字の絵を書き換える（DS = 部品のデータ）
transform:
    cld
    ; 前の呼び出しで書き換えた字の絵を元に戻す（同じフォントのときだけ）
    mov cx, word ptr cs:[{NBAK}]
    mov word ptr cs:[{NBAK}], 0
    jcxz tr_r_end
    mov ax, word ptr cs:[{FONTGEN}]
    cmp ax, word ptr cs:[{BAKGEN}]
    jne tr_r_end
    push si
    mov bx, cx
tr_r:
    dec bx
    push cx
    mov al, byte ptr cs:[{BAKSLOT}+bx]
    xor ah, ah
    shl ax, 1
    mov di, ax
    mov di, word ptr [di+{L_TAB}]
    mov si, bx
    shl si, 5
    add si, {BAKDATA}
    mov cx, word ptr cs:[{STRIDE}]
tr_r2:
    mov al, byte ptr cs:[si]
    mov byte ptr [di], al
    inc si
    inc di
    loop tr_r2
    pop cx
    loop tr_r
    pop si
tr_r_end:
    mov ax, word ptr cs:[{FONTGEN}]
    mov word ptr cs:[{BAKGEN}], ax
    ; 日本語があるか
    push si
tr_q:
    lodsb
    or al, al
    jz tr_q_none
    cmp al, 0x80
    jb tr_q
    pop si
    jmp tr_has
tr_q_none:
    pop si
    ret
tr_has:
    inc word ptr cs:[0xae2]
    call log_str
    ; この行に出てくる英数字の印
    push cs
    pop es
    mov di, {PRESENT}
    mov cx, 64
    xor ax, ax
    rep stosw
    push si
    xor bx, bx
tr_p:
    lodsb
    or al, al
    jz tr_p_end
    cmp al, 0x80
    jae tr_p
    mov bl, al
    mov byte ptr cs:[{PRESENT}+bx], 1
    jmp tr_p
tr_p_end:
    pop si
    ; 字の絵を書けるフォント: 1 = 高さ 8〜15・1 行 1 バイト、2 = 高さ 8〜14・1 行 2 バイト、3 = 高さ 15・1 行 2 バイト（2 倍で描く）
    mov word ptr cs:[{CANJP}], 0
    mov ax, word ptr [{L_H}]
    mov cx, word ptr [{L_RB}]
    cmp ax, 8
    jb tr_nojp
    cmp ax, 15
    ja tr_nojp
    cmp cx, 1
    jne tr_rb2
    mov word ptr cs:[{CANJP}], 1
    jmp tr_canok
tr_rb2:
    cmp cx, 2
    jne tr_nojp
    mov word ptr cs:[{CANJP}], 2
    cmp ax, 15
    jb tr_canok
    mov word ptr cs:[{CANJP}], 3
tr_canok:
    push dx
    mul cx
    pop dx
    inc ax
    mov word ptr cs:[{STRIDE}], ax
tr_nojp:
    mov word ptr cs:[{NSLOT}], 0
    mov word ptr cs:[{WSLOT}], 0
    mov word ptr cs:[{CAND}], {CANDLIST}
    mov di, si
    mov word ptr cs:[{WPREV}], 2
tr_l:
    lodsb
    or al, al
    jz tr_end
    cmp al, 0x80
    jae tr_jp
    cmp al, 0x20
    jne tr_asc
    mov ah, byte ptr [si]
    cmp word ptr cs:[{WPREV}], 0
    je tr_asc
    cmp ah, 0x80
    jae tr_l
    or ah, ah
    jnz tr_asc
    cmp word ptr cs:[{WPREV}], 1
    je tr_l
tr_asc:
    mov word ptr cs:[{WPREV}], 0
    jmp tr_st
tr_jp:
    mov word ptr cs:[{WPREV}], 1
    mov bl, al
    xor bh, bh
    mov bl, byte ptr cs:[{CTAB}+bx]
    cmp al, 0xc0
    jae tr_lead
    ; 0x80〜0xBF: 1 バイトの字（表 0x80 + 番号）か、ひとりの 2 バイト目
    cmp bl, 0xff
    je tr_wide
    cmp bl, 0x80
    jb tr_wide
    and bx, 0x7f
    mov ax, bx
    call slot_for
    jmp tr_st
tr_lead:
    ; 組: 番号 = 1 バイトの字の数 + (al-0xC0) × 2 バイト目の数 + 2 バイト目の番号
    mov bl, byte ptr [si]
    mov bl, byte ptr cs:[{CTAB}+bx]
    cmp bl, 0x40
    jae tr_wide
    inc si
    sub al, 0xc0
    xor ah, ah
    push dx
    mov dx, {NTRAIL}
    mul dx
    pop dx
    add ax, bx
    add ax, {NSINGLE}
    call slot_for
    jmp tr_st
tr_wide:
    call wide_slot
tr_st:
    mov byte ptr [di], al
    inc di
    jmp tr_l
tr_end:
    mov byte ptr [di], 0
    ret

; ---- 番号 AX の字の字番号を AL に（なければ割り当てて絵を書く）
slot_for:
    push bx
    push cx
    push si
    mov cx, word ptr cs:[{NSLOT}]
    xor bx, bx
sf_f:
    cmp bx, cx
    jae sf_new
    push bx
    shl bx, 1
    cmp ax, word ptr cs:[{SLOTCODE}+bx]
    pop bx
    je sf_hit
    inc bx
    jmp sf_f
sf_hit:
    mov al, byte ptr cs:[{SLOTID}+bx]
    jmp sf_ret
sf_new:
    cmp cx, 62
    jae sf_q
    push ax
    call next_cand
    mov bl, al
    pop ax
    or bl, bl
    jz sf_q
    ; 記録
    mov si, cx
    shl si, 1
    mov word ptr cs:[{SLOTCODE}+si], ax
    mov si, cx
    mov byte ptr cs:[{SLOTID}+si], bl
    inc word ptr cs:[{NSLOT}]
    ; 絵（AX = 字の番号）
    mov si, ax
    shl si, 3
    add si, {GLYPHS}
    mov al, bl
    mov ah, 8
    call put_glyph
    mov al, bl
    jmp sf_ret
sf_q:
    mov al, 0x3f
sf_ret:
    pop si
    pop cx
    pop bx
    ret

; ---- 途中で切れた日本語の字（幅 255 の空の字にして、巻物の折り返しがその手前で切るように）
wide_slot:
    mov ax, word ptr cs:[{WSLOT}]
    or ax, ax
    jnz ws_ret
    push bx
    push si
    call next_cand
    or al, al
    jz ws_q
    mov bl, al
    mov si, {BLANK}
    mov ah, 0xff
    call put_glyph
    mov al, bl
    xor ah, ah
    mov word ptr cs:[{WSLOT}], ax
    pop si
    pop bx
ws_ret:
    ret
ws_q:
    mov al, 0x3f
    pop si
    pop bx
    ret

; ---- 次に使える字の番号を AL に（なければ 0）
next_cand:
    push bx
    push si
    mov si, word ptr cs:[{CAND}]
nc_l:
    mov al, byte ptr cs:[si]
    or al, al
    jz nc_ret
    inc si
    mov bl, al
    xor bh, bh
    cmp byte ptr cs:[{PRESENT}+bx], 0
    jne nc_l
nc_ret:
    mov word ptr cs:[{CAND}], si
    pop si
    pop bx
    ret

; ---- 字の番号 AL の絵を、CS:SI の 8 行・幅 AH に書き換える（元の絵は控えておく）
put_glyph:
    cmp word ptr cs:[{CANJP}], 0
    je pg2_ret
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    mov bl, al
    xor bh, bh
    shl bx, 1
    mov di, word ptr [bx+{L_TAB}]
    ; 控え
    mov bx, word ptr cs:[{NBAK}]
    cmp bx, 64
    jae pg2_skip
    mov byte ptr cs:[{BAKSLOT}+bx], al
    push si
    push di
    mov si, di
    shl bx, 5
    lea di, [bx+{BAKDATA}]
    mov cx, word ptr cs:[{STRIDE}]
pg2_b:
    mov al, byte ptr [si]
    mov byte ptr cs:[di], al
    inc si
    inc di
    loop pg2_b
    pop di
    pop si
    inc word ptr cs:[{NBAK}]
    ; 書く
    cmp word ptr cs:[{CANJP}], 3
    je pg2_big
    mov cx, word ptr [{L_H}]
    sub cx, 8
    jcxz pg2_rows
pg2_pad:
    mov byte ptr [di], 0
    inc di
    cmp word ptr cs:[{CANJP}], 2
    jne pg2_pad1
    mov byte ptr [di], 0
    inc di
pg2_pad1:
    loop pg2_pad
pg2_rows:
    mov cx, 8
pg2_w:
    mov al, byte ptr cs:[si]
    mov byte ptr [di], al
    inc si
    inc di
    cmp word ptr cs:[{CANJP}], 2
    jne pg2_w1
    mov byte ptr [di], 0
    inc di
pg2_w1:
    loop pg2_w
    mov byte ptr [di], ah
    jmp pg2_skip
pg2_big:
    ; 2 倍: 絵の 1〜7 行目を 2 行ずつ（14 行）＋空き 1 行、1 行 16 ドット
    inc si
    mov cx, 7
pg2_bl:
    mov al, byte ptr cs:[si]
    inc si
    call dbl
    mov word ptr [di], bx
    mov word ptr [di+2], bx
    add di, 4
    loop pg2_bl
    mov word ptr [di], 0
    add di, 2
    cmp ah, 8
    jne pg2_bw
    mov ah, 16
pg2_bw:
    mov byte ptr [di], ah
pg2_skip:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
pg2_ret:
    ret

; ---- AL のビットを横に 2 倍に: BL = 上位 4 ビット分、BH = 下位 4 ビット分
dbl:
    push ax
    push si
    xor ah, ah
    mov si, ax
    shr si, 4
    mov bl, byte ptr cs:[{DBLTAB}+si]
    mov si, ax
    and si, 15
    mov bh, byte ptr cs:[{DBLTAB}+si]
    pop si
    pop ax
    ret
"""

TEST33 = r"""
; ======================================================== 試験用: INT 33h（MCMD.TXT の「番号 X Y ボタン」でカーソルを動かし、押す）
int33:
    cmp ax, 0x0b
    je m0b
    cmp ax, 3
    je m03
    {JMP_OLD33}
m0b:
    pushf
    {CALL_OLD33}
    cmp word ptr cs:[{MSTATE}], 1
    jne m0b2
    mov cx, 0xf000
    mov dx, 0xf000
    mov word ptr cs:[{MSTATE}], 2
    iret
m0b2:
    cmp word ptr cs:[{MSTATE}], 2
    jne m0b3
    mov cx, word ptr cs:[{MX}]
    shl cx, 1
    mov dx, word ptr cs:[{MY}]
    shl dx, 1
    mov word ptr cs:[{MSTATE}], 3
    mov word ptr cs:[{MTIMER}], 6
m0b3:
    iret
m03:
    pushf
    {CALL_OLD33}
    push ax
    push ds
    push dx
    inc word ptr cs:[{MPOLL}]
    test word ptr cs:[{MPOLL}], 15
    jnz m03_st
    call mpoll
m03_st:
    cmp word ptr cs:[{MSTATE}], 3
    jne m03_4
    dec word ptr cs:[{MTIMER}]
    jnz m03_ret
    cmp word ptr cs:[{MBTN}], 0
    je m03_end
    mov word ptr cs:[{MSTATE}], 4
    mov word ptr cs:[{MTIMER}], 8
    jmp m03_ret
m03_4:
    cmp word ptr cs:[{MSTATE}], 4
    jne m03_ret
    mov bx, word ptr cs:[{MBTN}]
    dec word ptr cs:[{MTIMER}]
    jnz m03_ret
m03_end:
    mov word ptr cs:[{MSTATE}], 0
m03_ret:
    pop dx
    pop ds
    pop ax
    iret

mpoll:
    push bx
    push cx
    push si
    push es
    les si, dword ptr cs:[{INDOS}]
    cmp byte ptr es:[si], 0
    jne mp_ret
    push cs
    pop ds
    mov dx, {MCMDNAME}
    mov ax, 0x3d00
    int 0x21
    jc mp_ret
    mov bx, ax
    mov ah, 0x3f
    mov cx, 30
    mov dx, {MBUF}
    int 0x21
    jc mp_close
    mov si, {MBUF}
    add si, ax
    mov byte ptr [si], 0
    mov si, {MBUF}
    call mnum
    cmp ax, word ptr cs:[{MSEQ}]
    je mp_close
    mov word ptr cs:[{MSEQ}], ax
    call mnum
    mov word ptr cs:[{MX}], ax
    call mnum
    mov word ptr cs:[{MY}], ax
    call mnum
    mov word ptr cs:[{MBTN}], ax
    mov word ptr cs:[{MSTATE}], 1
mp_close:
    mov ah, 0x3e
    int 0x21
mp_ret:
    pop es
    pop si
    pop cx
    pop bx
    ret

; DS:SI の 10 進数を AX に（前の空白は飛ばす）
mnum:
    xor ax, ax
mn_sp:
    cmp byte ptr [si], 0x20
    jne mn_d
    inc si
    jmp mn_sp
mn_d:
    mov cl, byte ptr [si]
    sub cl, 0x30
    cmp cl, 9
    ja mn_ret
    inc si
    mov bx, 10
    mul bx
    xor ch, ch
    add ax, cx
    jmp mn_d
mn_ret:
    ret
"""

TESTINST_SAVE = r"""
    mov ah, 0x34
    int 0x21
    mov word ptr [{INDOS}], bx
    mov word ptr [{INDOS}+2], es
    mov ax, 0x3533
    int 0x21
    mov word ptr [{OLD33}], bx
    mov word ptr [{OLD33}+2], es
"""
TESTINST_SET = r"""
    mov dx, {int33}
    mov ax, 0x2533
    int 0x21
"""

INSTALL = r"""
install:
    ; 自分のフォルダ（環境の後ろのプログラムの名前）から UWJP.DAT の名前を作る
    mov es, word ptr [0x2c]
    xor di, di
in_env:
    cmp word ptr es:[di], 0
    je in_env2
    inc di
    jmp in_env
in_env2:
    add di, 4
    mov si, {DATNAME}
    mov bx, si
in_cp:
    mov al, byte ptr es:[di]
    mov byte ptr [si], al
    inc di
    inc si
    or al, al
    jz in_cp2
    cmp al, 0x5c
    jne in_cp
    mov bx, si
    jmp in_cp
in_cp2:
    mov di, bx
    push ds
    pop es
    mov si, {DATFILE}
in_cp3:
    lodsb
    stosb
    or al, al
    jnz in_cp3
    ; 変数
    mov word ptr [{GBASE}], 0
    mov word ptr [{DATH}], 0xffff
    mov word ptr [{FONTH}], 0xffff
    mov word ptr [{NBAK}], 0
    mov word ptr [{FONTGEN}], 1
    mov word ptr [{NBLOCKS}], {NBLK}
    ; 割り込み
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21}+2], es
    mov ax, 0x3566
    int 0x21
    mov word ptr [{OLD66}], bx
    mov word ptr [{OLD66}+2], es
{TESTINST_SAVE}
    ; 上位メモリへ移せたら、割り込みをそちらに向けて、ふつうに終わる（下のメモリを使わない）
    call to_umb
    jc in_low
    push ds
    mov ds, bx
    mov dx, {int21}
    mov ax, 0x2521
    int 0x21
    mov dx, {int66}
    mov ax, 0x2566
    int 0x21
{TESTINST_SET}
    pop ds
    mov dx, {MSG}
    mov ah, 9
    int 0x21
    mov ax, 0x4c00
    int 0x21
in_low:
    mov dx, {int21}
    mov ax, 0x2521
    int 0x21
    mov dx, {int66}
    mov ax, 0x2566
    int 0x21
{TESTINST_SET}
    mov dx, {MSG}
    mov ah, 9
    int 0x21
    mov dx, {RESPARA}
    mov ax, 0x3100
    int 0x21

; ---- 上位メモリに RESPARA 段落を取り、CS:0 から写す。できたら CF=0・BX = 新しいセグメント
to_umb:
    mov ax, 0x5800
    int 0x21
    mov si, ax
    mov ax, 0x5802
    int 0x21
    xor ah, ah
    mov di, ax
    mov ax, 0x5803
    mov bx, 1
    int 0x21
    mov ax, 0x5801
    mov bx, 0x41
    int 0x21
    mov ah, 0x48
    mov bx, {RESPARA}
    int 0x21
    sbb dx, dx
    push ax
    push dx
    mov ax, 0x5801
    mov bx, si
    int 0x21
    mov ax, 0x5803
    mov bx, di
    int 0x21
    pop dx
    pop ax
    or dx, dx
    jnz tu_fail
    cmp ax, 0xa000
    jae tu_ok
    mov es, ax
    mov ah, 0x49
    int 0x21
tu_fail:
    stc
    ret
tu_ok:
    mov es, ax
    xor si, si
    xor di, di
    mov cx, {RESWORDS}
    cld
    rep movsw
    mov bx, ax
    dec ax
    push ds
    mov ds, ax
    mov word ptr [1], bx
    mov word ptr [8], 0x5755
    mov word ptr [10], 0x504a
    mov word ptr [12], 0
    mov word ptr [14], 0
    pop ds
    clc
    ret
"""


def strip(t):
    import re
    t = chr(10).join(l.split(';')[0].rstrip() for l in t.split(chr(10)))
    # loop は 128 バイトより遠くへ飛べず、keystone は黙って違う所へ飛ばすので、dec cx + jnz にする
    return re.sub(r'(?m)^(\s*)loop (\w+)$', r'\1dec cx\n\1jnz \2', t)


def asm(src, addr, kw):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(strip(src.format(**kw)), addr)
    return fix16(bytes(enc), addr)


def labels(src, addr, kw, names):
    """各ラベルの番地（ラベルの前までを組み立てて長さを測る）"""
    out = {}
    lines = src.format(**kw).split('\n')
    for n in names:
        i = lines.index(n + ':')
        part = '\n'.join(lines[:i]) + '\n'
        out[n] = addr + len(asm(part.replace('{', '{{').replace('}', '}}'), addr, {})) if part.strip() else addr
    return out


def read_tsv(path):
    tr = {}
    for line in open(path, encoding='utf-8-sig'):
        if not line[:1].isdigit(): continue
        c = line.rstrip('\n').split('\t')
        if len(c) < 3 or not c[2]: continue
        tr[(int(c[0]), int(c[1]) - 1)] = c[2]
    return tr


def unescape(t):
    out = []; i = 0
    while i < len(t):
        if t[i] == '\\' and i + 1 < len(t) and t[i + 1] in 'nt\\':
            out.append({'n': '\n', 't': '\t', '\\': '\\'}[t[i + 1]]); i += 2
        else:
            out.append(t[i]); i += 1
    return ''.join(out)


def read_exe_tsv(path):
    out = []
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or not line.strip(): continue
        c = line.rstrip('\n').split('\t')
        out.append((int(c[0], 16), unescape(c[1]), unescape(c[2])))
    return out


def game_kw(game):
    g = GAMES[game]
    k = {n: g[n] for n in ('DG', 'SEG_STR', 'SEG_RING', 'RINGIDX', 'SEG_LIB', 'SEG_LIBDS', 'SEG_CHUNK', 'CHUNKW',
                           'L_H', 'L_RB', 'L_TAB', 'L_W1', 'L_W2')}
    k.update(GS=g['GS'], GS1=g['GS'] + 1, GS2=g['GS'] + 2, GS3=g['GS'] + 3, GSC=g['GS'] + 6,
             CASE1=g['CASE1'], CASE1B=g['CASE1'] + 2, CASE2=g['CASE2'], CASE2B=g['CASE2'] + 2,
             WFAR=g['WFAR'], WFAR1=g['WFAR'] + 1, WFAR2=g['WFAR'] + 2, WFAR3=g['WFAR'] + 3,
             CHUNK=g['CHUNK'], CHUNK1=g['CHUNK'] + 1, CHUNK3=g['CHUNK'] + 3)
    k['PLATEFIX'] = plate_code(g)
    k.update(fill_code(g))
    return k


def plate_code(g):
    """名札だけ 2 行上に描く（INT 66h の中で呼ぶ。[bp-2] = x、[bp-4] = y、DS = 部品のデータ）"""
    pl = g.get('PLATE')
    if not pl:
        return 'plate_fix:' + NL + '    ret' + NL
    c = [f'plate_fix:', f"    cmp byte ptr [{g['L_H']:#x}], 8", '    jne pf_ret', '    push ax', '    push si', '    push ds',
         f"    mov ds, word ptr cs:[{V['LIBSEG']:#x}]", f"    mov ax, word ptr [{pl['SAVSS']:#x}]",
         f"    mov si, word ptr [{pl['SAVSP']:#x}]", '    mov ds, ax', '    mov ax, word ptr [si+10]', '    pop ds', '    pop si']
    for i, (ret, x, y) in enumerate(pl['SITES']):
        c += [f'    cmp ax, {ret:#x}', f'    jne pf_n{i}']
        if x is not None:
            c += [f'    cmp word ptr [bp-2], {x:#x}', f'    jne pf_n{i}']
        c += [f'    cmp word ptr [bp-4], {y:#x}', f'    jne pf_n{i}', '    add word ptr [bp-4], 2', '    jmp pf_done', f'pf_n{i}:']
    c += ['pf_done:', '    pop ax', 'pf_ret:', '    ret']
    return NL.join(c) + NL


NL = chr(10)


def fill_code(g):
    """名札を消す四角を広げる（FILLPATCH: patch_game の中、ES = 部品。FILLCHK: INT 66h の頭、BX = 戻り先。FILLFIX: 本体）"""
    f = g.get('FILL')
    if not f:
        return dict(FILLPATCH='', FILLCHK='', FILLFIX='')
    o = f['OFF']
    patch = [f'    cmp word ptr es:[{o:#x}], 0x468b', '    jne pg_nofill', f'    cmp byte ptr es:[{o + 2:#x}], 6', '    jne pg_nofill',
             f'    mov word ptr es:[{o:#x}], 0x66cd', f'    mov byte ptr es:[{o + 2:#x}], 0x90', 'pg_nofill:']
    chk = [f'    cmp bx, {o + 2:#x}', '    jne fc_no', '    mov ax, word ptr [bp+4]', f"    cmp ax, word ptr cs:[{V['LIBSEG']:#x}]",
           '    jne fc_no', '    call fill_fix', '    jmp i66_out', 'fc_no:']
    x1, y1, x2, y2 = f['ARGS']
    # [bp] = 4D3C の bp（SS は呼び出し側のスタック）。+2 戻り先、+6 x1、+8 y1、+10 x2、+12 y2
    fix = ['fill_fix:', '    mov si, word ptr [bp]', f"    cmp word ptr ss:[si+2], {f['RET']:#x}", '    jne ff_ld',
           f'    cmp word ptr ss:[si+6], {x1:#x}', '    jne ff_ld', f'    cmp word ptr ss:[si+8], {y1:#x}', '    jne ff_ld',
           f'    cmp word ptr ss:[si+10], {x2:#x}', '    jne ff_ld', f'    cmp word ptr ss:[si+12], {y2:#x}', '    jne ff_ld',
           f"    mov word ptr ss:[si+8], {f['Y1']:#x}", f"    mov word ptr ss:[si+10], {f['X2']:#x}",
           'ff_ld:', '    ; 書き換えた mov ax,[bp+6] の代わり', '    mov ax, word ptr ss:[si+6]', '    mov word ptr [bp-2], ax', '    ret']
    return dict(FILLPATCH=NL.join(patch), FILLCHK=NL.join(chk), FILLFIX=NL.join(fix) + NL)


def build(tsv, outdir, game='uw1'):
    g = GAMES[game]
    DG = g['DG']; SINGLES = g['SINGLES']; LIB_ENTRIES = g['LIB_ENTRIES']; LIB_TARGETS = lib_targets(game)
    tr = {k: unescape(v) for k, v in read_tsv(tsv).items()}
    # UR の名前の書式（n:名前、m:/f: も）の印を外す
    import re
    for k, v in list(tr.items()):
        tr[k] = re.sub(r'^[nmf]:', '', v)
    # 物の名前などの「冠詞_名前」の冠詞を外す（原作は冠詞をそのまま前に付けるので、日本語では空にする）
    import re
    for k, v in list(tr.items()):
        if k[0] in (4, 7, 8):
            tr[k] = re.sub(r'^(a|an|some|the)?_', '', v)
    TR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'translation')
    exe_tr = read_exe_tsv(os.path.join(TR, g['EXE_TSV'])) if os.path.exists(os.path.join(TR, g['EXE_TSV'])) else []
    # 英語の原文（長さを比べるだけ。手元の uw1_en.tsv から）
    en_len = {k: unescape(v) for k, v in read_tsv(os.path.join(TR, g['EN_TSV'])).items()}
    over = sum(1 for k, v in tr.items() if k in en_len and len(v.encode('utf-8')) and False)
    glyphs = load_bdf()
    enc = Encoder(list(tr.values()) + [j for o, e, j in exe_tr], glyphs, SINGLES)
    from uwexe import Exe
    img = Exe(game).img
    exetab = bytearray()
    for off, en, ja in exe_tr:
        cur = img[DG * 16 + off:DG * 16 + off + len(en) + 1]
        if cur != en.encode('latin1') + b'\0': raise RuntimeError('EXE の文字列が合わない: %04x %r %r' % (off, en, cur))
        b = enc.encode(ja) + b'\0'
        if len(b) > len(en) + 1: raise RuntimeError('EXE の訳が長すぎる: %04x %r（%d > %d）' % (off, ja, len(b) - 1, len(en)))
        exetab += struct.pack('<HB', off, len(b)) + b
    exetab += b'\xff\xff'
    print('EXE の文字列', len(exe_tr))
    if enc.missing: print('フォントにない字:', ''.join(enc.missing))
    print('字の数', len(enc.chars))
    # ---- UWJP.DAT: 'UWJP' + ブロックごとに（番号の表 u32×数）＋ 文字列
    blocks = sorted(set(b for b, i in tr))
    dat = bytearray(b'UWJP\x01\x00\x00\x00')
    btab = []
    strings = bytearray()
    long = 0
    for b in blocks:
        n = max(i for bb, i in tr if bb == b) + 1
        tpos = len(dat)
        btab.append((b, n, tpos))
        dat += bytes(4 * n)
    for b, n, tpos in btab:
        for i in range(n):
            if (b, i) not in tr: continue
            # 切れ目の空白は、英語の長さを超えない範囲で入れる（本編には文字列を決まった大きさの所へ写す所がある）
            lim = min(0x1ff, max(len(en_len.get((b, i), '')), 1))
            s = enc.encode(tr[(b, i)])
            for every in (() if os.environ.get('UWJP_NOBREAK') else (1, 2, 3, 4, 6, 8)):
                t = enc.encode(add_breaks(tr[(b, i)], every))
                if len(t) <= lim:
                    s = t; break
            else:
                # 空白なしでも英語より長い文は、それでも 8 字ごとに切れ目を入れる（空白のない長い語は、
                # 会話の窓の折り返しが切れ目を探し続けて止まる。UW2 の王座の間のミランダの台詞など）
                if not os.environ.get('UWJP_NOBREAK'):
                    s = enc.encode(add_breaks(tr[(b, i)], 8))
            if len(s) > 0x1ff:
                long += 1; s = s[:0x1ff]
                if 0xc0 <= s[-1]: s = s[:-1]
            struct.pack_into('<I', dat, tpos + 4 * i, len(dat))
            dat += s + b'\0'
    if long: print('0x1FF バイトを超えて切った文:', long)
    # ---- 常駐部
    kw = dict(V)
    kw.update(game_kw(game))
    kw.update(JMP_OLD21=fjmp(V['OLD21']), CALL_OLD21=fcall(V['OLD21']), JMP_ORIG=fjmp(V['ORIGCONT']),
              JMP_OLD33=fjmp(V['OLD33']), CALL_OLD33=fcall(V['OLD33']))
    names = ['getstr', 'breakfind', 'int21', 'int66', 'width_far']
    test = os.environ.get('UWJP_TEST') == '1'
    global RES
    if test and 'int33:' not in RES:
        RES = RES + TEST33
    if test: names.append('int33')
    kw['MCMDNAME'] = 0
    kw['width_far'] = 0
    kw['int33'] = 0
    # 2 回組み立てる（1 回目で長さとラベルを測る）
    tail = {}
    for k in ('PAT_STR', 'PAT_F56', 'PAT_FNT', 'LIBTAB', 'BLOCKTAB', 'GLYPHS', 'BLANK', 'CANDLIST', 'CTAB', 'EXESTR', 'DBLTAB', 'BAKDATA', 'FONTBUF'): kw[k] = 0
    kw['FMAXH'] = int(os.environ.get('UWJP_FMAXH', '7')); kw['NSINGLE'] = len(enc.singles); kw['NTRAIL'] = len(enc.trails)
    for n in names: kw[n] = 0
    for _ in range(2):
        res = asm(RES, CODE, kw)
        lab = labels(RES, CODE, kw, names)
        kw.update(lab)
        p = CODE + len(res)
        def put(name, data):
            nonlocal p
            tail[name] = (p, data); kw[name] = p; p += len(data)
        put('PAT_STR', b'STRINGS.PAK\0')
        put('PAT_F56', b'FONT5X6P.SYS\0')
        put('PAT_FNT', b'.SYS\0')
        if test: put('MCMDNAME', b'C:\\MCMD.TXT\0')
        lt = bytearray()
        for e in LIB_ENTRIES:
            # 元の jmp の行き先は、組み立て時に EXE から読む
            lt += struct.pack('<HH', e, LIB_TARGETS[e])
        put('LIBTAB', bytes(lt))
        put('CANDLIST', bytes(CANDS) + b'\0')
        put('BLANK', bytes(8))
        put('CTAB', enc.table())
        put('EXESTR', bytes(exetab))
        put('DBLTAB', bytes(int(''.join(c * 2 for c in format(n, '04b')), 2) for n in range(16)))
        put('BAKDATA', bytes(64 * 32))
        put('FONTBUF', bytes(14 * 128))
        bt = b''.join(struct.pack('<HHI', b, n, t) for b, n, t in btab)
        put('BLOCKTAB', bt)
        put('GLYPHS', enc.glyphs)
        resend = p
    res = asm(RES, CODE, kw)
    lab2 = labels(RES, CODE, kw, names)
    assert lab2 == lab, (lab, lab2)
    respara = (resend + 15) // 16
    inst_kw = dict(kw); inst_kw.update(DATFILE=0, MSG=0, NBLK=len(btab), RESPARA=respara)
    inst_kw['TESTINST_SAVE'] = TESTINST_SAVE.format(**kw) if test else ''
    inst_kw['TESTINST_SET'] = TESTINST_SET.format(**kw) if test else ''
    inst_kw['RESWORDS'] = respara * 8
    ins = asm(INSTALL, resend, inst_kw)
    datfile = (g['NAME'] + '.DAT').encode() + b'\0'
    inst_kw['DATFILE'] = resend + len(ins)
    inst_kw['MSG'] = inst_kw['DATFILE'] + len(datfile)
    ins = asm(INSTALL, resend, inst_kw)
    com = bytearray(resend + len(ins) - 0x100)
    jmp = resend - (0x100 + 3)
    com[0:3] = b'\xe9' + struct.pack('<H', jmp & 0xffff)
    com[3:7] = b'UWJP'
    com[CODE - 0x100:CODE - 0x100 + len(res)] = res
    for name, (a, data) in tail.items():
        com[a - 0x100:a - 0x100 + len(data)] = data
    com[resend - 0x100:] = ins
    com += datfile + (g['NAME'] + ': ' + g['TITLE'] + ' 日本語化\r\n$').encode('cp932')
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, g['NAME'] + '.COM'), 'wb').write(com)
    open(os.path.join(outdir, g['NAME'] + '.DAT'), 'wb').write(dat)
    print(f"{g['NAME']}.COM {len(com)} バイト（常駐 {respara * 16} バイト）  {g['NAME']}.DAT {len(dat)} バイト  ブロック {len(btab)}  文字列 {len(tr)}")
    print('ラベル', {k: hex(v) for k, v in lab.items()})


def lib_targets(game):
    from uwexe import Exe
    e = Exe(game)
    t = {}
    for a in GAMES[game]['LIB_ENTRIES']:
        o = GAMES[game]['SEG_LIB'] * 16 + a
        assert e.img[o] == 0xe9
        t[a] = (a + 3 + struct.unpack_from('<h', e.img, o + 1)[0]) & 0xffff
    return t


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--game=')]
    gm = next((x.split('=', 1)[1] for x in sys.argv[1:] if x.startswith('--game=')), 'uw1')
    build(a[0], a[1], gm)
