# Savage Empire 用の常駐プログラム SEJP.COM と、人物ごとの表のファイル SEJP.DAT を作る
# （ウルティマVI の build_u6jp.py を写して、SE の番地に直したもの。SE の GAME.EXE は U6 と同じエンジンで、EXEPACK はない）
#
# 常駐部（INT 21h AH=3Dh を横取り）: 本編 GAME.EXE が SYSTEM.LZC（画面ドライバとフォント）を開いたときに、
#   照合してから次を行う。DS = 本編のデータ（DGROUP 0x2FA6）
#   1. 1文字出力の関数ポインタ DS:0x03D9（初期値 05D0:028B）を hook に向ける（本編のコードは書き換えない）
#   2. 折り返しの 05D0:2811〜282F を wrapbrk の呼び出しに（組の途中で切らない、日本語の前後で切る、行頭禁則）
#   3. @ の強調の 05D0:2D0F〜2D31 を hlend の呼び出しに（0x7F で強調を止め、字は描かない）
#   4. 会話の本体の判定 0F8D:1EF3 の cmp [bp-1],80h を 9Ch に（0x80〜0x9B を文章として通す）
#   5. 本編のデータの文字列を日本語に置き換える（元の長さ以内）
#
# 符号（1バイト = 1マス、美咲フォント 8×8）:
#   0x80〜0x9B  場面の表（人物ごと。SEJP.DAT から読む）: 1バイトの字 0x80〜0x8F、組のリード 0x90〜0x9B
#   0xA0〜0xFF  常に持つ表（常駐部の中）: 1バイトの字 0xA0〜（数は組み立てで決める）、残りが組のリード（0xF1 を除く）
#   トレイルは 0x21〜0x7E から本編が特別扱いする記号と @ の強調を止める字と DEL を除いたもの＋ 0x80〜0x9B（場面の表）、
#   常に持つ表はさらに 0xA0〜0xFF（0xF1 を除く）
#   場面の表は、場面の符号が来たときに、会話スクリプトの置き場所 [0x6EF8] の2バイト目（FF <人物の番号>）を見て、
#   前と違えば SEJP.DAT から読み込む
#
# 使い方: python build_sejp.py <ゲームのフォルダ> <本編の文字列の訳> <出力 SEJP.COM>
#   本編の文字列の訳: 「英文<TAB>訳」。\n は改行。本編のデータの中の、前後が 0 の英文を全部置き換える
#   SEJP_CONVTEST=<会話の訳 番号<TAB>訳>  SEJP_CONVOUT=<出力先>: TALK.LZC と SEJP.DAT を作る
#   SEJP_NOWRAP=1: 折り返しを直さない版（比べる用）
import contextlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import jpenc  # noqa: E402
from jpenc import Encoder, load_bdf, is_jp, fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

jpenc.PAIR_ASCII = set()      # 英数字と日本語の字は組にしない（英字はゲームの字形で描く）
# 本編の文字出力（05D0:2B58）が特別扱いする記号（表 05D0:2D73 の9つ。@ 強調、\ 複数形など。U6 の & < > は無い）と、
# @ の強調を止める字（DS:0x04B5）。どちらも組のトレイルに使わない。
# & は SE のフォントでは閉じの引用符（特別扱いはない）
SPECIAL = set(b"#$%*/@\\^`") | set(b" ,.:;!?'-\"\n") | {0x7F}
ASC_TRAILS = [c for c in range(0x21, 0x7F) if c not in SPECIAL]
NO_F1 = [c for c in range(0xA0, 0x100) if c != 0xF1]   # 人物の名前は 0xF1 まで写されるので 0xF1 は使わない


class CodeSet:
    def __init__(self, singles, leads, trails):
        self.singles, self.leads, self.trails = singles, leads, trails


NS = 16   # 場面の表の1バイトの字の数（0x80〜0x8F）。リードは 0x90〜0x9B（12 × トレイル 104 = 1,248 組）。12 だと強調の前後などで1マス空く所が 12 残った
SCENE = CodeSet(list(range(0x80, 0x80 + NS)), list(range(0x80 + NS, 0x9C)), ASC_TRAILS + list(range(0x80, 0x9C)))
_GS = int(os.environ.get("SEJP_GSINGLES", "40"))   # 試験用: 常に持つ表の1バイトの字の数（0 で全部を組にする）
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
            # 1バイトの字は「組の相手がいなくて1字だけ余る字」（強調の前後や英字の手前の奇数字の並びの最後）から選ぶ。
            # 余った字は組（2マス）になって1マス空くので、そこを1バイトの字で埋める。足りなければよく出る字で埋める
            # 奇数字の並びは、偶数番目のどれか1字が1バイトの字なら埋まるので、空く所が一番減る字を1字ずつ選ぶ
            n = len(cs.singles)
            seg = self.e.segment

            def gaps(sel, ts):
                self.e.single = dict.fromkeys(sel, 0)
                return sum(1 for t in ts for u in seg(t) if u[0] == 'p' and u[2] is None)
            self.e.single = {}
            bad = [t for t in texts if gaps([], [t])]
            top, cur = [], gaps([], bad)
            while len(top) < n and cur:
                cands = {c for t in bad for c in t if is_jp(c) and c not in top}
                best = min(cands, key=lambda c: (gaps(top + [c], bad), -self.e.freq[c], c))
                nb = gaps(top + [best], bad)
                if nb >= cur:
                    break
                top.append(best)
                cur = nb
                bad = [t for t in bad if gaps(top, [t])]
            top += [c for c in sorted(self.e.freq, key=lambda c: (-self.e.freq[c], c)) if c not in top][:n - len(top)]
            self.e.single = {ch: cs.singles[i] for i, ch in enumerate(top)}

    def encode(self, t):
        with codes(self.cs):
            return self.e.encode(t)

    def gaps(self, texts):
        """組の相手がいなくて1マス空く所の数"""
        return sum(1 for t in texts for u in self.e.segment(t) if u[0] == 'p' and u[2] is None)


