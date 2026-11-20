# ウルティマV 用の常駐プログラム U5JP.COM を作る（試作）
#   - ゲームが DATA.OVL を開いたとき、ULTIMA.EXE の1文字関数の入口（イメージ内 0x16BA）を
#     常駐部への far call に書き換える。中継（call 0x16BA; retf）は Phoenix の著作権表示の場所に置く
#   - 1文字関数の横取り: 日本語の字（2バイトか3バイト）を美咲フォントで描く
#       字形を ES=[0x5398] のフォント表の SLOT 番に写し、引数を SLOT に変えて元の処理を続ける
#   - DATA.OVL を読み込んだ直後に、文字列を日本語に置き換える
#       元の長さに収まらない訳は、3バイトの「長い訳の印」に置き換え、常駐部の中の訳を中継で1文字ずつ書く
# 使い方: python build_u5jp.py <訳のファイル> <出力 U5JP.COM>
#   訳のファイル: 「DATA.OVL の位置（16進）<TAB>訳」。\n は改行。# で始まる行は注釈
#
# 文字の符号（ゲームの中では下位7ビットで判断する。会話は最上位ビットを消されてから来るため）
#   2バイト: リード LEAD2（7種）＋トレイル TRAIL（84種）→ よく使う 588 字
#   3バイト: リード LEAD3 ＋トレイル＋トレイル → 番号 STRBASE 未満は残りの字、以上は常駐部の中の長い訳
#   0x00〜0x1F と 0x7B〜0x7F は枠や矢印の字形なので使わない
#   店の文章が置き換えに使う # $ % & * @ ^ や、物語の { _、会話の ~ はトレイルにも使わない
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jpenc import load_bdf, fix16  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

LEAD2 = "+<=>[\\]"
LEAD3 = "`"
SPECIAL = set("#$%&*@^_{~")
TRAIL = [c for c in range(0x21, 0x7F) if chr(c) not in SPECIAL]
NT = len(TRAIL)
N2 = len(LEAD2) * NT
STRBASE = 5000                   # 3バイトの番号のうち、これ以上は長い訳
NOTEXT = set(LEAD2) | set(LEAD3) | set("{|}~\x7f")   # 訳の中に英数字として書けない字
SLOT = 0x5C                      # 字形を写すフォント表の番号（'\' はリードなので、そのままでは描かれない）

PUTC = 0x16BA                    # 1文字関数の入口（イメージ内）
PUTC_SIG = bytes.fromhex("558bec56571e8b7e0481e7ff00")
STRLEN = 0x216C                  # 本体の strlen（中央そろえと名前の長さの判定だけに使われている）
STRLEN_SIG = bytes.fromhex("558bec83ec02562bc98b7604")
# タイトルのメニュー: DATA.OVL の項目の文字列 → INTRO.OVL の中の、その項目の桁（mov ax,桁 の即値）の位置
# 英語の桁は 20 - (幅 + 2) // 2 で決まっている
MENU_COLS = {0x311C: 0x6C6, 0x312B: 0x6D8, 0x3140: 0x6EA, 0x3158: 0x6FC, 0x316E: 0x70E, 0x317F: 0x720}
GADGET = 0x251C                  # 本体にもとからある retf（pop bp; retf の retf）。常駐部から1文字関数を呼ぶときの戻り先
THUNK_SIG = bytes.fromhex("5e8be55dcb")   # GADGET で終わる5バイト
FONTSEG = 0x5398                 # DS:[0x5398] = フォント表のセグメント
WINPTR = 0x539A                  # DS:[0x539A] = いまの窓（+4 桁、+5 行）
DRVENT = 0x5350                  # DS:[0x5350] = 表示ドライバの far ポインタ（入口の番号を書いてから call far）
# 可変幅の文章（FONT.OVL）が使う DS の変数
GAMEVARS = dict(WTAB=0x50CA,     # 字の幅の表（0x20〜0x7B）
                PLEFT=0x5146, PRIGHT=0x514C,   # 左右の余白（2組。絵の横は2番目）
                PY0=0x5150, PY1=0x5152,        # 2番目の余白を使う y の範囲
                PSPACE=0x5154, PX=0x5156, PY=0x5158)
FONT_SIG = bytes.fromhex("558bec83ec1c")
PUTS = 0x1850                    # 本体の「文字列を窓に書く」関数（単語の折り返しをバイト数で数える）
PUTS_SIG = bytes.fromhex("558bec83ec42")   # FONT.OVL の先頭（文字を並べる関数）
DAT_BUF = 2000                   # 物語などは 1 文字列ずつ 2000 バイト読まれる（DS:0xB21E）
DAT_BUF_OF = {"SHOPPE.DAT": 1500}   # 店の文章は 1500 バイト（SHOPPES.OVL）
# 1 回の読み込みで、いくつもの文字列を読んで中を番号で引くもの: (元の位置, バイト数)
# その範囲に始まっていた文字列は、日本語版でも同じ読み込みの範囲に収まっていなければならない
DAT_WINDOWS = {"MISCMSG.DAT": [(0, 1000), (939, 2000)],   # BLCKTHRN.OVL、CAST2.OVL
               "ENDMSG.DAT": [(0, 1000)]}                  # ENDGAME.OVL

FAR_JMP = lambda a: f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"
FAR_CALL = lambda a: f".byte 0x2e,0xff,0x1e,{a & 0xff},{a >> 8}"

# ---- 常駐部の変数（0x103 から）----
V = {}
_p = 0x103
for name, size in [("OLD21", 4), ("THUNK", 4), ("RETIP", 2), ("RETCS", 2), ("POS", 2),
                   ("ST", 1), ("LEAD", 1), ("T1", 1), ("E1", 1), ("NGLYPHV", 2), ("NSTRV", 2),
                   ("OPENAX", 2), ("CURENT", 2), ("CURPL", 2), ("LASTJP", 1), ("EXEOK", 1), ("JPWIN", 2), ("JPPOS", 2),
                   ("SRETIP", 2), ("SRETCS", 2), ("FRETIP", 2), ("FRETCS", 2), ("PRETIP", 2), ("PRETCS", 2), ("NAMEBUF", 80)]:
    V[name] = _p
    _p += size
CODE = (_p + 15) & ~15

