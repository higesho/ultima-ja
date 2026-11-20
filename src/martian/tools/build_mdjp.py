# Martian Dreams 用の常駐プログラム MDJP.COM と、人物ごとの表のファイル MDJP.DAT を作る
# （ウルティマVI の build_u6jp.py を写して直したもの。本編の作りは U6 とほぼ同じ）
#
# 常駐部（INT 21h を横取り）:
#   AH=3Dh: 本編 GAME.EXE が SYSTEM.LZC を開いたとき（DX = 0x0251、フォントの読み込み）に、照合してから次を行う。
#     DS = 本編のデータ（DGROUP 0x2FAB）
#     1. 1文字出力の関数ポインタ DS:0x1BC8（2238:02FF）を hook に向ける
#     2. 折り返しの 2238:2E51〜2E6F を wrapbrk の呼び出しに（組の途中で切らない、日本語の前後で切る、行頭禁則）
#     3. @ の強調の 2238:334E〜3370 を hlend の呼び出しに（0x7F で強調を止め、字は描かない）
#     4. 本編のデータ（far データ 0x2BB4〜と DGROUP）の文字列を日本語に置き換える（元の長さ以内）
#   AH=3Fh: 読み込んだ直後に、オーバーレイ（GAME.EXE の FBOV の部分）の決まった位置なら照合して書き換える
#     会話の文章の判定（オーバーレイ 2F88 の 175D: cmp [bp-1],80h）の 80h を 9Ch に（0x80〜0x9B を文章として通す）
#     オーバーレイは必要なときに読み直されるので、メモリ上で1度書き換えるのではなく、読むたびに書き換える
#
# 符号（1バイト = 1マス、美咲フォント 8×8）:
#   0x80〜0x9B  場面の表（人物ごと。MDJP.DAT から読む）: 1バイトの字 0x80〜0x83、組のリード 0x84〜0x9B
#   0xA0〜0xFF  常に持つ表（常駐部の中）: 1バイトの字 0xA0〜0xC7、組のリード 0xC8〜0xFF（0xF1 を除く）
#   トレイルは 0x21〜0x7E から本編が特別扱いする記号と @ の強調を止める字と DEL を除いたもの＋ 0x80〜0x9B（場面の表）、
#   常に持つ表はさらに 0xA0〜0xFF（0xF1 を除く）
#   場面の表は、場面の符号が来たときに、会話スクリプトの置き場所 [0x6EC2] の2バイト目（FF <人物の番号>）を見て、
#   前と違えば MDJP.DAT から読み込む
#
# 使い方: python build_mdjp.py <ゲームのフォルダ> <本編の文字列の訳> <出力 MDJP.COM>
#   本編の文字列の訳: 「英文<TAB>訳」。\n は改行。本編のデータの中の、前後が 0 の英文を全部置き換える
#   MDJP_CONVTEST=<会話の訳 番号<TAB>訳>  MDJP_CONVOUT=<出力先>: TALK.LZC と MDJP.DAT を作る
#   MDJP_NOWRAP=1: 折り返しを直さない版（比べる用）
import contextlib
import os
import re
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
# 本編の文字出力（2238:3197）が特別扱いする記号（表 2238:33B2 の9個。@ 強調、\ 複数形、* キー待ち、` 大文字など）と、
# @ の強調を止める字（DS:0x1CAD）。どちらも組のトレイルに使わない。& は MD では閉じの引用符の字形（特別扱いはない）
SPECIAL = set(b"#$%*/@\\^`") | set(b" ,.:;!?'-\"\n") | {0x7F}
ASC_TRAILS = [c for c in range(0x21, 0x7F) if c not in SPECIAL]
NO_F1 = [c for c in range(0xA0, 0x100) if c != 0xF1]   # 人物の名前は 0xF1 まで写されるので 0xF1 は使わない


class CodeSet:
    def __init__(self, singles, leads, trails):
        self.singles, self.leads, self.trails = singles, leads, trails


NS_S = 12                     # 場面の表の1バイトの字の数（0x80〜0x8B）。リード 0x8C〜0x9B（16 × 104 = 1,664 組）
SCENE = CodeSet(list(range(0x80, 0x80 + NS_S)), list(range(0x80 + NS_S, 0x9C)), ASC_TRAILS + list(range(0x80, 0x9C)))
_GS = int(os.environ.get("MDJP_GSINGLES", "40"))   # 試験用: 常に持つ表の1バイトの字の数（0 で全部を組にする）
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
        if not smart and cs.singles:
            # 1バイトの字は「組の相手がいなくて1字だけ余る字」から、1マス空く所が一番減る字を1字ずつ選ぶ（SE と同じ）。
            # 足りなければよく出る字で埋める
            n = len(cs.singles)
            seg = self.e.segment

            def gaps(sel, ts):
                self.e.single = dict.fromkeys(sel, 0)
                return sum(1 for t in ts for u in seg(t) if u[0] == 'p' and u[2] is None)
            with codes(cs):
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

    def gaps(self, texts):
        """組の相手がいなくて1マス空く所の数"""
        with codes(self.cs):
            return sum(1 for t in texts for u in self.e.segment(t) if u[0] == 'p' and u[2] is None)


