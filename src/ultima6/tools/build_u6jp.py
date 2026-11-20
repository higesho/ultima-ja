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
    """符号の割り当てを決めた Encoder。
    smart: 1バイトの字を「奇数字の日本語の並びの最後に来る回数」を重く見て選ぶ（相手のいない組で1マス空くのを減らす）"""
    def __init__(self, cs, texts, smart=False):
        self.cs = cs
        with codes(cs):
            self.e = Encoder(texts)
        if smart and cs.singles:
            import re
            score = {}
            for t in texts:
                for run in re.findall(r'[^\x00-\x7e]+', t):
                    for c in run:
                        score[c] = score.get(c, 0) + 1
                    if len(run) % 2:
                        score[run[-1]] = score.get(run[-1], 0) + 50
            top = sorted(score, key=lambda c: (-score[c], c))[:len(cs.singles)]
            self.e.single = {c: cs.singles[i] for i, c in enumerate(top)}

    def encode(self, t):
        with codes(self.cs):
            return self.e.encode(t)


# 本編の位置
CONV_SEG, CONV_OFF, CONV_NEW = 0x0ECB, 0x1C51, 0x9C   # 会話の文章の判定 cmp [bp-1],80h → 9Ch
DGROUP = 0x2D85               # 本編のデータのセグメント（ロード位置から）
DATA2 = 0x2D32                # DGROUP の手前のデータの区画（戦闘・状態の文字列）。文字列の置き換えはここを基準にする
SHIFT = (DGROUP - DATA2) * 16
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

# 導入（U.EXE）: 可変幅フォント U6.SET。1文字は 135A:0040 が描き、画面ドライバの far ポインタ DS:45C8 を呼ぶ
#   （ax=字、bx=描く構造体 [bx+2] 横の位置 [bx+6] フォント、cx=高さ、dx=幅、si=縦の位置×2）
def _x(exe, ds, name, ptr, putc_seg, chk_off, idx, fontp, lay_seg, lay_func, data):
    """data: 折り返しの関数の変数の番地（U.EXE の 457C 4580 4582 4584 4586 4588 に当たるもの）"""
    a457c, a4580, a4582, a4584, a4586, a4588 = data
    w = lambda v: struct.pack("<H", v).hex()
    d = lay_func - 0x1F                  # U.EXE では関数が 128D:001F
    return dict(EXE=exe, DS=ds, NAME_OFF=name, PTR=ptr, ORIGOFF=0x0012, PUTC_SEG=putc_seg, CHK_OFF=chk_off,
                CHK_LEN=0x3A, IDX=idx, FONTP=fontp, LAY_SEG=lay_seg,
                A457C=a457c, A4580=a4580, A4582=a4582, A4584=a4584, A4586=a4586, A4588=a4588,
                SITES=[   # (セグメントの中の位置, 元のバイト列, 呼ぶ関数, 呼んだ後のバイト列)
                    (0x5A + d, "268a00463c0074093c0a74053c2075f04e", "FIRST", "eb0a" + "90" * 10),   # 行の最初の語
                    (0x82 + d, "3c2075048936" + w(a4584), "BRK", "909090"),                          # 区切りを探す
                    (0x1B0 + d, "a1" + w(a4586) + "3b06" + w(a4588) + "73d7", "JUST", "72d99090"),   # 両端そろえ（日本語の行はしない）
                ])


# 1文字は putc（U.EXE 135A:0040）が描き、画面ドライバの far ポインタ（DS:45C8）を呼ぶ
#   （ax=字、bx=描く構造体 [bx+2] 横の位置 [bx+6] フォント、cx=高さ、dx=幅、si=縦の位置×2）
# 照合は putc の +16h から 3Ah バイト（far ジャンプのセグメントを含まない所）。
# 折り返し（U.EXE 128D:001F）は空白でしか行を分けないので、日本語の字の前でも分けられるようにする
# U6JP.DAT の索引: 人物は 0〜255、256・257 = U.EXE の表と文字列、258・259 = END.EXE
XEXE = {
    "U": _x("U.EXE", 0x1499, 0x0297, 0x45C8, 0x135A, 0x0056, 256, 0x566D + 6, 0x128D, 0x001F,
            (0x457C, 0x4580, 0x4582, 0x4584, 0x4586, 0x4588)),
    "E": _x("END.EXE", 0x07B4, 0x0D69, 0x1334, 0x0690, 0x0050, 258, 0x1E37 + 6, 0x05DD, 0x0019,
            (0x12E8, 0x12EC, 0x12EE, 0x12F0, 0x12F2, 0x12F4)),
}
U_IDX = 256
# 本編が開くときに日本語版へ振り替えるファイル。ゲームのファイルは書き換えない
#   CONVERSE.JA/JB は遊ぶ人の所で U6JPMK.COM が作る。LOOK.JZD は配る（中身はタイルの番号と訳だけ）
REDIRECT = [(b"CONVERSE.A", b"CONVERSE.JA"), (b"CONVERSE.B", b"CONVERSE.JB"), (b"LOOK.LZD", b"LOOK.JZD"),
            (b"BOOK.DAT", b"BOOK.JDT")]