RES = r'''
int21:
    cmp ah, 0x3d
    je do_open
    cmp ah, 0x3f
    je do_read
    cmp ah, 0x42
    je do_seek
    cmp ah, 0x3e
    je do_close
chain:
    {jmp_old}

; 表の項目: +0 名前の長さ, +1 名前(12), +13 ハンドル, +15 置き換えの表か位置の対応表（17 バイト）
; CS:SI の表から、ハンドルが BX の項目を探す。見つかれば ZF=1（SI=項目）
findh:
    cmp byte ptr cs:[si], 0
    je fh_no
    cmp bx, word ptr cs:[si+13]
    je fh_ret
    add si, 17
    jmp findh
fh_no:
    cmp si, 0
fh_ret:
    ret

; CS:SI の表で、ハンドルが BX の項目を空にする
clrh:
    cmp byte ptr cs:[si], 0
    je ch_ret
    cmp bx, word ptr cs:[si+13]
    jne ch_next
    mov word ptr cs:[si+13], 0xffff
ch_next:
    add si, 17
    jmp clrh
ch_ret:
    ret

do_close:
    push si
    mov si, {PFILES}
    call clrh
    mov si, {RFILES}
    call clrh
    pop si
    jmp chain

; 差し替えたファイルの位置の指定（先頭から）: 元の文字列の位置なら、日本語版の位置に読み替える
do_seek:
    cmp al, 0
    jne chain
    push si
    mov si, {RFILES}
    call findh
    jne sk_out
    mov si, word ptr cs:[si+15]
    or si, si
    je sk_out
    or cx, cx
    jne sk_out
sk_loop:
    cmp word ptr cs:[si], 0xffff
    je sk_out
    cmp dx, word ptr cs:[si]
    je sk_hit
    add si, 4
    jmp sk_loop
sk_hit:
    mov dx, word ptr cs:[si+2]
sk_out:
    pop si
    jmp chain

do_open:
    mov word ptr cs:[{OPENAX}], ax
    mov word ptr cs:[{CURENT}], 0
    push bx
    push cx
    push si
    push di
    mov si, dx
o_end:
    cmp byte ptr [si], 0
    je o_got
    inc si
    jmp o_end
o_got:
    mov bx, si
    cmp byte ptr cs:[{EXEOK}], 0
    je or_none
    mov di, {RFILES}
or_loop:
    cmp byte ptr cs:[di], 0
    je or_none
    call tailcmp
    je or_hit
    add di, 17
    jmp or_loop
or_hit:
    mov word ptr cs:[{CURENT}], di
    pop di
    pop si
    pop cx
    pop bx
    jmp o_redir
or_none:
    mov di, {PFILES}
op_loop:
    cmp byte ptr cs:[di], 0
    je op_none
    call tailcmp
    je op_hit
    add di, 17
    jmp op_loop
op_hit:
    mov word ptr cs:[{CURENT}], di
op_none:
    pop di
    pop si
    pop cx
    pop bx
o_normal:
    mov ax, word ptr cs:[{OPENAX}]
    pushf
    {call_old}
    jc o_ret
    push si
    mov si, word ptr cs:[{CURENT}]
    or si, si
    je o_r2
    mov word ptr cs:[si+13], ax
    cmp si, {PFILES}
    jne o_r2
    call patch_exe
o_r2:
    pop si
    clc
o_ret:
    sti
    retf 2
; 差し替え: 名前の最後の字を J にした写しを開く。なければ元の名前で開く
o_redir:
    push si
    push di
    push es
    push cs
    pop es
    mov si, dx
    mov di, {NAMEBUF}
    cld
o_cp:
    lodsb
    stosb
    or al, al
    jne o_cp
    mov byte ptr cs:[di-2], 0x4a
    pop es
    pop di
    pop si
    push ds
    push dx
    push cs
    pop ds
    mov dx, {NAMEBUF}
    mov ax, word ptr cs:[{OPENAX}]
    pushf
    {call_old}
    pop dx
    pop ds
    jc o_fallback
    push si
    mov si, word ptr cs:[{CURENT}]
    mov word ptr cs:[si+13], ax
    pop si
    clc
    jmp o_ret
o_fallback:
    mov word ptr cs:[{CURENT}], 0
    jmp o_normal

; 名前（DS:DX〜BX）の終わりが CS:DI の項目の名前と同じか。同じなら ZF=1
tailcmp:
    push cx
    push si
    push di
    mov cl, byte ptr cs:[di]
    xor ch, ch
    mov si, bx
    sub si, cx
    cmp si, dx
    jb tc_ne
    inc di
    call cmpname
    jmp tc_out
tc_ne:
    cmp si, 0xffff
tc_out:
    pop di
    pop si
    pop cx
    ret

; DS:SI（大文字にして）と CS:DI を CX バイト比べる。同じなら ZF=1
cmpname:
    mov al, byte ptr [si]
    cmp al, 0x61
    jb c_up
    cmp al, 0x7a
    ja c_up
    sub al, 0x20
c_up:
    cmp al, byte ptr cs:[di]
    jne c_ret
    inc si
    inc di
    loop cmpname
    cmp al, al
c_ret:
    ret

do_read:
    cmp byte ptr cs:[{EXEOK}], 0
    je chain
    push si
    mov si, {PFILES}
    call findh
    jne rd_no
    mov si, word ptr cs:[si+15]
    mov word ptr cs:[{CURPL}], si
    pop si
    push ax
    push cx
    push dx
    mov ax, 0x4201
    xor cx, cx
    xor dx, dx
    pushf
    {call_old}
    mov word ptr cs:[{POS}], ax
    pop dx
    pop cx
    pop ax
    pushf
    {call_old}
    jc r_ret
    call apply
    cmp word ptr cs:[{CURPL}], {PATCHF}
    jne r_ok
    call patch_font
r_ok:
    clc
r_ret:
    sti
    retf 2
rd_no:
    pop si
    jmp chain

; FONT.OVL の先頭（文字を並べる関数）を、常駐部の jlay への far call にする（読んだのが先頭からで、照合が合うときだけ）
patch_font:
    cmp word ptr cs:[{POS}], 0
    jne pf_ret
    cmp ax, 6
    jb pf_ret
    push ax
    push cx
    push si
    push di
    push es
    push ds
    pop es
    mov di, dx
    push di
    mov si, {FSIG}
    mov cx, 6
    call hcmp
    pop di
    jne pf_out
    mov al, 0x9a
    stosb
    mov ax, {JLAY}
    stosw
    mov ax, cs
    stosw
    mov al, 0x90
    stosb
pf_out:
    pop es
    pop di
    pop si
    pop cx
    pop ax
pf_ret:
    ret

; 読み込んだ DS:DX（AX バイト、ファイルの位置 [POS]）に置き換えを当てる
apply:
    push ax
    push bx
    push cx
    push si
    push di
    push es
    push ds
    pop es
    mov bx, ax
    add bx, word ptr cs:[{POS}]
    mov si, word ptr cs:[{CURPL}]
a_next:
    mov ax, word ptr cs:[si]
    cmp ax, 0xffff
    je a_done
    mov cx, word ptr cs:[si+2]
    add si, 4
    cmp ax, word ptr cs:[{POS}]
    jb a_skip
    push ax
    add ax, cx
    cmp ax, bx
    pop ax
    ja a_skip
    sub ax, word ptr cs:[{POS}]
    add ax, dx
    mov di, ax
    push ds
    push cs
    pop ds
    cld
    rep movsb
    pop ds
    jmp a_next
a_skip:
    add si, cx
    jmp a_next
a_done:
    pop es
    pop di
    pop si
    pop cx
    pop bx
    pop ax
    ret

; ES:DI から CX バイトのハッシュ（h1 = rol(h1,1)+b、h2 = rol(h2+b,3)）を、CS:SI の h1, h2 と比べる。同じなら ZF=1
; 原作のバイト列を常駐部に持たないため（DI と CX は進む。AX, BX は壊す）
hcmp:
    push bx
    push dx
    xor bx, bx
    xor dx, dx
hc_loop:
    mov al, byte ptr es:[di]
    inc di
    xor ah, ah
    rol bx, 1
    add bx, ax
    add dx, ax
    rol dx, 1
    rol dx, 1
    rol dx, 1
    loop hc_loop
    cmp bx, word ptr cs:[si]
    jne hc_ret
    cmp dx, word ptr cs:[si+2]
hc_ret:
    pop dx
    pop bx
    ret

; ゲームの1文字関数を書き換える（照合が合うときだけ）
patch_exe:
    push ax
    push bx
    push cx
    push si
    push di
    push ds
    push es
    mov ah, 0x62
    pushf
    {call_old}
    add bx, 0x10
    mov es, bx
    push cs
    pop ds
    mov si, {PSIG}
    mov di, {PUTC}
    mov cx, {PSIGLEN}
    call hcmp
    jne p_done
    mov si, {TSIG}
    mov di, {GADGET} - {TSIGLEN} + 1
    mov cx, {TSIGLEN}
    call hcmp
    jne p_done
    mov si, {SSIG}
    mov di, {STRLEN}
    mov cx, {SSIGLEN}
    call hcmp
    jne p_done
    mov si, {USIG}
    mov di, {PUTS}
    mov cx, 6
    call hcmp
    jne p_done
    mov di, {PUTS}
    mov al, 0x9a
    stosb
    mov ax, {JPUTS}
    stosw
    mov ax, cs
    stosw
    mov al, 0x90
    stosb
    mov di, {STRLEN}
    mov al, 0x9a
    stosb
    mov ax, {SLEN}
    stosw
    mov ax, cs
    stosw
    mov word ptr cs:[{THUNK}], {PUTC}
    mov word ptr cs:[{THUNK}+2], es
    mov byte ptr cs:[{ST}], 0
    mov di, {PUTC}
    mov al, 0x9a
    stosb
    mov ax, {HOOK}
    stosw
    mov ax, cs
    stosw
    mov byte ptr cs:[{EXEOK}], 1
p_done:
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop bx
    pop ax
    ret

; 1文字関数の入口から far call で来る。[bp+2]=戻りIP [bp+4]=CS [bp+6]=呼び出し元 [bp+8]=文字
hook:
    push bp
    mov bp, sp
    push ax
    push bx
    mov al, byte ptr [bp+8]
    cmp al, 0xfb
    jae h_reset
    and al, 0x7f
    mov bl, byte ptr cs:[{ST}]
    or bl, bl
    jne h_state
    cmp al, 0x20
    jne h_notsp
    cmp byte ptr cs:[{LASTJP}], 0
    je h_notsp
    mov bx, word ptr [{WINPTR}]
    cmp bx, word ptr cs:[{JPWIN}]
    jne h_notsp
    mov bx, word ptr [bx+4]
    cmp bx, word ptr cs:[{JPPOS}]
    je h_swallow
h_notsp:
    mov bl, al
    xor bh, bh
    mov bl, byte ptr cs:[bx+{LEADTAB}]
    or bl, bl
    je h_ascii
    mov byte ptr cs:[{LEAD}], bl
    mov byte ptr cs:[{ST}], 1
    cmp bl, 0x80
    jne h_swallow
    mov byte ptr cs:[{ST}], 2
    jmp h_swallow
h_state:
    push cx
    mov cl, bl
    mov bl, al
    xor bh, bh
    mov bl, byte ptr cs:[bx+{TRTAB}]
    mov byte ptr cs:[{ST}], 0
    cmp bl, 0xff
    je h_bad
    cmp cl, 1
    je h_st1
    cmp cl, 2
    je h_st2
    mov al, byte ptr cs:[{T1}]
    mov ah, {NT}
    mul ah
    add ax, bx
    cmp ax, {STRBASE}
    jae h_isstr
    add ax, {N2}
    jmp h_draw
h_isstr:
    sub ax, {STRBASE}
    pop cx
    jmp h_print
h_st1:
    mov al, byte ptr cs:[{LEAD}]
    dec al
    mov ah, {NT}
    mul ah
    add ax, bx
    jmp h_draw
h_st2:
    mov byte ptr cs:[{T1}], bl
    mov byte ptr cs:[{ST}], 3
    pop cx
    jmp h_swallow
h_bad:
    pop cx
h_bad2:
    mov byte ptr [bp+8], 0x3f
    jmp h_pass
h_draw:
    pop cx
    cmp ax, word ptr cs:[{NGLYPHV}]
    jae h_bad2
    push cx
    push si
    push di
    push es
    mov si, ax
    shl si, 3
    add si, {GLYPHS}
    mov es, word ptr [{FONTSEG}]
    mov di, {SLOT8}
    mov cx, 4
    push ds
    push cs
    pop ds
    cld
    rep movsw
    pop ds
    pop es
    pop di
    pop si
    pop cx
    mov byte ptr [bp+8], {SLOT}
    mov byte ptr cs:[{LASTJP}], 1
    mov bx, word ptr [{WINPTR}]
    mov word ptr cs:[{JPWIN}], bx
    mov bx, word ptr [bx+4]
    inc bl
    mov word ptr cs:[{JPPOS}], bx
    jmp h_pass
h_print:
    cmp ax, word ptr cs:[{NSTRV}]
    jae h_bad2
    push cx
    push dx
    push si
    push di
    push es
    mov si, ax
    shl si, 1
    mov si, word ptr cs:[si+{STRTAB}]
h_loop:
    mov al, byte ptr cs:[si]
    or al, al
    je h_pdone
    inc si
    push si
    xor ah, ah
    push cs
    call h_tramp
    pop si
    jmp h_loop
h_pdone:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    jmp h_swallow
; 1文字関数を呼ぶ。積み方: [GADGET][文字][戻りIP][CS]。1文字関数の ret 2 で GADGET の retf に行き、ここへ戻る
h_tramp:
    push ax
    .byte 0x68, {GADGET_LO}, {GADGET_HI}
    {call_thunk}
h_reset:
    mov byte ptr cs:[{ST}], 0
h_ascii:
    mov byte ptr cs:[{LASTJP}], 0
h_pass:
    pop bx
    pop ax
    pop bp
    pop word ptr cs:[{RETIP}]
    pop word ptr cs:[{RETCS}]
    push bp
    mov bp, sp
    push si
    push di
    {jmp_ret}
h_swallow:
    pop bx
    pop ax
    pop bp
    pop word ptr cs:[{RETIP}]
    pop word ptr cs:[{RETCS}]
    pop word ptr cs:[{RETIP}]
    add sp, 2
    {jmp_ret}

; strlen（本体 0x216C）の代わり。表示の幅を返す: 日本語1字は 1、長い訳の印は中身の字数
; far call で来る。[bp+2]=戻りIP [bp+4]=CS [bp+6]=呼び出し元 [bp+8]=文字列
slen:
    push bp
    mov bp, sp
    push si
    push bx
    push cx
    cld
    mov si, word ptr [bp+8]
    xor cx, cx
    xor bh, bh
s_loop:
    lodsb
    or al, al
    je s_done
    and al, 0x7f
    mov bl, al
    mov bl, byte ptr cs:[bx+{LEADTAB}]
    or bl, bl
    je s_one
    cmp byte ptr [si], 0
    je s_one
    cmp bl, 0x80
    je s_l3
    inc si
    jmp s_one
s_l3:
    cmp byte ptr [si+1], 0
    je s_one
    mov bl, byte ptr [si]
    and bl, 0x7f
    mov al, byte ptr cs:[bx+{TRTAB}]
    mov ah, {NT}
    mul ah
    mov bl, byte ptr [si+1]
    and bl, 0x7f
    mov bl, byte ptr cs:[bx+{TRTAB}]
    add ax, bx
    add si, 2
    cmp ax, {STRBASE}
    jb s_one
    sub ax, {STRBASE}
    cmp ax, word ptr cs:[{NSTRV}]
    jae s_one
    push si
    mov si, ax
    shl si, 1
    mov si, word ptr cs:[si+{STRTAB}]
w_loop:
    mov al, byte ptr cs:[si]
    inc si
    or al, al
    je w_end
    and al, 0x7f
    mov bl, al
    mov bl, byte ptr cs:[bx+{LEADTAB}]
    or bl, bl
    je w_one
    cmp bl, 0x80
    jne w_l2
    inc si
w_l2:
    inc si
w_one:
    inc cx
    jmp w_loop
w_end:
    pop si
    xor bh, bh
    jmp s_loop
s_one:
    inc cx
    jmp s_loop
s_done:
    mov ax, cx
    pop cx
    pop bx
    pop si
    pop bp
    pop word ptr cs:[{SRETIP}]
    pop word ptr cs:[{SRETCS}]
    pop word ptr cs:[{SRETIP}]
    add sp, 2
    {jmp_sret}

; 文字列を窓に書く関数（本体 0x1850）の代わり
; far call で来る。[bp+2]=戻りIP [bp+4]=CS [bp+6]=呼び出し元 [bp+8]=文字列
; 日本語のリードを含まない文字列は、元の関数をそのまま続ける（先頭の6バイトは far call と nop に書き換えてある）
; 日本語があれば: 日本語の字は1文字関数へそのまま送る（行の右端の折り返しは1文字関数がやる）
;   英単語は見える幅を測り、行に入らなければ先に改行する。行頭の空白は書かない
jputs:
    push bp
    mov bp, sp
    push si
    push bx
    xor bh, bh
    mov si, word ptr [bp+8]
jp_scan:
    mov bl, byte ptr [si]
    inc si
    or bl, bl
    je jp_orig
    and bl, 0x7f
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    je jp_scan
    pop bx
    jmp jp_go
jp_orig:
    pop bx
    pop si
    pop bp
    pop word ptr cs:[{PRETIP}]
    pop word ptr cs:[{PRETCS}]
    inc word ptr cs:[{PRETIP}]
    push bp
    mov bp, sp
    sub sp, 0x42
    {jmp_pret}
jp_go:
    push di
    push bx
    push cx
    push dx
    push es
    mov si, word ptr [bp+8]
jp_loop:
    mov al, byte ptr [si]
    or al, al
    je jp_done
    mov bl, al
    and bl, 0x7f
    xor bh, bh
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    jne jp_jp
    cmp al, 0x20
    jne jp_n1
    inc si
    mov bx, word ptr [{WINPTR}]
    cmp byte ptr [bx+4], 0
    je jp_loop
    call jp_putc
    jmp jp_loop
jp_n1:
    cmp al, 0x21
    jb jp_one
    cmp al, 0x7f
    jb jp_word
jp_one:
    inc si
    call jp_putc
    jmp jp_loop
jp_word:
    push si
    xor cx, cx
jp_wm:
    mov bl, byte ptr [si]
    cmp bl, 0x21
    jb jp_wme
    cmp bl, 0x7f
    jae jp_wme
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    jne jp_wme
    inc cx
    inc si
    jmp jp_wm
jp_wme:
    pop si
    mov bx, word ptr [{WINPTR}]
    cmp byte ptr [bx+4], 0
    je jp_wout
    mov al, byte ptr [bx+2]
    sub al, byte ptr [bx]
    sub al, byte ptr [bx+4]
    inc al
    xor ah, ah
    cmp cx, ax
    jle jp_wout
    mov al, 0x0a
    call jp_putc
jp_wout:
    mov al, byte ptr [si]
    inc si
    call jp_putc
    loop jp_wout
    jmp jp_loop
jp_jp:
    mov cx, 2
    cmp byte ptr cs:[bx+{LEADTAB}], 0x80
    jne jp_jl
    inc cx
jp_jl:
    mov al, byte ptr [si]
    or al, al
    je jp_loop
    inc si
    call jp_putc
    loop jp_jl
    jmp jp_loop
jp_done:
    pop es
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    pop bp
    pop word ptr cs:[{PRETIP}]
    pop word ptr cs:[{PRETCS}]
    pop word ptr cs:[{PRETIP}]
    add sp, 2
    {jmp_pret}

; AL を1文字関数で書く（SI, CX は保つ）
jp_putc:
    push si
    push cx
    xor ah, ah
    push cs
    call h_tramp
    pop cx
    pop si
    ret

; 物語などの可変幅の文章を並べる（FONT.OVL の先頭の関数の代わり）
; far call で来る。[bp+2]=戻りIP [bp+4]=CS [bp+6]=呼び出し元 [bp+8]=文字列 [bp+10]=フォントのセグメント
; 日本語のリードを含まない文字列は、元の関数をそのまま続ける（先頭の6バイトは far call と nop に書き換えてある）
jlay:
    push bp
    mov bp, sp
    push si
    push bx
    xor bh, bh
    mov si, word ptr [bp+8]
jl_scan:
    mov bl, byte ptr [si]
    inc si
    or bl, bl
    je jl_orig
    and bl, 0x7f
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    je jl_scan
    pop bx
    jmp jl_jp
jl_orig:
    pop bx
    pop si
    pop bp
    pop word ptr cs:[{FRETIP}]
    pop word ptr cs:[{FRETCS}]
    inc word ptr cs:[{FRETIP}]
    push bp
    mov bp, sp
    sub sp, 0x1c
    {jmp_fret}
jl_jp:
    push di
    push cx
    push dx
    push es
    mov ax, 1
    call drv0f
    mov si, word ptr [bp+8]
    call region
jl_loop:
    mov al, byte ptr [si]
    or al, al
    je jl_done
    cmp al, 0x0a
    jne jl_n1
    inc si
    call newline
    jmp jl_loop
jl_n1:
    cmp al, 0x7b
    jne jl_n2
    add word ptr [{PX}], 15
    inc si
    jmp jl_loop
jl_n2:
    cmp al, 0x5f
    jne jl_n3
    inc si
    jmp jl_loop
jl_n3:
    cmp al, 0x20
    jne jl_n4
    inc si
    cmp word ptr [{PX}], cx
    jle jl_loop
    mov ax, word ptr [{PSPACE}]
    add word ptr [{PX}], ax
    jmp jl_loop
jl_n4:
    mov bl, al
    and bl, 0x7f
    xor bh, bh
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    jne jl_jpch
    push si
    xor di, di
jl_wm:
    mov bl, byte ptr [si]
    cmp bl, 0x21
    jb jl_wme
    cmp bl, 0x7c
    jae jl_wme
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    jne jl_wme
    mov bl, byte ptr [bx+{WTAB}]
    inc bx
    add di, bx
    xor bh, bh
    inc si
    jmp jl_wm
jl_wme:
    pop si
    mov ax, word ptr [{PX}]
    add ax, di
    cmp ax, dx
    jle jl_wd
    cmp word ptr [{PX}], cx
    jle jl_wd
    call newline
jl_wd:
    mov bl, byte ptr [si]
    cmp bl, 0x21
    jb jl_loop
    cmp bl, 0x7c
    jae jl_wbad
    cmp byte ptr cs:[bx+{LEADTAB}], 0
    jne jl_loop
    sub bx, 0x20
    mov ax, word ptr [bp+10]
    call drawg
    mov bl, byte ptr [si]
    mov bl, byte ptr [bx+{WTAB}]
    inc bx
    add word ptr [{PX}], bx
    xor bh, bh
    inc si
    jmp jl_wd
jl_wbad:
    inc si
    jmp jl_loop
jl_jpch:
    mov ax, word ptr [{PX}]
    add ax, 8
    cmp ax, dx
    jle jl_jfit
    call newline
jl_jfit:
    call jpidx
    cmp ax, word ptr cs:[{NGLYPHV}]
    jae jl_jskip
    push si
    push cx
    push ds
    push es
    mov si, ax
    shl si, 3
    add si, {GLYPHS}
    push cs
    pop ds
    push cs
    pop es
    mov di, {FFONT} + 8
    mov cx, 4
    cld
    rep movsw
    pop es
    pop ds
    pop cx
    pop si
    mov ax, cs
    add ax, {FFONTSEG}
    xor bx, bx
    call drawg
jl_jskip:
    add word ptr [{PX}], 8
    jmp jl_loop
jl_done:
    xor ax, ax
    call drv0f
    pop es
    pop dx
    pop cx
    pop di
    pop si
    pop bp
    pop word ptr cs:[{FRETIP}]
    pop word ptr cs:[{FRETCS}]
    pop word ptr cs:[{FRETIP}]
    add sp, 4
    {jmp_fret}

; 改行: 9 ドット下へ。左の余白に戻る
newline:
    add word ptr [{PY}], 9
    call region
    mov word ptr [{PX}], cx
    ret

; いまの y で使う余白: CX=左、DX=右（絵の横の範囲 [PY0]〜[PY1] は2番目）
region:
    push bx
    mov ax, word ptr [{PY}]
    xor bx, bx
    cmp ax, word ptr [{PY0}]
    jle rg0
    cmp ax, word ptr [{PY1}]
    jge rg0
    mov bx, 2
rg0:
    mov cx, word ptr [bx+{PLEFT}]
    mov dx, word ptr [bx+{PRIGHT}]
    pop bx
    ret

; DS:SI の日本語の字の番号を AX に（不正なら 0xffff）。SI を字の後ろへ進める
jpidx:
    push bx
    xor bh, bh
    mov bl, byte ptr [si]
    and bl, 0x7f
    mov bl, byte ptr cs:[bx+{LEADTAB}]
    cmp byte ptr [si+1], 0
    je ji_bad
    cmp bl, 0x80
    je ji_3
    mov al, bl
    dec al
    mov ah, {NT}
    mul ah
    mov bl, byte ptr [si+1]
    and bl, 0x7f
    mov bl, byte ptr cs:[bx+{TRTAB}]
    add si, 2
    cmp bl, 0xff
    je ji_bad2
    add ax, bx
    pop bx
    ret
ji_3:
    cmp byte ptr [si+2], 0
    je ji_bad
    mov bl, byte ptr [si+1]
    and bl, 0x7f
    mov al, byte ptr cs:[bx+{TRTAB}]
    mov ah, {NT}
    mul ah
    mov bl, byte ptr [si+2]
    and bl, 0x7f
    mov bl, byte ptr cs:[bx+{TRTAB}]
    add ax, bx
    add ax, {N2}
    add si, 3
    pop bx
    ret
ji_bad:
    inc si
ji_bad2:
    mov ax, 0xffff
    pop bx
    ret

; AX=フォントのセグメント、BX=字の番号を、([PX],[PY]) に描く（y が 0xC0 以上なら描かない）
drawg:
    cmp word ptr [{PY}], 0xc0
    jge dg_ret
    push ax
    push bx
    push si
    push di
    push cx
    push dx
    push ds
    push es
    push bp
    mov si, word ptr [{PX}]
    mov di, word ptr [{PY}]
    mov word ptr [{DRVENT}], 0x4e
    {call_drv}
    pop bp
    pop es
    pop ds
    pop dx
    pop cx
    pop di
    pop si
    pop bx
    pop ax
dg_ret:
    ret

; 表示ドライバの入口 0x0F（AX=引数）。元の関数も最初に 1、最後に 0 で呼んでいる
drv0f:
    push si
    push di
    push cx
    push dx
    push ds
    push es
    push bp
    mov word ptr [{DRVENT}], 0x0f
    {call_drv}
    pop bp
    pop es
    pop ds
    pop dx
    pop cx
    pop di
    pop si
    ret
'''

