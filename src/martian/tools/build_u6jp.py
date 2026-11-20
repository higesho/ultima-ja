# ウルティマVI 用の常駐プログラム U6JP.COM と、人物ごとの表のファイル U6JP.DAT を作る
#
# 常駐部（INT 21h AH=3Dh を横取り）: 本編 GAME.EXE が U6.CH を開いたとき（EXEPACK の展開は済んでいる）に、
#   照合してから次を行う。DS = 本編のデータ（DGROUP）、DX = 0x02EB（"U6.CH"）
#   1. 1文字出力の関数ポインタ DS:0x04CC を hook に向ける（本編のコードは書き換えない）
#   2. 折り返しの 0x76E8〜0x7706 を wrapbrk の呼び出しに（組の途中で切らない、日本語の前後で切る、行頭禁則）
#   3. @ の強調の 0x7C1F〜0x7C41 を hlend の呼び出しに（0x7F で強調を止め、字は描かない）
#   4. 会話の文章の判定 0x10901 の 80h を 9Ch に（0x80〜0x9B を文章として通す）
#   5. 本編のデータの文字列を日本語に置き換える（元の長さ以内）
#
# 符号（1バイト = 1マス、美咲フォント 8×8）:
#   0x80〜0x9B  場面の表（人物ごと。U6JP.DAT から読む）: 1バイトの字 0x80〜0x83、組のリード 0x84〜0x9B
#   0xA0〜0xFF  常に持つ表（常駐部の中）: 1バイトの字 0xA0〜0xC7、組のリード 0xC8〜0xFF（0xF1 を除く）
#   トレイルは 0x21〜0x7E から本編が特別扱いする記号と @ の強調を止める字と DEL を除いたもの＋ 0x80〜0x9B（場面の表）、
#   常に持つ表はさらに 0xA0〜0xFF（0xF1 を除く）
#   場面の表は、場面の符号が来たときに、会話スクリプトの置き場所 [0x4D50] の2バイト目（FF <人物の番号>）を見て、
#   前と違えば U6JP.DAT から読み込む
#
# 使い方: python build_u6jp.py <ゲームのフォルダ> <本編の文字列の訳> <出力 U6JP.COM>
#   本編の文字列の訳: 「英文<TAB>訳」。\n は改行。本編のデータの中の、前後が 0 の英文を全部置き換える
#   U6JP_CONVTEST=<会話の訳 番号<TAB>訳>  U6JP_CONVOUT=<出力先>: CONVERSE.A/B と U6JP.DAT を作る
#   U6JP_NOWRAP=1: 折り返しを直さない版（比べる用）
import contextlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import jpenc  # noqa: E402
from jpenc import Encoder, load_bdf, is_jp, fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402
from unexepack import unpack  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

jpenc.PAIR_ASCII = set()      # 英数字と日本語の字は組にしない（英字はゲームの字形で描く）
# 本編の文字出力（0464:33D3）が特別扱いする記号（@ 強調、\ 複数形、< > ルーン表示など）と、
# @ の強調を止める字（DS:0x05BE）。どちらも組のトレイルに使わない
SPECIAL = set(b"#$%&*/<>@\\^`") | set(b" ,.:;!?'-\"\n") | {0x7F}
ASC_TRAILS = [c for c in range(0x21, 0x7F) if c not in SPECIAL]
NO_F1 = [c for c in range(0xA0, 0x100) if c != 0xF1]   # 人物の名前は 0xF1 まで写されるので 0xF1 は使わない


class CodeSet:
    def __init__(self, singles, leads, trails):
        self.singles, self.leads, self.trails = singles, leads, trails


SCENE = CodeSet(list(range(0x80, 0x84)), list(range(0x84, 0x9C)), ASC_TRAILS + list(range(0x80, 0x9C)))
_GS = int(os.environ.get("U6JP_GSINGLES", "40"))   # 試験用: 常に持つ表の1バイトの字の数（0 で全部を組にする）
GLOBAL = CodeSet(NO_F1[:_GS], NO_F1[_GS:], ASC_TRAILS + list(range(0x80, 0x9C)) + NO_F1)


@contextlib.contextmanager
def codes(cs):
    old = jpenc.SINGLE_CODES, jpenc.LEADS, jpenc.TRAILS
    jpenc.SINGLE_CODES, jpenc.LEADS, jpenc.TRAILS = cs.singles, cs.leads, cs.trails
    try:
        yield
    finally:
        jpenc.SINGLE_CODES, jpenc.LEADS, jpenc.TRAILS = old