# 本編の位置
CONV_SEG, CONV_OFF, CONV_NEW = 0x0F8D, 0x1EF6, 0x9C   # 会話の本体の判定 cmp [bp-1],80h → 9Ch
DGROUP = 0x2FA6               # 本編のデータのセグメント（ロード位置から）
SEG2 = 0x2F65                 # DGROUP の手前の、文字列だけのセグメント（戦闘・操作の短いメッセージ）
NAME_SYS = b"SYSTEM.LZC"      # これを開いたときに書き換える（DX は見ない。DS - DGROUP と関数ポインタの中身で照合する）
PUTC_SEG, PUTC_OFF = 0x05D0, 0x028B   # 本編の1文字出力
PUTC_LEN = 0x72               # 照合する長さ（関数の全体 0x5F8B〜0x5FFC）
PTR_PUTC = 0x03D9             # 1文字出力の関数ポインタ
WIN = 0x03EC                  # 今の窓の構造体へのポインタ（+8 が属性、8 = 0x80 を足す表示。SE での使い道は未確認）
DRVP = 0xED0C                 # 画面ドライバの構造体への far ポインタ（+6 がフォントの far ポインタ）
SCRP = 0x6EF8                 # 会話スクリプトの置き場所の far ポインタ（先頭 FF <人物の番号>）
SLOT = 0x02                   # フォント（SYSTEM.LZC の 3 番、128字）の空いている字（日本語の字形を一時的に写す）
WRAP_OFF, WRAP_LEN = 0x2811, 31                  # 折り返しの「空白か - の直後」を探す部分（05D0 の中）
WRAP_BP = 0xFC                                   # 切る位置の変数 [bp-4]（U6 は [bp-6]）
BUF, LLEN, LDONE = 0xB593, 0x048E, 0x048F        # 1行分の文字、たまった長さ、描いた所まで
HL_OFF, HL_LEN = 0x2D0F, 35                      # @ の強調の処理（05D0 の中）
# hlend の戻りの飛び先（HL_OFF からの距離）: 0 = 強調を続ける（+35）、1 = 止めて字を出す（+61）、2 = 止めて字を出さない（+68 = 関数の終わり）
HL_CONT, HL_TERM, HL_ZW = 35, 61, 68
HL_LIST, LPREFIX, COL_NORMAL = 0x04B5, 0x0491, 0x24E6
# 人物の名前を読む所（0F8D:0094）が名前の終わりを「最上位ビットが立ったバイト」で決める test [si-1948h],80h / jnz（0F8D:00ED）。
# 日本語の名前は 0xA0 以上の符号なので、cmp [si-1948h],0F1h / jz に書き換える（同じ7バイト）
NAMEEND_OFF = 0x00ED
KINSOKU = set("、。，．・：；？！ー～…‥」』）］｝〉》ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々ゝゞヽヾ")
ASC_NOSTART = set(".,!?:;)]}")
SCENE_MAX = 14 * 1024         # 人物ごとの表を読み込む場所の大きさ

# ---- 常駐部の変数（0x103 から）----
V = dict(OLD21=0x103, ORIG=0x107, LEAD=0x10B, LROW=0x10C, LCOL=0x10E, SAVE=0x110,
         WPREV=0x118, WBEST=0x11A, WLAST=0x11C, CURGLY=0x11E, WDESC=0x120, CURNPC=0x122,
         ENTRY=0x124, DESC_G=0x12A, DESC_S=0x136, WSCN=0x142, GDS=0x144,
         SDS=0x146, SLEAD=0x148, ORIG2=0x14A, RET0=0x150, RET1=0x154, RET2=0x158, ORIG3=0x15C)
# GDS: 本編のデータのセグメント（書き換えたときに覚える。終了 4Ch で 0 に戻す）。ファイルを閉じるたびに仲間の名前の表を直すのに使う
PARTY = 0x5104                # 仲間の名前の表（14 バイト × 16。セーブデータ OBJLIST の 0xF00 から読まれる）
PARTY_NAME_MAX = 13           # 名前は 0 終わりで 14 バイトまで
# 表の説明（12バイト）: +0 組の位置、+2 組の数、+4 トレイルの数、+6 トレイルの表、+8 字形、+10 行頭禁則
CODE = 0x160


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
    cmp ah, 0x3e
    je cl21
    cmp ah, 0x40
    je w21
    cmp ah, 0x4c
    jne c21
    mov word ptr cs:[{GDS}], 0
c21:
    {JMP_OLD21}
cl21:
    pushf
    {CALL_OLD21}
    pushf
    call fixnames
    popf
    retf 2
w21:
    call unfixnames
    pushf
    {CALL_OLD21}
    pushf
    call fixnames
    popf
    retf 2

unfixnames:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ax, word ptr cs:[{GDS}]
    or ax, ax
    jz un_x
    mov es, ax
    push cs
    pop ds
    cld
    mov di, {PARTY}
    mov dx, 16
un_e:
    mov si, {NAMES}
un_n:
    cmp byte ptr [si], 0
    je un_next
    mov bx, si
un_s1:
    lodsb
    or al, al
    jnz un_s1
    push si
    push di
un_c:
    mov al, byte ptr [si]
    cmp al, byte ptr es:[di]
    jne un_ne
    inc si
    inc di
    or al, al
    jnz un_c
    pop di
    pop ax
    push di
    mov si, bx
un_cp:
    lodsb
    stosb
    or al, al
    jnz un_cp
    pop di
    jmp un_next
un_ne:
    pop di
    pop si
un_s2:
    lodsb
    or al, al
    jnz un_s2
    jmp un_n
un_next:
    add di, 14
    dec dx
    jnz un_e
un_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

fixnames:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ax, word ptr cs:[{GDS}]
    or ax, ax
    jz fn_x
    mov es, ax
    push cs
    pop ds
    cld
    mov di, {PARTY}
    mov dx, 16
fn_e:
    mov si, {NAMES}
fn_n:
    cmp byte ptr [si], 0
    je fn_next
    push si
    push di
fn_c:
    mov al, byte ptr [si]
    cmp al, byte ptr es:[di]
    jne fn_ne
    inc si
    inc di
    or al, al
    jnz fn_c
    pop di
    pop ax
    push di
fn_cp:
    lodsb
    stosb
    or al, al
    jnz fn_cp
    pop di
    jmp fn_next
fn_ne:
    pop di
    pop si
fn_s1:
    lodsb
    or al, al
    jnz fn_s1
fn_s2:
    lodsb
    or al, al
    jnz fn_s2
    jmp fn_n
fn_next:
    add di, 14
    dec dx
    jnz fn_e
fn_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
o21:
    push di
    push bx
    mov bx, {RLIST}
