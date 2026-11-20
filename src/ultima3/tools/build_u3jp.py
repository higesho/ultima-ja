# ウルティマIII 用の常駐プログラム U3JP.COM を作る
#   - INT 21h AH=14h（FCB の一括読み込み）の直後に、FCB の名前・大きさ・中身のハッシュ値を照合し、
#     GOG 版の BOOTUP.BIN / EXODUS.BIN / 町・地下牢のファイルなら、読み込んだメモリを書き換える
#       BIN: 訳文を CS:0xB000 以降に置き、lea si,[番地] の即値と番地の表を付け替える（元の英文は残す）
#            1文字を描く関数の先頭を中継（CS:0xB000）への jmp にし、0x80 以上の字だけ INT 66h に回す
#       町・地下牢: 会話（CS:0x1100 の位置表＋0 区切りの文）の訳を CS:0xF000 に置き、位置表を付け替える
#   - INT 66h: 日本語の字を CGA の画面（B800h）に直接描く
#       1バイトの字（よく使う字）と、2バイトの組（リード＋トレイル、2マスに2字）
#       組の片方が英数字のときは、ゲームのフォント（CHARSET.ULT）の形を使う
# 使い方: python build_u3jp.py <ゲームのフォルダ> <訳のファイル> <出力 U3JP.COM>
#   訳のファイル: 「E.1707<TAB>訳」（EXODUS.BIN の番地）、「B.0ca9<TAB>訳」（BOOTUP.BIN）、
#                 「BRITISH.3<TAB>訳」（町・地下牢のファイルの会話、0〜7 番）。\n は改行、{10} {11} は飾り
import json
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jpenc  # noqa: E402
import u3data  # noqa: E402
from jpenc import Encoder, load_bdf, is_jp, fix16, FAR_JMP, FAR_CALL  # noqa: E402
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

# ウルティマIII では1バイトが必ず1マス。日本語の字はどの英数字とも組にしてよい（改行や飾りとは組まない）
jpenc.PAIR_ASCII = set(chr(c) for c in range(0x20, 0x7F))
jpenc.TRAILS = list(range(0x80, 0x100))       # トレイルは 0x80〜0xFF（中継は 0x80 以上だけを常駐部に回すため）
CODES = list(range(0x80, 0x100))               # リードと1バイトの字に使う番号

# ゲームの中の場所（GOG 版）
BIN = {
    "B": dict(name="BOOTUP  BIN", hook=0x4440, font=0x33E9, cursor=0x1F40, vseg=0x43E9),
    "E": dict(name="EXODUS  BIN", hook=0x4F90, font=0x3F39, cursor=0x2A90, vseg=0x4F39),
}
HOOK_ORIG = bytes.fromhex("9c5053")            # pushf; push ax; push bx（jmp で置き換える3バイト）
STUB = 0xB000                                  # 中継と訳文を置く場所（プログラムの後ろの空き）
TALK_TAB = 0x1100                              # 会話の位置表（町は CS:0x100、地下牢は CS:0x900 に読まれる）
TALK_AREA = 0xF000                             # 会話の訳を置く場所
TALK_END = 0xFF00
HSTRIDE = 4                                    # BIN のハッシュ値は 4 バイトおきに計算する（速さのため）
STACK_SIZE = 256

# ---- 常駐部の変数（0x100 から）----
OLD21, LEAD, LEADPOS, SAVESS, SAVESP, FONTP = 0x103, 0x107, 0x108, 0x10A, 0x10C, 0x10E
CODE = 0x120