INIT = r'''
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21}+2], es
    mov word ptr [{NGLYPHV}], {NGLYPH}
    mov word ptr [{NSTRV}], {NSTR}
    mov ax, 0x2521
    mov dx, {INT21}
    int 0x21
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''


def asm(src, addr, kw):
    k = dict(kw)
    k.update(jmp_old=FAR_JMP(V["OLD21"]), call_old=FAR_CALL(V["OLD21"]),
             call_thunk=FAR_JMP(V["THUNK"]), jmp_ret=FAR_JMP(V["RETIP"]), jmp_sret=FAR_JMP(V["SRETIP"]),
             jmp_fret=FAR_JMP(V["FRETIP"]), jmp_pret=FAR_JMP(V["PRETIP"]),
             call_drv=f".byte 0xff,0x1e,{DRVENT & 0xff},{DRVENT >> 8}")   # call far [DS:0x5350]（表示ドライバ）
    src = "\n".join(line.split(";")[0] for line in src.format(**k).splitlines())   # 注釈（日本語）を除く
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src, addr)
    return fix16(bytes(enc), addr)


def read_translation(path):
    items = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        off, ja = line.split("\t", 1)
        items.append((int(off, 16), ja.replace("\\n", "\n")))
    return items


def norm(t):
    """日本語の字のすぐ後の半角空白は全角空白にする（常駐部は日本語の直後の半角空白を描かないため）"""
    out = []
    for ch in t:
        if ch == " " and out and ord(out[-1]) > 0x7E:
            ch = "　"
        out.append(ch)
    return "".join(out)


class Enc:
    def __init__(self, texts):
        freq = {}
        for t in texts:
            for ch in norm(t):
                if ord(ch) > 0x7E:
                    freq[ch] = freq.get(ch, 0) + 1
        self.order = sorted(freq, key=lambda c: (-freq[c], c))
        self.index = {ch: i for i, ch in enumerate(self.order)}
        if len(self.order) > N2 + STRBASE:
            raise RuntimeError("字が多すぎます")

    def encode(self, t, allow=""):
        out = bytearray()
        for ch in norm(t):
            if ord(ch) <= 0x7E:
                if ch in NOTEXT and ch not in allow:
                    raise RuntimeError(f"訳に使えない記号 {ch!r}: {t!r}")
                out.append(ord(ch))
                continue
            i = self.index[ch]
            if i < N2:
                out += bytes([ord(LEAD2[i // NT]), TRAIL[i % NT]])
            else:
                i -= N2
                out += bytes([ord(LEAD3), TRAIL[i // NT], TRAIL[i % NT]])
        return bytes(out)


def read_story(path):
    """物語などの訳: 「ファイル<TAB>何番目の文字列か<TAB>訳」"""
    items = []
    for p in (path.split(",") if path else []):     # カンマで区切って いくつでも
        for line in open(p, encoding="utf-8"):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            f, k, ja = line.split("\t", 2)
            items.append((f.upper(), k if ":" in k else int(k), ja.replace("\\n", "\n")))
    return items


SELF_TABLE = ("LOOK2.DAT", "SIGNS.DAT")   # 位置の表がファイルの中にあるもの（表ごと作り直すので、位置の読み替えはいらない）


def build_look2(game, items, enc):
    """調べる（LOOK2.DAT）: 先頭に 512 個の位置の表、続いて 0 区切りの文字列。番号は位置の順に数えたもの"""
    d = open(os.path.join(game, "LOOK2.DAT"), "rb").read()
    offs = struct.unpack_from("<512H", d, 0)
    uniq = sorted(set(offs))
    strs = [d[o:d.index(b"\0", o)] for o in uniq]
    for k, ja in items:
        strs[k] = enc.encode(ja)
    body, newpos = bytearray(), {}
    for o, s in zip(uniq, strs):
        if len(s) + 1 > 0x80:
            raise RuntimeError(f"LOOK2.DAT: 128 バイトを超える文字列があります: {s!r}")
        newpos[o] = 1024 + len(body)
        body += s + b"\0"
    body += d[d.index(b"\0", uniq[-1]) + 1:]      # 元の最後の文字列の後ろの余り（1 バイト）も写す
    return struct.pack("<512H", *[newpos[o] for o in offs]) + bytes(body)


def sign_runs(txt):
    """看板の文字列の中の、普通の字（最上位ビットあり）のまとまりで英数字を含むもの: [(始まり, 終わり)]"""
    runs, i = [], 0
    while i < len(txt):
        if txt[i] & 0x80 and (txt[i] & 0x7F) >= 0x20:
            j = i
            while j < len(txt) and txt[j] & 0x80 and (txt[j] & 0x7F) >= 0x20:
                j += 1
            if any(chr(c & 0x7F).isalnum() for c in txt[i:j]):
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def build_signs(game, items, enc):
    """看板（SIGNS.DAT）: 先頭に場所ごとの位置の表（33 個）、場所ごとに「4 バイトの見出し＋0 終わりの文字列」が並ぶ
    普通の字のまとまりだけを、同じ幅に中央そろえした訳に替える（ルーン文字と枠はそのまま）"""
    d = open(os.path.join(game, "SIGNS.DAT"), "rb").read()
    table = struct.unpack_from("<33H", d, 0)
    trans = {}
    for k, ja in items:
        rec, seg = map(int, k.split(":"))
        trans[(rec, seg)] = ja
    out, pos, rec, newpos = bytearray(d[:66]), 66, 0, {}
    starts = sorted(set(t for t in table if t))
    while pos < len(d):
        if pos in starts:
            newpos[pos] = len(out)
        if d[pos] == 0xFF or pos + 4 > len(d):
            out.append(d[pos])
            pos += 1
            continue
        j = d.index(b"\0", pos + 4)
        head, txt = d[pos:pos + 4], bytearray(d[pos + 4:j])
        for seg, (a, b) in reversed(list(enumerate(sign_runs(txt)))):
            ja = trans.get((rec, seg))
            if ja is None:
                continue
            width = b - a
            w = len(B_norm(ja))
            if w > width:
                raise RuntimeError(f"SIGNS.DAT {rec}:{seg}: 幅 {width} に入りません（{w}）: {ja}")
            left = (width - w) // 2
            text = " " * left + ja + " " * (width - w - left)
            txt[a:b] = bytes(c | 0x80 for c in enc.encode(text))
        out += head + txt + b"\0"
        pos = j + 1
        rec += 1
    struct.pack_into("<33H", out, 0, *[newpos[t] if t else 0 for t in table])
    blocks = sorted(newpos.values()) + [len(out)]
    for a, b in zip(blocks, blocks[1:]):
        if b - a > DAT_BUF:
            raise RuntimeError(f"SIGNS.DAT: 1 つの場所の看板が {DAT_BUF} バイトを超えました")
    return bytes(out)


def B_norm(t):
    return norm(t)


def build_daj(game, story, enc):
    """物語などの日本語版（*.DAJ）を作る。返り値: {元のファイル名: [(元の位置, 新しい位置)]}"""
    maps = {}
    for name in SELF_TABLE:
        its = [(k, ja) for f, k, ja in story if f == name]
        if its:
            blob = build_look2(game, its, enc) if name == "LOOK2.DAT" else build_signs(game, its, enc)
            out = os.path.join(game, name[:-1] + "J")
            open(out, "wb").write(blob)
            print("書き出し:", out)
            maps[name] = []
    for name in sorted({f for f, *_ in story} - set(SELF_TABLE)):
        parts = open(os.path.join(game, name), "rb").read().split(b"\0")
        old_starts, pos = [], 0
        for s in parts:
            old_starts.append(pos)
            pos += len(s) + 1
        for f, k, ja in story:
            if f == name:
                parts[k] = enc.encode(ja, allow="{")     # { は段落の字下げ
        old_len = [len(s) for s in open(os.path.join(game, name), "rb").read().split(b"\0")]
        new_starts, pos = [], 0
        for s in parts:
            lim = DAT_BUF_OF.get(name, DAT_BUF)
            if len(s) + 1 > lim:
                raise RuntimeError(f"{name}: {lim} バイトを超える文字列があります（{len(s) + 1}）")
            new_starts.append(pos)
            pos += len(s) + 1
        for o, n in DAT_WINDOWS.get(name, []):
            k0 = old_starts.index(o)
            for k, a in enumerate(old_starts):
                if o <= a and a + old_len[k] + 1 <= o + n and parts[k]:     # 元は読み込みの範囲に収まっていたもの
                    end = new_starts[k] + len(parts[k]) + 1
                    if end > new_starts[k0] + n:
                        raise RuntimeError(f"{name}: {k} 番が、位置 {o} から {n} バイトの読み込みに収まりません"
                                           f"（{end - new_starts[k0]} バイト）")
        out = os.path.join(game, name[:-1] + "J")
        open(out, "wb").write(b"\0".join(parts))
        print("書き出し:", out)
        maps[name] = [(a, b) for a, b in zip(old_starts, new_starts) if a != b and a < 0x10000]
    return maps


def main(trfile, out, tlkfile=None, storyfile=None):
    game = os.path.join(HERE, "..", "game_test")
    data = open(os.path.join(game, "DATA.OVL"), "rb").read()
    items = read_translation(trfile)
    story = read_story(storyfile)
    texts = [ja for _, ja in items] + [ja for *_, ja in story]
    if tlkfile:
        import re
        for line in open(tlkfile, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                texts.append(re.sub(r"\{..\}", "", line.rstrip("\n").split("\t", 3)[3]))
    enc = Enc(texts)
    if tlkfile:
        import build_tlj
        build_tlj.main(tlkfile, game, enc)
    maps = build_daj(game, story, enc)
    glyphs = load_bdf(BDF)
    missing = [ch for ch in enc.order if ord(ch) not in glyphs]
    patches = []           # (位置, バイト列)
    strs = []              # 常駐部に置く長い訳
    for off, ja in items:
        n = data.index(b"\0", off) - off         # 元の長さ（0 を除く）
        e = enc.encode(ja)
        if e == data[off:off + n]:
            continue                                # 訳が元と同じなら置き換えない（原作のデータを常駐部に持たないため）
        if len(e) <= n:
            patches.append((off, e + b"\0"))
        else:
            if n < 3:
                raise RuntimeError(f"{off:05X}: 元が短すぎて印を置けません")
            k = STRBASE + len(strs)
            strs.append(e)
            patches.append((off, bytes([ord(LEAD3), TRAIL[k // NT], TRAIL[k % NT], 0])))
    leadtab = bytearray(128)
    for i, ch in enumerate(LEAD2):
        leadtab[ord(ch)] = i + 1
    leadtab[ord(LEAD3)] = 0x80
    trtab = bytearray([0xFF] * 128)
    for i, c in enumerate(TRAIL):
        trtab[c] = i
    qmark = bytes([0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00])
    gl = b"".join(glyphs.get(ord(ch), qmark) for ch in enc.order)

    kw = dict(V)
    kw.update(STRBASE=STRBASE, NT=NT, N2=N2, SLOT=SLOT, SLOT8=SLOT * 8, PUTC=PUTC, GADGET=GADGET, GADGET_LO=GADGET & 0xFF, GADGET_HI=GADGET >> 8,
              FONTSEG=FONTSEG, WINPTR=WINPTR, PSIGLEN=len(PUTC_SIG), TSIGLEN=len(THUNK_SIG),
              STRLEN=STRLEN, SSIGLEN=len(STRLEN_SIG), DRVENT=DRVENT, **GAMEVARS,
              PFILES=0x9000, RFILES=0x9000, PUTS=PUTS, USIG=0x9000, JPUTS=0x9000, PATCHF=0x9000, FSIG=0x9000, JLAY=0x9000, FFONT=0x9000, FFONTSEG=0x900,
              SSIG=0x9000, SLEN=0x9000, PSIG=0x9000, TSIG=0x9000, HOOK=0x9000, LEADTAB=0x9000,
              TRTAB=0x9000, GLYPHS=0x9000, STRTAB=0x9000)
    res = asm(RES, CODE, kw)
    p = CODE + len(res)
    lay = {}
    def put(name, blob):
        nonlocal p
        lay[name] = (p, blob)
        p += len(blob)
    # 字形を1つだけ持つフォント（表示ドライバの形式: 字の数、位置の表、幅・高さ・ビット列）。セグメントの先頭に置く
    p = (p + 15) & ~15
    put("FFONT", struct.pack("<HHHH", 1, 4, 8, 8) + bytes(8))
    # 照合は原作のバイト列ではなく、ハッシュ値（h1, h2）で持つ
    from make_patch import h12
    put("PSIG", struct.pack("<HH", *h12(PUTC_SIG)))
    put("FSIG", struct.pack("<HH", *h12(FONT_SIG)))
    put("USIG", struct.pack("<HH", *h12(PUTS_SIG)))
    put("TSIG", struct.pack("<HH", *h12(THUNK_SIG)))
    put("SSIG", struct.pack("<HH", *h12(STRLEN_SIG)))
    put("LEADTAB", bytes(leadtab))
    put("TRTAB", bytes(trtab))
    pt = b"".join(struct.pack("<HH", off, len(b)) + b for off, b in patches) + b"\xff\xff"
    put("PATCHES", pt)
    # TALK.OVL: 英語用の折り返し判定（桁＋単語のバイト数 >= 18 なら改行）を止める。日本語は行の右端で折り返す
    put("PATCHT", struct.pack("<HHB", 0x5A3, 1, 0xFF) + struct.pack("<H", 0xFFFF))
    # INTRO.OVL: メニューの項目の桁を、訳の見える幅に合わせる
    pi = b""
    for off, ja in items:
        if off in MENU_COLS:
            col = 20 - (len(norm(ja)) + 2) // 2
            pi += struct.pack("<HHB", MENU_COLS[off], 1, max(col, 0))
    put("PATCHI", pi + struct.pack("<H", 0xFFFF))
    put("PATCHF", struct.pack("<H", 0xFFFF))      # FONT.OVL は読んだ後に patch_font で書き換える
    # 差し替えたファイルの位置の対応表（元の文字列の先頭 → 日本語版の先頭）
    mapat = {}
    for name, pairs in maps.items():
        mapat[name] = p
        put("MAP_" + name, b"".join(struct.pack("<HH", a, b) for a, b in pairs) + struct.pack("<H", 0xFFFF))
    # ファイルの表: 名前の長さ、名前（12）、ハンドル、置き換えの表（PFILES）か位置の対応表（RFILES）
    def ent(fname, ptr):
        return bytes([len(fname)]) + fname.encode().ljust(12, b"\0") + struct.pack("<HH", 0xFFFF, ptr)
    pf_at = p
    # PFILES の最初の項目は DATA.OVL（開いたときに本体を書き換える合図）
    pf = (ent("DATA.OVL", lay["PATCHES"][0]) + ent("TALK.OVL", lay["PATCHT"][0])
          + ent("INTRO.OVL", lay["PATCHI"][0]) + ent("FONT.OVL", lay["PATCHF"][0]) + b"\0")
    put("PFILES", pf)
    rf = ent(".TLK", 0) + b"".join(ent(n, mapat[n]) for n in maps) + b"\0"
    put("RFILES", rf)
    put("GLYPHS", gl)
    # 長い訳の表（番地は後で決まる）
    strtab_at = p
    p += 2 * len(strs)
    sbody = bytearray()
    sptr = []
    for s in strs:
        sptr.append(p + len(sbody))
        sbody += s + b"\0"
    p += len(sbody)
    resident_end = p
    for name, (a, _) in lay.items():
        kw[name] = a
    kw.update(STRTAB=strtab_at, FFONTSEG=lay["FFONT"][0] >> 4)
    kw["JLAY"] = CODE + len(asm(RES[:RES.index("\njlay:")], CODE, kw))
    kw["JPUTS"] = CODE + len(asm(RES[:RES.index("\njputs:")], CODE, kw))
    # 入口の位置を知るため、ラベル hook の位置を求める（hook: より前だけを組み立てる）
    pre = RES[:RES.index("\nhook:")]
    kw["HOOK"] = CODE + len(asm(pre, CODE, kw))
    kw["SLEN"] = CODE + len(asm(RES[:RES.index("\nslen:")], CODE, kw))
    res2 = asm(RES, CODE, kw)
    assert len(res2) == len(res), (len(res2), len(res))
    msg = f"U5JP: test build ({len(enc.order)} chars, {len(strs)} long strings)\r\n$".encode()
    ikw = dict(V)
    ikw.update(INT21=CODE, MSG=0x9000, PARAS=(resident_end + 15) // 16, NGLYPH=len(enc.order), NSTR=len(strs))
    init = asm(INIT, resident_end, ikw)
    ikw["MSG"] = resident_end + len(init)
    init2 = asm(INIT, resident_end, ikw)
    assert len(init2) == len(init)

    img = bytearray(b"\xe9" + struct.pack("<H", (resident_end - 0x103) & 0xFFFF))
    img += bytes(CODE - 0x100 - len(img))
    img += res2
    for name, (a, blob) in lay.items():
        assert 0x100 + len(img) <= a
        img += bytes(a - 0x100 - len(img))
        img += blob
    for a in sptr:
        img += struct.pack("<H", a)
    img += sbody
    assert 0x100 + len(img) == resident_end
    img += init2 + msg
    open(out, "wb").write(img)
    print(f"書き出し: {out}  {len(img)} バイト（常駐 {resident_end - 0x100}）")
    print(f"字 {len(enc.order)}（2バイト {min(len(enc.order), N2)}）、置き換え {len(patches)} 件、長い訳 {len(strs)} 件")
    print(f"hook = {kw['HOOK']:#x}")
    if missing:
        print("フォントにない字:", "".join(missing))


if __name__ == "__main__":
    # 試験用: --noexe（1文字関数を書き換えない）、--nodata（DATA.OVL を置き換えない）
    if "--noexe" in sys.argv:
        RES = RES.replace("    call patch_exe\n", "    nop\n    nop\n    nop\n")
    if "--nodata" in sys.argv:
        RES = RES.replace("    call apply\n", "    nop\n    nop\n    nop\n")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], args[1], args[2] if len(args) > 2 else None, args[3] if len(args) > 3 else None)