o_rl:
    cmp byte ptr cs:[bx], 0
    je o_rn
    mov di, bx
    call isname
    je o_rd
    add bx, 13
    jmp o_rl
o_rn:
    pop bx
    pop di
    jmp o_sys
o_rd:
    pop bx
    pop di
    call redir
    jc o_sys
    retf 2
o_sys:
    push di
    mov di, {NAME_SYS}
    call isname
    pop di
    je o_g
    push di
    mov di, {NAME_FNT}
    call isname
    pop di
    jne c21
    pushf
    {CALL_OLD21}
    jc o_x
    call spatch
    clc
    jmp o_x
o_g:
    pushf
    {CALL_OLD21}
    jc o_x
    call gpatch
    clc
o_x:
    retf 2

redir:
    push si
    push di
    push cx
    push ds
    push es
    push ax
    push cs
    pop es
    mov si, dx
    mov di, {RNAME}
    mov cx, 13
    cld
rd_c:
    lodsb
    stosb
    or al, al
    loopne rd_c
    mov byte ptr es:[di-2], 0x4a
    pop ax
    push ax
    push dx
    push cs
    pop ds
    mov dx, {RNAME}
    pushf
    {CALL_OLD21}
    pop dx
    jc rd_no
    add sp, 2
    clc
    jmp rd_x
rd_no:
    pop ax
    stc
rd_x:
    pop es
    pop ds
    pop cx
    pop di
    pop si
    ret

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
    mov word ptr cs:[{GDS}], ds
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
    mov word ptr es:[di+7], {WRAP_W7}
    mov byte ptr es:[di+9], {WRAP_LEN}-10
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
    mov word ptr es:[di+9], {HL_W9}
    mov word ptr es:[di+11], {HL_W11}
    mov word ptr es:[di+13], {HL_W13}
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
    cmp word ptr es:[{NAMEEND_OFF}], 0x84f6
    jne g_nonm
    cmp word ptr es:[{NAMEEND_OFF}+2], 0xe6b8
    jne g_nonm
    cmp word ptr es:[{NAMEEND_OFF}+4], 0x7580
    jne g_nonm
    mov word ptr es:[{NAMEEND_OFF}], 0xbc80
    mov word ptr es:[{NAMEEND_OFF}+4], 0x74f1
g_nonm:
    push ds
    pop es
    push cs
    pop ds
    mov di, {STRS}
    call strpatch
    mov ax, es
    sub ax, {DGROUP}-{SEG2}
    mov es, ax
    mov di, {STRS2}
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
    push ax
    push cs
    pop es
    mov di, {SMAP}+0x100
    mov cx, {NS}
    mov ax, 0xfffe
    cld
    rep stosw
    pop ax
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
    mov si, {SCENE}+8
    mov di, {SMAP}+0x100
    mov cx, {NS}
    push cs
    pop es
    cld
    rep movsw
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

spatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push es
    mov ax, ds
    sub ax, {S_DGROUP}
    jb sp_x
    mov bx, ax
    add ax, {S_PRINT_SEG}
    mov es, ax
    cmp word ptr es:[{S_PR0}], 0x8b55
    jne sp_x
    cmp word ptr es:[{S_PR1}], 0x8b55
    jne sp_x
    cmp word ptr es:[{S_PR2}], 0x8b55
    jne sp_x
    cmp word ptr es:[{S_PR0}+4], 0x468d
    jne sp_x
    mov ax, bx
    add ax, {S_WRAP_SEG}
    mov es, ax
    cmp word ptr es:[{S_BRK}], 0x203c
    jne sp_x
    cmp word ptr es:[{S_BRK}+2], 0x0475
    jne sp_x
    cmp word ptr es:[{S_BRK}+4], 0x3689
    jne sp_x
    mov ax, bx
    add ax, {S_DRAW_SEG}
    cmp word ptr es:[{S_DC0}+3], ax
    jne sp_x
    cmp word ptr es:[{S_DC0}+1], {S_DRAW_OFF}
    jne sp_x
    mov word ptr cs:[{ORIG2}], {S_DRAW_OFF}
    mov word ptr cs:[{ORIG2}+2], ax
    mov word ptr cs:[{SDS}], ds
    mov byte ptr cs:[{SLEAD}], 0
    mov word ptr es:[{S_BRK}], 0x9a
    mov word ptr es:[{S_BRK}+1], {CHKBRK}
    mov word ptr es:[{S_BRK}+3], cs
    mov word ptr es:[{S_BRK}+5], 0x9090
    mov byte ptr es:[{S_BRK}+7], 0x90
    mov si, {S_DC0}
    call sp_dc
    mov si, {S_DC1}
    call sp_dc
    mov si, {S_DC2}
    call sp_dc
    mov si, {S_DC3}
    call sp_dc
    mov ax, bx
    add ax, {S_PRINT_SEG}
    mov es, ax
    mov ax, bx
    add ax, {S_DRAW_SEG}
    cmp byte ptr es:[{S_PUTC_PUSH}], 0xb8
    jne sp_np
    cmp word ptr es:[{S_PUTC_PUSH}+1], ax
    jne sp_np
    cmp word ptr es:[{S_PUTC_PUSH}+5], {S_PUTC_OFF}
    jne sp_np
    mov word ptr cs:[{ORIG3}], {S_PUTC_OFF}
    mov word ptr cs:[{ORIG3}+2], ax
    mov word ptr es:[{S_PUTC_PUSH}+1], cs
    mov word ptr es:[{S_PUTC_PUSH}+5], {HOOK3}
sp_np:
    mov si, {S_PR0}
    mov di, {SSTUB0}
    mov dx, {RET0}
    call sp_pr
    mov si, {S_PR1}
    mov di, {SSTUB1}
    mov dx, {RET1}
    call sp_pr
    mov si, {S_PR2}
    mov di, {SSTUB2}
    mov dx, {RET2}
    call sp_pr
    push ds
    push ds
    pop es
    push cs
    pop ds
    mov di, {SSTRS}
    call strpatch
    pop ds
sp_x:
    pop es
    pop di
    pop si
    pop cx
    pop dx
    pop bx
    pop ax
    ret
sp_dc:
    mov word ptr es:[si+1], {HOOK2}
    mov word ptr es:[si+3], cs
    ret