# INT 21h: AH=14h なら読み込んだあとで照合・書き換え
RES21 = r'''
    cmp ah, 0x14
    je i21_read
i21_chain:
    {jmp_old21}
i21_read:
    pushf
    {call_old21}
    cmp al, 0
    jne i21_ret
    mov word ptr cs:[{SAVESS}], ss
    mov word ptr cs:[{SAVESP}], sp
    cli
    push cs
    pop ss
    mov sp, {STACKTOP}
    sti
    pusha
    push ds
    push es
    call check
    pop es
    pop ds
    popa
    cli
    mov ss, word ptr cs:[{SAVESS}]
    mov sp, word ptr cs:[{SAVESP}]
    sti
i21_ret:
    iret

; DS:DX = FCB（ゲーム側）。ファイルの表 FILES（26 バイトずつ）と照合する
check:
    mov ah, 0x2f
    pushf
    {call_old21}
    ; ES:BX = DTA
    mov bp, dx
    mov di, {FILES}
c_next:
    cmp byte ptr cs:[di], 0
    je c_none
    ; 名前 11 バイト
    mov si, bp
    inc si
    push di
    mov cx, 11
c_cmp:
    mov al, byte ptr [si]
    cmp al, byte ptr cs:[di]
    jne c_ne
    inc si
    inc di
    loop c_cmp
    pop di
    ; 大きさ（FCB の記録の大きさ）と DTA
    mov si, bp
    mov ax, word ptr [si + 0x0e]
    cmp ax, word ptr cs:[di + 11]
    jne c_skip
    cmp bx, word ptr cs:[di + 13]
    jne c_skip
    ; ハッシュ値
    push di
    push bx
    mov si, word ptr cs:[di + 15]
    mov cx, word ptr cs:[di + 17]
    mov al, byte ptr cs:[di + 19]
    xor ah, ah
    call hash
    pop bx
    pop di
    cmp ax, word ptr cs:[di + 20]
    jne c_skip
    cmp dx, word ptr cs:[di + 22]
    jne c_skip
    ; 書き換え: [書き込み先, 長さ, 中身...]、長さ 0 で終わり
    mov si, word ptr cs:[di + 24]
    push cs
    pop ds
    cld
c_w:
    lodsw
    mov di, ax
    lodsw
    mov cx, ax
    jcxz c_none
    rep movsb
    jmp c_w
c_ne:
    pop di
c_skip:
    add di, 26
    jmp c_next
c_none:
    ret

; ES:SI から AX バイトおきに CX 個のハッシュ値 → AX=h1, DX=h2（壊す: BX, CX, SI）
hash:
    push bp
    mov bp, ax
    xor ax, ax
    xor dx, dx
    xor bh, bh
h_l:
    mov bl, byte ptr es:[si]
    rol ax, 1
    add ax, bx
    add dx, bx
    rol dx, 1
    rol dx, 1
    rol dx, 1
    add si, bp
    loop h_l
    pop bp
    ret
'''