# 本（BOOK.DAT）: 本編は 1冊を会話と同じ置き場所 [0x4D50] に読んで出す。字の表は人物と同じく1冊ごと（U6JP.DAT の BOOK_IDX + 本の番号）。
#   日本語の本は「文 + 0 + FE + 本の番号」。会話（先頭 FF）でないときは、常駐部が 0 の後ろの FE を探して本の表を読む
BOOK_IDX = 260
IDX_N = BOOK_IDX + 128          # U6JP.DAT の索引の数
# END.EXE は年月日の文（「one year」など）をフォントより先に作るので、config.u6 を開いた時に文字列だけ先に置き換える
XEXE["E"]["CFG_OFF"] = 0x0D0E
# U の表（SCENE に読み込む）の中の位置
UR_SMAP, UR_LIDX, UR_TIDX, UR_FAKE, UR_HEAD, UR_DATA = 0x000, 0x100, 0x180, 0x280, 0x5C0, 0x5D0
U_CODES = list(range(0x80, 0x100))

# ---- 常駐部の変数（0x103 から）----
V = dict(OLD21=0x103, ORIG=0x107, LEAD=0x10B, LROW=0x10C, LCOL=0x10E, SAVE=0x110,
         WPREV=0x118, WBEST=0x11A, WLAST=0x11C, CURGLY=0x11E, WDESC=0x120, CURNPC=0x122,
         ENTRY=0x124, DESC_G=0x12A, DESC_S=0x136, WSCN=0x142,
         UORIG=0x144, ULEAD=0x148, ULX=0x14A, ULSI=0x14C, UWSEG=0x14E, UPEND=0x150, UDSEG=0x152, UBT=0x154, UFONTPV=0x156, GOK=0x158, BKPOS=0x15A, BKW0=0x15C, BKID=0x15E)
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
    cmp byte ptr cs:[{UPEND}], 0
    jne u_pend
i_go:
    cmp ah, 0x3d
    je o21
c21:
    {JMP_OLD21}
o21:
    cmp byte ptr cs:[{GOK}], 0
    je o21b
    call redir
    jc o21b
    clc
    retf 2
o21b:
    cmp dx, {NAME_OFF}
    je o_game
    cmp dx, {U_NAME_OFF}
    je o_u
    cmp dx, {E_CFG_OFF}
    je o_ecfg
    cmp dx, {E_NAME_OFF}
    jne c21
    push di
    mov di, {NAME_U6SET}
    call isname
    pop di
    jne c21
    pushf
    {CALL_OLD21}
    jc o_x
    call epatch
    clc
    jmp o_x
o_ecfg:
    push di
    mov di, {NAME_CFG}
    call isname
    pop di
    jne c21
    pushf
    {CALL_OLD21}
    jc o_x
    call ecfg
    clc
    jmp o_x
o_u:
    push di
    mov di, {NAME_U6SET}
    call isname
    pop di
    jne c21
    pushf
    {CALL_OLD21}
    jc o_x
    call upatch
    clc
    jmp o_x
o_game:
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

u_pend:
    push es
    push di
    push ax
    push cx
    mov es, word ptr cs:[{UDSEG}]
    mov di, word ptr cs:[{UFONTPV}]
    les di, dword ptr es:[di]
    mov ax, es
    or ax, ax
    jz upd_n
    cmp word ptr es:[di], 8
    jne upd_n
    cmp byte ptr es:[di+2], 0x0f
    jne upd_n
    mov byte ptr cs:[{UPEND}], 0
    mov word ptr cs:[{UWSEG}], ax
    add di, 4+0x80
    mov al, 8
    mov cx, 0x80
    cld
    rep stosb
upd_n:
    pop cx
    pop ax
    pop di
    pop es
    jmp i_go

ecfg:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ax, ds
    sub ax, {E_DS}-{E_PUTC_SEG}
    jb ec_x
    mov es, ax
    mov si, {E_CHK_OFF}
    mov cx, {E_CHK_LEN}
    call hash
    cmp bx, {ECHK_H1}
    jne ec_x
    cmp dx, {ECHK_H2}
    jne ec_x
    push ds
    pop es
    push cs
    pop ds
    mov word ptr [{CURNPC}], 0xffff
    mov si, ({E_IDX}+1)*6
    call loadrec
    jc ec_x
    mov di, {SCENE}
    call strpatch
ec_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

redir:
    push ax
    push bx
    push si
    push di
    mov si, dx
    mov bx, dx
rd_l:
    mov al, byte ptr [si]
    or al, al
    jz rd_e
    inc si
    cmp al, 0x5c
    je rd_s
    cmp al, 0x3a
    jne rd_l
rd_s:
    mov bx, si
    jmp rd_l
rd_e:
    mov di, {RTAB}
rt_l:
    cmp byte ptr cs:[di], 0
    je rd_no
    mov si, bx
    push di
rc_l:
    mov al, byte ptr [si]
    cmp al, 0x61
    jb rc_u
    cmp al, 0x7a
    ja rc_u
    sub al, 0x20
rc_u:
    cmp al, byte ptr cs:[di]
    jne rc_ne
    inc si
    inc di
    or al, al
    jnz rc_l
    pop di
    jmp rd_hit
rc_ne:
    pop di
    add di, 28
    jmp rt_l
rd_hit:
    mov si, sp
    mov ax, word ptr ss:[si+6]
    push ds
    push dx
    push cs
    pop ds
    lea dx, [di+14]
    pushf
    {CALL_OLD21}
    pop dx
    pop ds
    jc rd_no
    pop di
    pop si
    pop bx
    add sp, 2
    clc
    ret
rd_no:
    pop di
    pop si
    pop bx
    pop ax
    stc
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
    mov byte ptr cs:[{GOK}], 0
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
    mov byte ptr cs:[{UPEND}], 0
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
    mov byte ptr cs:[{GOK}], 1