sp_pr:
    push bx
    mov bx, dx
    lea ax, [si+7]
    mov word ptr cs:[bx], ax
    mov word ptr cs:[bx+2], es
    pop bx
    mov byte ptr es:[si], 0xea
    mov word ptr es:[si+1], di
    mov word ptr es:[si+3], cs
    ret

sstub0:
    call sfmt
    push bp
    mov bp, sp
    push si
    lea ax, [bp+0xa]
    {JMP_RET0}
sstub1:
    call sfmt
    push bp
    mov bp, sp
    push si
    lea ax, [bp+0xa]
    {JMP_RET1}
sstub2:
    call sfmt
    push bp
    mov bp, sp
    push si
    lea ax, [bp+0xa]
    {JMP_RET2}

sfmt:
    push bp
    mov bp, sp
    push ax
    push si
    push ds
    mov ax, word ptr [bp+10]
    cmp ax, word ptr cs:[{SDS}]
    jne sf_x
    mov ax, word ptr [bp+8]
    push cs
    pop ds
    mov si, {STAB}
sf_l:
    cmp word ptr [si], 0xffff
    je sf_ps
    cmp word ptr [si], ax
    je sf_hit
    add si, 4
    jmp sf_l
sf_ps:
    mov si, ax
    mov ds, word ptr [bp+10]
    cmp word ptr [si], 0x7325
    jne sf_x
    cmp word ptr [si+2], 0x5025
    jne sf_x
    cmp byte ptr [si+4], 0
    jne sf_x
    mov ax, word ptr [bp+12]
    push cs
    pop ds
    mov si, {STAB2}
sf_l2:
    cmp word ptr [si], 0xffff
    je sf_x
    cmp word ptr [si], ax
    je sf_hit
    add si, 4
    jmp sf_l2
sf_hit:
    mov ax, word ptr [si+2]
    mov word ptr [bp+8], ax
    mov word ptr [bp+10], cs
sf_x:
    pop ds
    pop si
    pop ax
    pop bp
    ret

chkbrk:
    push es
    push di
    les di, dword ptr ds:[bp+6]
    cmp byte ptr es:[di+4+0x90], 8
    je cb_0
    call fontpatch
cb_0:
    pop di
    pop es
    cmp al, 0x20
    je cb_set
    cmp al, {S_LEAD1}
    jb cb_x
    cmp al, {S_LEADE}
    ja cb_x
    cmp si, word ptr [{S_LSTART}]
    je cb_x
cb_set:
    mov word ptr [{S_BRKPOS}], si
cb_x:
    retf

fontpatch:
    cmp byte ptr es:[di+4+0x41], 7
    jne fp_x
    cmp byte ptr es:[di+0x104+0x80], {S_SLOT_LO}
    jne fp_x
    cmp byte ptr es:[di+0x204+0x80], {S_SLOT_HI}
    jne fp_x
    push ax
    push cx
    push di
    add di, 0x80
    mov cx, 0x80
fp_l:
    mov al, 0
    cmp cx, 0x90
    jb fp_w
    mov al, 8
    mov byte ptr es:[di+0x104], {S_SLOT_LO}
    mov byte ptr es:[di+0x204], {S_SLOT_HI}
fp_w:
    mov byte ptr es:[di+4], al
    inc di
    inc cx
    cmp cx, 0x100
    jb fp_l
    pop di
    pop cx
    pop ax
fp_x:
    ret

hook2:
    cmp al, 0x80
    jb h2_pass
    cmp al, 0x90
    jae h2_tr
    mov byte ptr cs:[{SLEAD}], al
    retf
h2_tr:
    call putgly
h2_pass:
    {JMP_ORIG2}

hook3:
    push bp
    mov bp, sp
    push ax
    mov al, byte ptr [bp+6]
    cmp al, 0x80
    jb h3_x
    cmp al, 0x90
    jae h3_tr
    mov byte ptr cs:[{SLEAD}], al
    jmp h3_x
h3_tr:
    call putgly
h3_x:
    pop ax
    pop bp
    {JMP_ORIG3}

putgly:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push es
    mov bl, byte ptr cs:[{SLEAD}]
    sub bl, 0x80
    xor bh, bh
    sub al, 0x90
    xor ah, ah
    mov si, ax
    mov ax, 112
    mul bx
    add si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    add si, {SGLY}
    mov bx, word ptr [{S_CTX}]
    les di, dword ptr [bx+6]
    add di, {S_SLOT}
    mov cx, 8
pg_r:
    mov dl, byte ptr cs:[si]
    inc si
    mov dh, 8
pg_c:
    mov al, 0x48
    shl dl, 1
    jnc pg_p
    xor al, al
pg_p:
    mov byte ptr es:[di], al
    inc di
    dec dh
    jnz pg_c
    loop pg_r
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
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
LABELS = ("hook", "wrapbrk", "hlend", "ensure_scene", "draw", "spatch", "sstub0", "sstub1", "sstub2", "sfmt", "chkbrk", "fontpatch", "hook2", "hook3", "putgly", "redir", "unfixnames")


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
    """人物ごとの表: 見出し 8+2*NS バイト（組の数、組の位置、行頭禁則の位置、字形の位置、1バイトの字 NS 個の字の番号）"""
    chars, gidx, gly = glyph_table(font, [enc], texts)
    pairs = pair_list(enc.e, gidx)
    singles = [0xFFFE] * NS
    for ch, code in enc.e.single.items():
        singles[code - 0x80] = gidx[ch]
    body_pairs = b"".join(struct.pack("<HH", a, b) for a, b in pairs)
    nost = bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars)
    p_pairs = 8 + 2 * NS
    p_nost = p_pairs + len(body_pairs)
    p_gly = p_nost + len(nost)
    head = struct.pack("<4H%dH" % NS, len(pairs), p_pairs, p_nost, p_gly, *singles)
    return head + body_pairs + nost + gly, len(chars), len(pairs)


TALK_MAX = 11708   # 会話スクリプトの最大（英語版の Rafkin）。読み込み先の大きさは未確認なので、これを超えたら止める