class Enc:
    """符号の割り当てを決めた Encoder"""
    def __init__(self, cs, texts):
        self.cs = cs
        with codes(cs):
            self.e = Encoder(texts)

    def encode(self, t):
        with codes(self.cs):
            return self.e.encode(t)


# 本編の位置
CONV_SEG, CONV_OFF, CONV_NEW = 0x0ECB, 0x1C51, 0x9C   # 会話の文章の判定 cmp [bp-1],80h → 9Ch
DGROUP = 0x2D85               # 本編のデータのセグメント（ロード位置から）
NAME_OFF = 0x02EB             # データの "U6.CH"
PUTC_SEG, PUTC_OFF = 0x0464, 0x0286   # 本編の1文字出力
PUTC_LEN = 0x6B               # 照合する長さ（関数の全体 0x48C6〜0x4930）
PTR_PUTC = 0x04CC             # 1文字出力の関数ポインタ
WIN = 0x04DF                  # 今の窓の構造体へのポインタ（+8 が属性、8 = ルーン表示）
DRVP = 0xECC4                 # 画面ドライバの構造体への far ポインタ（+6 がフォントの far ポインタ）
SCRP = 0x4D50                 # 会話スクリプトの置き場所の far ポインタ（先頭 FF <人物の番号>）
SLOT = 0x0D                   # U6.CH の空いている字（日本語の字形を一時的に写す）
WRAP_OFF, WRAP_LEN = 0x30A8, 31                  # 折り返しの「空白か - の直後」を探す部分（0464 の中）
BUF, LLEN, LDONE = 0xB651, 0x057A, 0x057B        # 1行分の文字、たまった長さ、描いた所まで
HL_OFF, HL_LEN = 0x35DF, 35                      # @ の強調の処理（0464 の中）
HL_LIST, LPREFIX, COL_NORMAL = 0x05BE, 0x057D, 0x2A56
KINSOKU = set("、。，．・：；？！ー～…‥」』）］｝〉》ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々ゝゞヽヾ")
ASC_NOSTART = set(".,!?:;)]}")
SCENE_MAX = 14 * 1024         # 人物ごとの表を読み込む場所の大きさ

# ---- 常駐部の変数（0x103 から）----
V = dict(OLD21=0x103, ORIG=0x107, LEAD=0x10B, LROW=0x10C, LCOL=0x10E, SAVE=0x110,
         WPREV=0x118, WBEST=0x11A, WLAST=0x11C, CURGLY=0x11E, WDESC=0x120, CURNPC=0x122,
         ENTRY=0x124, DESC_G=0x12A, DESC_S=0x136, WSCN=0x142)
# 表の説明（12バイト）: +0 組の位置、+2 組の数、+4 トレイルの数、+6 トレイルの表、+8 字形、+10 行頭禁則
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
c21:
    {JMP_OLD21}
o21:
    cmp dx, {NAME_OFF}
    jne c21
    push di
    mov di, {NAME_U6CH}
    call isname
    pop di
    jne c21
    pushf
    {CALL_OLD21}
    jc o_x
    call gpatch
    clc
o_x:
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
    ret

gpatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ax, ds
    sub ax, {DGROUP}
    jb g_x
    add ax, {PUTC_SEG}
    cmp word ptr [{PTR_PUTC}], {PUTC_OFF}
    jne g_x
    cmp word ptr [{PTR_PUTC}+2], ax
    jne g_x
    mov es, ax
    mov si, {PUTC_OFF}
    mov cx, {PUTC_LEN}
    call hash
    cmp bx, {CHK_H1}
    jne g_x
    cmp dx, {CHK_H2}
    jne g_x
    mov ax, word ptr [{PTR_PUTC}]
    mov word ptr cs:[{ORIG}], ax
    mov ax, word ptr [{PTR_PUTC}+2]
    mov word ptr cs:[{ORIG}+2], ax
    mov word ptr [{PTR_PUTC}], {HOOK}
    mov word ptr [{PTR_PUTC}+2], cs
    mov byte ptr cs:[{LEAD}], 0
    mov word ptr cs:[{CURNPC}], 0xffff
    mov si, {WRAP_OFF}
    mov cx, {WRAP_LEN}
    call hash
    cmp bx, {WCHK_H1}
    jne g_nowrap
    cmp dx, {WCHK_H2}
    jne g_nowrap
    mov di, {WRAP_OFF}
    mov byte ptr es:[di], 0x9a
    mov word ptr es:[di+1], {WRAPBRK}
    mov word ptr es:[di+3], cs
    mov word ptr es:[di+5], 0x4689
    mov word ptr es:[di+7], 0xebfa
    mov byte ptr es:[di+9], 0x15
    add di, 10
    mov cx, {WRAP_LEN}-10
    mov al, 0x90
    cld
    rep stosb