g_noconv:
    mov ax, ds
    sub ax, {DGROUP}-{DATA2}
    mov es, ax
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
    cmp byte ptr es:[bx], 0xff
    jne es_book
    mov al, byte ptr es:[bx+1]
    xor ah, ah
    jmp es_cmp
es_book:
    mov di, word ptr cs:[{BKPOS}]
    or di, di
    jz es_scan
    mov ax, word ptr es:[bx]
    cmp ax, word ptr cs:[{BKW0}]
    jne es_scan
    cmp byte ptr es:[bx+di-1], 0
    jne es_scan
    cmp byte ptr es:[bx+di], 0xfe
    jne es_scan
    mov al, byte ptr es:[bx+di+1]
    xor ah, ah
    add ax, {BOOK_IDX}
    cmp ax, word ptr cs:[{BKID}]
    je es_cmp
es_scan:
    mov di, bx
    mov cx, 0x2800
    xor al, al
    cld
    repne scasb
    jne es_none
    cmp byte ptr es:[di], 0xfe
    jne es_none
    mov al, byte ptr es:[di+1]
    xor ah, ah
    add ax, {BOOK_IDX}
    mov word ptr cs:[{BKID}], ax
    sub di, bx
    mov word ptr cs:[{BKPOS}], di
    mov dx, word ptr es:[bx]
    mov word ptr cs:[{BKW0}], dx
es_cmp:
    cmp ax, word ptr cs:[{CURNPC}]
    jne es_load
es_none:
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
    call loadrec
    jc es_x
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

loadrec:
    mov ax, 0x3d00
    mov dx, {NAME_DAT}
    pushf
    {CALL_OLD21}
    jc lr_x
    mov bx, ax
    mov dx, si
    xor cx, cx
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc lr_f
    mov ah, 0x3f
    mov cx, 6
    mov dx, {ENTRY}
    pushf
    {CALL_OLD21}
    jc lr_f
    cmp ax, 6
    jne lr_f
    mov cx, word ptr [{ENTRY}+4]
    or cx, cx
    jz lr_f
    cmp cx, {SCENE_MAX}
    ja lr_f
    mov dx, word ptr [{ENTRY}]
    mov cx, word ptr [{ENTRY}+2]
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc lr_f
    mov ah, 0x3f
    mov cx, word ptr [{ENTRY}+4]
    mov dx, {SCENE}
    pushf
    {CALL_OLD21}
    jc lr_f
    cmp ax, word ptr [{ENTRY}+4]
    jne lr_f
    mov ah, 0x3e
    pushf
    {CALL_OLD21}
    clc
    ret
lr_f:
    mov ah, 0x3e
    pushf
    {CALL_OLD21}
    stc
lr_x:
    ret

uhook:
    cmp byte ptr cs:[{ULEAD}], 0
    jne u_tr
    cmp al, 0x80
    jae u_jp
u_pass:
    {JMP_UORIG}
u_jp:
    call u_wid
    xor ah, ah
    mov di, ax
    shl di, 1
    mov ax, word ptr cs:[di+{U_SMAP}-0x100]
    cmp ax, 0xfffe
    je u_ret
    ja u_lead
    call u_draw
u_ret:
    retf
u_lead:
    mov ax, di
    shr ax, 1
    mov byte ptr cs:[{ULEAD}], al
    mov ax, word ptr [bx+2]
    mov word ptr cs:[{ULX}], ax
    mov word ptr cs:[{ULSI}], si
    add word ptr [bx+2], 8
    retf
u_tr:
    push cx
    push di
    xor ah, ah
    mov di, ax
    mov cl, byte ptr cs:[di+{U_TIDX}]
    pop di
    cmp cl, 0xff
    jne u_tr2
    pop cx
    mov byte ptr cs:[{ULEAD}], 0
    jmp u_pass
u_tr2:
    add sp, 2
    xor ch, ch
    xor ah, ah
    mov al, byte ptr cs:[{ULEAD}]
    mov byte ptr cs:[{ULEAD}], 0
    mov di, ax
    mov al, byte ptr cs:[di+{U_LIDX}-0x80]
    mul word ptr cs:[{U_HNTR}]
    add ax, cx
    cmp ax, word ptr cs:[{U_HNPAIRS}]
    jae u_ret
    shl ax, 1
    shl ax, 1
    mov di, ax
    add di, word ptr cs:[{U_HPAIRS}]
    push word ptr cs:[di+2]
    cmp si, word ptr cs:[{ULSI}]
    je u_same
    mov ax, word ptr cs:[di]
    call u_draw
    pop ax
    call u_draw
    retf
u_same:
    push word ptr [bx+2]
    push si
    mov ax, word ptr cs:[{ULX}]
    mov word ptr [bx+2], ax
    mov si, word ptr cs:[{ULSI}]
    mov ax, word ptr cs:[di]
    call u_draw
    pop si
    pop word ptr [bx+2]
    pop ax
    call u_draw
    retf

u_kin:
    push di
    push cx
    push dx
    xor ah, ah
    mov al, byte ptr es:[bx+si]
    mov di, ax
    shl di, 1
    mov ax, word ptr cs:[di+{U_SMAP}-0x100]
    mov dl, 1
    cmp ax, 0xfffe
    je uk_no
    jb uk_g
    mov dl, 2
    xor ah, ah
    mov al, byte ptr es:[bx+si+1]
    mov di, ax
    mov cl, byte ptr cs:[di+{U_TIDX}]
    cmp cl, 0xff
    je uk_no
    xor ch, ch
    mov al, byte ptr es:[bx+si]
    mov di, ax
    mov al, byte ptr cs:[di+{U_LIDX}-0x80]
    push dx
    mul word ptr cs:[{U_HNTR}]
    pop dx
    add ax, cx
    cmp ax, word ptr cs:[{U_HNPAIRS}]
    jae uk_no
    shl ax, 1
    shl ax, 1
    mov di, ax
    add di, word ptr cs:[{U_HPAIRS}]
    mov ax, word ptr cs:[di]