def make_converse(gamedir, ctr, genc, font, outdir):
    """会話の訳を取り込んだ TALK.LZC と、人物ごとの表 SEJP.DAT を outdir に書く"""
    from conv_text import apply_translation
    from sefmt import lzc_raw, save_lzc
    encs = {}

    def make_encoder(pid, npc, texts):
        e = Enc(SCENE, texts)
        encs[npc] = (pid, e, texts)
        return e.encode
    new = apply_translation(gamedir, ctr, make_encoder, encode_name=genc.encode,
                            warn=lambda m: print("注意:", m))
    rows = lzc_raw(open(os.path.join(gamedir, "TALK.LZC"), "rb").read())
    for (tag, k), raw in new.items():
        if len(raw) > TALK_MAX:
            sys.exit(f"{tag}{k:03d}: 会話スクリプトが大きすぎる {len(raw)} > {TALK_MAX}")
        rows[k] = (2, raw)                       # 変えた人物は圧縮なし（印 2。本編の LZC の読み込みは 1 以外をそのまま読む）
    save_lzc(os.path.join(outdir, "TALK.LZC"), rows)
    # SEJP.DAT: 索引 256 × (位置 4、大きさ 2) と、人物ごとの表
    index = bytearray(256 * 6)
    body = bytearray()
    ngap = 0
    for npc in sorted(encs):
        pid, e, texts = encs[npc]
        rec, nch, npr = scene_record(font, e, texts)
        if len(rec) > SCENE_MAX:
            sys.exit(f"{pid}: 表が大きすぎる {len(rec)} > {SCENE_MAX}")
        struct.pack_into("<IH", index, npc * 6, len(index) + len(body), len(rec))
        body += rec
        g = e.gaps(texts)
        ngap += g
        print(f"表 {pid}（人物 {npc:#04x}）: 字 {nch}、組 {npr}、1バイトの字 {len(e.e.single)}、1マス空く所 {g}、{len(rec)} バイト")
    open(os.path.join(outdir, "SEJP.DAT"), "wb").write(bytes(index + body))
    print(f"会話で1マス空く所: 全部で {ngap}")


def load_image(path):
    """GAME.EXE のロードイメージ（ヘッダを除いたもの。再配置は足さない）"""
    exe = open(path, "rb").read()
    return exe[struct.unpack_from("<H", exe, 8)[0] * 16:]


# 本編の文字列で訳してはいけないもの（データの中の位置）: 入力と比べたり、入力の代わりに入れたりする語
KEEP_GAME = {0x0AAD,   # "bye"（会話で空の入力をこれに置き換える）
             0x0B24,   # "look"
             0x0A75,   # "you"
             0x00DB, 0x00E1}   # "vetch" "narp"


def read_game_tsv(paths, data, keep=None):
    """本編の文字列の訳: {データの中の位置: (英文 bytes, 訳)}。番号 game:XXXX はデータ（DGROUP）の中の位置"""
    from conv_text import read_tsv, mark_highlight
    gtr = {}
    keep = KEEP_GAME if keep is None else keep
    for path in paths:
        ja = read_tsv(path)
        en = read_tsv(path.replace("other_ja", "other_en"))
        for k, v in ja.items():
            off = int(k.split(':')[1], 16)
            if off in keep:
                continue
            e = en[k].encode('latin1')
            if data[off:off + len(e) + 1] != e + bytes([0]):
                sys.exit(f"{k}: データの中の英文が違う")
            if v != en[k]:
                gtr[off] = (e, mark_highlight(v, lambda m: print("注意:", m), k))
    return gtr


def genc_encode(genc, t):
    """0x7F（閉じの @）で区切って符号にする（組が 0x7F をまたがないように）"""
    return bytes([0x7F]).join(genc.encode(part) for part in t.split(chr(0x7F)))


LOOK_NAME_MAX = 24     # 名前を写す場所 DS:0xE60C（0D64:0988）は長さを確かめない。英語の一番長い名前（rope hanging from a hole）の長さまで


def read_look(gamedir, tsv):
    """LOOK.LZC（物の名前）: [(タイル, 英語の名前 bytes, 訳 or None)], 末尾の残り"""
    from conv_text import read_tsv
    from sefmt import lzc_items
    ja = read_tsv(tsv) if tsv else {}
    raw = lzc_items(open(os.path.join(gamedir, "LOOK.LZC"), "rb").read())[0][1]
    out = []
    p = 0
    while p + 2 < len(raw):
        tile = struct.unpack_from("<H", raw, p)[0]
        e = raw.find(bytes([0]), p + 2)
        if e < 0:
            break
        name = raw[p + 2:e]
        v = ja.get(f"look:{tile:04x}")
        out.append((tile, name, v if v and v != name.decode('latin1') else None))
        p = e + 1
    return out, raw[p:]


def write_look(gamedir, look, genc, outdir):
    """物の名前を常に持つ表の符号にして LOOK.LZC を作る（1項目、圧縮なし、印 2）。
    名前は LOOK_NAME_MAX バイトまで。ファイル全体は元の大きさ以内（作業用の領域に読み込まれるため）"""
    ents, rest = look
    body = bytearray()
    n = 0
    for tile, name, ja in ents:
        b = name
        if ja:
            enc = genc.encode(ja)
            if len(enc) > LOOK_NAME_MAX or 0 in enc:
                print(f"注意: 物の名前が長すぎるので英語のまま: look:{tile:04x} {ja!r}（{len(enc)} バイト）")
            else:
                b = enc
                n += 1
        body += struct.pack("<H", tile) + b + bytes([0])
    body += rest
    orig = os.path.getsize(os.path.join(gamedir, "LOOK.LZC"))
    data = struct.pack("<II", 8 + len(body), 8 | (2 << 24)) + bytes(body)
    if len(data) > orig:
        sys.exit(f"LOOK.LZC が元より大きい: {len(data)} > {orig}")
    open(os.path.join(outdir, "LOOK.LZC"), "wb").write(data)
    print(f"LOOK.LZC: 名前 {n} / {len(ents)} を日本語に（{len(data)} バイト、元 {orig}）")


def write_midgame(gamedir, mid, genc, outdir):
    """訳を入れた MIDGAME1〜5.LZC を outdir に書く（項目は圧縮なし。元も圧縮なし）"""
    from sefmt import lzc_raw, save_lzc
    for n in range(1, 6):
        name = f"MIDGAME{n}.LZC"
        rows = lzc_raw(open(os.path.join(gamedir, name), "rb").read())
        for k, v in mid.items():
            if k.startswith(f"mid{n}:"):
                i = int(k.split(":")[1])
                rows[i] = (2, genc_encode(genc, v) + bytes([0]))
        save_lzc(os.path.join(outdir, name), rows)
    print(f"MIDGAME1〜5.LZC: 文 {len(mid)}")