# INT 66h: AL=字の番号（0x80 以上）、DH=行、DL=桁、ES=画面、BX=ゲームのフォント（DS:BX）
RES66 = r'''
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    mov word ptr cs:[{FONTP}], bx
    mov bl, al
    xor bh, bh
    mov ah, byte ptr cs:[bx + {KIND} - 0x80]
    cmp byte ptr cs:[{LEAD}], 0
    jne g_trail
    or ah, ah
    jnz g_lead
    ; 1バイトの字
    sub bx, 0x80
    shl bx, 1
    shl bx, 1
    shl bx, 1
    lea si, [bx + {SINGLES}]
    call draw_jp
    jmp g_done
g_lead:
    mov byte ptr cs:[{LEAD}], ah
    mov word ptr cs:[{LEADPOS}], dx
    jmp g_done
g_trail:
    ; 組の番号 = (リードの番号-1)*128 + (トレイル-0x80)
    mov cl, byte ptr cs:[{LEAD}]
    mov byte ptr cs:[{LEAD}], 0
    dec cl
    xor ch, ch
    shl cx, 7
    sub bx, 0x80
    add bx, cx
    cmp bx, {NPAIRS}
    jae g_bad
    shl bx, 1
    shl bx, 1
    add bx, {PAIRS}
    ; 1字目はリードの位置（行が変わっていたら、スクロールで1行上がったとみなす）
    push dx
    mov cx, word ptr cs:[{LEADPOS}]
    cmp ch, dh
    je g_same
    mov ch, dh
    dec ch
g_same:
    mov dx, cx
    mov si, word ptr cs:[bx]
    call draw
    pop dx
    mov si, word ptr cs:[bx + 2]
    call draw
    jmp g_done
g_bad:
    mov si, {QMARK}
    call draw_jp
g_done:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    iret

; SI = 0（空白）/ 英数字の番号（0x01〜0x7F）/ 常駐部の字の形の番地。DX = 位置
draw:
    cmp si, 0x100
    jae draw_jp
    or si, si
    jz draw_blank
    ; ゲームのフォント: 16 バイト（行 0,2,4,6,1,3,5,7 の順）
    push bx
    shl si, 4
    add si, word ptr cs:[{FONTP}]
    call cell
    mov ax, word ptr [si]
    mov word ptr es:[di], ax
    mov ax, word ptr [si + 2]
    mov word ptr es:[di + 0x50], ax
    mov ax, word ptr [si + 4]
    mov word ptr es:[di + 0xa0], ax
    mov ax, word ptr [si + 6]
    mov word ptr es:[di + 0xf0], ax
    mov ax, word ptr [si + 8]
    mov word ptr es:[di + 0x2000], ax
    mov ax, word ptr [si + 10]
    mov word ptr es:[di + 0x2050], ax
    mov ax, word ptr [si + 12]
    mov word ptr es:[di + 0x20a0], ax
    mov ax, word ptr [si + 14]
    mov word ptr es:[di + 0x20f0], ax
    pop bx
    ret
draw_blank:
    call cell
    xor ax, ax
    mov word ptr es:[di], ax
    mov word ptr es:[di + 0x50], ax
    mov word ptr es:[di + 0xa0], ax
    mov word ptr es:[di + 0xf0], ax
    mov word ptr es:[di + 0x2000], ax
    mov word ptr es:[di + 0x2050], ax
    mov word ptr es:[di + 0x20a0], ax
    mov word ptr es:[di + 0x20f0], ax
    ret
; 常駐部の字の形（8 バイト、1 行 1 バイト）を 2 ビット/点に広げて描く
draw_jp:
    push bx
    call cell
    mov cx, 4
dj_l:
    mov bl, byte ptr cs:[si]
    xor bh, bh
    shl bx, 1
    mov ax, word ptr cs:[bx + {EXP}]
    mov word ptr es:[di], ax
    mov bl, byte ptr cs:[si + 1]
    xor bh, bh
    shl bx, 1
    mov ax, word ptr cs:[bx + {EXP}]
    mov word ptr es:[di + 0x2000], ax
    add si, 2
    add di, 0x50
    loop dj_l
    pop bx
    ret
; DX（DH=行、DL=桁）→ DI = 画面の番地（行*320 + 桁*2）
cell:
    push ax
    mov al, dh
    xor ah, ah
    mov di, ax
    shl di, 6
    shl ax, 8
    add di, ax
    mov al, dl
    xor ah, ah
    shl ax, 1
    add di, ax
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
    mov ax, 0x2566
    mov dx, {E66}
    int 0x21
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''

# ゲームの中に置く中継（STUB）。1文字を描く関数の先頭の3バイトをこれへの jmp にする
STUBSRC = r'''
    cmp al, 0x80
    jb s_asc
    push bx
    push dx
    push es
    mov bx, {font}
    mov dx, word ptr [{cursor}]
    mov es, word ptr [{vseg}]
    int 0x66
    pop es
    pop dx
    pop bx
    ret
s_asc:
    pushf
    push ax
    push bx
    jmp {back}