uk_g:
    mov di, ax
    add di, word ptr cs:[{U_HNOST}]
    mov al, byte ptr cs:[di]
    jmp uk_x
uk_no:
    xor al, al
uk_x:
    mov ah, dl
    pop dx
    pop cx
    pop di
    ret

u_wid:
    push es
    push di
    push ax
    push cx
    les di, dword ptr [bx+6]
    mov ax, es
    cmp ax, word ptr cs:[{UWSEG}]
    je uw_x
    mov word ptr cs:[{UWSEG}], ax
    add di, 4+0x80
    mov al, 8
    mov cx, 0x80
    cld
    rep stosb
uw_x:
    pop cx
    pop ax
    pop di
    pop es
    ret

u_draw:
    or ax, ax
    jz ud_x
    push bx
    push si
    push di
    push es
    push ds
    mov si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    add si, word ptr cs:[{U_HGLY}]
    push cs
    pop ds
    push cs
    pop es
    mov di, {U_FAKE}+0x300
    cld
    mov cx, 8
ud_r:
    lodsb
    mov ah, al
    mov dx, 8
ud_b:
    xor al, al
    shl ah, 1
    jnc ud_0
    mov al, 0x0f
ud_0:
    stosb
    dec dx
    jnz ud_b
    loop ud_r
    pop ds
    pop es
    pop di
    pop si
    pop bx
    push word ptr [bx+6]
    push word ptr [bx+8]
    mov word ptr [bx+6], {U_FAKE}
    mov word ptr [bx+8], cs
    push bx
    push si
    mov ax, 0x80
    mov cx, 8
    mov dx, 8
    {CALL_UORIG}
    pop si
    pop bx
    pop word ptr [bx+8]
    pop word ptr [bx+6]
ud_x:
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

X_TPL = r'''
upatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    cmp word ptr [{U_PTR}], {U_ORIGOFF}
    jne up_x
    mov ax, ds
    sub ax, {U_DS}-{U_PUTC_SEG}
    jb up_x
    mov es, ax
    mov si, {U_CHK_OFF}
    mov cx, {U_CHK_LEN}
    call hash
    cmp bx, {UCHK_H1}
    jne up_x
    cmp dx, {UCHK_H2}
    jne up_x
    push ds
    push cs
    pop ds
    mov word ptr [{CURNPC}], 0xffff
    mov si, ({U_IDX}+1)*6
    call loadrec
    pop ds
    jc up_x
    push ds
    pop es
    push cs
    pop ds
    mov di, {SCENE}
    call strpatch
    mov si, {U_IDX}*6
    call loadrec
    push es
    pop ds
    jc up_x
    mov word ptr cs:[{UCP_S0}], cs
    mov word ptr cs:[{UCP_S1}], cs
    mov word ptr cs:[{UCP_S2}], cs
    mov ax, ds
    sub ax, {U_DS}-{U_LAY_SEG}
    mov es, ax
    push ds
    push cs
    pop ds
    mov di, {UCP}
    call strpatch
    pop ds
    mov ax, word ptr [{U_PTR}]
    mov word ptr cs:[{UORIG}], ax
    mov ax, word ptr [{U_PTR}+2]
    mov word ptr cs:[{UORIG}+2], ax
    mov word ptr [{U_PTR}], {UHOOK}
    mov word ptr [{U_PTR}+2], cs
    mov byte ptr cs:[{ULEAD}], 0
    mov word ptr cs:[{UWSEG}], 0
    mov word ptr cs:[{UDSEG}], ds
    mov word ptr cs:[{UFONTPV}], {U_FONTP}
    mov byte ptr cs:[{GOK}], 0
    mov byte ptr cs:[{UPEND}], 1
up_x:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

ufirst:
    mov word ptr cs:[{UBT}], 0xffff
uf_l:
    mov al, byte ptr es:[bx+si]
    inc si
    or al, al
    je uf_r
    cmp al, 0x0a
    je uf_r
    cmp al, 0x20
    je uf_b
    cmp al, 0x80
    jb uf_l
    dec si
    cmp si, word ptr [{U_A4580}]
    jne uf_r
uf_u:
    call u_kin
    mov al, ah
    xor ah, ah
    add si, ax
    mov al, byte ptr es:[bx+si]
    cmp al, 0x80
    jb uf_r
    call u_kin
    or al, al
    jnz uf_u
    jmp uf_r
uf_b:
    dec si
uf_r:
    retf

ubrk:
    cmp al, 0x20
    je ub_set
    cmp al, 0x80
    jb ub_x
    cmp si, word ptr cs:[{UBT}]
    je ub_x
    push ax
    call u_kin
    cmp ah, 2
    jne ub_1
    inc si
    mov word ptr cs:[{UBT}], si
    dec si
ub_1:
    cmp si, word ptr [{U_A4582}]
    je ub_n
    or al, al
    jnz ub_n
    pop ax
ub_set:
    mov word ptr [{U_A4584}], si
    retf
ub_n:
    pop ax
ub_x:
    retf

ujust:
    mov ax, word ptr [{U_A4586}]
    cmp ax, word ptr [{U_A4588}]
    jae uj_p
    push si
    les bx, dword ptr [{U_A457C}]
    mov si, word ptr [{U_A4582}]
uj_l:
    cmp si, word ptr [{U_A4584}]
    jae uj_ok
    cmp byte ptr es:[bx+si], 0x80
    jae uj_p2
    inc si
    jmp uj_l
uj_ok:
    pop si
    clc
    retf
uj_p2:
    pop si
uj_p:
    stc
    retf

'''


