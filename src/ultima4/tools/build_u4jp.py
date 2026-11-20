# ウルティマIV 用の常駐プログラム U4JP.COM を作る（試作）
#   INT 21h AH=3Dh / 3Fh を横取りして、2つのプログラムを書き換える
#   - AVATAR.EXE（本編）: EGA.DRV を開いて読み終わったら（AH=3Fh の後）、
#       ドライバの文字を描く関数（表の25番、0x114C）の先頭を常駐部への far jmp にし、本体の文字列を置き換える
#   - TITLE.EXE（タイトル・キャラクター作成）: CHARSET.EGA を開いたら（AH=3Dh の後）、
#       TITLE の文字を描く関数（EGA 用、0x1F2E）の先頭を far jmp にし、TITLE の文字列を置き換える
#       TITLE のコードのセグメントは、データ（開いたときの DS）− 0x3FD
#   どちらも書き換える前にハッシュ値で照合する。合わなければ何もしない（AVATAR も CHARSET.EGA を開くが、照合で外れる）
#   日本語の字の描き方は共通（jpchar / draw）: 0x80 未満は元の処理へ戻す。1バイトの字はその場で描く。
#   リードが来たら位置だけ覚え、トレイルが来たら2マスまとめて描く。字の色は 'A' の字形に合わせる
# 使い方: python build_u4jp.py <ゲームのフォルダ> <訳のファイル> <出力 U4JP.COM>
#   訳のファイル（試作）: 「英文<TAB>訳」。\n は改行。AVATAR と TITLE の中の同じ英文（前後が 0）を全部置き換える
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import jpenc  # noqa: E402
from jpenc import Encoder, load_bdf, is_jp, fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402
from u4exe import unpack_avatar, DGROUP  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

# 日本語の字と英数字も組にしてよい（相手のない字が「字＋空白」の2マスになるのを減らす）
jpenc.PAIR_ASCII = set(chr(c) for c in range(0x21, 0x7F))   # 組の中の英数字はゲームの字形で描く（番号 0x8000+文字コード）

DRV_LEN = 4730               # EGA.DRV の大きさ
DRV_PUTC = 0x114C            # 文字を描く関数（表の25番）。先頭5バイト = push bp; mov bp,sp; push si; push di
DRV_CHECK = (0x114C, 0x78)   # 照合する範囲（文字を描く関数の全体）
# Ultima IV Upgrade（v1.3）の 256 色の表示部。名前は同じ EGA.DRV で、元のものと入れ替えて使われる
#   文字を描く関数（表の25番）は 0x0F7C。先頭5バイトは push bp; mov bp,sp; push si; push di
#   画面は 320×200 の 256 色（A000、1行 320 バイト）、字は 1字 64 バイト（8×8 の色番号）で、セグメントは表示部の 0x48
VGA_LEN = 5356
VGA_PUTC = 0x0F7C
VGA_CHECK = (0x0F7C, 0x514)  # 照合する範囲: 文字を描く関数から、曲の見分けの英語の表・関数・場面の表まで（0x0F7C〜0x148F）
#                              途中の変数 0x0FDC〜0x0FF7 は、読み込んだ直後に照合するので 0 のまま
VGA_HASH = (0xB92D, 0x1F81)  # その範囲の h12（配布されている EGA.DRV、5,356 バイトから求めた）
VGA_FG = 0x0F                # 日本語の字の色（256 色版の字の白と同じ色番号）
# 256 色の表示部は、文字を描くたびに画面の英語を見て曲を選ぶ（0x0F8A から 0x1110 で記録し、0x146F の表で場面ごとに照合）
#   記録: 23 行 7 桁の字 → 0xFDF（W = 地上、D = ダンジョン）、23 行 24〜39 桁 → 0xFE8（伝言欄の最後の行）、15 行 24〜31 桁 → 0xFE0
#   いまの場面（曲）の番号は 0xFDC。照合が合うと INT 66h AH=8 で曲を替える
# 日本語の字は表示部を通らないので、次のようにして同じ見分けを働かせる
#   - 日本語の字を描くたびに、その位置に「何でもない字」0xFF を記録させ（前の英語が残らないように）、場面ごとの照合を走らせる
#   - 見分けに使う英語にあたる訳の文は、最初の2マスを専用の組（合図）にしておき、その組を描いたら
#     表示部が持っている同じ英語（0x0FF8 からの表）を表示部の記録に写して照合を走らせ、書き込んだ英語はすぐ消す
#     （元は行の最後の字で合い、次の行の最初の字が記録を上書きする。合図は行の頭で出るので、残すと誤って合う）
VGA_REC = 0x1110             # 記録する関数（[bp+6] 行、[bp+8] 桁、[bp+0Ah] 字）
VGA_MODE = 0x0FDC            # いまの場面の番号
VGA_TAB = 0x146F             # 場面ごとの照合の関数の表（0〜12）
VGA_NMODE = 13
VGA_RETF6 = 0x0FD9           # retf 6（近い呼び出しの関数を外から呼ぶ踏み台の戻り先）
#   表示部の比べる関数 0x115B は DS と ES を入れ替えたまま戻るので、踏み台で DS・ES を保存して戻す
MUSIC_CUES = {               # 本体の文字列の位置: (書き込む先, 表示部の英語の表の位置 または 1 文字)
    0x08D2: (0xFE8, 0x0FF8),     # Leaving...
    0x1777: (0xFE8, 0x1003),     # (矢印)Enter towne!
    0x1780: (0xFE8, 0x102E),     # (矢印)Enter castle!
    0x178A: (0xFE8, 0x101E),     # (矢印)Enter village!
    0x1795: (0xFE8, 0x1011),     # (矢印)Enter ruin!
    0x26C0: (0xFE8, 0x103D),     # (矢印)Hole up & Camp
    0x83C5: (0xFE8, 0x104F),     # ancient shrine
    0x7966: (0xFE8, 0x105E),     # Lord British
    0x7AAC: (0xFE8, 0x105E),
    0x6457: (0xFE8, 0x105E),
    0x6A66: (0xFE8, 0x105E),
    0x6B2B: (0xFE8, 0x105E),
    0x3D29: (0xFE8, 0x106B),     # I am Hawkwind
    0x3FE7: (0xFE8, 0x1086),     # Are you in need
    0x553C: (0xFE8, 0x1086),
    0x5A31: (0xFE8, 0x1086),
    0x48DA: (0xFE8, 0x10A5),     # Art thou here to
    0x4DAC: (0xFE8, 0x10B6),     # Want to Buy or
    0x6150: (0xFE8, 0x10C5),     # Food er Ale?
    0x6220: (0xFE8, 0x10D2),     # May I interest
    0x4DEC: (0xFE8, 0x10E1),     # Can I interest
    0x50A2: (0xFE8, 0x10F0),     # Like to see my
    0x116B: (0xFE8, 0x10FF),     # sudden darkness,
    0x164E: (0xFDF, "W"),
    0x167C: (0xFDF, "D"),
}
CUE_MAX = 64
CUE_BASE = len(jpenc.LEADS) * len(jpenc.TRAILS) - CUE_MAX    # 合図の組の番号（普通の組とは別の表を引く）
T_SEGDIFF = 0x3FD            # TITLE: データのセグメント − コードのセグメント
T_PUTC = 0x1F2E              # TITLE の文字を描く関数（EGA 用）。先頭5バイトはドライバと同じ
T_EXIT = 0x1FA4              # その後始末（pop es; pop ds; pop di; pop si; pop bp; ret 2）
T_CHECK = (0x1F2E, 0x7E)     # 照合する範囲