g_nowrap:
    mov si, {HL_OFF}
    mov cx, 10
    call hash
    cmp bx, {HCHK_H1}
    jne g_nohl
    cmp dx, {HCHK_H2}
    jne g_nohl
    mov si, {HL_OFF}+12
    mov cx, {HL_LEN}-12
    call hash
    cmp bx, {HCHK2_H1}
    jne g_nohl
    cmp dx, {HCHK2_H2}
    jne g_nohl
    mov di, {HL_OFF}+3
    mov byte ptr es:[di], 0x9a
    mov word ptr es:[di+1], {HLEND}
    mov word ptr es:[di+3], cs
    mov word ptr es:[di+5], 0x0b59
    mov word ptr es:[di+7], 0x74c0
    mov word ptr es:[di+9], 0x4816
    mov word ptr es:[di+11], 0x2474
    mov word ptr es:[di+13], 0x29eb
    add di, 15
    mov cx, {HL_LEN}-18
    mov al, 0x90
    cld
    rep stosb
g_nohl:
    mov ax, es
    sub ax, {PUTC_SEG}
    add ax, {CONV_SEG}
    mov es, ax
    cmp word ptr es:[{CONV_OFF}-3], 0x7e80
    jne g_noconv
    cmp word ptr es:[{CONV_OFF}-1], 0x80ff
    jne g_noconv
    mov byte ptr es:[{CONV_OFF}], {CONV_NEW}
g_noconv:
    push ds
    pop es
    push cs
    pop ds
    mov di, {STRS}
    call strpatch
g_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

hook:
    push bp
    mov bp, sp
    push si
    push di
    mov al, byte ptr [bp+0xa]
    cmp byte ptr cs:[{LEAD}], 0
    je k_0
    jmp k_trail
k_0:
    cmp al, 0x80
    jb k_pass
    mov bx, word ptr [{WIN}]
    test byte ptr [bx+8], 8
    jnz k_pass
    mov si, {DESC_G}
    cmp al, 0xa0
    jae k_s
    cmp al, 0x9c
    jae k_pass
    call ensure_scene
    mov al, byte ptr [bp+0xa]
    mov si, {DESC_S}
k_s:
    xor ah, ah
    mov bx, ax
    shl bx, 1
    mov ax, word ptr cs:[bx+{SMAP}]
    cmp ax, 0xfffe
    ja k_lead
    je k_done
    mov bx, word ptr cs:[si+8]
    mov word ptr cs:[{CURGLY}], bx
    mov dx, word ptr [bp+6]
    mov cx, word ptr [bp+8]
    call draw
    jmp k_done
k_lead:
    mov al, byte ptr [bp+0xa]
    mov byte ptr cs:[{LEAD}], al
    mov ax, word ptr [bp+6]
    mov word ptr cs:[{LROW}], ax
    mov ax, word ptr [bp+8]
    mov word ptr cs:[{LCOL}], ax
    jmp k_done
k_trail:
    xor bh, bh
    mov bl, byte ptr cs:[{LEAD}]
    mov byte ptr cs:[{LEAD}], 0
    mov si, {DESC_G}
    cmp bl, 0xa0
    jae kt0
    mov si, {DESC_S}
kt0:
    xor ah, ah
    mov di, ax
    add di, word ptr cs:[si+6]
    mov al, byte ptr cs:[di]
    cmp al, 0xff
    je k_pass
    mov di, ax
    mov bl, byte ptr cs:[bx+{LIDX}]
    mov ax, bx
    mul word ptr cs:[si+4]
    add ax, di
    cmp ax, word ptr cs:[si+2]
    jae k_done
    shl ax, 1
    shl ax, 1
    mov bx, ax
    add bx, word ptr cs:[si]
    mov ax, word ptr cs:[si+8]
    mov word ptr cs:[{CURGLY}], ax
    push word ptr cs:[bx+2]
    mov ax, word ptr cs:[bx]
    mov dx, word ptr cs:[{LROW}]
    mov cx, word ptr cs:[{LCOL}]
    call draw
    pop ax
    mov dx, word ptr [bp+6]
    mov cx, word ptr [bp+8]
    call draw