# 本編の位置（GAME.EXE のロードイメージ。ヘッダ 0x3400 バイト、FBOV は 0x422B0 から）
EXE_HDR, FBOV = 0x3400, 0x422B0
DGROUP = 0x2FAB               # 本編のデータのセグメント（ロード位置から）
FARDATA = 0x2BB4              # far データ（文字列が多い）の始まり。ここから DGROUP の終わりまでを置き換えの対象にする
NAME_OFF = 0x0251             # データの "system.lzc"（フォントを読むとき）
PUTC_SEG, PUTC_OFF = 0x2238, 0x02FF   # 本編の1文字出力
PUTC_LEN = 0x72               # 照合する長さ（関数の全体 0x2267F〜0x226F0）
PTR_PUTC = 0x1BC8             # 1文字出力の関数ポインタ
WIN = 0x1BDB                  # 今の窓の構造体へのポインタ（+6 文字色、+8 が属性。8 は U6 のルーン表示の名残）
DRVP = 0xBA66                 # 画面ドライバの構造体への far ポインタ（+6 がフォントの far ポインタ）
SCRP = 0x6EC2                 # 会話スクリプトの置き場所の far ポインタ（先頭 FF <人物の番号>）
SLOT = 0x0D                   # フォント（SYSTEM.LZC の 3 番、128字）の空いている字（日本語の字形を一時的に写す）
WRAP_OFF, WRAP_LEN = 0x2E51, 31                  # 折り返しの「空白か - の直後」を探す部分（2238 の中）
WRAP_VAR = 0xFC                                  # 切る位置の変数 [bp-4]
BUF, LLEN, LDONE = 0xEB1F, 0x1C7D, 0x1C7E        # 1行分の文字、たまった長さ、描いた所まで
HL_OFF, HL_LEN = 0x334E, 35                      # @ の強調の処理（2238 の中）
HL_JMP_TERM, HL_JMP_ZW = 0x2D, 0x32              # 書き換えた後の飛び先（338B = 字を出す、3392 = 終わり）
HL_LIST, LPREFIX, COL_NORMAL = 0x1CAD, 0x1C80, 0x081E
# オーバーレイの書き換え: (ファイルの位置, 照合するバイト列, 書き換える所（照合の先頭から）, 新しい値)
OVL_PATCHES = [(0x4C7FD, bytes.fromhex("807eff807327807eff20"), 3, bytes([0x9C])),   # 2F88:175D 会話の文章の判定
               # 2F83: 仲間になるとき台本の名前を写す所。0x80 以上で止まる（test [si-13A4h],80h / jne）のを
               # 0xF1 で止まる（cmp [si-13A4h],0F1h / je）に変える。日本語の名前（0xA0 以上）を写せるように
               (0x4A163, bytes.fromhex("f6845cec80750a"), 0, bytes.fromhex("80bc5cecf1740a"))]
NAMETAB, NAMELEN, NAME_N, NAME_W = 0x50CE, 0xE0, 16, 14   # 仲間の名前の表（セーブデータ OBJLIST から 0xE0 バイト）
KINSOKU = set("、。，．・：；？！ー～…‥」』）］｝〉》ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々ゝゞヽヾ")
ASC_NOSTART = set(".,!?:;)]}")
SCENE_MAX = 14 * 1024         # 人物ごとの表を読み込む場所の大きさ

# ---- 常駐部の変数（0x103 から）----
V = dict(OLD21=0x103, ORIG=0x107, LEAD=0x10B, LROW=0x10C, LCOL=0x10E, SAVE=0x110,
         WPREV=0x118, WBEST=0x11A, WLAST=0x11C, CURGLY=0x11E, WDESC=0x120, CURNPC=0x122,
         ENTRY=0x124, DESC_G=0x12A, DESC_S=0x136, WSCN=0x142,
         RPOS=0x144, RBUF=0x148, RVALID=0x14C, RCNT=0x150, GDS=0x152,
         BKPOS=0x154, BKW0=0x156, BKID=0x158, MDS=0x15A, SLEAD=0x15C, ORIG2=0x15E)
# 表の説明（12バイト）: +0 組の位置、+2 組の数、+4 トレイルの数、+6 トレイルの表、+8 字形、+10 行頭禁則
CODE = 0x170

# ---- 本・途中の場面（本編が会話スクリプトの置き場所 [0x6EC2] に読んで出す）----
# 文の後ろに 0 FE <表の番号> を付け、場面の表の番号にする（人物は 0x80 未満なので重ならない）
BOOK_ID0 = 0x80               # 本 MDTEXT.LZC の k 番 → 0x80 + k
MID_ID0 = 0xA0                # 途中の場面 MIDGAMEx.LZC → 0xA0 + ファイルの順
MIDGAMES = "123456789ABCD"
SCRIPT_MAX = 0x36B0           # 置き場所の大きさ（0 FE を探す長さ）

# ---- MARTIAN.EXE（導入・キャラクター作成・エンディング。Turbo C++、DGROUP 0x172A）----
# 字幕は SCENETXT.LZC の行を 0526:0055 が ^ で分け、0E7E:000A（折り返しつきの出力）で出す。字は FONTS.LZC の可変幅の字
# （高さ 11、+4 幅、+0x104/+0x204 字形の位置、1 ドット 1 バイトで 0 が透明、0xDC が字の点）
# 常駐部は FONTS.LZC を開いたとき（DX = 0x05C4）に照合してから:
#   - 折り返しの「空白なら切れ目」0E7E:0080 を chkbrk へ（リード 0x81〜0x8F の前でも切る。初めて呼ばれたときにフォントの幅と位置を直す）
#   - 1字描画の far call 4 か所（0E7E:0199/01CA/01F7/0268 → 0EA9:001E）を hook2 へ（トレイルの字形を 0x80 の字の場所に写す）
#   - 字形の表を MDJP.DAT の 0xFF 番から人物ごとの表を読む場所に読む（本編が動いていないので使える）
# 符号: リード 0x80（行頭禁則の字）・0x81〜0x8F × トレイル 0x90〜0xFF（112）
M_DGROUP = 0x172A
M_FONTNAME = 0x05C4
M_WRAP_SEG, M_BRK = 0x0E7E, 0x0080
M_DRAW_SEG, M_DRAW_OFF = 0x0EA9, 0x001E
M_DCS = (0x0199, 0x01CA, 0x01F7, 0x0268)
M_LSTART, M_BRKPOS, M_CTX = 0x1516, 0x1518, 0x14FA
M_SLOT, M_INK = 0x2472, 0xDC
MGLY_ID = 0xFF
M_TRAILS = 112


def fjmp(name):
    a = V[name]
    return f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"


def fcall(name):
    a = V[name]
    return f".byte 0x2e,0xff,0x1e,{a & 0xff},{a >> 8}"