# ジプシーのカードの名前（絵の中の文字）
#   TITLE の 0x2B6D がカードを1枚描く: 0x119A で絵のファイル（HONCOM.EGA など、2枚1組）を
#   確保したメモリ（[bp-4] off, [bp-2] seg）に展開し、0x1195 でその一部を画面に写す
#   展開先はプレーン 8,4,2,1 の順に 8000 バイトずつ（1行 40 バイト）。絵の中の左のカード（徳の番号が偶数）は
#   1 バイト目から、右（奇数）は 27 バイト目から。名前の欄の内側は、カードの左端から 10〜86 ドット × 115〜130 行
#   展開の直後（0x2BC5: add sp,6 / cmp word [bp+4],0 の7バイト）を常駐部への far call にして、欄を日本語で描き直す
C_CALL = 0x2BC5
C_CHECK = (0x2B6D, 0xA2)     # 照合する範囲（カードを描く関数）
CARD_NAMES = ["正直", "慈愛", "勇気", "正義", "献身", "名誉", "霊性", "謙虚"]   # 徳の番号の順
# 下線の色（標準の EGA パレットの番号、上の行・下の行）。元の絵と同じ色にする
CARD_UL = [(13, 5), (13, 5), (1, 8), (1, 8), (7, 8), (7, 8), (1, 5), (1, 5)]
CARD_FONT = ("C:/Windows/Fonts/BIZ-UDMinchoM.ttc", 13)   # BIZ UD 明朝（SIL OFL）
C_ROW0, C_ROWS = 115, 16     # 欄の行
C_X0, C_X1 = 10, 86          # 欄の内側（カードの左端から、両端を含む）
C_BYTES = 10                 # 書き換えるバイト: カードの 1〜10 バイト目（8〜87 ドット）
C_MASK = [0x3F] + [0xFF] * 8 + [0xFE]   # その中で書き換えるビット（10〜86 ドット）

# ---- 常駐部の変数（0x103 から）----
V = dict(OLD21=0x103, DRVH=0x107, DGRP=0x109, DRVSEG=0x10B, DRVCONT=0x10D, TCONT=0x111, TEXIT=0x115,
         TGRP=0x119, LEAD=0x11B, CHR=0x11C, LROW=0x11D, LCOL=0x11F, CROW=0x121, CCOL=0x123,
         VSEG=0x125, LTOFF=0x127, LTSEG=0x129, FONTP=0x12B, CRET=0x12F,
         TLKH=0x133, TLJH=0x135, MSEG=0x137, MOFF=0x139, KWLEN=0x13B,
         GLYSEG=0x13D, PAIRSEG=0x13F, STRSEG=0x141, DATBASE=0x143,
         VDRV=0x145, DMODE=0x146, HOOKED=0x147, CUEACT=0x148)
# VDRV: 読み込んだ表示部が 256 色版（Ultima IV Upgrade の EGA.DRV）なら 1。DMODE: いま描く先が 256 色なら 1
# HOOKED: 本編の表示部を横取りできたら 1（そのときだけ会話を日本語にする。できないのに日本語を混ぜると字化けする）
CODE = 0x150


def fjmp(name):
    a = V[name]
    return f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"


def fcall(name):
    a = V[name]
    return f".byte 0x2e,0xff,0x1e,{a & 0xff},{a >> 8}"