k_done:
    pop di
    pop si
    pop bp
    retf 6
k_pass:
    pop di
    pop si
    pop bp
    {JMP_ORIG}

ensure_scene:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    les bx, dword ptr [{SCRP}]
    mov al, byte ptr es:[bx+1]
    xor ah, ah
    cmp ax, word ptr cs:[{CURNPC}]
    jne es_load
    jmp es_x
es_load:
    push cs
    pop ds
    mov word ptr [{CURNPC}], ax
    mov word ptr [{DESC_S}+2], 0
    mov word ptr [{SMAP}+0x100], 0xfffe
    mov word ptr [{SMAP}+0x102], 0xfffe
    mov word ptr [{SMAP}+0x104], 0xfffe
    mov word ptr [{SMAP}+0x106], 0xfffe
    mov dx, 6
    mul dx
    mov si, ax
    mov ax, 0x3d00
    mov dx, {NAME_DAT}
    pushf
    {CALL_OLD21}
    jc es_x
    mov bx, ax
    mov dx, si
    xor cx, cx
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc es_close
    mov ah, 0x3f
    mov cx, 6
    mov dx, {ENTRY}
    pushf
    {CALL_OLD21}
    jc es_close
    cmp ax, 6
    jne es_close
    mov cx, word ptr [{ENTRY}+4]
    or cx, cx
    jz es_close
    cmp cx, {SCENE_MAX}
    ja es_close
    mov dx, word ptr [{ENTRY}]
    mov cx, word ptr [{ENTRY}+2]
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc es_close
    mov ah, 0x3f
    mov cx, word ptr [{ENTRY}+4]
    mov dx, {SCENE}
    pushf
    {CALL_OLD21}
    jc es_close
    cmp ax, word ptr [{ENTRY}+4]
    jne es_close
    mov ax, word ptr [{SCENE}+2]
    add ax, {SCENE}
    mov word ptr [{DESC_S}], ax
    mov ax, word ptr [{SCENE}+4]
    add ax, {SCENE}
    mov word ptr [{DESC_S}+10], ax
    mov ax, word ptr [{SCENE}+6]
    add ax, {SCENE}
    mov word ptr [{DESC_S}+8], ax
    mov ax, word ptr [{SCENE}+8]
    mov word ptr [{SMAP}+0x100], ax
    mov ax, word ptr [{SCENE}+10]
    mov word ptr [{SMAP}+0x102], ax
    mov ax, word ptr [{SCENE}+12]
    mov word ptr [{SMAP}+0x104], ax
    mov ax, word ptr [{SCENE}+14]
    mov word ptr [{SMAP}+0x106], ax
    mov ax, word ptr [{SCENE}]
    mov word ptr [{DESC_S}+2], ax
es_close:
    mov ah, 0x3e
    pushf
    {CALL_OLD21}
es_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

hlend:
    push bp
    mov bp, sp
    push si
    mov al, byte ptr [bp+6]
    cmp al, 0x7f
    je hl_zw
    mov si, {HL_LIST}
hl_l:
    mov ah, byte ptr [si]
    or ah, ah
    jz hl_no
    cmp ah, al
    je hl_term
    inc si
    jmp hl_l
hl_no:
    xor ax, ax
    jmp hl_x
hl_zw:
    call hl_reset
    mov ax, 2
    jmp hl_x
hl_term:
    call hl_reset
    mov ax, 1
hl_x:
    pop si
    pop bp
    retf
hl_reset:
    mov byte ptr [{LPREFIX}], 0
    push bx
    mov bl, byte ptr [{COL_NORMAL}]
    mov si, word ptr [{WIN}]
    mov byte ptr [si+6], bl
    pop bx
    ret

wrapbrk:
    push si
    push di
    push bp
    xor bp, bp
    mov bx, word ptr [{WIN}]
    test byte ptr [bx+8], 8
    jz wb_0
    inc bp
wb_0:
    mov byte ptr cs:[{WPREV}], 0
    mov word ptr cs:[{WBEST}], 0
    mov word ptr cs:[{WLAST}], 0
    mov byte ptr cs:[{WSCN}], 0
    xor si, si
    mov dl, byte ptr [{LLEN}]
    xor dh, dh
wb_l:
    cmp si, dx
    jbe wb_1
    jmp wb_d