'''


def asm(src, addr, kw):
    src = "\n".join(line.split(";")[0] for line in src.format(**kw).split("\n"))   # コメントを除く
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src, addr)
    return fix16(bytes(enc), addr)


def h12(bs):
    h1 = h2 = 0
    for x in bs:
        h1 = (((h1 << 1) | (h1 >> 15)) + x) & 0xFFFF
        h2 = (h2 + x) & 0xFFFF
        h2 = ((h2 << 3) | (h2 >> 13)) & 0xFFFF
    return h1, h2


def read_translation(path):
    tr = {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        key, _, text = line.partition("\t")
        text = text.replace("\\n", "\n").replace("{10}", "\x10").replace("{11}", "\x11")
        tr[key.strip()] = text
    return tr


def talk_entries(data):
    """町・地下牢のファイル → (会話の位置表のファイル内の位置, [(番号, 英文バイト列, ファイル内の位置)])"""
    toff = 0x1000 if len(data) == 4648 else 0x800
    # 表の件数は「最初の文の位置 ÷ 2」（最大 8 件）。少ないファイルでは表のすぐ後ろから文が始まる
    first = struct.unpack_from("<H", data, toff)[0]
    n = min(8, first // 2) if first else 0
    offs = struct.unpack_from(f"<{n}H", data, toff)
    res = []
    for k, o in enumerate(offs):
        p = toff + o
        if p >= len(data) or o == 0:
            continue
        e = data.find(b"\0", p)
        if e < 0:
            continue
        res.append((k, data[p:e], p))
    return toff, res


TALK_FILES = {4648: 0x100, 2192: 0x900}     # ファイルの大きさ → 読み込まれる番地（DTA）
MSG_W = 16                                  # メッセージ欄の幅
ALIGNS = ("{c}", "{r}", "{l.}", "{l}")      # 訳の先頭に付ける、元の英文の幅に合わせる指定


def split_align(text):
    for a in ALIGNS:
        if text.startswith(a):
            return a, text[len(a):]
    return None, text


def align(b, mode, width):
    """符号化したバイト列 b を、元の幅 width マスにそろえる（先頭の改行・飾り、末尾の改行・飾りの内側に詰める）"""
    i = 0
    while i < len(b) and b[i] in (0x0A, 0x10):
        i += 1
    j = len(b)
    while j > i and b[j - 1] in (0x0A, 0x11):
        j -= 1
    head, mid, tail = b[:i], b[i:j], b[j:]
    n = width - len(mid)
    if n <= 0:
        return b
    fill = b"." if mode == "{l.}" else b" "
    if mode == "{c}":
        mid = b" " * (n // 2) + mid + b" " * (n - n // 2)
    elif mode == "{r}":
        mid = b" " * n + mid
    else:
        mid = mid + fill * n
    return head + mid + tail


def width_of(b):
    """先頭・末尾の改行と飾りを除いた、いちばん長い行のマス数"""
    return max(cells(bytes(x for x in b if x not in (0x10, 0x11)).strip(b"\n")) or [0])


def read_kinds():
    p = os.path.join(HERE, "..", "translation", "en_all.tsv")
    res = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            t = line.rstrip("\n").split("\t")
            if len(t) >= 2:
                res[t[0]] = t[1]
    return res


def cells(b):
    """符号化したバイト列の、行ごとのマス数"""
    lines = [0]
    for x in b:
        if x == 0x0A:
            lines.append(0)
        else:
            lines[-1] += 1
    return lines


def main(game, trfile, out):
    tr = read_translation(trfile)
    errors = []
    # ---- 単位（BIN の文字列）と会話 ----
    bins = {t: u3data.collect(game, t) for t in BIN}
    talk = {}
    for fn in sorted(os.listdir(game)):
        if not fn.upper().endswith(".ULT"):
            continue
        data = open(os.path.join(game, fn), "rb").read()
        if len(data) not in TALK_FILES:
            continue
        toff, ents = talk_entries(data)
        if ents:
            talk[fn.upper()[:-4]] = (data, toff, ents)
    for key in tr:
        if key[:2] in ("B.", "E."):
            if int(key[2:], 16) not in bins[key[0]]["units"]:
                errors.append(f"{key} は文字列の単位ではありません")
        else:
            stem, _, k = key.rpartition(".")
            if stem not in talk or not any(str(e[0]) == k for e in talk[stem][2]):
                errors.append(f"{key} は会話ではありません")

    # ---- 符号化（リードの数は、組が足りるまで増やす）----
    english0 = {}
    for tag in BIN:
        for a, t in bins[tag]["units"].items():
            english0[f"{tag}.{a:04x}"] = t
    aligns = {}
    for k in list(tr):
        a, t = split_align(tr[k])
        if a:
            aligns[k] = a
            tr[k] = t
        # 英文の末尾の空白は、訳の末尾に空白や改行がなければ引き継ぐ（入力の後ろの空白など）
        en = english0.get(k)
        if en and en.endswith(b" ") and not tr[k].endswith((" ", "\n")):
            tr[k] += " " * (len(en) - len(en.rstrip(b" ")))
    texts = list(tr.values())
    nlead = 16
    while True:
        jpenc.LEADS = CODES[:nlead]
        jpenc.SINGLE_CODES = CODES[nlead:]
        enc = Encoder(texts)
        # 1字だけの組（相手がなく空白が1マス入る）になった字を、1バイトの字に優先して選び直す
        bonus = Counter()
        for _ in range(3):
            enc.pairs = {}
            encoded = {k: enc.encode(t) for k, t in tr.items()}
            for t in texts:
                for u in enc.segment(t):
                    if u[0] == "p" and u[2] is None:
                        bonus[u[1]] += 1
            rank = sorted(enc.freq, key=lambda c: (-(enc.freq[c] + 100 * bonus[c]), c))
            enc.single = {ch: jpenc.SINGLE_CODES[i] for i, ch in enumerate(rank[:len(jpenc.SINGLE_CODES)])}
        enc.pairs = {}
        encoded = {k: enc.encode(t) for k, t in tr.items()}
        if len(enc.pairs) <= nlead * len(jpenc.TRAILS):
            break
        nlead += 4
    # 元の英文
    english = {}
    for tag in BIN:
        for a, t in bins[tag]["units"].items():
            english[f"{tag}.{a:04x}"] = t
    for stem, (data, toff, ents) in talk.items():
        for k, t, p in ents:
            english[f"{stem}.{k}"] = t
    for k, a in aligns.items():
        encoded[k] = align(encoded[k], a, width_of(english[k]))
    kinds = read_kinds()
    warns = []
    for k, b in encoded.items():
        kind = kinds.get(k, "")
        lines = cells(bytes(x for x in b))
        if "MSG" in kind or kind == "TALK":
            for w in lines:
                if w > MSG_W:
                    errors.append(f"{k}: メッセージ欄の1行が {w} マスあります（{MSG_W} まで）")
        elif width_of(b) > width_of(english[k]):
            warns.append(f"{k}: 英文より長い（{width_of(b)} > {width_of(english[k])}） {tr[k]!r}")
    lone = sum(1 for (a, b) in enc.pairs if b is None)

    # ---- BIN の書き換え ----
    files = []      # (名前11, 大きさ, DTA, ハッシュの開始, 個数, 間隔, h1, h2, 書き換えの並び)
    for tag, info in BIN.items():
        r = bins[tag]
        d = r["data"]
        writes = []
        assert d[info["hook"] - 0x100:info["hook"] - 0x100 + 3] == HOOK_ORIG, tag
        stub = asm(STUBSRC, STUB, dict(info, back=info["hook"] + 3))
        hook = bytes([0xE9]) + struct.pack("<h", STUB - (info["hook"] + 3))
        writes.append((info["hook"], hook))
        p = STUB + len(stub)
        writes.append((STUB, stub))
        blob = bytearray()
        for a in sorted(r["units"]):
            key = f"{tag}.{a:04x}"
            if key not in tr:
                continue
            new = p + len(blob)
            blob += encoded[key] + b"\0"
            for ins in r["code"].get(a, []):
                writes.append((ins + 2, struct.pack("<H", new)))
            for t in r["tab"].get(a, []):
                writes.append((t, struct.pack("<H", new)))
        writes.append((p, bytes(blob)))
        end = p + len(blob)
        if end > TALK_AREA:
            errors.append(f"{tag}: 訳文が置き場に入りません（{end:04x}）")
        # 書き換えが重ならないこと
        spans = sorted((a, a + len(b)) for a, b in writes)
        for (a1, e1), (a2, e2) in zip(spans, spans[1:]):
            if a2 < e1:
                errors.append(f"{tag}: 書き換えが重なっています {a1:04x}-{e1:04x} / {a2:04x}")
        n = len(d)
        cnt = (n + HSTRIDE - 1) // HSTRIDE
        h1, h2 = h12(d[0:n:HSTRIDE])
        files.append((info["name"], n, 0x100, 0x100, cnt, HSTRIDE, h1, h2, writes))
        print(f"{u3data.FILES[tag]}: 訳 {sum(1 for k in tr if k.startswith(tag + '.'))} 件、訳文 {len(blob)} バイト"
              f"（{p:04x}〜{end:04x}）")

    # ---- 会話 ----
    tsize = 0
    for stem, (data, toff, ents) in sorted(talk.items()):
        keys = [f"{stem}.{k}" for k, _, _ in ents]
        if not any(k in tr for k in keys):
            continue
        dta = TALK_FILES[len(data)]
        assert dta + toff == TALK_TAB
        last = max(p + len(t) for _, t, p in ents)
        region = data[toff:last + 1]
        h1, h2 = h12(region)
        # 訳した文の位置表の項目だけを書き換える（元のデータは配布物に入れない）
        writes = []
        blob = bytearray()
        for k, t, p in ents:
            key = f"{stem}.{k}"
            if key in tr:
                writes.append((TALK_TAB + 2 * k, struct.pack("<H", (TALK_AREA + len(blob) - TALK_TAB) & 0xFFFF)))
                blob += encoded[key] + b"\0"
        if TALK_AREA + len(blob) > TALK_END:
            errors.append(f"{stem}: 会話の訳が長すぎます（{len(blob)} バイト）")
        tsize = max(tsize, len(blob))
        name = (stem.ljust(8) + "ULT")[:11]
        writes.append((TALK_AREA, bytes(blob)))
        files.append((name, len(data), dta, TALK_TAB, len(region), 1, h1, h2, writes))

    if warns:
        print("注意:\n  " + "\n  ".join(warns))

    if errors:
        print("\n".join(errors))
        sys.exit("入らない訳があります")

    # ---- 字の形 ----
    glyphs = load_bdf(BDF)
    missing = set()
    qmark = bytes([0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00])

    def gl(ch):
        g = glyphs.get(ord(ch))
        if g is None:
            missing.add(ch)
            return qmark
        return g

    pool = {}
    for (a, b) in enc.pairs:
        for x in (a, b):
            if x is not None and is_jp(x):
                pool.setdefault(x, len(pool))

    # 2 ビット/点に広げる表（下位バイトが左の 4 点）
    def ex4(n):
        v = 0
        for i in range(4):
            if n & (8 >> i):
                v |= 3 << (6 - 2 * i)
        return v
    exp = b"".join(struct.pack("<BB", ex4(g >> 4), ex4(g & 15)) for g in range(256))

    # ---- 常駐部の配置 ----
    kw = dict(jmp_old21=FAR_JMP(OLD21), call_old21=FAR_CALL(OLD21), SAVESS=SAVESS, SAVESP=SAVESP,
              LEAD=LEAD, LEADPOS=LEADPOS, FONTP=FONTP, NPAIRS=len(enc.pairs))
    names = ["STACKTOP", "FILES", "KIND", "SINGLES", "PAIRS", "QMARK", "EXP"]

    def build(lay):
        k = dict(kw)
        k.update({n: lay.get(n, 0x9000) for n in names})
        c21 = asm(RES21, CODE, k)
        c66 = asm(RES66, CODE + len(c21), k)
        return c21, c66

    c21, c66 = build({})
    p = CODE + len(c21) + len(c66)
    lay = {}
    lay["QMARK"] = p; p += 8
    p = (p + 1) & ~1
    lay["EXP"] = p; p += 512
    lay["KIND"] = p; p += 128
    lay["SINGLES"] = p; p += 8 * 128
    lay["PAIRS"] = p; p += 4 * len(enc.pairs)
    gly = p; p += 8 * len(pool)
    lay["FILES"] = p; p += 26 * len(files) + 1
    wbase = p
    wblob = bytearray()
    frecs = bytearray()
    for name, size, dta, hoff, hcnt, hst, h1, h2, writes in files:
        wp = wbase + len(wblob)
        for a, b in sorted(writes):
            wblob += struct.pack("<HH", a, len(b)) + b
        wblob += struct.pack("<HH", 0, 0)
        frecs += name.encode("ascii") + struct.pack("<HHHHBHHH", size, dta, hoff, hcnt, hst, h1, h2, wp)
    p += len(wblob)
    p = (p + 1) & ~1
    p += STACK_SIZE
    lay["STACKTOP"] = p
    resident_end = p
    c21b, c66b = build(lay)
    assert len(c21b) == len(c21) and len(c66b) == len(c66)
    E21, E66 = CODE, CODE + len(c21)

    kind = bytearray(128)
    for i, c in enumerate(jpenc.LEADS):
        kind[c - 0x80] = i + 1
    singles = bytearray(8 * 128)
    for ch, c in enc.single.items():
        singles[(c - 0x80) * 8:(c - 0x80) * 8 + 8] = gl(ch)

    def ptr(ch):
        if ch is None:
            return 0
        if not is_jp(ch):
            return ord(ch)
        return gly + 8 * pool[ch]
    pairs = b"".join(struct.pack("<HH", ptr(a), ptr(b))
                     for (a, b), _ in sorted(enc.pairs.items(), key=lambda kv: kv[1]))
    poolb = b"".join(gl(ch) for ch, _ in sorted(pool.items(), key=lambda kv: kv[1]))

    msg = "U3JP: Ultima III Japanese patch loaded\r\n$".encode()
    ikw = dict(OLD21=OLD21, E21=E21, E66=E66, MSG=0x9000, PARAS=(resident_end + 15) // 16)
    init = asm(INIT, resident_end, ikw)
    ikw["MSG"] = resident_end + len(init)
    init2 = asm(INIT, resident_end, ikw)
    assert len(init2) == len(init)

    com = bytearray(b"\xe9" + struct.pack("<H", (resident_end - 0x103) & 0xFFFF))
    com += bytes(CODE - 0x103)
    com += c21b + c66b
    com += qmark
    com += bytes(lay["EXP"] - 0x100 - len(com))
    com += exp + kind + singles + pairs + poolb
    assert 0x100 + len(com) == lay["FILES"]
    com += frecs + b"\0" + wblob
    com += bytes(resident_end - 0x100 - len(com))
    com += init2 + msg
    if resident_end > 0xF000:
        sys.exit("常駐部が大きすぎます")
    open(out, "wb").write(com)
    with open(os.path.splitext(out)[0] + "_enc.json", "w", encoding="utf-8") as f:
        json.dump({"encoded": {k: v.hex() for k, v in encoded.items()},
                   "single": enc.single, "nlead": nlead,
                   "pairs": [list(k) for k, _ in sorted(enc.pairs.items(), key=lambda kv: kv[1])]},
                  f, ensure_ascii=False)
    print(f"{out}: {len(com)} バイト（常駐 {resident_end - 0x100}）、1バイトの字 {len(enc.single)}、"
          f"リード {nlead}、組 {len(enc.pairs)}（1字だけの組 {lone}）、字の形 {len(pool)}、"
          f"ファイル {len(files)}、会話の訳の最大 {tsize} バイト")
    if missing:
        print("フォントにない字:", "".join(sorted(missing)))


if __name__ == "__main__":
    main(*sys.argv[1:4])