RES = r'''
int21:
    sti
    cmp ah, 0x3d
    je o21
    cmp ah, 0x3f
    je r21
    cmp ah, 0x3e
    je cl21
c21:
    {JMP_OLD21}
o21:
    push di
    mov di, {NAME_DRV}
    call isname
    pop di
    je o_drv
    call istlk
    jne o_nt
    cmp byte ptr cs:[{HOOKED}], 0
    jne o_tlk
o_nt:
    push di
    mov di, {NAME_CHR}
    call isname
    pop di
    jne c21
    pushf
    {CALL_OLD21}
    jc o_x
    call tpatch
    clc
    jmp o_x
o_drv:
    pushf
    {CALL_OLD21}
    jc o_x
    mov word ptr cs:[{DRVH}], ax
    mov word ptr cs:[{DGRP}], ds
    mov byte ptr cs:[{HOOKED}], 0
o_x:
    retf 2
o_tlk:
    pushf
    {CALL_OLD21}
    jc o_x
    call tljopen
    clc
    jmp o_x
cl21:
    cmp bx, word ptr cs:[{TLKH}]
    jne c21
    push bx
    mov bx, word ptr cs:[{TLJH}]
    cmp bx, 0xffff
    je cl_n
    mov ah, 0x3e
    pushf
    {CALL_OLD21}
cl_n:
    pop bx
    mov word ptr cs:[{TLKH}], 0xffff
    mov word ptr cs:[{TLJH}], 0xffff
    mov ah, 0x3e
    jmp c21
r21:
    cmp bx, word ptr cs:[{TLKH}]
    je r_tlk
    cmp bx, word ptr cs:[{DRVH}]
    jne c21
    mov word ptr cs:[{DRVH}], 0xffff
    pushf
    {CALL_OLD21}
    jc r_x
    call apatch
    clc
r_x:
    retf 2

isname:
    push si
    push ax
    mov si, dx
in_l:
    mov al, byte ptr [si]
    cmp al, 0x61
    jb in_u
    cmp al, 0x7a
    ja in_u
    sub al, 0x20
in_u:
    cmp al, byte ptr cs:[di]
    jne in_x
    inc si
    inc di
    or al, al
    jnz in_l
in_x:
    pop ax
    pop si
    ret

r_tlk:
    cmp word ptr cs:[{TLJH}], 0xffff
    jne r_t2
    jmp c21
r_t2:
    pushf
    {CALL_OLD21}
    jc r_t3
    call tlkmerge
    clc
r_t3:
    retf 2

istlk:
    push si
    push ax
    mov si, dx
it_l:
    cmp byte ptr [si], 0
    je it_e
    inc si
    jmp it_l
it_e:
    mov ax, si
    sub ax, dx
    cmp ax, 4
    jb it_no
    cmp byte ptr [si-4], 0x2e
    jne it_x
    mov al, byte ptr [si-3]
    and al, 0xdf
    cmp al, 0x54
    jne it_x
    mov al, byte ptr [si-2]
    and al, 0xdf
    cmp al, 0x4c
    jne it_x
    mov al, byte ptr [si-1]
    and al, 0xdf
    cmp al, 0x4b
    jmp it_x
it_no:
    or si, si
it_x:
    pop ax
    pop si
    ret

tljopen:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov word ptr cs:[{TLKH}], ax
    mov word ptr cs:[{TLJH}], 0xffff
    push cs
    pop es
    mov si, dx
    mov di, {TLJNAME}
    mov cx, 79
    cld
tj_c:
    lodsb
    stosb
    or al, al
    jz tj_d
    loop tj_c
    jmp tj_x
tj_d:
    mov byte ptr es:[di-2], 0x4a
    push cs
    pop ds
    mov dx, {TLJNAME}
    mov ax, 0x3d00
    pushf
    {CALL_OLD21}
    jc tj_x
    mov word ptr [{TLJH}], ax
tj_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

tlkmerge:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    cmp ax, 288
    jne m_x
    mov word ptr cs:[{MSEG}], ds
    mov word ptr cs:[{MOFF}], dx
    mov ax, 0x4201
    xor cx, cx
    xor dx, dx
    pushf
    {CALL_OLD21}
    jc m_x
    sub ax, 288
    sbb dx, 0
    mov cx, dx
    mov dx, ax
    mov bx, word ptr cs:[{TLJH}]
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc m_x
    push cs
    pop ds
    mov dx, {TBUF}
    mov cx, 288
    mov ah, 0x3f
    pushf
    {CALL_OLD21}
    jc m_x
    cmp ax, 288
    jne m_x
    cmp byte ptr [{TBUF}], 0
    jne m_x
    cld
    mov es, word ptr [{MSEG}]
    mov di, word ptr [{MOFF}]
    add di, 3
    mov cx, 10
m_s:
    cmp byte ptr es:[di], 0
    je m_s2
    inc di
    jmp m_s
m_s2:
    inc di
    loop m_s
    mov si, di
    push es
    pop ds
    push cs
    pop es
    mov di, {KWBUF}
    mov cx, 2
m_k:
    lodsb
    stosb
    or al, al
    jnz m_k
    loop m_k
    push cs
    pop ds
    sub di, {KWBUF}
    mov word ptr [{KWLEN}], di
    mov es, word ptr [{MSEG}]
    mov di, word ptr [{MOFF}]
    add di, 3
    mov si, {TBUF}+3
    mov cx, 10
m_c:
    lodsb
    cmp al, 3
    jb m_k1
    stosb
    jmp m_c
m_k1:
    or al, al
    jz m_e
    push si
    mov si, {KWBUF}
    cmp al, 1
    je m_kc
m_ks:
    lodsb
    or al, al
    jnz m_ks
m_kc:
    lodsb
    or al, al
    jz m_kd
    stosb
    jmp m_kc
m_kd:
    pop si
    jmp m_c
m_e:
    stosb
    loop m_c
    mov si, {KWBUF}
    mov cx, word ptr [{KWLEN}]
    rep movsb
    mov cx, word ptr [{MOFF}]
    add cx, 288
    sub cx, di
    jbe m_x
    xor al, al
    rep stosb
m_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

hash:
    xor bx, bx
    xor dx, dx
h_l:
    mov al, byte ptr es:[si]
    xor ah, ah
    rol bx, 1
    add bx, ax
    add dx, ax
    rol dx, 1
    rol dx, 1
    rol dx, 1
    inc si
    loop h_l
    ret

strpatch:
    push ds
    mov ds, word ptr cs:[{STRSEG}]
s_l:
    mov si, word ptr [di]
    cmp si, 0xffff
    je s_x
    mov cx, word ptr [di+2]
    push di
    call hash
    pop di
    cmp bx, word ptr [di+4]
    jne s_n
    cmp dx, word ptr [di+6]
    jne s_n
    push di
    mov si, word ptr [di+8]
    mov cx, word ptr [di+10]
    mov di, word ptr [di]
    cld
    rep movsb
    pop di
s_n:
    add di, 12
    jmp s_l
s_x:
    pop ds
    ret

apatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    test dx, 0x0f
    jnz a_x
    mov cl, 4
    shr dx, cl
    mov bx, ds
    add bx, dx
    push cs
    pop ds
    mov word ptr [{DRVSEG}], bx
    mov word ptr [{DRVCONT}+2], bx
    mov es, bx
    cmp ax, {DRV_LEN}
    je a_ega
    cmp ax, {VGA_LEN}
    jne a_x
    mov si, {VCHK_OFF}
    mov cx, {VCHK_LEN}
    call hash
    cmp bx, {VCHK_H1}
    jne a_x
    cmp dx, {VCHK_H2}
    jne a_x
    mov di, {VGA_PUTC}
    mov word ptr [{DRVCONT}], {VGA_PUTC}+5
    mov byte ptr [{VDRV}], 1
    jmp a_hook
a_ega:
    mov si, {DCHK_OFF}
    mov cx, {DCHK_LEN}
    call hash
    cmp bx, {DCHK_H1}
    jne a_x
    cmp dx, {DCHK_H2}
    jne a_x
    mov di, {DRV_PUTC}
    mov word ptr [{DRVCONT}], {DRV_PUTC}+5
    mov byte ptr [{VDRV}], 0
a_hook:
    mov byte ptr es:[di], 0xea
    mov word ptr es:[di+1], {DRVHOOK}
    mov word ptr es:[di+3], cs
    mov byte ptr [{LEAD}], 0
    mov byte ptr [{HOOKED}], 1
    mov es, word ptr [{DGRP}]
    mov di, {ASTRS}
    call strpatch
    mov ax, word ptr [{DGRP}]
    sub ax, 0xf0d
    mov es, ax
    mov di, {ACODE}
    call strpatch
a_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

tpatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov bx, ds
    sub bx, {T_SEGDIFF}
    jb t_x
    mov ax, ds
    push cs
    pop ds
    mov word ptr [{TGRP}], ax
    mov word ptr [{TCONT}+2], bx
    mov word ptr [{TEXIT}+2], bx
    mov es, bx
    mov si, {TCHK_OFF}
    mov cx, {TCHK_LEN}
    call hash
    cmp bx, {TCHK_H1}
    jne t_x
    cmp dx, {TCHK_H2}
    jne t_x
    mov di, {T_PUTC}
    mov byte ptr es:[di], 0xea
    mov word ptr es:[di+1], {TITLEHOOK}
    mov word ptr es:[di+3], cs
    mov byte ptr [{LEAD}], 0
    mov es, word ptr [{TCONT}+2]
    mov si, {CCHK_OFF}
    mov cx, {CCHK_LEN}
    call hash
    cmp bx, {CCHK_H1}
    jne t_s
    cmp dx, {CCHK_H2}
    jne t_s
    mov di, {C_CALL}
    mov byte ptr es:[di], 0x9a
    mov word ptr es:[di+1], {CARDHOOK}
    mov word ptr es:[di+3], cs
    mov word ptr es:[di+5], 0x9090
t_s:
    mov es, word ptr [{TGRP}]
    mov di, {TSTRS}
    call strpatch
t_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

drvhook:
    push bp
    mov bp, sp
    push si
    push di
    push ds
    push es
    push cs
    pop ds
    mov es, word ptr [{DRVSEG}]
    mov ax, word ptr es:[0x34]
    mov word ptr [{VSEG}], ax
    mov al, byte ptr [{VDRV}]
    mov byte ptr [{DMODE}], al
    or al, al
    jnz dh_v
    mov word ptr [{LTSEG}], es
    mov word ptr [{LTOFF}], 0x52
    mov ax, word ptr es:[0x4a]
    mov word ptr [{FONTP}], ax
    mov ax, word ptr es:[0x4c]
    mov word ptr [{FONTP}+2], ax
    jmp dh_c
dh_v:
    mov word ptr [{FONTP}], 0
    mov ax, word ptr es:[0x48]
    mov word ptr [{FONTP}+2], ax
dh_c:
    mov word ptr [{CUEACT}], 0
    mov al, byte ptr [bp+0xa]
    mov dx, word ptr [bp+6]
    mov cx, word ptr [bp+8]
    call jpchar
    jc d_asc
    cmp byte ptr [{DMODE}], 0
    je d_ret
    call music
d_ret:
    pop es
    pop ds
    pop di
    pop si
    pop bp
    retf 6
d_asc:
    pop es
    pop ds
    pop di
    pop si
    pop bp
    push bp
    mov bp, sp
    push si
    push di
    {JMP_DRVCONT}

titlehook:
    push bp
    mov bp, sp
    push si
    push di
    push ds
    push es
    push cs
    pop ds
    mov es, word ptr [{TGRP}]
    mov byte ptr [{DMODE}], 0
    mov ax, word ptr es:[0x337e]
    mov word ptr [{VSEG}], ax
    mov word ptr [{LTSEG}], es
    mov word ptr [{LTOFF}], 0x23c
    mov ax, word ptr es:[0x7084]
    mov word ptr [{FONTP}], ax
    mov ax, word ptr es:[0x7086]
    mov word ptr [{FONTP}+2], ax
    mov al, byte ptr [bp+4]
    mov dx, word ptr es:[0x708a]
    mov cx, word ptr es:[0x7088]
    call jpchar
    jc t_asc
    {JMP_TEXIT}
t_asc:
    pop es
    pop ds
    pop di
    pop si
    pop bp
    push bp
    mov bp, sp
    push si
    push di
    {JMP_TCONT}

cardhook:
    pop word ptr cs:[{CRET}]
    pop word ptr cs:[{CRET}+2]
    add sp, 6
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    push cs
    pop ds
    mov es, word ptr [{TGRP}]
    cmp word ptr es:[0x7078], 2
    jne k_x
    mov ax, word ptr ss:[bp+6]
    cmp ax, 8
    jae k_x
    and ax, 0xfe
    les di, dword ptr ss:[bp-4]
    call cardlabel
    inc ax
    call cardlabel
k_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    cmp word ptr ss:[bp+4], 0
    {JMP_CRET}

cardlabel:
    push ax
    push di
    mov si, ax
    mov cl, 6
    shl si, cl
    mov bx, si
    shl si, 1
    shl si, 1
    add si, bx
    add si, si
    add si, {LABELS}
    mov bx, {C_START_EVEN}
    test al, 1
    jz kl_b
    mov bx, {C_START_ODD}
kl_b:
    add di, bx
    mov dl, 4
kl_p:
    push di
    mov dh, {C_ROWS}
kl_r:
    mov bx, {C_MASKS}
    mov cx, {C_BYTES}
kl_c:
    mov al, byte ptr [bx]
    not al
    and al, byte ptr es:[di]
    or al, byte ptr [si]
    mov byte ptr es:[di], al
    inc bx
    inc si
    inc di
    loop kl_c
    add di, {C_NEXT}
    dec dh
    jnz kl_r
    pop di
    add di, 0x1f40
    dec dl
    jnz kl_p
    pop di
    pop ax
    ret

jpchar:
    mov byte ptr [{CHR}], al
    mov bl, byte ptr [{LEAD}]
    or bl, bl
    jnz j_trail
    cmp al, 0x80
    jb j_pass
    xor ah, ah
    mov bx, ax
    shl bx, 1
    mov ax, word ptr [bx+{SMAP}]
    cmp ax, 0xfffe
    ja j_lead
    je j_done
    call draw
    jmp j_done
j_lead:
    mov al, byte ptr [{CHR}]
    mov byte ptr [{LEAD}], al
    mov word ptr [{LROW}], dx
    mov word ptr [{LCOL}], cx
    jmp j_done
j_trail:
    mov byte ptr [{LEAD}], 0
    cmp al, 0x40
    jb j_pass
    mov word ptr [{CROW}], dx
    mov word ptr [{CCOL}], cx
    xor bh, bh
    sub bl, 0x81
    cmp bl, 31
    jb jt1
    sub bl, 0x40
jt1:
    xor ah, ah
    sub al, 0x40
    mov di, ax
    mov ax, bx
    mov dx, 192
    mul dx
    add ax, di
    cmp ax, {CUE_BASE}
    jae j_cue
    cmp ax, {NPAIRS}
    jae j_done
    shl ax, 1
    shl ax, 1
    mov bx, ax
    mov es, word ptr [{PAIRSEG}]
    push word ptr es:[bx+2]
    mov ax, word ptr es:[bx]
j_d2:
    mov dx, word ptr [{LROW}]
    mov cx, word ptr [{LCOL}]
    call draw
    pop ax
    mov dx, word ptr [{CROW}]
    mov cx, word ptr [{CCOL}]
    call draw
j_done:
    clc
    ret
j_pass:
    stc
    ret
j_cue:
    sub ax, {CUE_BASE}
    cmp ax, {NCUES}
    jae j_done
    mov bx, ax
    shl bx, 1
    add bx, ax
    shl bx, 1
    add bx, {CUETAB}
    mov ax, word ptr [bx+4]
    mov word ptr [{CUEACT}], ax
    push word ptr [bx+2]
    mov ax, word ptr [bx]
    jmp j_d2

music:
    mov ah, 9
    int 0x66
    mov al, byte ptr [bp+0xa]
    push ax
    mov byte ptr [bp+0xa], 0xff
    mov ax, {VGA_REC}
    call callnear
    mov si, word ptr [{CUEACT}]
    or si, si
    jz mu_d
    xor al, al
    call cuecopy
mu_d:
    mov es, word ptr [{DRVSEG}]
    mov bl, byte ptr es:[{VGA_MODE}]
    xor bh, bh
    cmp bx, {VGA_NMODE}
    jae mu_c
    shl bx, 1
    mov ax, word ptr es:[bx+{VGA_TAB}]
    call callnear
mu_c:
    mov si, word ptr [{CUEACT}]
    or si, si
    jz mu_x
    mov al, 1
    call cuecopy
mu_x:
    pop ax
    mov byte ptr [bp+0xa], al
    ret

cuecopy:
    mov es, word ptr [{DRVSEG}]
    mov di, word ptr [si]
    mov bx, word ptr [si+2]
    mov cx, 1
    or bx, bx
    jnz cc_s
    mov ah, byte ptr [si+4]
    jmp cc_w
cc_s:
    mov cl, byte ptr es:[bx]
    inc bx
cc_w:
    cld
    or al, al
    jnz cc_f
    or bx, bx
    jz cc_l
    push ds
    push es
    pop ds
    mov si, bx
    rep movsb
    pop ds
    ret
cc_l:
    mov al, ah
    stosb
    ret
cc_f:
    mov al, 0xff
    rep stosb
    ret

callnear:
    push ds
    push es
    sub sp, 6
    push cs
    call cn_go
    pop es
    pop ds
    ret
cn_go:
    mov bx, {VGA_RETF6}
    push bx
    push word ptr [{DRVSEG}]
    push ax
    retf

draw:
    cmp byte ptr [{DMODE}], 0
    je dw_e
    jmp vdraw
dw_e:
    push bp
    push es
    push ax
    les bx, dword ptr [{LTOFF}]
    mov di, dx
    shl di, 1
    shl di, 1
    shl di, 1
    shl di, 1
    mov bx, word ptr es:[bx+di]
    add bx, cx
    pop ax
    test ah, 0x80
    jz dj
    push ds
    xor ah, ah
    mov si, ax
    mov cl, 5
    shl si, cl
    mov es, word ptr [{VSEG}]
    lds di, dword ptr [{FONTP}]
    add si, di
    mov cl, 8
da_p:
    mov dx, 0x3c4
    mov al, 2
    out dx, al
    inc dx
    mov al, cl
    out dx, al
    push bx
    mov ah, 8
da_r:
    lodsb
    mov byte ptr es:[bx], al
    add bx, 0x28
    dec ah
    jnz da_r
    pop bx
    shr cl, 1
    jnz da_p
    pop ds
    pop es
    pop bp
    ret
dj:
    mov si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    push ds
    lds di, dword ptr [{FONTP}]
    add di, 0x820
    xor ah, ah
    mov dl, 8
cm_l:
    mov cx, 8
    xor al, al
cm_b:
    or al, byte ptr [di]
    inc di
    loop cm_b
    or al, al
    jz cm_n
    or ah, dl
cm_n:
    shr dl, 1
    jnz cm_l
    pop ds
    mov es, word ptr [{VSEG}]
    mov ch, ah
    mov cl, 8
    push ds
    mov ds, word ptr [{GLYSEG}]
pl:
    mov dx, 0x3c4
    mov al, 2
    out dx, al
    inc dx
    mov al, cl
    out dx, al
    push si
    push bx
    mov ah, 8
rl:
    lodsb
    test ch, cl
    jnz rk
    xor al, al
rk:
    mov byte ptr es:[bx], al
    add bx, 0x28
    dec ah
    jnz rl
    pop bx
    pop si
    shr cl, 1
    jnz pl
    pop ds
    pop es
    pop bp
    ret

vdraw:
    push bp
    push es
    push ax
    mov ax, dx
    mov bx, 2560
    mul bx
    mov di, cx
    shl di, 1
    shl di, 1
    shl di, 1
    add di, ax
    pop ax
    mov es, word ptr [{VSEG}]
    cld
    test ah, 0x80
    jz vj
    push ds
    xor ah, ah
    mov si, ax
    mov cl, 6
    shl si, cl
    lds bx, dword ptr [{FONTP}]
    add si, bx
    mov dx, 8
va_r:
    mov cx, 8
    rep movsb
    add di, 312
    dec dx
    jnz va_r
    pop ds
    pop es
    pop bp
    ret
vj:
    mov si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    push ds
    mov ds, word ptr [{GLYSEG}]
    mov dx, 8
vj_r:
    lodsb
    mov ah, al
    mov cx, 8
vj_b:
    xor al, al
    shl ah, 1
    jnc vj_0
    mov al, {VGA_FG}
vj_0:
    stosb
    loop vj_b
    add di, 312
    dec dx
    jnz vj_r
    pop ds
    pop es
    pop bp
    ret
'''