wb_1:
    mov al, byte ptr [si+{BUF}]
    xor ah, ah
    mov bx, 0x0100
    xor cl, cl
    cmp al, 0x80
    jb wb_asc
    or bp, bp
    jnz wb_cls
    mov word ptr cs:[{WDESC}], {DESC_G}
    cmp al, 0xa0
    jae wb_g
    cmp al, 0x9c
    jae wb_cls
    mov word ptr cs:[{WDESC}], {DESC_S}
    cmp byte ptr cs:[{WSCN}], 0
    jne wb_g
    mov byte ptr cs:[{WSCN}], 1
    call ensure_scene
wb_g:
    mov di, ax
    shl di, 1
    mov ax, word ptr cs:[di+{SMAP}]
    cmp ax, 0xfffe
    je wb_cls
    mov bl, 1
    jb wb_gly
    lea ax, [si+1]
    cmp ax, dx
    ja wb_cls
    mov bh, 2
    push bx
    push dx
    push si
    mov bl, byte ptr [si+{BUF}]
    xor bh, bh
    mov bl, byte ptr cs:[bx+{LIDX}]
    mov al, byte ptr [si+{BUF}+1]
    xor ah, ah
    mov si, word ptr cs:[{WDESC}]
    mov di, ax
    add di, word ptr cs:[si+6]
    mov al, byte ptr cs:[di]
    cmp al, 0xff
    je wb_3
    mov di, ax
    mov ax, bx
    mul word ptr cs:[si+4]
    add ax, di
    cmp ax, word ptr cs:[si+2]
    jae wb_3
    shl ax, 1
    shl ax, 1
    mov di, ax
    add di, word ptr cs:[si]
    mov ax, word ptr cs:[di]
    jmp wb_4
wb_3:
    xor ax, ax
wb_4:
    pop si
    pop dx
    pop bx
wb_gly:
    mov di, word ptr cs:[{WDESC}]
    mov di, word ptr cs:[di+10]
    add di, ax
    mov cl, byte ptr cs:[di]
    jmp wb_cls
wb_asc:
    mov di, ax
    mov cl, byte ptr cs:[di+{ASCNS}]
wb_cls:
    mov al, byte ptr [{LDONE}]
    xor ah, ah
    cmp si, ax
    jbe wb_n
    mov word ptr cs:[{WLAST}], si
    cmp byte ptr [si+{BUF}], 0x20
    je wb_ok
    cmp byte ptr [si+{BUF}-1], 0x2d
    je wb_ok
    or bp, bp
    jnz wb_n
    mov al, bl
    or al, byte ptr cs:[{WPREV}]
    jz wb_n
    or cl, cl
    jnz wb_n
wb_ok:
    mov word ptr cs:[{WBEST}], si
wb_n:
    mov byte ptr cs:[{WPREV}], bl
    mov al, bh
    xor ah, ah
    add si, ax
    jmp wb_l
wb_d:
    mov ax, word ptr cs:[{WBEST}]
    or ax, ax
    jnz wb_r
    mov al, byte ptr [{LDONE}]
    xor ah, ah
    or ax, ax
    jnz wb_r
    mov ax, word ptr cs:[{WLAST}]
wb_r:
    pop bp
    pop di
    pop si
    retf

draw:
    or ax, ax
    jz dr_x
    push si
    push di
    push es
    push ds
    mov si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    add si, word ptr cs:[{CURGLY}]
    les bx, dword ptr [{DRVP}]
    les di, dword ptr es:[bx+6]
    add di, {SLOT}*8
    push di
    mov bx, {SAVE}
    mov ax, word ptr es:[di]
    mov word ptr cs:[bx], ax
    mov ax, word ptr es:[di+2]
    mov word ptr cs:[bx+2], ax
    mov ax, word ptr es:[di+4]
    mov word ptr cs:[bx+4], ax
    mov ax, word ptr es:[di+6]
    mov word ptr cs:[bx+6], ax
    push cs
    pop ds
    cld
    movsw
    movsw
    movsw
    movsw
    pop di
    pop ds
    push es
    push di
    mov ax, {SLOT}
    push ax
    push cx
    push dx
    {CALL_ORIG}
    pop di
    pop es
    mov bx, {SAVE}
    mov ax, word ptr cs:[bx]
    mov word ptr es:[di], ax
    mov ax, word ptr cs:[bx+2]
    mov word ptr es:[di+2], ax
    mov ax, word ptr cs:[bx+4]
    mov word ptr es:[di+4], ax
    mov ax, word ptr cs:[bx+6]
    mov word ptr es:[di+6], ax
    pop es
    pop di
    pop si