def x_render(tag):
    """EXE ごとの部分（U = 導入 U.EXE、E = エンディング END.EXE）"""
    import re
    t = X_TPL.replace('{U_', '{' + tag + '_').replace('{UCHK_', '{' + tag + 'CHK_').replace('{UCP', '{' + tag + 'CP')
    if tag != 'U':
        t = re.sub(r'\b(upatch|up_x|ufirst|uf_[a-z0-9]+|ubrk|ub_[a-z0-9]+|ujust|uj_[a-z0-9]+)\b',
                   lambda m: tag.lower() + m.group(1)[1:], t)
    return t


RES = RES + x_render('U') + x_render('E')

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
LABELS = ("hook", "wrapbrk", "hlend", "ensure_scene", "draw", "loadrec", "upatch", "uhook", "u_wid", "u_draw", "u_kin", "ufirst", "ubrk", "ujust",
          "epatch", "efirst", "ebrk", "ejust")


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


def read_look(gamedir, tsv):
    """LOOK.LZD（物の名前）: 「タイル番号 2バイト＋名前＋0」の並び＋末尾の残り。
    戻り値: ([(タイル, 英語の名前 bytes, 訳 or None)], 末尾の残り)"""
    from u6fmt import lzw
    raw, _ = lzw(open(os.path.join(gamedir, "LOOK.LZD"), "rb").read())
    ja = {}
    if tsv:
        from conv_text import read_tsv
        ja = read_tsv(tsv)
    ents = []
    p = 0
    while p + 2 < len(raw):
        e = raw.find(b"\0", p + 2)
        if e < 0:
            break
        tile = struct.unpack_from("<H", raw, p)[0]
        name = raw[p + 2:e]
        v = ja.get(f"look:{tile:04x}")
        ents.append((tile, name, v if v is not None and v != name.decode('latin1') else None))
        p = e + 1
    return ents, raw[p:]


def write_look(look, genc, outdir):
    """物の名前を常に持つ表の符号にして LOOK.LZD を作る。名前を引く関数（00CB:C445 付近）は DS:0xD7DC に長さを確かめずに写すので、
    英語の最も長い名前を超える訳は英語のまま残す"""
    from u6fmt import lzw_pack
    ents, rest = look
    maxlen = max(len(n) for _, n, _ in ents)
    out = bytearray()
    n = 0
    for tile, name, ja in ents:
        b = name
        if ja:
            enc = genc.encode(ja)
            if len(enc) > maxlen or 0 in enc:
                print(f"注意: 物の名前が長すぎるので英語のまま: look:{tile:04x} {ja!r}")
            else:
                b = enc
                n += 1
        out += struct.pack("<H", tile) + b + b"\0"
    out += rest
    open(os.path.join(outdir, "LOOK.JZD"), "wb").write(lzw_pack(bytes(out)))
    print(f"LOOK.JZD: 名前 {n} / {len(ents)} を日本語に（{len(out)} バイト、英語の最長 {maxlen} バイト）")


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
    index = bytearray(IDX_N * 6)        # 256・257 = 導入（U.EXE）の表と文字列、258・259 = エンディング（END.EXE）
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


def strtab(base, ss):
    """文字列の置き換えの表（base は表を置く常駐部の中の位置）"""
    tab = bytearray()
    body = bytearray()
    start = base + 12 * len(ss) + 2
    for off, n, a, b, new in ss:
        tab += struct.pack("<6H", off, n, a, b, start + len(body), len(new))
        body += new
    return bytes(tab + b"\xff\xff" + body)


def exe_image(gamedir, name):
    d = open(os.path.join(gamedir, name), "rb").read()
    return d[struct.unpack_from("<H", d, 8)[0] * 16:]