INIT = r'''
    cli
    mov sp, {ISTACK}
    sti
    mov ax, cs
    add ax, {BASE}
    mov word ptr [{DATBASE}], ax
    add ax, {DATPARAS}
    cmp ax, word ptr [2]
    ja e_open
    mov dx, {DATNAME}
    mov ax, 0x3d00
    int 0x21
    jc e_open
    mov bx, ax
    mov bp, word ptr [{DATBASE}]
r_l:
    push ds
    mov ds, bp
    xor dx, dx
    mov cx, 0x8000
    mov ah, 0x3f
    int 0x21
    pop ds
    jc e_read
    add bp, 0x800
    cmp ax, 0x8000
    je r_l
    mov ah, 0x3e
    int 0x21
    mov es, word ptr [{DATBASE}]
    mov si, {SIG}
    xor di, di
    mov cx, 8
    cld
    repe cmpsb
    jne e_open
    mov ax, word ptr [{DATBASE}]
    add ax, word ptr es:[8]
    mov word ptr [{GLYSEG}], ax
    mov ax, word ptr [{DATBASE}]
    add ax, word ptr es:[10]
    mov word ptr [{PAIRSEG}], ax
    mov ax, word ptr [{DATBASE}]
    add ax, word ptr es:[12]
    mov word ptr [{STRSEG}], ax
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21}+2], es
    mov ax, 0x2521
    mov dx, {E21}
    int 0x21
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
e_read:
    mov ah, 0x3e
    int 0x21
e_open:
    mov ah, 9
    mov dx, {EMSG}
    int 0x21
    mov ax, 0x4c01
    int 0x21
'''