dr_x:
    ret
'''

INIT = r'''
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
'''
LABELS = ("hook", "wrapbrk", "hlend", "ensure_scene", "draw")


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


def read_translation(path):
    tr = {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        en, ja = line.split("\t")
        tr[en.replace("\\n", "\n")] = ja.replace("\\n", "\n")
    return tr


def find_strings(data, tr, enc):
    """データの中の、前後が 0 の英文を探す: [(位置, 長さ, h1, h2, 中身)]"""
    out = []
    for en, ja in tr.items():
        key = b"\0" + en.encode("latin1") + b"\0"
        new = enc.encode(ja) + b"\0"
        n = len(en)
        if len(new) > n + 1:
            sys.exit(f"訳が長すぎます: {en!r} → {ja!r}（{len(new) - 1} > {n} バイト）")
        pos = 0
        hits = 0
        while True:
            pos = data.find(key, pos)
            if pos < 0:
                break
            off = pos + 1
            out.append((off, n) + h12(data[off:off + n]) + (new,))
            hits += 1
            pos = off
        if not hits:
            print(f"見つからない: {en!r}")
    return out


def glyph_table(font, enc_list, texts):
    """字の並び（1 から）と字形のバイト列"""
    chars = sorted({c for t in texts for c in t if is_jp(c) and c != '\x7f'})
    gidx = {c: i + 1 for i, c in enumerate(chars)}
    gly = bytearray(8)
    for c in chars:
        g = font.get(ord(c))
        if g is None:
            sys.exit(f"美咲フォントに字がありません: {c}")
        gly += g
    return chars, gidx, bytes(gly)


def pair_list(e, gidx):
    pairs = [None] * len(e.pairs)
    for (a, b), i in e.pairs.items():
        pairs[i] = (gidx[a], gidx[b] if b else 0)
    return pairs


def scene_record(font, enc, texts):
    """人物ごとの表: 見出し 16 バイト（組の数、組の位置、行頭禁則の位置、字形の位置、1バイトの字 4つの字の番号）"""
    chars, gidx, gly = glyph_table(font, [enc], texts)
    pairs = pair_list(enc.e, gidx)
    singles = [0xFFFE] * 4
    for ch, code in enc.e.single.items():
        singles[code - 0x80] = gidx[ch]
    body_pairs = b"".join(struct.pack("<HH", a, b) for a, b in pairs)
    nost = bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars)
    p_pairs = 16
    p_nost = p_pairs + len(body_pairs)
    p_gly = p_nost + len(nost)
    head = struct.pack("<4H4H", len(pairs), p_pairs, p_nost, p_gly, *singles)
    return head + body_pairs + nost + gly, len(chars), len(pairs)


def make_converse(gamedir, ctr, genc, font, outdir):
    """会話の訳を取り込んだ CONVERSE.A/B と、人物ごとの表 U6JP.DAT を outdir に書く"""
    from conv_text import apply_translation
    from u6conv import load_items, load_raw_items, save_items
    encs = {}

    def make_encoder(pid, npc, texts):
        e = Enc(SCENE, texts)
        encs[npc] = (pid, e, texts)
        return e.encode
    new = apply_translation(gamedir, ctr, make_encoder, encode_name=genc.encode,
                            warn=lambda m: print("注意:", m))
    for tag, fname in (('A', 'CONVERSE.A'), ('B', 'CONVERSE.B')):
        items = load_items(os.path.join(gamedir, fname))
        origs = load_raw_items(os.path.join(gamedir, fname))
        rows = []
        for k, raw in items:
            if (tag, k) in new:
                rows.append((k, new[(tag, k)], None))
            else:
                rows.append((k, raw, origs.get(k)))
        save_items(os.path.join(outdir, fname), rows)
    # U6JP.DAT: 索引 256 × (位置 4、大きさ 2) と、人物ごとの表
    index = bytearray(256 * 6)
    body = bytearray()
    for npc in sorted(encs):
        pid, e, texts = encs[npc]
        rec, nch, npr = scene_record(font, e, texts)
        if len(rec) > SCENE_MAX:
            sys.exit(f"{pid}: 表が大きすぎる {len(rec)} > {SCENE_MAX}")
        struct.pack_into("<IH", index, npc * 6, len(index) + len(body), len(rec))
        body += rec
        print(f"表 {pid}（人物 {npc:#04x}）: 字 {nch}、組 {npr}、1バイトの字 {len(e.e.single)}、{len(rec)} バイト")
    open(os.path.join(outdir, "U6JP.DAT"), "wb").write(bytes(index + body))


def main(gamedir, trfile, out):
    img, regs, rel = unpack(os.path.join(gamedir, "GAME.EXE"))
    data = img[DGROUP * 16:]
    assert data[NAME_OFF:NAME_OFF + 6] == b"U6.CH\0"
    assert struct.unpack_from("<2H", data, PTR_PUTC) == (PUTC_OFF, PUTC_SEG)
    putc = PUTC_SEG * 16 + PUTC_OFF
    chk = h12(img[putc:putc + PUTC_LEN])
    wrap = PUTC_SEG * 16 + WRAP_OFF
    assert img[wrap:wrap + 2] == b"\xeb\x03"
    assert img[wrap + WRAP_LEN:wrap + WRAP_LEN + 4] == bytes.fromhex("837efa00")
    wchk = h12(img[wrap:wrap + WRAP_LEN])
    if os.environ.get("U6JP_NOWRAP"):
        wchk = (wchk[0] ^ 1, wchk[1])
    conv = CONV_SEG * 16 + CONV_OFF
    assert img[conv - 3:conv + 3] == bytes.fromhex("807eff807328")
    hl = PUTC_SEG * 16 + HL_OFF
    assert img[hl:hl + HL_LEN] == bytes.fromhex(
        "ff7606b8be05509a0a001b2c59590bc07411c6067d0500a0562a8b1edf04884706eb11")
    # 0x7C28 の far call のセグメント（2バイト）は読み込み位置で足し直されるので、照合から外す
    hchk = h12(img[hl:hl + 10])
    hchk2 = h12(img[hl + 12:hl + HL_LEN])
    tr = read_translation(trfile)
    font = load_bdf(BDF)

    ctr = {}
    if os.environ.get("U6JP_CONVTEST"):
        from conv_text import read_tsv
        ctr = read_tsv(os.environ["U6JP_CONVTEST"])
    names = [v for k, v in ctr.items() if k.endswith(':name')]
    gtexts = list(tr.values()) + names
    genc = Enc(GLOBAL, gtexts)
    strs = find_strings(data, tr, genc)
    if ctr:
        make_converse(gamedir, ctr, genc, font, os.environ.get("U6JP_CONVOUT", "."))

    chars, gidx, gly = glyph_table(font, [genc], gtexts)
    pairs = pair_list(genc.e, gidx)
    smap = [0xFFFE] * 256                    # 文字コード → 字の番号（0xFFFF=リード、0xFFFE=使わない）
    for c in GLOBAL.leads + SCENE.leads:
        smap[c] = 0xFFFF
    for ch, code in genc.e.single.items():
        smap[code] = gidx[ch]
    lidx = [0xFF] * 256
    for i, c in enumerate(GLOBAL.leads):
        lidx[c] = i
    for i, c in enumerate(SCENE.leads):
        lidx[c] = i

    def tidx(cs):
        return bytes(cs.trails.index(c) if c in cs.trails else 0xFF for c in range(256))

    def strtab(base, ss):
        tab = bytearray()
        body = bytearray()
        start = base + 12 * len(ss) + 2
        for off, n, a, b, new in ss:
            tab += struct.pack("<6H", off, n, a, b, start + len(body), len(new))
            body += new
        return bytes(tab + b"\xff\xff" + body)

    def build(addr):
        kw = dict(V, DGROUP=DGROUP, NAME_OFF=NAME_OFF, PUTC_SEG=PUTC_SEG, PUTC_OFF=PUTC_OFF,
                  PUTC_LEN=PUTC_LEN, PTR_PUTC=PTR_PUTC, WIN=WIN, DRVP=DRVP, SLOT=SLOT, SCRP=SCRP,
                  CHK_H1=chk[0], CHK_H2=chk[1],
                  WRAP_OFF=WRAP_OFF, WRAP_LEN=WRAP_LEN, WCHK_H1=wchk[0], WCHK_H2=wchk[1],
                  BUF=BUF, LLEN=LLEN, LDONE=LDONE, CONV_SEG=CONV_SEG, CONV_OFF=CONV_OFF, CONV_NEW=CONV_NEW,
                  HL_OFF=HL_OFF, HL_LEN=HL_LEN, HCHK_H1=hchk[0], HCHK_H2=hchk[1],
                  HCHK2_H1=hchk2[0], HCHK2_H2=hchk2[1], HL_LIST=HL_LIST, LPREFIX=LPREFIX, COL_NORMAL=COL_NORMAL,
                  SCENE_MAX=SCENE_MAX,
                  JMP_OLD21=fjmp("OLD21"), CALL_OLD21=fcall("OLD21"),
                  JMP_ORIG=fjmp("ORIG"), CALL_ORIG=fcall("ORIG"), **addr)
        code = asm(RES, CODE, kw)

        def label(name):
            src = RES.split("\n" + name + ":")[0]
            later = [x for x in LABELS if "\n" + x + ":" not in src]
            return CODE + len(asm(src + "".join(f"\n{x}:" for x in later) + "\n", CODE, kw))
        lay = {"HOOK": label("hook"), "WRAPBRK": label("wrapbrk"), "HLEND": label("hlend")}
        p = CODE + len(code)
        tail = bytearray()

        def put(name, d):
            lay[name] = p + len(tail)
            tail.extend(d)
        put("NAME_U6CH", b"U6.CH\0")
        put("NAME_DAT", b"U6JP.DAT\0")
        put("SMAP", b"".join(struct.pack("<H", x) for x in smap))
        put("LIDX", bytes(lidx))
        put("TIDX_G", tidx(GLOBAL))
        put("TIDX_S", tidx(SCENE))
        put("PAIRS_G", b"".join(struct.pack("<HH", a, b) for a, b in pairs))
        put("NOST_G", bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars))
        put("ASCNS", bytes(1 if chr(c) in ASC_NOSTART else 0 for c in range(128)))
        put("GLY_G", gly)
        put("STRS", strtab(p + len(tail), strs))
        if len(tail) % 2:
            tail.append(0)
        lay["SCENE"] = p + len(tail)
        return code, bytes(tail), lay

    keys = ["HOOK", "WRAPBRK", "HLEND", "NAME_U6CH", "NAME_DAT", "SMAP", "LIDX", "TIDX_G", "TIDX_S",
            "PAIRS_G", "NOST_G", "ASCNS", "GLY_G", "STRS", "SCENE"]
    addr = {k: 0x1234 for k in keys}
    for _ in range(8):
        code, tail, lay = build(addr)
        new = {k: lay[k] for k in keys}
        if new == addr:
            break
        addr = new
    assert {k: lay[k] for k in keys} == addr
    scene = lay["SCENE"]
    res_end = scene + SCENE_MAX                  # 人物ごとの表を読む場所（ファイルには含めない）
    msg = "U6JP: 日本語化（試作）を組み込みました\r\n$".encode("cp932")
    init_addr = CODE + len(code) + len(tail)     # 初期化のコードは、表を読む場所に重ねて置く（常駐後は使わない）
    paras = (max(res_end, init_addr + 0x40) + 15) // 16 + 1
    init = asm(INIT, init_addr, dict(OLD21=V["OLD21"], E21=CODE, MSG=init_addr + 0x30, PARAS=paras))
    assert len(init) <= 0x30
    init = init.ljust(0x30, b"\x90") + msg
    head = bytearray(CODE - 0x100)
    head[0] = 0xE9
    head[1:3] = struct.pack("<H", (init_addr - 0x103) & 0xFFFF)

    def setw(off, val):
        head[off - 0x100:off - 0x100 + 2] = struct.pack("<H", val)
    # 表の説明: +0 組、+2 組の数、+4 トレイルの数、+6 トレイルの表、+8 字形、+10 行頭禁則
    g = V["DESC_G"]
    for i, v in enumerate((lay["PAIRS_G"], len(pairs), len(GLOBAL.trails), lay["TIDX_G"], lay["GLY_G"], lay["NOST_G"])):
        setw(g + 2 * i, v)
    s = V["DESC_S"]
    for i, v in enumerate((0, 0, len(SCENE.trails), lay["TIDX_S"], lay["GLY_G"], lay["NOST_G"])):
        setw(s + 2 * i, v)
    setw(V["CURNPC"], 0xFFFF)
    com = bytes(head) + code + tail + init
    open(out, "wb").write(com)
    print(f"{out}: {len(com)} バイト（常駐 {res_end - 0x100}、うち人物ごとの表 {SCENE_MAX}）、常に持つ表: 字 {len(chars)}、"
          f"組 {len(pairs)}、1バイトの字 {len(genc.e.single)}、置き換え {len(strs)} か所")


if __name__ == "__main__":
    main(*sys.argv[1:4])