def party_names(ctr, genc):
    """仲間の名前の表を直すための並び（英語の名前 0 日本語 0 …、最後に 0）"""
    from conv_text import read_tsv  # noqa: F401
    en = {}
    for line in open(os.path.join(HERE, "..", "translation", "conv_en.tsv"), encoding="utf-8"):
        if ':name\t' in line:
            k, v = line.rstrip("\n").split("\t", 1)
            en[k] = v
    out = bytearray()
    seen = set()
    for k, v in ctr.items():
        if not k.endswith(':name') or k not in en or en[k] in seen:
            continue
        b = genc.encode(v)
        if len(b) > PARTY_NAME_MAX or len(en[k]) > PARTY_NAME_MAX:
            print(f"注意: 仲間の名前の表に入らない: {k} {v!r}（{len(b)} バイト）")
            continue
        seen.add(en[k])
        out += en[k].encode("latin1") + bytes([0]) + b + bytes([0])
    return bytes(out + bytes([0]))


# ---- SAVAGE.EXE（導入・キャラクター作成・エンディング）----
# 可変幅のフォント SAVAGE.FNT（幅の表 +4、字形の位置の表 下位 +0x104・上位 +0x204、字形は 1ドット1バイトで高さ 8。0 が字の点、0x48 が透明）。
# 日本語は 2バイトで1字: リード 0x80〜0x8F（幅 0、描かない）、トレイル 0x90〜0xFF（幅 8）。リード 0x80 は行頭禁則の字。
# 常駐部は SAVAGE.FNT を開いたときに次を書き換える（DS = SAVAGE.EXE のデータ、DGROUP 0x0DAA）
#   - 書式つき出力の入口 078E:0230 / 0252 / 027E → sstub（英文のポインタを常駐部の日本語の文に差し替える）
#   - 折り返しの「空白なら切れ目」 0756:0078 → chkbrk（日本語の字の前でも切る。初めて呼ばれたときフォントの幅と位置を直す）
#   - 1字描画の far call 0756:0191 / 01C2 / 01EF / 0260（→ 0784:0016）→ hook2（トレイルの字形を置き場 +0x1814 に書いてから描かせる）
SAV = dict(S_DGROUP=0x0DAA, S_PRINT_SEG=0x078E, S_PR0=0x0230, S_PR1=0x0252, S_PR2=0x027E,
           S_WRAP_SEG=0x0756, S_BRK=0x0078, S_DC0=0x0191, S_DC1=0x01C2, S_DC2=0x01EF, S_DC3=0x0260,
           S_DRAW_SEG=0x0784, S_DRAW_OFF=0x0016, S_LEAD1=0x81, S_LEADE=0x8F, S_LSTART=0x2038, S_BRKPOS=0x203C,
           S_CTX=0x201E, S_SLOT=0x1814, S_SLOT_LO=0x14, S_SLOT_HI=0x18,
           S_PUTC_PUSH=0x0240, S_PUTC_OFF=0x0002)   # 078E:0240 mov ax,0784 / push ax / mov ax,0002 / push ax（折り返しなしの出力の1字出力 0784:0002）
S_TRAILS = list(range(0x90, 0x100))