def asm(src, addr, kw):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src.format(**kw), addr)
    return fix16(bytes(enc), addr)


def h12(bs):
    """常駐部の hash と同じ計算（h1 = rol(h1,1)+b、h2 = rol(h2+b,3)）"""
    h1 = h2 = 0
    for b in bs:
        h1 = (((h1 << 1) | (h1 >> 15)) + b) & 0xFFFF
        h2 = (h2 + b) & 0xFFFF
        h2 = ((h2 << 3) | (h2 >> 13)) & 0xFFFF
    return h1, h2


def card_label_pixels(v):
    """徳 v のカードの名前の欄（カードの左端から 8〜87 ドット × 16 行）の色の配列"""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(CARD_FONT[0], CARD_FONT[1])
    t = CARD_NAMES[v]
    im = Image.new("1", (CARD_FONT[1] * len(t) + 8, CARD_FONT[1] + 8), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((2, 2), t, font=f, fill=1)
    g = im.crop(im.getbbox())
    gw, gh = g.size
    assert gh <= 12, (t, gh)
    center = 49 if v % 2 == 0 else 47     # 欄の黒地の中央（絵の左右で 2 ドットずれている）
    gx = center - gw // 2
    px = [[0] * 80 for _ in range(C_ROWS)]
    for y in range(gh):
        for x in range(gw):
            if g.getpixel((x, y)):
                px[y + (12 - gh) // 2][gx + x - 8] = 15
    u1, u2 = CARD_UL[v]
    for x in range(max(C_X0, gx - 2), min(C_X1, gx + gw + 1) + 1):
        px[13][x - 8] = u1
        px[14][x - 8] = u2
    return px


def card_labels():
    """常駐部に持たせる名前の絵: 徳ごとに プレーン 8,4,2,1 × 16 行 × 10 バイト（自分で描いた部分だけ）"""
    out = bytearray()
    for v in range(8):
        px = card_label_pixels(v)
        for k in range(4):
            bit = 8 >> k
            for row in px:
                for b in range(C_BYTES):
                    val = 0
                    for i in range(8):
                        if row[b * 8 + i] & bit:
                            val |= 0x80 >> i
                    out.append(val & C_MASK[b])
    assert len(out) == 8 * 640
    return bytes(out)


# ---- 会話（TLK）----
# 1人 288 バイト: 先頭 3 バイト＋0 区切りの 12 個の文字列。訳すのは前の 10 個（打つ言葉 2 つは英語のまま）
TLK_FIELDS = ["name", "pronoun", "look", "job", "health", "kw1", "kw2", "question", "yes", "no"]
TLK_WIDTH = 16               # 会話欄の幅（桁 24〜39）
NOSTART = set("、。，．！？!?）」』〕】…ーっゃゅょァィゥェォッャュョぁぃぅぇぉ：:")   # 行の頭に来てはいけない字


def read_tlk_translation(path):
    """{('MOONGLOW.TLK', 番号 1〜16): {項目: 訳}}。書き方: MOONGLOW#01.job<TAB>訳（\\n で改行）"""
    tlk = {}
    if not os.path.exists(path):
        return tlk
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        key, ja = line.split("\t")
        town, rest = key.split("#")
        num, field = rest.split(".")
        if field not in TLK_FIELDS:
            sys.exit(f"{path}:{n}: 項目の名前がちがいます: {field}")
        tlk.setdefault((town.upper() + ".TLK", int(num)), {})[field] = ja.replace("\\n", "\n")
    return tlk


def cells(enc, s):
    """画面で使うマスの数（1バイト＝1マス）"""
    return sum(1 if u[0] in "as" else 2 for u in enc.segment(s))


def wrap(enc, text, width=TLK_WIDTH):
    """width マスごとに改行を入れる。英数字の続きは切らない。行の頭に句読点などが来ないようにする"""
    lines = []
    for para in text.split("\n"):
        toks = []
        for ch in para:
            if toks and not is_jp(ch) and not is_jp(toks[-1][-1]) and ch != " " and toks[-1][-1] != " ":
                toks[-1] += ch
            else:
                toks.append(ch)
        cur = []
        for tok in toks:
            if cells(enc, "".join(cur + [tok])) <= width:
                cur.append(tok)
                continue
            if tok in NOSTART and len(cur) >= 2:     # 句読点は前の字と一緒に次の行へ
                carry = cur.pop()
                lines.append("".join(cur).rstrip())
                cur = [carry, tok]
            else:
                lines.append("".join(cur).rstrip())
                cur = [tok] if tok.strip() else []
        lines.append("".join(cur))
    for ln in lines:
        if cells(enc, ln) > width:
            sys.exit(f"{width} マスに収まらない行があります: {ln}")
    return "\n".join(lines)


def kw_mark(b, k, mark):
    """符号にした訳 b の中で、言葉 k が1バイトずつの字として並んでいる最初の所を印 mark（1 バイト）に替える"""
    cells = []
    i = 0
    while i < len(b):
        n = 2 if b[i] in jpenc.LEADS else 1
        cells.append((i, n))
        i += n
    for j in range(len(cells) - len(k) + 1):
        if all(cells[j + t][1] == 1 and b[cells[j + t][0]] == k[t] for t in range(len(k))):
            s = cells[j][0]
            return b[:s] + bytes([mark]) + b[s + len(k):], True
    return b, False


def build_tlj(gamedir, tlk, enc, outdir):
    """訳のある町ごとに .TLJ を作る。1人 288 バイト: 先頭 0（訳あり）/ 0xFF（訳なし）、2 バイト空き、訳 10 個"""
    made = []
    towns = sorted({t for t, _ in tlk})
    for town in towns:
        orig = open(os.path.join(gamedir, town), "rb").read()
        out = bytearray()
        for i in range(len(orig) // 288):
            rec = orig[i * 288:(i + 1) * 288]
            tr = tlk.get((town, i + 1))
            if not tr:
                out += b"\xff" + bytes(287)
                continue
            parts = rec[3:].split(b"\0")
            keys = parts[10:12]
            body = bytearray()
            marks = 0
            for f in TLK_FIELDS:
                if f not in tr:
                    sys.exit(f"{town} {i + 1}: {f} の訳がありません")
                b = enc.encode(tr[f] if f == "pronoun" else wrap(enc, tr[f]))
                # 訳に添えた「(言葉)」が会話ファイルの言葉と同じなら、読むときにその言葉を差し込む印（1 / 2）にする
                #   Upgrade で言葉が直された人（ユーのこじき SINE→SINN）でも、打つ言葉と添えた言葉が合う
                for n, k in enumerate(keys):
                    kt = k.decode("latin-1")
                    if kt and "(" + kt + ")" in tr[f]:
                        b, ok = kw_mark(b, k, n + 1)
                        marks += ok          # 折り返しで言葉が行をまたぐ所（HO E など）は印にせずそのまま
                body += b + b"\0"
            need = 3 + len(body) + 3 * marks + sum(len(k) + 1 for k in keys)   # 差し込む言葉は 4 文字までとみる
            if need > 288:
                sys.exit(f"{town} {i + 1}: {need} バイト > 288（訳を短くしてください）")
            out += b"\0\0\0" + body + bytes(285 - len(body))
        name = town[:-1] + "J"
        open(os.path.join(outdir, name), "wb").write(out)
        made.append(name)
    return made


def read_translation(path):
    tr = {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        en, ja = line.split("\t")
        tr[en.replace("\\n", "\n")] = ja.replace("\\n", "\n")
    return tr


def unesc(t):
    """表の書き方を元に戻す: \n は改行、\x12（右へ）と \x08（戻る）は入力欄の制御バイト"""
    return t.replace("\\n", "\n").replace("\\x12", "\x12").replace("\\x08", "\x08")


def read_master(path):
    """元表: {位置: (最大バイト, 種類, 英文)}"""
    m = {}
    for line in open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        i, n, k, note, en = line.rstrip("\n").split("\t")
        m[int(i[2:], 16)] = (int(n), k, unesc(en))
    return m


def read_id_translation(path, prefix, master):
    """訳のファイル（id<TAB>訳）: {位置: 訳}。ファイルがなければ空"""
    out = {}
    if not os.path.exists(path):
        return out
    for no, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        i, ja = line.split("\t", 1)
        if not i.startswith(prefix + ":"):
            sys.exit(f"{path}:{no}: id がちがいます: {i}")
        off = int(i[2:], 16)
        if off not in master or master[off][1] != "text":
            sys.exit(f"{path}:{no}: 元表で訳す行ではありません: {i}")
        out[off] = unesc(ja)
    return out


TITLE_WIDTH = 39


def cue_encode(enc, text, code):
    """最初に並ぶ2マス（改行や入力欄の制御バイトをはさまない2字）を合図の組 code(字, 字) にして符号にする"""
    ctrl = "\n\x12\x08"
    for i in range(len(text) - 1):
        if text[i] not in ctrl and text[i + 1] not in ctrl:
            return enc.encode(text[:i]) + code(text[i], text[i + 1]) + enc.encode(text[i + 2:])
    sys.exit(f"合図にする2マスがありません: {text!r}")


def id_strings(data, items, master, enc, prefix, errors, cues=None, cuereg=None):
    """id で指定した訳: [(位置, 長さ, h1, h2, 中身)]。AVATAR は 16 マスで改行を入れる
    cues: {位置: (書き込む先, 英語の位置)} の文は最初の2マスを合図の組にし、cuereg に (字, 字, 書き込む先, 英語の位置) を足す"""
    out = []

    def code(a, b, off):
        cuereg.append((a, b) + cues[off])
        idx = CUE_BASE + len(cuereg) - 1
        nt = len(jpenc.TRAILS)
        return bytes([jpenc.LEADS[idx // nt], jpenc.TRAILS[idx % nt]])
    for off, ja in sorted(items.items()):
        n, k, en = master[off]
        orig = data[off:off + n]
        if orig != en.encode("latin1") or data[off + n] != 0:
            errors.append(f"{prefix}:{off:04X}: 元表と本体が合いません")
            continue
        if prefix == "A":
            body = ja.rstrip("\x12\x08")       # 末尾の入力欄の制御バイトは改行の計算から外す
            text = wrap(enc, body) + ja[len(body):]
        else:
            text = ja
            for ln in text.split("\n"):
                if cells(enc, ln) > TITLE_WIDTH:
                    errors.append(f"{prefix}:{off:04X}: {TITLE_WIDTH} マスを越える行: {ln}")
        if cues and off in cues:
            new = cue_encode(enc, text, lambda a, b: code(a, b, off)) + b"\0"
        else:
            new = enc.encode(text) + b"\0"
        if len(new) > n + 1:
            errors.append(f"{prefix}:{off:04X}: 長すぎます {len(new) - 1} > {n} バイト: {ja!r}")
            continue
        out.append((off, n) + h12(orig) + (new,))
    return out


def merge_strs(by_text, by_id):
    """同じ位置は id の訳を優先する"""
    d = {s[0]: s for s in by_text}
    d.update({s[0]: s for s in by_id})
    return [d[k] for k in sorted(d)]


def find_strings(data, tr, enc, label):
    """データの中の、前後が 0 の英文を探す: [(位置, 長さ, h1, h2, 中身)]"""
    out = []
    for en, ja in tr.items():
        if en.startswith("@"):               # 「@英文」: 前が 0 でなくてもよい（後ろが 0 だけで探す）
            en = en[1:]
            key = en.encode("latin1") + b"\0"
            skip = 0
        else:
            key = b"\0" + en.encode("latin1") + b"\0"
            skip = 1
        new = enc.encode(ja) + b"\0"
        n = len(en)
        pos = 0
        hits = 0
        while True:
            pos = data.find(key, pos)
            if pos < 0:
                break
            off = pos + skip
            if len(new) > n + 1:
                sys.exit(f"訳が長すぎます: {en!r} → {ja!r}（{len(new) - 1} > {n} バイト）")
            out.append((off, n) + h12(data[off:off + n]) + (new,))
            hits += 1
            pos = off + 1
        if hits:
            print(f"{label} {en!r}: {hits} か所 → {new.hex()}")
    return out


# 本体（AVATAR）のコードの書き換え: 英語の複数形の「s」を 1 文字出す所（mov ax,73h / push ax / call 0x0C9F）を nop にする
#   0xCDD3 武器屋の品物の一覧、0xDE1D 酒場の「〜皿」、0xE6CD ロード・ブリティッシュの別れの言葉（friend → friends）
#   0xE5BC ロード・ブリティッシュの最初の言葉で、名前のあとの「,」（mov ax,2Ch）
#   0x4B21 状態欄の「Candl」に足す「e」、0x760B「may NOT use」のあとの「a」、0xDE24「〜皿」のあとの「.」
A_CODE_NOP = [0xCDD3, 0xDE1D, 0xE6CD, 0xE5BC, 0x4B21, 0x760B, 0xDE24]


def code_patches(img):
    out = []
    for off in A_CODE_NOP:
        orig = img[off:off + 7]
        if orig[0] != 0xB8 or orig[2:4] != bytes.fromhex("0050") or orig[4] != 0xE8:
            sys.exit(f"本体のコード {off:04X} が予想とちがいます: {orig.hex()}")
        out.append((off, 7) + h12(orig) + (b"\x90" * 7,))
    return out


def make_dat(gly, pairs, astrs, tstrs, strtab, acode=()):
    """U4JP.DAT を作る: 先頭 16 バイト（照合用の 8 バイト、字形・組・文字列のセグメント（段落）、全体の段落数）
    のあとに、段落の境目から字形、組、文字列の表を置く。どれも 64KB 未満"""
    import zlib
    pairs_b = b"".join(struct.pack("<HH", a, b) for a, b in pairs)
    abl = strtab(0, astrs)
    tbl = strtab(len(abl), tstrs)
    cbl = strtab(len(abl) + len(tbl), list(acode))
    strs_b = abl + tbl + cbl
    for name, x in (("字形", gly), ("組", pairs_b), ("文字列", strs_b)):
        if len(x) >= 0x10000:
            sys.exit(f"U4JP.DAT の{name}の表が 64KB を越えました（{len(x)} バイト）")

    def pad(x):
        return x + bytes(-len(x) % 16)
    gseg = 1
    pseg = gseg + len(pad(gly)) // 16
    sseg = pseg + len(pad(pairs_b)) // 16
    body = pad(gly) + pad(pairs_b) + pad(strs_b)
    total = 1 + len(body) // 16
    sig = b"U4JD" + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    dat = sig + struct.pack("<4H", gseg, pseg, sseg, total) + body
    return dat, dict(ASTRS=0, TSTRS=len(abl), ACODE=len(abl) + len(tbl), DATPARAS=total), sig


def main(gamedir, trfile, out):
    img = unpack_avatar(os.path.join(gamedir, "AVATAR.EXE"))
    adata = img[DGROUP:]
    t = open(os.path.join(gamedir, "TITLE.EXE"), "rb").read()
    timg = t[struct.unpack_from("<H", t, 8)[0] * 16:]
    tdata = timg[T_SEGDIFF * 16:]
    drv = open(os.path.join(gamedir, "EGA.DRV"), "rb").read()
    assert len(drv) == DRV_LEN
    dchk = h12(drv[DRV_CHECK[0]:DRV_CHECK[0] + DRV_CHECK[1]])
    tchk = h12(timg[T_CHECK[0]:T_CHECK[0] + T_CHECK[1]])
    cchk = h12(timg[C_CHECK[0]:C_CHECK[0] + C_CHECK[1]])
    assert timg[C_CALL:C_CALL + 7] == bytes.fromhex("83c406837e0400")
    labels = card_labels()
    assert timg[T_PUTC:T_PUTC + 5] == drv[DRV_PUTC:DRV_PUTC + 5]
    tr = read_translation(trfile)
    font = load_bdf(BDF)

    trdir = os.path.dirname(trfile)
    tlk = read_tlk_translation(os.path.join(trdir, "tlk_ja.txt"))
    amaster = read_master(os.path.join(trdir, "master_avatar.tsv"))
    tmaster = read_master(os.path.join(trdir, "master_title.tsv"))
    ida = read_id_translation(os.path.join(trdir, "ja_avatar.tsv"), "A", amaster)
    idt = read_id_translation(os.path.join(trdir, "ja_title.tsv"), "T", tmaster)
    alltext = (list(tr.values()) + [t for p in tlk.values() for t in p.values()]
               + list(ida.values()) + list(idt.values()))
    enc = Encoder(alltext)
    if os.environ.get("U4JP_NOSINGLE"):      # 試験用: 1バイトの字を使わず、全部を2バイトの組にする
        enc.single = {}
    tljs = build_tlj(gamedir, tlk, enc, os.path.dirname(out))
    errors = []
    cuereg = []
    missing = [f"A:{o:04X}" for o in MUSIC_CUES if o not in ida]
    if missing:
        sys.exit(f"曲の合図にする文の訳がありません: {missing}")
    astrs = merge_strs(find_strings(adata, tr, enc, "AVATAR"),
                       id_strings(adata, ida, amaster, enc, "A", errors, MUSIC_CUES, cuereg))
    if len(cuereg) != len(MUSIC_CUES) or len(cuereg) > CUE_MAX:
        sys.exit(f"曲の合図の数が合いません: {len(cuereg)}")
    tstrs = merge_strs(find_strings(tdata, tr, enc, "TITLE"), id_strings(tdata, idt, tmaster, enc, "T", errors))
    if errors:
        print(chr(10).join(errors))
        sys.exit(f"直す所が {len(errors)} か所あります")
    unused = [en for en in tr if not any(en.lstrip("@").encode("latin1") in d for d in (adata, tdata))]
    if unused:
        print("見つからない英文:", unused)

    # 字形: 0 は空白。使う日本語の字を順に並べる
    chars = sorted({c for t in alltext for c in t if is_jp(c)})
    gidx = {c: i + 1 for i, c in enumerate(chars)}
    gly = bytearray(8)
    for c in chars:
        g = font.get(ord(c))
        if g is None:
            sys.exit(f"美咲フォントに字がありません: {c}")
        gly += g
    # 1バイトの字: 文字コード → 字の番号（0xFFFF=リード、0xFFFE=使わない）
    smap = [0xFFFE] * 256
    for c in jpenc.LEADS:
        smap[c] = 0xFFFF
    for ch, code in enc.single.items():
        smap[code] = gidx[ch]
    def gi(ch):
        return gidx[ch] if is_jp(ch) else 0x8000 | ord(ch)
    pairs = [None] * len(enc.pairs)
    for (a, b), i in enc.pairs.items():
        pairs[i] = (gi(a), gi(b) if b else 0)
    if len(pairs) >= CUE_BASE:
        sys.exit(f"組が多すぎて合図の番号と重なります（{len(pairs)}）")

    def strtab(base, strs):
        tab = bytearray()
        body = bytearray()
        start = base + 12 * len(strs) + 2
        for off, n, a, b, new in strs:
            tab += struct.pack("<6H", off, n, a, b, start + len(body), len(new))
            body += new
        return bytes(tab + b"\xff\xff" + body)

    def build(addr):
        kw = dict(V, DRV_LEN=DRV_LEN, DRV_PUTC=DRV_PUTC, T_PUTC=T_PUTC, T_SEGDIFF=T_SEGDIFF,
                  VGA_LEN=VGA_LEN, VGA_PUTC=VGA_PUTC, VCHK_OFF=VGA_CHECK[0], VCHK_LEN=VGA_CHECK[1],
                  VCHK_H1=VGA_HASH[0], VCHK_H2=VGA_HASH[1], VGA_FG=VGA_FG,
                  VGA_REC=VGA_REC, VGA_MODE=VGA_MODE, VGA_TAB=VGA_TAB, VGA_NMODE=VGA_NMODE, VGA_RETF6=VGA_RETF6,
                  CUE_BASE=CUE_BASE, NCUES=len(cuereg),
                  DCHK_OFF=DRV_CHECK[0], DCHK_LEN=DRV_CHECK[1], DCHK_H1=dchk[0], DCHK_H2=dchk[1],
                  TCHK_OFF=T_CHECK[0], TCHK_LEN=T_CHECK[1], TCHK_H1=tchk[0], TCHK_H2=tchk[1],
                  JMP_OLD21=fjmp("OLD21"), CALL_OLD21=fcall("OLD21"), JMP_DRVCONT=fjmp("DRVCONT"),
                  JMP_TCONT=fjmp("TCONT"), JMP_TEXIT=fjmp("TEXIT"), NPAIRS=len(pairs),
                  CCHK_OFF=C_CHECK[0], CCHK_LEN=C_CHECK[1], CCHK_H1=cchk[0], CCHK_H2=cchk[1], C_CALL=C_CALL,
                  JMP_CRET=fjmp("CRET"), C_START_EVEN=C_ROW0 * 40 + 2, C_START_ODD=C_ROW0 * 40 + 28,
                  C_ROWS=C_ROWS, C_BYTES=C_BYTES, C_NEXT=40 - C_BYTES, **datkw, **addr)
        code = asm(RES, CODE, kw)

        def label(name):
            # ラベルの手前までを組み立てて長さを測る。後ろで定義される呼び先は仮のラベルを置く（call は長さが一定）
            src = RES.split("\n" + name + ":")[0]
            later = [x for x in ("jpchar", "draw", "music") if "\n" + x + ":" not in src]
            return CODE + len(asm(src + "".join(f"\n{x}:" for x in later) + "\n", CODE, kw))
        lay = {"DRVHOOK": label("drvhook"), "TITLEHOOK": label("titlehook"), "CARDHOOK": label("cardhook")}
        p = CODE + len(code)
        tail = bytearray()

        def put(name, data):
            lay[name] = p + len(tail)
            tail.extend(data)
        put("NAME_DRV", b"EGA.DRV\0")
        put("NAME_CHR", b"CHARSET.EGA\0")
        put("SMAP", b"".join(struct.pack("<H", x) for x in smap))
        put("C_MASKS", bytes(C_MASK))
        put("TLJNAME", bytes(80))
        put("KWBUF", bytes(40))
        put("TBUF", bytes(288))
        put("LABELS", labels)
        # 曲の合図: 書き込みの記録（先 2 バイト、表示部の英語の表の位置 2 バイト（0 なら次の 1 文字）、1 文字）と、
        #   合図の組の表（左の字、右の字、記録の位置）
        recs = bytearray()
        rpos = []
        for a, b, dest, src in cuereg:
            rpos.append(len(recs))
            recs += struct.pack("<HHB", dest, 0, ord(src)) if isinstance(src, str) else struct.pack("<HHB", dest, src, 0)
        put("CUEREC", recs)
        put("CUETAB", b"".join(struct.pack("<3H", gi(a), gi(b), lay["CUEREC"] + r)
                               for (a, b, _, _), r in zip(cuereg, rpos)))
        return code, bytes(tail), lay

    names = ["DRVHOOK", "TITLEHOOK", "CARDHOOK", "NAME_DRV", "NAME_CHR", "SMAP",
             "C_MASKS", "LABELS", "TLJNAME", "KWBUF", "TBUF", "CUETAB"]
    dat, datkw, sig = make_dat(gly, pairs, astrs, tstrs, strtab, code_patches(img))
    addr = {k: 0x1234 for k in names}
    for _ in range(4):
        code, tail, lay = build(addr)
        new = {k: lay[k] for k in names}
        if new == addr:
            break
        addr = new
    assert {k: lay[k] for k in names} == addr
    res_end = CODE + len(code) + len(tail)
    # 組み込みのときだけ使う部分（常駐しない）: 知らせの文、DAT の名前と照合用の 8 バイト、組み込みの処理
    msg = "U4JP: Ultima IV Japanese patch loaded\r\n$".encode("ascii")
    emsg = "U4JP: U4JP.DAT missing or mismatched - patch NOT loaded\r\n$".encode("ascii")   # DOS の文字画面は日本語を出せない
    datname = b"U4JP.DAT\0"
    idata = msg + emsg + datname + sig + bytes(512)    # 最後の 512 バイトは組み込み中のスタック（DAT を読むと元のスタック cs:FFFE を上書きするため）
    o_msg = res_end
    o_emsg = o_msg + len(msg)
    o_name = o_emsg + len(emsg)
    o_sig = o_name + len(datname)
    init_addr = res_end + len(idata)
    base = 0x2000
    for _ in range(4):
        kwi = dict(V, E21=CODE, MSG=o_msg, EMSG=o_emsg, DATNAME=o_name, SIG=o_sig, ISTACK=init_addr - 2,
                   BASE=base, DATPARAS=datkw["DATPARAS"], PARAS=base + datkw["DATPARAS"])
        init = asm(INIT, init_addr, kwi)
        nb = (init_addr + len(init) + 15) // 16
        if nb == base:
            break
        base = nb
    assert (init_addr + len(init) + 15) // 16 == base
    head = bytearray(CODE - 0x100)
    head[0] = 0xE9
    head[1:3] = struct.pack("<H", (init_addr - 0x103) & 0xFFFF)

    def setw(name, val):
        o = V[name] - 0x100
        head[o:o + 2] = struct.pack("<H", val)
    setw("DRVH", 0xFFFF)
    setw("TLKH", 0xFFFF)
    setw("TLJH", 0xFFFF)
    setw("DRVCONT", DRV_PUTC + 5)      # セグメントは読み込み時に入れる
    setw("TCONT", T_PUTC + 5)
    setw("TEXIT", T_EXIT)
    com = bytes(head) + code + tail + idata + init
    if len(com) > 0xF000:
        sys.exit(f"U4JP.COM が大きすぎます（{len(com)} バイト）")
    open(out, "wb").write(com)
    datpath = os.path.join(os.path.dirname(out), "U4JP.DAT")
    open(datpath, "wb").write(dat)
    print(f"{out}: {len(com)} バイト（常駐 {res_end - 0x100}）、U4JP.DAT: {len(dat)} バイト、"
          f"常駐の合計 {(base + datkw['DATPARAS']) * 16} バイト、字 {len(chars)}、組 {len(pairs)}、"
          f"1バイトの字 {len(enc.single)}、置き換え AVATAR {len(astrs)} / TITLE {len(tstrs)} か所、"
          f"会話 {', '.join(tljs)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