RES = r'''
int21:
    sti
    cmp ah, 0x3f
    je r21
    cmp ah, 0x40
    je w21
    cmp ah, 0x3d
    je o21
c21:
    {JMP_OLD21}

w21:
    cmp dx, {NAMETAB}
    jne c21
    cmp cx, {NAMELEN}
    jne c21
    push ax
    mov ax, ds
    cmp ax, word ptr cs:[{GDS}]
    pop ax
    jne c21
    push bx
    mov bx, 2
    call names_conv
    pop bx
    pushf
    {CALL_OLD21}
    pushf
    push bx
    xor bx, bx
    call names_conv
    pop bx
    popf
    retf 2
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
    cmp dx, {M_FONTNAME}
    je o_fnt
    cmp dx, {NAME_OFF}
    jne o_c21
    push di
    mov di, {NAME_SYS}
    call isname
    pop di
    jne o_c21
    pushf
    {CALL_OLD21}
    jc o_x
    call gpatch
    clc
o_x:
    retf 2
o_c21:
    jmp c21
o_fnt:
    push di
    mov di, {NAME_FNT}
    call isname
    pop di
    jne o_c21
    pushf
    {CALL_OLD21}
    jc o_x
    call mpatch
    clc
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

mpatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push es
    mov ax, ds
    sub ax, {M_DGROUP}
    jb mp_x
    mov bx, ax
    add ax, {M_WRAP_SEG}
    mov es, ax
    cmp word ptr es:[{M_BRK}], 0x203c
    jne mp_x
    cmp word ptr es:[{M_BRK}+2], 0x0475
    jne mp_x
    cmp word ptr es:[{M_BRK}+4], 0x3689
    jne mp_x
    cmp word ptr es:[{M_BRK}+6], {M_BRKPOS}
    jne mp_x
    mov ax, bx
    add ax, {M_DRAW_SEG}
    mov si, {M_DC0}
    call mp_chk
    jne mp_x
    mov si, {M_DC1}
    call mp_chk
    jne mp_x
    mov si, {M_DC2}
    call mp_chk
    jne mp_x
    mov si, {M_DC3}
    call mp_chk
    jne mp_x
    push ax
    push bx
    call mload
    pop bx
    pop ax
    jc mp_x
    mov word ptr cs:[{ORIG2}], {M_DRAW_OFF}
    mov word ptr cs:[{ORIG2}+2], ax
    mov word ptr cs:[{MDS}], ds
    mov byte ptr cs:[{SLEAD}], 0
    mov byte ptr es:[{M_BRK}], 0x9a
    mov word ptr es:[{M_BRK}+1], {CHKBRK}
    mov word ptr es:[{M_BRK}+3], cs
    mov word ptr es:[{M_BRK}+5], 0x9090
    mov byte ptr es:[{M_BRK}+7], 0x90
    mov si, {M_DC0}
    call mp_dc
    mov si, {M_DC1}
    call mp_dc
    mov si, {M_DC2}
    call mp_dc
    mov si, {M_DC3}
    call mp_dc
mp_x:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret
mp_chk:
    cmp byte ptr es:[si], 0x9a
    jne mc_x
    cmp word ptr es:[si+1], {M_DRAW_OFF}
    jne mc_x
    cmp word ptr es:[si+3], ax
mc_x:
    ret
mp_dc:
    mov word ptr es:[si+1], {HOOK2}
    mov word ptr es:[si+3], cs
    ret

mload:
    push ds
    push cs
    pop ds
    mov word ptr [{CURNPC}], 0xffff
    mov ax, 0x3d00
    mov dx, {NAME_DAT}
    pushf
    {CALL_OLD21}
    jc ml_f
    mov bx, ax
    mov dx, {MGLY_POS}
    xor cx, cx
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc ml_c
    mov ah, 0x3f
    mov cx, 6
    mov dx, {ENTRY}
    pushf
    {CALL_OLD21}
    jc ml_c
    cmp ax, 6
    jne ml_c
    mov cx, word ptr [{ENTRY}+4]
    or cx, cx
    jz ml_c
    cmp cx, {SCENE_MAX}
    ja ml_c
    mov dx, word ptr [{ENTRY}]
    mov cx, word ptr [{ENTRY}+2]
    mov ax, 0x4200
    pushf
    {CALL_OLD21}
    jc ml_c
    mov ah, 0x3f
    mov cx, word ptr [{ENTRY}+4]
    mov dx, {SCENE}
    pushf
    {CALL_OLD21}
    jc ml_c
    cmp ax, word ptr [{ENTRY}+4]
    jne ml_c
    mov ah, 0x3e
    pushf
    {CALL_OLD21}
    clc
    pop ds
    ret
ml_c:
    mov ah, 0x3e
    pushf
    {CALL_OLD21}
ml_f:
    stc
    pop ds
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
    cmp al, 0x81
    jb cb_x
    cmp al, 0x8f
    ja cb_x
    cmp si, word ptr [{M_LSTART}]
    je cb_x
cb_set:
    mov word ptr [{M_BRKPOS}], si
cb_x:
    retf

fontpatch:
    cmp byte ptr es:[di+4+0x41], 11
    jne fp_x
    cmp byte ptr es:[di+0x104+0x80], {M_SLOT_LO}
    jne fp_x
    cmp byte ptr es:[di+0x204+0x80], {M_SLOT_HI}
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
    mov byte ptr es:[di+0x104], {M_SLOT_LO}
    mov byte ptr es:[di+0x204], {M_SLOT_HI}
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
    and bl, 0x0f
    xor bh, bh
    sub al, 0x90
    xor ah, ah
    mov si, ax
    mov ax, {M_TRAILS}
    mul bx
    add si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    add si, {SCENE}
    mov bx, word ptr [{M_CTX}]
    les di, dword ptr [bx+6]
    add di, {M_SLOT}
    cld
    xor al, al
    mov cx, 8
    rep stosb
    mov cx, 8
pg_r:
    mov dl, byte ptr cs:[si]
    inc si
    mov dh, 8
pg_c:
    xor al, al
    shl dl, 1
    jnc pg_p
    mov al, {M_INK}
pg_p:
    stosb
    dec dh
    jnz pg_c
    loop pg_r
    xor al, al
    mov cx, 16
    rep stosb
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

r21:
    mov word ptr cs:[{RCNT}], cx
    push ax
    push cx
    push dx
    mov byte ptr cs:[{RVALID}], 0
    mov ax, 0x4201
    xor cx, cx
    xor dx, dx
    pushf
    {CALL_OLD21}
    jc r_0
    mov word ptr cs:[{RPOS}], ax
    mov word ptr cs:[{RPOS}+2], dx
    mov byte ptr cs:[{RVALID}], 1
r_0:
    pop dx
    pop cx
    pop ax
    mov word ptr cs:[{RBUF}], dx
    mov word ptr cs:[{RBUF}+2], ds
    pushf
    {CALL_OLD21}
    jc r_x
    cmp byte ptr cs:[{RVALID}], 0
    je r_ok
    call ovlpatch
r_ok:
    call nmread
    clc
r_x:
    retf 2

nmread:
    cmp ax, {NAMELEN}
    jne nr_x
    cmp word ptr cs:[{RCNT}], {NAMELEN}
    jne nr_x
    cmp word ptr cs:[{RBUF}], {NAMETAB}
    jne nr_x
    push ax
    mov ax, ds
    cmp ax, word ptr cs:[{GDS}]
    pop ax
    jne nr_x
    push bx
    xor bx, bx
    call names_conv
    pop bx
nr_x:
    ret

names_conv:
    push ax
    push cx
    push dx
    push si
    push di
    push es
    push ds
    pop es
    mov dx, {NAMETAB}
    mov cx, {NAME_N}
nc_e:
    mov si, {NAMES}
nc_p:
    cmp word ptr cs:[si], 0
    je nc_n
    push si
    mov si, word ptr cs:[si+bx]
    mov di, dx
nc_c:
    mov al, byte ptr cs:[si]
    cmp al, byte ptr es:[di]
    jne nc_f
    inc si
    inc di
    or al, al
    jnz nc_c
    pop si
    xor bx, 2
    mov si, word ptr cs:[si+bx]
    xor bx, 2
    mov di, dx
nc_k:
    mov al, byte ptr cs:[si]
    mov byte ptr es:[di], al
    inc si
    inc di
    or al, al
    jnz nc_k
    jmp nc_n
nc_f:
    pop si
    add si, 4
    jmp nc_p
nc_n:
    add dx, {NAME_W}
    loop nc_e
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop ax
    ret

ovlpatch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov bp, ax
    push cs
    pop ds
    mov si, {OPATCH}
op_l:
    mov ax, word ptr [si]
    mov dx, word ptr [si+2]
    mov cx, word ptr [si+4]
    or cx, cx
    jz op_x
    sub ax, word ptr [{RPOS}]
    sbb dx, word ptr [{RPOS}+2]
    jc op_n
    or dx, dx
    jnz op_n
    mov bx, ax
    add bx, cx
    jc op_n
    cmp bx, bp
    ja op_n
    les di, dword ptr [{RBUF}]
    add di, ax
    push si
    push di
    add si, 6
    cld
    repe cmpsb
    pop di
    pop si
    jne op_n
    push si
    mov bx, word ptr [si+4]
    add di, word ptr [si+bx+6]
    mov cx, word ptr [si+bx+8]
    lea si, [si+bx+10]
    rep movsb
    pop si
op_n:
    mov bx, word ptr [si+4]
    add bx, word ptr [si+bx+8]
    lea si, [si+bx+10]
    jmp op_l
op_x:
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
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
    mov ax, word ptr [di]
    cmp ax, 0xffff
    je s_x
    add ax, bp
    mov es, ax
    mov si, word ptr [di+2]
    mov cx, word ptr [di+4]
    push di
    call hash
    pop di
    cmp bx, word ptr [di+6]
    jne s_n
    cmp dx, word ptr [di+8]
    jne s_n
    push di
    mov si, word ptr [di+10]
    mov cx, word ptr [di+12]
    mov di, word ptr [di+2]
    cld
    rep movsb
    pop di
s_n:
    add di, 14
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
    push bp
    push ds
    push es
    mov ax, ds
    sub ax, {DGROUP}
    jb g_x
    mov bp, ax
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
    mov word ptr es:[di+7], 0xeb00+{WRAP_VAR}
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
    mov word ptr es:[di+11], 0x0074+{HL_JMP_TERM}*256
    mov word ptr es:[di+13], 0x00eb+{HL_JMP_ZW}*256
    add di, 15
    mov cx, {HL_LEN}-18
    mov al, 0x90
    cld
    rep stosb
g_nohl:
    push cs
    pop ds
    mov di, {STRS}
    call strpatch
g_x:
    pop es
    pop ds
    pop bp
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
    cmp ax, word ptr cs:[{BKID}]
    je es_cmp
es_scan:
    mov di, bx
    mov cx, {SCRIPT_MAX}
    xor al, al
    cld
    repne scasb
    jne es_none
    cmp byte ptr es:[di], 0xfe
    jne es_none
    mov al, byte ptr es:[di+1]
    xor ah, ah
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
    push ax
    push es
    push cs
    pop es
    mov di, {SMAP}+0x100
    mov ax, 0xfffe
    mov cx, {NS_S}
    cld
    rep stosw
    pop es
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
    push es
    push cs
    pop es
    mov si, {SCENE}+8
    mov di, {SMAP}+0x100
    mov cx, {NS_S}
    cld
    rep movsw
    pop es
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
LABELS = ("hook", "wrapbrk", "hlend", "ensure_scene", "draw", "redir", "mpatch", "mload", "chkbrk", "fontpatch", "hook2", "putgly", "isname", "gpatch", "names_conv", "r21")


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


# 本編のデータのセグメント（GAME.EXE のセグメントの表で印 0 のもの）。文字列はこの中で置き換える
DATA_SEGS = [0x2BB4, 0x2DE5, 0x2E08, 0x2E67, 0x2F10, 0x2FAB]
DATA_END = DGROUP * 16 + 0xF378


def find_strings(img, tr, enc):
    """データの中の、前後が 0 の英文を探す: [(セグメント, 位置, 長さ, h1, h2, 中身)]"""
    out = []
    lo = FARDATA * 16
    data = img[lo:DATA_END]
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
            lin = lo + pos + 1
            seg = max(s for s in DATA_SEGS if s * 16 <= lin)
            out.append((seg, lin - seg * 16, n) + h12(img[lin:lin + n]) + (new,))
            hits += 1
            pos += 1
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
    singles = [0xFFFE] * NS_S
    for ch, code in enc.e.single.items():
        singles[code - 0x80] = gidx[ch]
    body_pairs = b"".join(struct.pack("<HH", a, b) for a, b in pairs)
    nost = bytes([0]) + bytes(1 if c in KINSOKU else 0 for c in chars)
    p_pairs = 8 + 2 * NS_S
    p_nost = p_pairs + len(body_pairs)
    p_gly = p_nost + len(nost)
    head = struct.pack("<4H%dH" % NS_S, len(pairs), p_pairs, p_nost, p_gly, *singles)
    return head + body_pairs + nost + gly, len(chars), len(pairs)


LOOK_NAME_MAX = 24     # 名前を写す場所 DS:0xEA32（1B09:4730）は長さを確かめない。英語の一番長い名前の長さまで


def read_look(gamedir, tsv):
    """LOOK.LZC（物の名前）: ([(タイル, 英語の名前 bytes, 訳 or None)], 末尾の残り)"""
    from extract_other import look_entries
    from conv_text import read_tsv
    ja = read_tsv(tsv) if tsv else {}
    ents, rest = look_entries(gamedir)
    out = []
    for tile, name in ents:
        v = ja.get(f"look:{tile:04x}")
        out.append((tile, name, v if v and v != name.decode('latin1') else None))
    return out, rest


def write_look(gamedir, look, genc, outdir):
    """物の名前を常に持つ表の符号にして LOOK.LZC を作る（1項目、圧縮なし、印 0xE0）。
    名前は LOOK_NAME_MAX バイトまで。ファイル全体は元の大きさ以内（作業用の領域 [0x54B2] に読み込まれるため）"""
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
        body += struct.pack("<H", tile) + b + b"\0"
    body += rest
    orig = os.path.getsize(os.path.join(gamedir, "LOOK.LZC"))
    data = struct.pack("<II", 8 + len(body), 8 | (0xE0 << 24)) + bytes(body)
    if len(data) > orig:
        sys.exit(f"LOOK.LZC が元より大きい: {len(data)} > {orig}")
    open(os.path.join(outdir, "LOOK.LZC"), "wb").write(data)
    print(f"LOOK.LZC: 名前 {n} / {len(ents)} を日本語に（{len(data)} バイト、元 {orig}）")


# 本編の文字列で訳してはいけないもの（ロードイメージの位置）: 入力と比べたり、入力の代わりに入れたりする語
KEEP_GAME = {0x3231C,   # "bye"（会話で空の入力をこれに置き換える）
             0x32387}   # "look"（会話で入力と比べる）


def read_game_tsv(paths, img):
    """本編の文字列の訳: {ロードイメージの位置: (英文 bytes, 訳)}。番号 game:XXXXX はロードイメージの位置"""
    from conv_text import read_tsv
    gtr = {}
    for path in paths:
        ja = read_tsv(path)
        en = read_tsv(path.replace("other_ja", "other_en"))
        for k, v in ja.items():
            lin = int(k.split(':')[1], 16)
            if lin in KEEP_GAME:
                continue
            e = en[k].encode('latin1')
            if img[lin:lin + len(e) + 1] != e + b"\0":
                sys.exit(f"{k}: データの中の英文が違う")
            if v != en[k]:
                from conv_text import mark_highlight
                gtr[lin] = (e, mark_highlight(v, lambda m: print("注意:", m), k))
    return gtr


def genc_encode(genc, t):
    """0x7F（閉じの @）で区切って符号にする（組が 0x7F をまたがないように）"""
    return b"\x7f".join(genc.encode(part) for part in t.split("\x7f"))


def party_names(gamedir, ctr, genc):
    """仲間の名前の表の差し替え: [(英語 bytes, 日本語の符号 bytes)]。
    読み込んだ表の英語の名前を日本語に、書き出すときは日本語を英語に戻す（セーブデータは英語のまま）。
    名前は表の 14 バイトに入るよう 13 バイトまで。入らない訳は台本でも英語のままにする（ctr から消す）"""
    from mdtalk import load_items
    out = []
    for k, raw in load_items(os.path.join(gamedir, "TALK.LZC")):
        if raw is None:
            continue
        key = f"T{k:03d}:name"
        if key not in ctr:
            continue
        en = raw[2:raw.index(0xF1)][:NAME_W - 1]
        ja = genc.encode(ctr[key])
        if len(ja) > NAME_W - 1:
            print(f"注意: 名前が長すぎるので英語のまま: {key} {ctr[key]}（{len(ja)} > {NAME_W - 1} バイト）")
            del ctr[key]
            continue
        if ja != en and (en, ja) not in out:
            out.append((en, ja))
    # 日本語 → 英語は最初に合うものを使うので、末尾に _ のない（本来の）名前を先に
    out.sort(key=lambda x: x[0].endswith(b"_"))
    print(f"仲間の名前の差し替え: {len(out)} 組")
    return out


def make_converse(gamedir, ctr, genc, font, outdir, recs):
    """会話の訳を取り込んだ TALK.LZC を outdir に書き、人物ごとの表を recs（番号 → 表）に足す"""
    from conv_text import apply_translation
    from mdtalk import save_talk
    encs = {}

    def make_encoder(pid, npc, texts):
        e = Enc(SCENE, texts)
        encs[npc] = (pid, e, texts)
        return e.encode
    new = apply_translation(gamedir, ctr, make_encoder, encode_name=genc.encode,
                            warn=lambda m: print("注意:", m))
    save_talk(os.path.join(gamedir, "TALK.LZC"), os.path.join(outdir, "TALK.LZC"),
              {k: v for (tag, k), v in new.items()})
    big = []
    gap_total = [0]
    for npc in sorted(encs):
        pid, e, texts = encs[npc]
        assert npc < BOOK_ID0
        rec, nch, npr = scene_record(font, e, texts)
        if len(rec) > SCENE_MAX:
            sys.exit(f"{pid}: 表が大きすぎる {len(rec)} > {SCENE_MAX}")
        recs[npc] = rec
        big.append((npr, pid, nch, len(rec)))
        gap_total[0] += e.gaps(texts)
    big.sort(reverse=True)
    print(f"会話の1マス空く所: {gap_total[0]}")
    print(f"会話の表: {len(encs)} 人。組の多い順 " + "、".join(f"{p} 組 {n}（字 {c}、{b} バイト）" for n, p, c, b in big[:3]))


def write_dat(outdir, recs):
    """MDJP.DAT: 索引 256 × (位置 4、大きさ 2) と、番号ごとの表（人物・本・途中の場面・MARTIAN.EXE の字形）"""
    index = bytearray(256 * 6)
    body = bytearray()
    for k in sorted(recs):
        struct.pack_into("<IH", index, k * 6, len(index) + len(body), len(recs[k]))
        body += recs[k]
    open(os.path.join(outdir, "MDJP.DAT"), "wb").write(bytes(index + body))
    print(f"MDJP.DAT: 表 {len(recs)}、{len(index) + len(body)} バイト")


def crlf(t):
    return t.replace("\r\n", "\n").replace("\n", "\r\n")


def make_books(gamedir, tsv, font, outdir, recs):
    """本 MDTEXT.LZC: 1冊ごとの場面の表で符号にし、後ろに 0 FE <番号> を付けて outdir/MDTEXT.LZC に（全部日本語のファイル）"""
    import mdfmt
    from conv_text import read_tsv, mark_highlight
    ja = read_tsv(tsv)
    items = mdfmt.raw_items(open(os.path.join(gamedir, "MDTEXT.LZC"), "rb").read())
    out = []
    nj = 0
    for k, (flag, raw) in enumerate(items):
        v = ja.get(f"mdtext:{k:02d}")
        if raw is None or v is None:
            out.append((flag, raw))
            continue
        assert flag == 0xE0 and BOOK_ID0 + k < MID_ID0
        v = crlf(mark_highlight(v, lambda m: print("注意:", m), f"mdtext:{k:02d}"))
        enc = Enc(SCENE, [v])
        b = enc.encode(v)
        assert 0 not in b
        rec, nch, npr = scene_record(font, enc, [v])
        if len(rec) > SCENE_MAX or len(b) + 3 > SCRIPT_MAX:
            sys.exit(f"本 {k}: 大きすぎる")
        recs[BOOK_ID0 + k] = rec
        out.append((0xE0, b + bytes([0, 0xFE, BOOK_ID0 + k])))
        nj += 1
    data = mdfmt.pack(out)
    open(os.path.join(outdir, "MDTEXT.LZC"), "wb").write(data)
    print(f"MDTEXT.LZC: 本 {nj} / {len(items)} を日本語に（{len(data)} バイト）")


def make_midgames(gamedir, tsv, font, outdir, recs):
    """途中の場面 MIDGAMEx.LZC: 文の項目だけ場面の表の符号にして差し替える（絵の項目はそのまま）。表はファイルごとに1つ"""
    import mdfmt
    from conv_text import read_tsv
    ja = read_tsv(tsv)
    for fi, c in enumerate(MIDGAMES):
        name = f"MIDGAME{c}.LZC"
        items = mdfmt.raw_items(open(os.path.join(gamedir, name), "rb").read())
        texts = {k: crlf(ja[f"midgame{c}:{k:02d}"]) for k in range(len(items)) if f"midgame{c}:{k:02d}" in ja}
        if not texts:
            continue
        tid = MID_ID0 + fi
        assert tid < MGLY_ID
        enc = Enc(SCENE, list(texts.values()))
        out = []
        for k, (flag, raw) in enumerate(items):
            if k in texts:
                assert flag == 0xE0 and "%" not in texts[k]
                b = enc.encode(texts[k])
                assert 0 not in b
                out.append((0xE0, b + bytes([0, 0xFE, tid])))
            else:
                out.append((flag, raw))
        rec, nch, npr = scene_record(font, enc, list(texts.values()))
        recs[tid] = rec
        open(os.path.join(outdir, name), "wb").write(mdfmt.pack(out))
    print(f"MIDGAME*.LZC: {len(MIDGAMES)} ファイルの文を日本語に")


def martian_codes(texts):
    """MARTIAN.EXE の符号: {字: 2バイト}、字形の表（(リード-0x80)*112 + (トレイル-0x90) 番、8 バイトずつ）"""
    chars = sorted({c for t in texts for c in t if ord(c) > 0x7E})
    kin = [c for c in chars if c in KINSOKU]
    oth = [c for c in chars if c not in KINSOKU]
    if len(kin) > M_TRAILS or len(oth) > 15 * M_TRAILS:
        sys.exit("MARTIAN.EXE の字が多すぎる")
    code = {}
    for i, c in enumerate(kin):
        code[c] = (0, i)
    for i, c in enumerate(oth):
        code[c] = (1 + i // M_TRAILS, i % M_TRAILS)
    return code


def make_scenetxt(gamedir, tsv, font, outdir, recs):
    """導入・エンディングの字幕 SCENETXT.LZC: 行ごとに訳を入れ、MARTIAN.EXE の符号で LZW に詰めて outdir に。字形の表は recs[0xFF]"""
    import mdfmt
    from conv_text import read_tsv
    ja = read_tsv(tsv)
    items = mdfmt.raw_items(open(os.path.join(gamedir, "SCENETXT.LZC"), "rb").read())
    # 日本語の行の英数字（答えのキー A) など）は全角に（元の字は太く大きいので）。$P はそのまま
    ja = {k: re.sub(r"(?<!\$)[0-9A-Z()]", lambda m: chr(ord(m.group()) + 0xFEE0), v) if any(ord(c) > 0x7E for c in v) else v
          for k, v in ja.items()}
    code = martian_codes(list(ja.values()))
    n = max([l * M_TRAILS + t for l, t in code.values()] + [0]) + 1
    gly = bytearray(8 * n)
    for c, (l, t) in code.items():
        g = font.get(ord(c))
        if g is None:
            sys.exit(f"美咲フォントに字がありません: {c}")
        gly[8 * (l * M_TRAILS + t):8 * (l * M_TRAILS + t) + 8] = g
    if len(gly) > SCENE_MAX:
        sys.exit("MARTIAN.EXE の字形の表が大きすぎる")
    recs[MGLY_ID] = bytes(gly)

    def encode(t):
        out = bytearray()
        for c in t:
            if ord(c) <= 0x7E:
                out.append(ord(c))
            else:
                l, tr = code[c]
                out += bytes([0x80 + l, 0x90 + tr])
        return bytes(out)
    out = []
    longest = (0, 0)
    for k, (flag, raw) in enumerate(items):
        dec = mdfmt.item(0, flag, raw)
        lines = dec.split(b"\r\n")
        for j, line in enumerate(lines):
            v = ja.get(f"scene:{k}:{j:02d}")
            if v is not None:
                lines[j] = encode(v)
            longest = max(longest, (len(lines[j]), max(len(x) for x in dec.split(b"\r\n"))))
        out.append((0xE0, b"\r\n".join(lines)))      # 圧縮なし（パッチで元の行を写せるように）
    data = mdfmt.pack(out)
    open(os.path.join(outdir, "SCENETXT.LZC"), "wb").write(data)
    print(f"SCENETXT.LZC: 字 {len(code)}、字形の表 {len(gly)} バイト、一番長い行 {longest[0]} バイト（英語は {longest[1]}）")


def main(gamedir, trfile, out):
    exe = open(os.path.join(gamedir, "GAME.EXE"), "rb").read()
    assert exe[FBOV:FBOV + 4] == b"FBOV"
    img = exe[EXE_HDR:FBOV]
    data = img[DGROUP * 16:]
    assert data[NAME_OFF:NAME_OFF + 11] == b"system.lzc\0"
    assert struct.unpack_from("<2H", data, PTR_PUTC) == (PUTC_OFF, PUTC_SEG)
    putc = PUTC_SEG * 16 + PUTC_OFF
    assert img[putc + PUTC_LEN - 3:putc + PUTC_LEN] == bytes.fromhex("ca0600")
    chk = h12(img[putc:putc + PUTC_LEN])
    wrap = PUTC_SEG * 16 + WRAP_OFF
    assert img[wrap:wrap + 2] == bytes.fromhex("eb03")
    assert img[wrap + WRAP_LEN:wrap + WRAP_LEN + 4] == bytes([0x83, 0x7E, WRAP_VAR, 0x00])
    wchk = h12(img[wrap:wrap + WRAP_LEN])
    if os.environ.get("MDJP_NOWRAP"):
        wchk = (wchk[0] ^ 1, wchk[1])
    for fo, chkb, po, val in OVL_PATCHES:
        assert exe[fo:fo + len(chkb)] == chkb and po + len(val) <= len(chkb)
    # 仲間の名前の表を読み書きする所（2238:06B9 読み込み、2238:0E51 書き出し）が 0xE0 バイトを DS:50CE に
    for lin in (0x22A39, 0x231D1):
        assert img[lin:lin + 9] == bytes.fromhex("ba" + NAMELEN.to_bytes(2, "little").hex() + "50521eb8") + NAMETAB.to_bytes(2, "little")
    hl = PUTC_SEG * 16 + HL_OFF
    assert img[hl:hl + HL_LEN] == bytes.fromhex(
        "ff7606b8ad1c509a6919000059590bc07411c606801c008b1edb1ba01e08884706eb1a")
    # 2238:3358 の far call のセグメント（2バイト）は読み込み位置で足し直されるので、照合から外す
    hchk = h12(img[hl:hl + 10])
    hchk2 = h12(img[hl + 12:hl + HL_LEN])
    tr = read_translation(trfile)
    font = load_bdf(BDF)

    ctr = {}
    if os.environ.get("MDJP_CONVTEST"):
        from conv_text import read_tsv
        for path in os.environ["MDJP_CONVTEST"].split(os.pathsep):
            ctr.update(read_tsv(path))
    names = [v for k, v in ctr.items() if k.endswith(':name')]
    # 本編の文字列の訳（番号 = ロードイメージの位置）: MDJP_GAMETSV=translation/other_ja/game.tsv
    gtr = read_game_tsv(os.environ["MDJP_GAMETSV"].split(os.pathsep), img) if os.environ.get("MDJP_GAMETSV") else {}
    look = read_look(gamedir, os.environ.get("MDJP_LOOKTSV"))
    gtexts = list(tr.values()) + names + [p for _, v in gtr.values() for p in v.split("\x7f")] + [ja for _, _, ja in look[0] if ja]
    # 1バイトの字は、組が入りきる範囲でなるべく多くとる（多いほうから試し、全部の文が元の長さに収まる最初の数）
    global GLOBAL
    best = None
    cands = [_GS] if os.environ.get("MDJP_GSINGLES") else list(range(88, 39, -4))
    for ns in cands:
        cs = CodeSet(NO_F1[:ns], NO_F1[ns:], GLOBAL.trails)
        genc = Enc(cs, gtexts, smart=True)
        try:
            for t in gtexts:
                genc.encode(t)
            over = [lin for lin, (e, v) in gtr.items() if len(genc_encode(genc, v)) > len(e)]
            over += [t for t, n, ja in look[0] if ja and len(genc.encode(ja)) > LOOK_NAME_MAX]
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
    strs = find_strings(img, tr, genc)
    done = {s[0] * 16 + s[1] for s in strs}
    for lin, (e, v) in sorted(gtr.items()):
        if lin in done:
            continue
        new = genc_encode(genc, v) + b"\0"
        if len(new) > len(e) + 1:
            print(f"注意: 本編の文字列が長すぎるので英語のまま: game:{lin:05x} {v!r}（{len(new) - 1} > {len(e)} バイト）")
            continue
        seg = max(x for x in DATA_SEGS if x * 16 <= lin)
        strs.append((seg, lin - seg * 16, len(e)) + h12(img[lin:lin + len(e)]) + (new,))
    print(f"本編の文字列の置き換え: {len(strs)} か所")
    if os.environ.get("MDJP_LOOKTSV"):
        write_look(gamedir, look, genc, os.environ.get("MDJP_CONVOUT", "."))
    party = party_names(gamedir, ctr, genc)
    outdir = os.environ.get("MDJP_CONVOUT", ".")
    recs = {}
    if ctr:
        make_converse(gamedir, ctr, genc, font, outdir, recs)
    if os.environ.get("MDJP_BOOKTSV"):
        make_books(gamedir, os.environ["MDJP_BOOKTSV"], font, outdir, recs)
    if os.environ.get("MDJP_MIDTSV"):
        make_midgames(gamedir, os.environ["MDJP_MIDTSV"], font, outdir, recs)
    if os.environ.get("MDJP_SCENETSV"):
        make_scenetxt(gamedir, os.environ["MDJP_SCENETSV"], font, outdir, recs)
    if recs:
        write_dat(outdir, recs)
    # MARTIAN.EXE の照合する所
    mx = open(os.path.join(gamedir, "MARTIAN.EXE"), "rb").read()
    mimg = mx[struct.unpack_from("<H", mx, 8)[0] * 16:]
    assert mimg[M_DGROUP * 16 + M_FONTNAME:M_DGROUP * 16 + M_FONTNAME + 10] == b"fonts.lzc\0"
    assert mimg[M_WRAP_SEG * 16 + M_BRK:M_WRAP_SEG * 16 + M_BRK + 8] == bytes.fromhex("3c2075048936") + M_BRKPOS.to_bytes(2, "little")
    for dc in M_DCS:
        assert mimg[M_WRAP_SEG * 16 + dc:M_WRAP_SEG * 16 + dc + 5] == b"\x9a" + struct.pack("<HH", M_DRAW_OFF, M_DRAW_SEG)

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
        start = base + 14 * len(ss) + 2
        for seg, off, n, a, b, new in ss:
            tab += struct.pack("<7H", seg, off, n, a, b, start + len(body), len(new))
            body += new
        return bytes(tab + b"\xff\xff" + body)

    # オーバーレイの書き換えの表: 位置 4、照合の長さ 2、照合のバイト列、書き換える所 2、新しい値 1。照合の長さ 0 で終わり
    opatch = b"".join(struct.pack("<IH", fo, len(c)) + c + struct.pack("<HH", po, len(v)) + v for fo, c, po, v in OVL_PATCHES)
    opatch += bytes(6)

    def build(addr):
        kw = dict(V, DGROUP=DGROUP, NAME_OFF=NAME_OFF, PUTC_SEG=PUTC_SEG, PUTC_OFF=PUTC_OFF,
                  PUTC_LEN=PUTC_LEN, PTR_PUTC=PTR_PUTC, WIN=WIN, DRVP=DRVP, SLOT=SLOT, SCRP=SCRP,
                  CHK_H1=chk[0], CHK_H2=chk[1],
                  WRAP_OFF=WRAP_OFF, WRAP_LEN=WRAP_LEN, WCHK_H1=wchk[0], WCHK_H2=wchk[1],
                  BUF=BUF, LLEN=LLEN, LDONE=LDONE, WRAP_VAR=WRAP_VAR, HL_JMP_TERM=HL_JMP_TERM, HL_JMP_ZW=HL_JMP_ZW,
                  HL_OFF=HL_OFF, HL_LEN=HL_LEN, HCHK_H1=hchk[0], HCHK_H2=hchk[1],
                  HCHK2_H1=hchk2[0], HCHK2_H2=hchk2[1], HL_LIST=HL_LIST, LPREFIX=LPREFIX, COL_NORMAL=COL_NORMAL,
                  SCENE_MAX=SCENE_MAX, NS_S=NS_S, NAMETAB=NAMETAB, NAMELEN=NAMELEN, NAME_N=NAME_N, NAME_W=NAME_W,
                  SCRIPT_MAX=SCRIPT_MAX, M_DGROUP=M_DGROUP, M_FONTNAME=M_FONTNAME, M_WRAP_SEG=M_WRAP_SEG, M_BRK=M_BRK,
                  M_DRAW_SEG=M_DRAW_SEG, M_DRAW_OFF=M_DRAW_OFF, M_DC0=M_DCS[0], M_DC1=M_DCS[1], M_DC2=M_DCS[2], M_DC3=M_DCS[3],
                  M_LSTART=M_LSTART, M_BRKPOS=M_BRKPOS, M_CTX=M_CTX, M_SLOT=M_SLOT, M_SLOT_LO=M_SLOT & 0xFF,
                  M_SLOT_HI=M_SLOT >> 8, M_INK=M_INK, M_TRAILS=M_TRAILS, MGLY_POS=MGLY_ID * 6,
                  JMP_ORIG2=fjmp("ORIG2"),
                  JMP_OLD21=fjmp("OLD21"), CALL_OLD21=fcall("OLD21"),
                  JMP_ORIG=fjmp("ORIG"), CALL_ORIG=fcall("ORIG"), **addr)
        code = asm(RES, CODE, kw)

        def label(name):
            src = RES.split("\n" + name + ":")[0]
            later = [x for x in LABELS if "\n" + x + ":" not in src]
            return CODE + len(asm(src + "".join(f"\n{x}:" for x in later) + "\n", CODE, kw))
        lay = {"HOOK": label("hook"), "WRAPBRK": label("wrapbrk"), "HLEND": label("hlend"),
               "CHKBRK": label("chkbrk"), "HOOK2": label("hook2")}
        p = CODE + len(code)
        tail = bytearray()

        def put(name, d):
            lay[name] = p + len(tail)
            tail.extend(d)
        put("NAME_SYS", b"SYSTEM.LZC\0")
        put("NAME_DAT", b"MDJP.DAT\0")
        put("NAME_FNT", b"FONTS.LZC\0")
        # 開くときに日本語版 *.LZJ に読み替える名前（13 バイトずつ、0 で終わり）
        put("RLIST", b"".join(n.ljust(13, bytes([0])) for n in
                              [b"TALK.LZC", b"LOOK.LZC", b"MDTEXT.LZC", b"SCENETXT.LZC"] +
                              [b"MIDGAME%s.LZC" % c.encode() for c in MIDGAMES]) + bytes([0]))
        put("RNAME", bytes(14))
        put("OPATCH", opatch)
        nbase = p + len(tail)
        nhead = 4 * len(party) + 2
        nbody = bytearray()
        ntab = bytearray()
        for en, ja in party:
            ntab += struct.pack("<HH", nbase + nhead + len(nbody), nbase + nhead + len(nbody) + len(en) + 1)
            nbody += en + b"\0" + ja + b"\0"
        put("NAMES", bytes(ntab) + b"\0\0" + bytes(nbody))
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

    keys = ["HOOK", "WRAPBRK", "HLEND", "CHKBRK", "HOOK2", "NAME_SYS", "NAME_DAT", "NAME_FNT", "RLIST", "RNAME", "OPATCH", "NAMES", "SMAP", "LIDX", "TIDX_G", "TIDX_S",
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
    msg = "MDJP: 日本語化（試作）を組み込みました\r\n$".encode("cp932")
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