def build_savage(gamedir, path, font):
    """SAVAGE.EXE の訳: (字形, [(データの位置, 日本語 bytes)], [その場で置き換える (位置, 長さ, h1, h2, 中身)])"""
    from conv_text import read_tsv
    exe = open(os.path.join(gamedir, "SAVAGE.EXE"), "rb").read()
    img = exe[struct.unpack_from("<H", exe, 8)[0] * 16:]
    ds = SAV["S_DGROUP"] * 16
    assert img[ds + 0x0C2E:ds + 0x0C39] == b"savage.fnt" + bytes([0])
    ja = read_tsv(path)
    en = read_tsv(path.replace("other_ja", "other_en"))
    chars = sorted({c for v in ja.values() for c in v if ord(c) > 0x7E})
    nost = [c for c in chars if c in KINSOKU]
    rest = [c for c in chars if c not in KINSOKU]
    if len(nost) > len(S_TRAILS) or len(rest) > 15 * len(S_TRAILS):
        sys.exit("SAVAGE.EXE の字が多すぎる")
    code = {}
    for i, c in enumerate(nost):
        code[c] = bytes([0x80, S_TRAILS[i]])
    for i, c in enumerate(rest):
        code[c] = bytes([0x81 + i // len(S_TRAILS), S_TRAILS[i % len(S_TRAILS)]])
    gly = bytearray(16 * len(S_TRAILS) * 8)
    for c, b in code.items():
        g = font.get(ord(c))
        if g is None:
            sys.exit(f"美咲フォントに字がありません: {c}")
        idx = (b[0] - 0x80) * len(S_TRAILS) + (b[1] - 0x90)
        gly[idx * 8:idx * 8 + 8] = g
    last = max([(b[0] - 0x80) * len(S_TRAILS) + (b[1] - 0x90) for b in code.values()] + [0])
    gly = bytes(gly[:(last + 1) * 8])
    stab, inplace = [], []
    for k, v in ja.items():
        e = en[k].encode("latin1")
        off = int(k.split(':')[1], 16) - ds
        if img[ds + off:ds + off + len(e) + 1] != e + bytes([0]):
            sys.exit(f"{k}: SAVAGE.EXE のデータの中の英文が違う")
        if v == en[k]:
            continue
        b = b"".join(code.get(c) or c.encode("latin1") for c in v)
        stab.append((off, b))
        if len(b) <= len(e):
            inplace.append((off, len(e)) + h12(img[ds + off:ds + off + len(e)]) + (b + bytes([0]),))
    data = img[ds:]
    ptrs = {struct.unpack_from("<H", data, i)[0] for i in range(0, 0x1000)}   # データの先頭の表（エンディングの文の表 DS:0x637 など。奇数の位置にもある）
    fits = {o for o, *_ in inplace}
    stab2 = [(off, b + b"%P") for off, b in stab if off in ptrs and off not in fits]
    print(f"SAVAGE.EXE: 字 {len(chars)}（行頭禁則 {len(nost)}）、文 {len(stab)}、その場で置き換え {len(inplace)}、%s で出す文 {len(stab2)}")
    return gly, stab, inplace, stab2


def main(gamedir, trfile, out):
    img = load_image(os.path.join(gamedir, "GAME.EXE"))
    data = img[DGROUP * 16:]
    assert NAME_SYS.lower() + bytes([0]) in data
    assert struct.unpack_from("<2H", data, PTR_PUTC) == (PUTC_OFF, PUTC_SEG)
    putc = PUTC_SEG * 16 + PUTC_OFF
    chk = h12(img[putc:putc + PUTC_LEN])
    assert img[putc + PUTC_LEN - 3:putc + PUTC_LEN] == bytes([0xCA, 0x06, 0x00])      # retf 6 で終わる
    wrap = PUTC_SEG * 16 + WRAP_OFF
    assert img[wrap:wrap + 2] == bytes([0xEB, 0x03])
    assert img[wrap + WRAP_LEN:wrap + WRAP_LEN + 4] == bytes([0x83, 0x7e, WRAP_BP, 0])
    wchk = h12(img[wrap:wrap + WRAP_LEN])
    if os.environ.get("SEJP_NOWRAP"):
        wchk = (wchk[0] ^ 1, wchk[1])
    ne = CONV_SEG * 16 + NAMEEND_OFF
    assert img[ne:ne + 7] == bytes.fromhex("f684b8e680750a")
    conv = CONV_SEG * 16 + CONV_OFF
    assert img[conv - 3:conv + 3] == bytes.fromhex("807eff807327")
    hl = PUTC_SEG * 16 + HL_OFF
    assert img[hl:hl + HL_LEN] == bytes.fromhex(
        "ff7606b8b504509a7a17000059590bc07411c6069104008b1eec03a0e624884706eb1a")
    # 05D0:2D19 の far call のセグメント（2バイト）は読み込み位置で足し直されるので、照合から外す
    hchk = h12(img[hl:hl + 10])
    hchk2 = h12(img[hl + 12:hl + HL_LEN])
    tr = read_translation(trfile)
    font = load_bdf(BDF)

    ctr = {}
    if os.environ.get("SEJP_CONVTEST"):
        from conv_text import read_tsv
        ctr = read_tsv(os.environ["SEJP_CONVTEST"])
    names = [v for k, v in ctr.items() if k.endswith(':name')]
    # 本編の文字列の訳（番号 = データの中の位置）: SEJP_GAMETSV="translation/other_ja/game.tsv;translation/other_ja/game_extra.tsv"
    gtr = read_game_tsv(os.environ["SEJP_GAMETSV"].split(";"), data) if os.environ.get("SEJP_GAMETSV") else {}
    # DGROUP の手前の文字列のセグメント 0x2F65（SEJP_GAME2TSV="translation/other_ja/game2.tsv"）
    data2 = img[SEG2 * 16:DGROUP * 16]
    gtr2 = read_game_tsv([os.environ["SEJP_GAME2TSV"]], data2, keep=set()) if os.environ.get("SEJP_GAME2TSV") else {}
    look = read_look(gamedir, os.environ.get("SEJP_LOOKTSV"))
    # 本編の途中の場面 MIDGAME1〜5.LZC（SEJP_MIDTSV="translation/other_ja/midgame.tsv"）。文は常に持つ表の符号で書く
    mid = {}
    if os.environ.get("SEJP_MIDTSV"):
        from conv_text import read_tsv
        mid = {k: v for k, v in read_tsv(os.environ["SEJP_MIDTSV"]).items()}
    gtexts = (list(tr.values()) + names + [p for _, v in list(gtr.values()) + list(gtr2.values()) for p in v.split(chr(0x7F))]
              + [ja for _, _, ja in look[0] if ja] + list(mid.values()))
    # 常に持つ表の1バイトの字は、組が入りきる範囲でなるべく多くとる（多いほうから試し、全部の文が元の長さに収まる最初の数）
    global GLOBAL
    best = None
    cands = [_GS] if os.environ.get("SEJP_GSINGLES") else list(range(94, 39, -2))
    for ns in cands:
        cs = CodeSet(NO_F1[:ns], NO_F1[ns:], GLOBAL.trails)
        genc = Enc(cs, gtexts)
        try:
            for t in gtexts:
                genc.encode(t)
            over = [o for o, (e, v) in list(gtr.items()) + list(gtr2.items()) if len(genc_encode(genc, v)) > len(e)]
            over += [t for t, n, ja in look[0] if ja and len(genc.encode(ja)) > LOOK_NAME_MAX]
        except RuntimeError:            # 組が入りきらない
            continue
        if best is None or len(over) < best[0]:
            best = (len(over), ns)
        if not over:
            break
    ns = best[1]
    GLOBAL = CodeSet(NO_F1[:ns], NO_F1[ns:], GLOBAL.trails)
    genc = Enc(GLOBAL, gtexts)
    print(f"常に持つ表: 1バイトの字 {ns}、リード {len(GLOBAL.leads)}、1マス空く所 {genc.gaps(gtexts)}")
    if os.environ.get("SEJP_SHOWGAPS"):
        for t in gtexts:
            if genc.gaps([t]):
                print("  1マス空く:", repr(t))
    strs = find_strings(data, tr, genc)
    done = {s[0] for s in strs}
    for off, (e, v) in sorted(gtr.items()):
        if off in done:
            continue
        new = genc_encode(genc, v) + bytes([0])
        if len(new) > len(e) + 1:
            print(f"注意: 本編の文字列が長すぎるので英語のまま: game:{off:04x} {v!r}（{len(new) - 1} > {len(e)} バイト）")
            continue
        strs.append((off, len(e)) + h12(data[off:off + len(e)]) + (new,))
    strs2 = []
    for off, (e, v) in sorted(gtr2.items()):
        new = genc_encode(genc, v) + bytes([0])
        if len(new) > len(e) + 1:
            print(f"注意: 本編の文字列が長すぎるので英語のまま: game2:{off:04x} {v!r}（{len(new) - 1} > {len(e)} バイト）")
            continue
        strs2.append((off, len(e)) + h12(data2[off:off + len(e)]) + (new,))
    print(f"本編の文字列の置き換え: {len(strs)} か所、セグメント 0x2F65 {len(strs2)} か所")
    outdir = os.environ.get("SEJP_CONVOUT", ".")
    if os.environ.get("SEJP_LOOKTSV"):
        write_look(gamedir, look, genc, outdir)
    if mid:
        write_midgame(gamedir, mid, genc, outdir)
    if ctr:
        make_converse(gamedir, ctr, genc, font, outdir)
    import se_graphics                          # 絵に描かれた文字（タイトルのメニュー、徳の板）→ CREATE.LZC
    se_graphics.build(gamedir, outdir)
    pnames = party_names(ctr, genc)
    sgly, sstab, sinplace, sstab2 = (build_savage(gamedir, os.environ["SEJP_SAVTSV"], font)
                                     if os.environ.get("SEJP_SAVTSV") else (bytes(8), [], [], []))

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

    def stabtab(base, ss):
        """SAVAGE.EXE の差し替え: (データの位置, 日本語の文の位置) の並び、0xFFFF、文"""
        tab = bytearray()
        body = bytearray()
        start = base + 4 * len(ss) + 2
        for off, b in ss:
            tab += struct.pack("<2H", off, start + len(body))
            body += b + bytes([0])
        return bytes(tab + bytes([0xFF, 0xFF]) + body)

    def strtab(base, ss):
        tab = bytearray()
        body = bytearray()
        start = base + 12 * len(ss) + 2
        for off, n, a, b, new in ss:
            tab += struct.pack("<6H", off, n, a, b, start + len(body), len(new))
            body += new
        return bytes(tab + b"\xff\xff" + body)

    def build(addr):
        kw = dict(V, DGROUP=DGROUP, SEG2=SEG2, PUTC_SEG=PUTC_SEG, PUTC_OFF=PUTC_OFF,
                  PUTC_LEN=PUTC_LEN, PTR_PUTC=PTR_PUTC, WIN=WIN, DRVP=DRVP, SLOT=SLOT, SCRP=SCRP,
                  CHK_H1=chk[0], CHK_H2=chk[1],
                  WRAP_OFF=WRAP_OFF, WRAP_LEN=WRAP_LEN, WRAP_W7=0xEB00 | WRAP_BP, WCHK_H1=wchk[0], WCHK_H2=wchk[1],
                  BUF=BUF, LLEN=LLEN, LDONE=LDONE, CONV_SEG=CONV_SEG, CONV_OFF=CONV_OFF, CONV_NEW=CONV_NEW, NAMEEND_OFF=NAMEEND_OFF,
                  HL_OFF=HL_OFF, HL_LEN=HL_LEN, HCHK_H1=hchk[0], HCHK_H2=hchk[1],
                  HCHK2_H1=hchk2[0], HCHK2_H2=hchk2[1], HL_W9=0x4800 | (HL_CONT - 13), HL_W11=0x74 | ((HL_TERM - 16) << 8), HL_W13=0xEB | ((HL_ZW - 18) << 8), HL_LIST=HL_LIST, LPREFIX=LPREFIX, COL_NORMAL=COL_NORMAL,
                  SCENE_MAX=SCENE_MAX, NS=NS, PARTY=PARTY,
                  JMP_OLD21=fjmp("OLD21"), CALL_OLD21=fcall("OLD21"),
                  JMP_ORIG=fjmp("ORIG"), CALL_ORIG=fcall("ORIG"),
                  JMP_ORIG2=fjmp("ORIG2"), JMP_ORIG3=fjmp("ORIG3"), JMP_RET0=fjmp("RET0"), JMP_RET1=fjmp("RET1"), JMP_RET2=fjmp("RET2"),
                  **SAV, **addr)
        code = asm(RES, CODE, kw)

        def label(name):
            src = RES.split("\n" + name + ":")[0]
            later = [x for x in LABELS if "\n" + x + ":" not in src]
            return CODE + len(asm(src + "".join(f"\n{x}:" for x in later) + "\n", CODE, kw))
        lay = {"HOOK": label("hook"), "WRAPBRK": label("wrapbrk"), "HLEND": label("hlend"),
               "CHKBRK": label("chkbrk"), "HOOK2": label("hook2"), "HOOK3": label("hook3"),
               "SSTUB0": label("sstub0"), "SSTUB1": label("sstub1"), "SSTUB2": label("sstub2")}
        p = CODE + len(code)
        tail = bytearray()

        def put(name, d):
            lay[name] = p + len(tail)
            tail.extend(d)
        put("NAME_SYS", NAME_SYS + b"\0")
        put("NAME_DAT", b"SEJP.DAT\0")
        put("SMAP", b"".join(struct.pack("<H", x) for x in smap))
        put("LIDX", bytes(lidx))
        put("TIDX_G", tidx(GLOBAL))
        put("TIDX_S", tidx(SCENE))
        put("PAIRS_G", b"".join(struct.pack("<HH", a, b) for a, b in pairs))
        put("NOST_G", bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars))
        put("ASCNS", bytes(1 if chr(c) in ASC_NOSTART else 0 for c in range(128)))
        put("GLY_G", gly)
        put("NAMES", pnames)
        put("NAME_FNT", b"SAVAGE.FNT" + bytes([0]))
        # 開くときに日本語版 *.LZJ に読み替える名前（13 バイトずつ、0 で終わり）
        put("RLIST", b"".join(n.ljust(13, bytes([0])) for n in
                              [b"TALK.LZC", b"LOOK.LZC", b"CREATE.LZC"] + [b"MIDGAME%d.LZC" % i for i in range(1, 6)]) + bytes([0]))
        put("RNAME", bytes(14))
        put("SGLY", sgly)
        put("STAB", stabtab(p + len(tail), sstab))
        put("STAB2", stabtab(p + len(tail), sstab2))
        put("SSTRS", strtab(p + len(tail), sinplace))
        put("STRS", strtab(p + len(tail), strs))
        put("STRS2", strtab(p + len(tail), strs2))
        if len(tail) % 2:
            tail.append(0)
        lay["SCENE"] = p + len(tail)
        return code, bytes(tail), lay

    keys = ["HOOK", "WRAPBRK", "HLEND", "CHKBRK", "HOOK2", "HOOK3", "SSTUB0", "SSTUB1", "SSTUB2",
            "NAME_FNT", "SGLY", "STAB", "STAB2", "SSTRS", "RLIST", "RNAME", "NAME_SYS", "NAME_DAT", "SMAP", "LIDX", "TIDX_G", "TIDX_S",
            "PAIRS_G", "NOST_G", "ASCNS", "GLY_G", "NAMES", "STRS", "STRS2", "SCENE"]
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
    msg = "SEJP: 日本語化（試作）を組み込みました\r\n$".encode("cp932")
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