class UPart:
    """導入（U.EXE）・エンディング（END.EXE）の文字列と、その表（U6JP.DAT の X["IDX"] 番。常駐部の SCENE に読み込む）"""
    def __init__(self, gamedir, tsv, font, x):
        from conv_text import read_tsv
        self.x = x
        img = exe_image(gamedir, x["EXE"])
        ds = x["DS"] * 16
        assert img[ds + x["NAME_OFF"]:ds + x["NAME_OFF"] + 7] == b"u6.set\0"
        assert img[ds + 4:ds + 11] == b"Turbo-C"
        c = x["PUTC_SEG"] * 16 + x["CHK_OFF"]
        assert img[c - 0x16:c - 0x11] == bytes.fromhex("b4003d0d00")
        self.chk = h12(img[c:c + x["CHK_LEN"]])
        for off, old, _, _ in x["SITES"]:
            a = x["LAY_SEG"] * 16 + off
            assert img[a:a + len(old) // 2] == bytes.fromhex(old), hex(a)
        self.font = font
        ja = read_tsv(tsv)
        en = read_tsv(tsv.replace("other_ja", "other_en"))
        self.rows = []
        for k, v in ja.items():
            off = int(k.split(':')[1], 16) - ds
            e = en[k].encode("latin1")
            if img[ds + off:ds + off + len(e) + 1] != e + b"\0":
                sys.exit(f"{k}: {x['EXE']} の中の英文が違う")
            if v.rstrip() != en[k].rstrip():          # 末尾の空白だけ違うものは訳していない（英語のまま）
                self.rows.append((off, e, v, h12(img[ds + off:ds + off + len(e)])))
        texts = [v for _, _, v, _ in self.rows]
        best = None
        for ns in range(120, 0, -4):
            cs = CodeSet(U_CODES[:ns], U_CODES[ns:], U_CODES)
            enc = Enc(cs, texts, smart=True)
            try:
                over = [r for r in self.rows if len(enc.encode(r[2])) > len(r[1])]
            except RuntimeError:
                continue
            if best is None or len(over) < best[0]:
                best = (len(over), ns)
            if not over:
                break
        self.cs = CodeSet(U_CODES[:best[1]], U_CODES[best[1]:], U_CODES)
        self.enc = Enc(self.cs, texts, smart=True)
        self.texts = texts

    def record(self, scene):
        enc, cs = self.enc, self.cs
        news = [enc.encode(v) + b"\0" for _, _, v, _ in self.rows]     # 先に符号にして組を決める
        chars, gidx, gly = glyph_table(self.font, [enc], self.texts)
        pairs = pair_list(enc.e, gidx)
        smap = [0xFFFE] * 128
        lidx = [0xFF] * 128
        for i, c in enumerate(cs.leads):
            smap[c - 0x80] = 0xFFFF
            lidx[c - 0x80] = i
        for ch, code in enc.e.single.items():
            smap[code - 0x80] = gidx[ch]
        tidx = bytes(cs.trails.index(c) if c in cs.trails else 0xFF for c in range(256))
        fake = bytearray(0x340)
        fake[0:4] = bytes([8, 0, 0x0F, 0x00])
        fake[4 + 0x80] = 8
        fake[0x104 + 0x80], fake[0x204 + 0x80] = 0x00, 0x03
        rec = bytearray(UR_DATA)
        rec[UR_SMAP:UR_SMAP + 256] = b"".join(struct.pack("<H", x) for x in smap)
        rec[UR_LIDX:UR_LIDX + 128] = bytes(lidx)
        rec[UR_TIDX:UR_TIDX + 256] = tidx
        rec[UR_FAKE:UR_FAKE + 0x340] = fake
        p_pairs = UR_DATA
        body_pairs = b"".join(struct.pack("<HH", a, b) for a, b in pairs)
        p_gly = p_pairs + len(body_pairs)
        nost = bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars)
        p_nost = p_gly + len(gly)
        ss = []
        skipped = []
        for (off, e, v, (h1, h2)), new in zip(self.rows, news):
            if len(new) > len(e) + 1:
                skipped.append((off, v, len(new) - 1, len(e)))
                continue
            ss.append((off, len(e), h1, h2, new))
        struct.pack_into("<5H", rec, UR_HEAD, len(cs.trails), len(pairs), scene + p_pairs, scene + p_gly, scene + p_nost)
        rec += body_pairs + gly + nost
        srec = strtab(scene, ss)          # 文字列の置き換えは別に読み込む（先に読んで置き換えてから表を読む）
        for off, v, a, b in skipped:
            print(f"注意: {self.x['EXE']} の文字列が長すぎるので英語のまま: {off:04x} {v!r}（{a} > {b} バイト）")
        if max(len(rec), len(srec)) > SCENE_MAX:
            sys.exit(f"{self.x['EXE']} の表が大きすぎる {len(rec)}、{len(srec)} > {SCENE_MAX}")
        print(f"{self.x['EXE']}: 字 {len(chars)}、組 {len(pairs)}、1バイトの字 {len(enc.e.single)}、リード {len(cs.leads)}、"
              f"置き換え {len(ss)} か所、表 {len(rec)} バイト、置き換え {len(srec)} バイト")
        return bytes(rec), srec


def make_books(gamedir, tsv, font, outdir):
    """BOOK.JDT（日本語の本）を outdir に書き、U6JP.DAT に本ごとの表を足す"""
    from u6fmt import lib
    from conv_text import read_tsv
    data = open(os.path.join(gamedir, "BOOK.DAT"), "rb").read()
    items = lib(data, 2)
    ja = read_tsv(tsv)
    new = []
    nj = 0
    for k, it in enumerate(items):
        v = ja.get(f"book:{k:03d}")
        if it is None or v is None or v == it.rstrip(b"\0").decode("latin1"):
            new.append(it)
            continue
        enc = Enc(SCENE, [v])
        b = enc.encode(v)
        assert 0 not in b
        rec, nch, npr = scene_record(font, enc, [v])
        if len(rec) > SCENE_MAX:
            sys.exit(f"本 {k}: 表が大きすぎる {len(rec)}")
        put_dat(outdir, BOOK_IDX + k, rec)
        new.append(b + b"\0\xfe" + bytes([k]))
        nj += 1
    head = bytearray(2 * len(items))
    body = bytearray()
    for k, it in enumerate(new):
        if it is None:
            continue
        struct.pack_into("<H", head, 2 * k, len(head) + len(body))
        body += it
    out = bytes(head + body)
    assert len(out) < 0x10000
    for k, it in enumerate(new):
        assert len(it) <= 0x2800
    open(os.path.join(outdir, "BOOK.JDT"), "wb").write(out)
    print(f"BOOK.JDT: 本 {nj} / {len(items)} を日本語に（{len(out)} バイト）")


def put_dat(outdir, idx, rec):
    """U6JP.DAT の idx 番に rec を足す（ファイルがなければ空の索引から作る）"""
    path = os.path.join(outdir, "U6JP.DAT")
    n = IDX_N * 6
    d = bytearray(open(path, "rb").read()) if os.path.exists(path) else bytearray(n)
    assert len(d) >= n
    struct.pack_into("<IH", d, idx * 6, len(d), len(rec))
    d += rec
    open(path, "wb").write(bytes(d))


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
    # 本編の文字列の訳（番号 = データの中の位置）: U6JP_GAMETSV=translation/other_ja/game.tsv
    # 置き換えの位置は、セグメント 0x2D32（DATA2）からの位置にそろえる。game: は DGROUP からの位置なので SHIFT を足す
    data2 = img[DATA2 * 16:]
    gtr = {}
    if os.environ.get("U6JP_GAMETSV"):
        from conv_text import read_tsv
        # 訳してはいけない: 入力と比べたり、入力の代わりに入れたりする文字列（DGROUP からの位置）
        #   0x0A0F "bye"（空の入力をこれに置き換える）、0x0AEA "look"（入力と strcmp して外見を出す）
        keep = {0x0A0F + SHIFT, 0x0AEA + SHIFT}
        for path in os.environ["U6JP_GAMETSV"].split(os.pathsep):
            ja = read_tsv(path)
            en = read_tsv(path.replace("other_ja", "other_en"))
            for k, v in ja.items():
                tag, h = k.split(':')
                off = int(h, 16) + (SHIFT if tag == 'game' else 0)
                if off in keep:
                    continue
                e = en[k].encode('latin1')
                if data2[off:off + len(e) + 1] != e + b"\0":
                    sys.exit(f"{k}: データの中の英文が違う")
                if v != en[k]:
                    gtr[off] = (e, v)
    look = read_look(gamedir, os.environ.get("U6JP_LOOKTSV"))
    gtexts = list(tr.values()) + names + [v for _, v in gtr.values()] + [ja for _, _, ja in look[0] if ja]
    # 奇数字の並びの最後が1バイトの字でないと1バイト増え、1マス空く。1バイトの字は組が入りきる範囲でなるべく多くとる
    # （多いほうから試し、全部の文が入りきって元の長さに収まる最初の数。U6JP_GSINGLES を指定したらその数）
    global GLOBAL
    best = None
    cands = [_GS] if os.environ.get("U6JP_GSINGLES") else list(range(88, 39, -4))
    for ns in cands:
        cs = CodeSet(NO_F1[:ns], NO_F1[ns:], GLOBAL.trails)
        genc = Enc(cs, gtexts, smart=True)
        try:
            for t in gtexts:
                genc.encode(t)
            over = [off for off, (e, v) in gtr.items() if len(genc.encode(v)) > len(e)]
        except RuntimeError:            # 組が入りきらない
            continue
        if best is None or len(over) < best[0]:
            best = (len(over), ns)
        if not over:
            break
    ns = best[1]
    cs = CodeSet(NO_F1[:ns], NO_F1[ns:], GLOBAL.trails)
    genc = Enc(cs, gtexts, smart=True)
    GLOBAL = cs
    print(f"常に持つ表: 1バイトの字 {ns}、リード {len(cs.leads)}")
    strs = [(s[0] + SHIFT,) + tuple(s[1:]) for s in find_strings(data, tr, genc)]
    done = {s[0] for s in strs}
    for off, (e, v) in sorted(gtr.items()):
        if off in done:
            continue
        new = genc.encode(v) + b"\0"
        if len(new) > len(e) + 1:
            print(f"注意: 本編の文字列が長すぎるので英語のまま: {off:04x} {v!r}（{len(new) - 1} > {len(e)} バイト）")
            continue
        strs.append((off, len(e)) + h12(data2[off:off + len(e)]) + (new,))
    print(f"本編の文字列の置き換え: {len(strs)} か所")
    if os.environ.get("U6JP_LOOKTSV"):
        write_look(look, genc, os.environ.get("U6JP_CONVOUT", "."))
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

    # 導入・エンディング: U6JP_UTSV=translation/other_ja/u.tsv、U6JP_ETSV=translation/other_ja/end.tsv
    parts = {}
    for tag, env in (("U", "U6JP_UTSV"), ("E", "U6JP_ETSV")):
        if os.environ.get(env):
            parts[tag] = UPart(gamedir, os.environ[env], font, XEXE[tag])

    def build(addr):
        sc = addr["SCENE"]
        ukw = dict(U_SMAP=sc + UR_SMAP, U_LIDX=sc + UR_LIDX, U_TIDX=sc + UR_TIDX, U_FAKE=sc + UR_FAKE,
                   U_HNTR=sc + UR_HEAD, U_HNPAIRS=sc + UR_HEAD + 2, U_HPAIRS=sc + UR_HEAD + 4,
                   U_HGLY=sc + UR_HEAD + 6, U_HNOST=sc + UR_HEAD + 8,
                   JMP_UORIG=fjmp("UORIG"), CALL_UORIG=fcall("UORIG"))
        for tag, x in XEXE.items():
            xchk = parts[tag].chk if tag in parts else (0, 1)     # 訳がなければ照合が合わないようにする
            ukw[tag + "CHK_H1"], ukw[tag + "CHK_H2"] = xchk
            for k, v in x.items():
                if isinstance(v, int):
                    ukw[tag + "_" + k] = v
        kw = dict(V, DGROUP=DGROUP, DATA2=DATA2, NAME_OFF=NAME_OFF, PUTC_SEG=PUTC_SEG, PUTC_OFF=PUTC_OFF,
                  PUTC_LEN=PUTC_LEN, PTR_PUTC=PTR_PUTC, WIN=WIN, DRVP=DRVP, SLOT=SLOT, SCRP=SCRP,
                  CHK_H1=chk[0], CHK_H2=chk[1],
                  WRAP_OFF=WRAP_OFF, WRAP_LEN=WRAP_LEN, WCHK_H1=wchk[0], WCHK_H2=wchk[1],
                  BUF=BUF, LLEN=LLEN, LDONE=LDONE, CONV_SEG=CONV_SEG, CONV_OFF=CONV_OFF, CONV_NEW=CONV_NEW,
                  HL_OFF=HL_OFF, HL_LEN=HL_LEN, HCHK_H1=hchk[0], HCHK_H2=hchk[1],
                  HCHK2_H1=hchk2[0], HCHK2_H2=hchk2[1], HL_LIST=HL_LIST, LPREFIX=LPREFIX, COL_NORMAL=COL_NORMAL,
                  SCENE_MAX=SCENE_MAX, BOOK_IDX=BOOK_IDX,
                  JMP_OLD21=fjmp("OLD21"), CALL_OLD21=fcall("OLD21"),
                  JMP_ORIG=fjmp("ORIG"), CALL_ORIG=fcall("ORIG"), **ukw, **addr)
        # 入口の番地は、末尾に .word で並べて組み立て器に出させる（途中までの長さで見積もると、跳び先の長さの違いでずれる）
        names = ["hook", "wrapbrk", "hlend", "uhook", "ufirst", "ubrk", "ujust", "efirst", "ebrk", "ejust"]
        full = asm(RES + "\n_labels:\n" + "".join(f"    .word {x}\n" for x in names), CODE, kw)
        code = full[:-2 * len(names)]
        labs = dict(zip(names, struct.unpack(f"<{len(names)}H", full[-2 * len(names):])))
        assert code == asm(RES, CODE, kw)

        def label(name):
            return labs[name]
        lay = {"HOOK": label("hook"), "WRAPBRK": label("wrapbrk"), "HLEND": label("hlend"), "UHOOK": label("uhook"),
               "UFIRST": label("ufirst"), "UBRK": label("ubrk"), "UJUST": label("ujust"),
               "EFIRST": label("efirst"), "EBRK": label("ebrk"), "EJUST": label("ejust")}
        p = CODE + len(code)
        tail = bytearray()

        def put(name, d):
            lay[name] = p + len(tail)
            tail.extend(d)
        put("NAME_U6CH", b"U6.CH\0")
        put("NAME_DAT", b"U6JP.DAT\0")
        put("NAME_U6SET", b"U6.SET\0")
        put("NAME_CFG", b"CONFIG.U6\0")
        # 開くときに振り替えるファイル（元の名前 14 バイト、日本語版の名前 14 バイト）
        put("RTAB", b"".join(a.ljust(14, b"\0") + b.ljust(14, b"\0") for a, b in REDIRECT) + b"\0")
        put("SMAP", b"".join(struct.pack("<H", x) for x in smap))
        put("LIDX", bytes(lidx))
        put("TIDX_G", tidx(GLOBAL))
        put("TIDX_S", tidx(SCENE))
        put("PAIRS_G", b"".join(struct.pack("<HH", a, b) for a, b in pairs))
        put("NOST_G", bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars))
        put("ASCNS", bytes(1 if chr(c) in ASC_NOSTART else 0 for c in range(128)))
        put("GLY_G", gly)
        put("STRS", strtab(p + len(tail), strs))
        # 折り返しの関数への割り込み（呼ぶ先のセグメントは常駐部が自分の cs を書き込む）
        for tag, x in XEXE.items():
            cps = []
            for off, old, fn, rest in x["SITES"]:
                old = bytes.fromhex(old)
                new = b"\x9a" + struct.pack("<HH", lay[tag + fn], 0) + bytes.fromhex(rest)
                assert len(new) == len(old)
                cps.append((off, len(old)) + h12(old) + (new,))
            base = p + len(tail)
            put(tag + "CP", strtab(base, cps))
            body = base + 12 * len(cps) + 2
            for i in range(len(cps)):
                lay[f"{tag}CP_S{i}"] = body + sum(len(c[4]) for c in cps[:i]) + 3
        if len(tail) % 2:
            tail.append(0)
        lay["SCENE"] = p + len(tail)
        return code, bytes(tail), lay

    keys = ["HOOK", "WRAPBRK", "HLEND", "UHOOK", "UFIRST", "UBRK", "UJUST", "UCP", "UCP_S0", "UCP_S1", "UCP_S2",
            "EFIRST", "EBRK", "EJUST", "ECP", "ECP_S0", "ECP_S1", "ECP_S2", "NAME_U6CH", "NAME_DAT", "NAME_U6SET", "NAME_CFG", "RTAB", "SMAP", "LIDX", "TIDX_G", "TIDX_S",
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
    if os.environ.get("U6JP_BOOKTSV"):
        make_books(gamedir, os.environ["U6JP_BOOKTSV"], font, os.environ.get("U6JP_CONVOUT", "."))
    for tag, part in parts.items():
        rec, srec = part.record(scene)
        put_dat(os.environ.get("U6JP_CONVOUT", "."), part.x["IDX"], rec)
        put_dat(os.environ.get("U6JP_CONVOUT", "."), part.x["IDX"] + 1, srec)
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
