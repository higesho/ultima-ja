# 配布用の常駐プログラム U1JP.COM を作る
#   - 日本語フォント（INT 10h のフック。jpenc.py と同じ仕組み）
#   - ゲームが EXE を読み込んだ直後に、メモリ上の英語を日本語に書き換える（INT 21h のフック）
#       AX=4B03h（オーバーレイ読み込み）: 読み込み成功の直後に書き換える（GEN/OUT/SPACE/MONDAIN）
#       AX=4B00h（最初の ULTIMA.EXE）: 印を付けておき、そのプログラムが最初に AH=30h を呼んだ時に書き換える
#   - 書き換える前に元の内容を照合し、GOG 版と違えば何もしない
# 書き換えデータは「元の EXE」と「翻訳済み EXE」の差分から作る（ゲーム本体のコードは含めない）
#
# 使い方: python build_patch.py <元のゲームのフォルダ> <翻訳表のフォルダ> <出力 U1JP.COM>
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
import jpenc
from jpenc import _asm, FAR_JMP, FAR_CALL, RES as RES10, load_bdf, is_jp
from apply_translation import main as apply_main, DEFAULT_BDF

EXES = ['ULTIMA.EXE', 'GEN.EXE', 'OUT.EXE', 'SPACE.EXE', 'MONDAIN.EXE']

# ---- 常駐部の変数の位置（0x100 から）----
OLD10, LEAD, P2 = 0x103, 0x107, 0x108      # jpenc の RES がこの位置を使う
OLD21, PENDING, PLIST, OLIST = 0x10a, 0x10e, 0x110, 0x112
# FORCE: 試験用（1=必ず探す、2=見つからないふり）。LBASE / LPTR: 書き込み中の読み込み位置と書き換えデータ
FORCE, LBASE, LPTR, LSEG, LREM = 0x114, 0x116, 0x118, 0x11a, 0x11c
CODE = 0x11e
HDR = 18            # 書き換えデータの見出しの大きさ
ANCHOR_LEN = 32     # 探すときの目印（最初の書き換え位置から32バイト。元の EXE のまま）

# DS:DX のファイル名から書き換えデータを探す → SI（見つからなければ 0）
IDENT = '''
    mov si, dx
    mov di, dx
id_l1_{u}:
    lodsb
    or al, al
    jz id_l2_{u}
    cmp al, 0x5c
    je id_set_{u}
    cmp al, 0x3a
    je id_set_{u}
    cmp al, 0x2f
    je id_set_{u}
    jmp id_l1_{u}
id_set_{u}:
    mov di, si
    jmp id_l1_{u}
id_l2_{u}:
    mov bx, {NAMES}
id_n1_{u}:
    cmp byte ptr cs:[bx], 0
    je id_nf_{u}
    mov si, di
    push bx
id_c1_{u}:
    mov al, byte ptr [si]
    cmp al, 0x61
    jb id_c2_{u}
    cmp al, 0x7a
    ja id_c2_{u}
    sub al, 0x20
id_c2_{u}:
    cmp al, byte ptr cs:[bx]
    jne id_nx_{u}
    or al, al
    jz id_ok_{u}
    inc si
    inc bx
    jmp id_c1_{u}
id_nx_{u}:
    pop bx
    add bx, 14
    jmp id_n1_{u}
id_ok_{u}:
    pop bx
    mov si, word ptr cs:[bx + 12]
    jmp id_end_{u}
id_nf_{u}:
    xor si, si
id_end_{u}:'''

# apply_list: CS:SI の書き換えデータを、DX を読み込み位置（セグメント）として当てる
#   元のバイト列は持たない（配布物に原作のデータを入れないため）。代わりにハッシュ値（h1, h2）で照合する
#   書き換えデータ: 件数、最初の位置（パラグラフ、オフセット）、イメージの大きさ（パラグラフ）、
#                   目印（最初の位置から32バイト）の先頭8バイトの合計と全体の h1, h2、
#                   探して見つけた場所（読み込み位置からのずれ（パラグラフ）、オフセット。0xFFFF=まだ）、
#                   そのあと1件ずつ（最初の位置からのずれ（パラグラフ、オフセット）、長さ、元の h1, h2、新しいバイト列）
#   1. GOG 版の位置で、全部のハッシュ値が一致すれば書き込む
#   2. 前に探して見つけた場所があれば、そこで照合する
#   3. イメージを 32KB ずつ走査し、8バイトの合計が合う所だけ目印のハッシュ値を見て、合えば全部を照合して書き込む
#   4. どこでも一致しなければ何もしない
APPLY_SUB = '''
apply_list:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push es
    push ds
    push cs
    pop ds
    cld
    mov word ptr [{LBASE}], dx
    mov word ptr [{LPTR}], si
    test byte ptr [{FORCE}], 2
    jnz al_end
    mov ax, dx
    add ax, word ptr [si+2]
    mov bx, word ptr [si+4]
    test byte ptr [{FORCE}], 1
    jnz al_search
    call verify_all
    je al_write
al_search:
    mov si, word ptr [{LPTR}]
    cmp word ptr [si+14], 0xffff
    je as_start
    mov ax, word ptr [{LBASE}]
    add ax, word ptr [si+14]
    mov bx, word ptr [si+16]
    call verify_all
    je al_write
as_start:
    mov ax, word ptr [{LBASE}]
    mov word ptr [{LSEG}], ax
    mov ax, word ptr [si+6]
    mov word ptr [{LREM}], ax
as_chunk:
    mov es, word ptr [{LSEG}]
    xor di, di
    xor bp, bp
    xor ah, ah
    mov cx, 8
as_init:
    mov al, byte ptr es:[di]
    add bp, ax
    inc di
    dec cx
    jnz as_init
    xor di, di
as_l:
    cmp bp, word ptr [si+8]
    jne as_roll
    mov cx, {ANCHOR_LEN}
    call hash
    cmp dx, word ptr [si+10]
    jne as_roll
    cmp ax, word ptr [si+12]
    jne as_roll
    mov ax, es
    mov bx, di
    call verify_all
    jne as_roll
    sub ax, word ptr [{LBASE}]
    mov word ptr [si+14], ax
    mov word ptr [si+16], bx
    mov ax, es
    jmp al_write
as_roll:
    xor ah, ah
    mov al, byte ptr es:[di]
    sub bp, ax
    mov al, byte ptr es:[di+8]
    add bp, ax
    inc di
    cmp di, 0x8000
    jb as_l
    add word ptr [{LSEG}], 0x800
    sub word ptr [{LREM}], 0x800
    ja as_chunk
    jmp al_end
al_write:
    call write_all
al_end:
    pop ds
    pop es
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

hash:
    push di
    push cx
    push si
    xor dx, dx
    xor si, si
hs_l:
    xor ah, ah
    mov al, byte ptr es:[di]
    rol dx, 1
    add dx, ax
    add si, ax
    rol si, 3
    inc di
    dec cx
    jnz hs_l
    mov ax, si
    pop si
    pop cx
    pop di
    ret

verify_all:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push es
    mov bp, ax
    mov si, word ptr [{LPTR}]
    mov cx, word ptr [si]
    add si, {HDR}
va_l:
    push cx
    mov ax, bp
    add ax, word ptr [si]
    mov es, ax
    mov di, bx
    add di, word ptr [si+2]
    mov cx, word ptr [si+4]
    call hash
    pop cx
    cmp dx, word ptr [si+6]
    jne va_out
    cmp ax, word ptr [si+8]
    jne va_out
    add si, 10
    add si, word ptr [si-6]
    dec cx
    jnz va_l
    xor ax, ax
va_out:
    pop es
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

write_all:
    mov dx, ax
    mov si, word ptr [{LPTR}]
    mov cx, word ptr [si]
    add si, {HDR}
wa_l:
    mov ax, dx
    add ax, word ptr [si]
    mov es, ax
    mov di, bx
    add di, word ptr [si+2]
    mov bp, word ptr [si+4]
    add si, 10
    push cx
    mov cx, bp
    rep movsb
    pop cx
    dec cx
    jnz wa_l
    ret
'''

# （古い書き込み処理。使わない）
APPLY = '''
    push ds
    push cs
    pop ds
    cld
    lodsw
    add ax, dx
    mov es, ax
    lodsw
    mov di, ax
    lodsw
    mov cx, ax
    repe cmpsb
    jne ap_end_{u}
    lodsw
    mov bp, ax
ap_next_{u}:
    or bp, bp
    jz ap_end_{u}
    lodsw
    add ax, dx
    mov es, ax
    lodsw
    mov di, ax
    lodsw
    mov cx, ax
    rep movsb
    dec bp
    jmp ap_next_{u}
ap_end_{u}:
    pop ds'''

RES21 = '''
int21:
    cmp ah, 0x4b
    je exec21
    cmp ah, 0x30
    jne chain21
    cmp byte ptr cs:[{PENDING}], 0
    jne pend21
chain21:
    {jmp_old21}
exec21:
    cmp al, 3
    je ovl21
    cmp al, 0
    jne chain21
    push ax
    push bx
    push si
    push di
{ident_a}
    or si, si
    jz ex_no
    mov word ptr cs:[{PLIST}], si
    mov byte ptr cs:[{PENDING}], 1
ex_no:
    pop di
    pop si
    pop bx
    pop ax
    jmp chain21
ovl21:
    push ax
    push bx
    push si
    push di
{ident_b}
    mov word ptr cs:[{OLIST}], si
    pop di
    pop si
    pop bx
    pop ax
    push es
    push bx
    pushf
    {call_old21}
    pop bx
    pop es
    jc ovl_ret
    push ax
    push cx
    push dx
    push si
    push di
    push bp
    push es
    mov si, word ptr cs:[{OLIST}]
    or si, si
    jz ovl_done
    mov dx, word ptr es:[bx]
    call apply_list
ovl_done:
    pop es
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop ax
    clc
ovl_ret:
    retf 2
pend21:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov byte ptr cs:[{PENDING}], 0
    mov ah, 0x62
    pushf
    {call_old21}
    mov dx, bx
    add dx, 0x10
    mov si, word ptr cs:[{PLIST}]
    call apply_list
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    jmp chain21
{apply_sub}
'''

INIT = '''
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
    mov dx, {INT10}
    int 0x21
    mov ax, 0x2521
    mov dx, {INT21}
    int 0x21
    xor ax, ax
    mov es, ax
    cli
    mov word ptr es:[0x10c], {FONT}
    mov es:[0x10e], cs
    mov word ptr es:[0x7c], {FONT2}
    mov es:[0x7e], cs
    sti
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''

def diff_records(orig, new):
    """元と翻訳後の EXE イメージの差分 → [(イメージ内の位置, 新しいバイト列)]"""
    h = struct.unpack_from('<H', orig, 8)[0] * 16
    a, b = orig[h:], new[h:]
    assert len(a) == len(b)
    runs = []; i = 0; n = len(a)
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and (a[j] != b[j] or (j + 6 < n and any(a[k] != b[k] for k in range(j, j + 6)))):
                j += 1
            runs.append((i, bytes(b[i:j]))); i = j
        else:
            i += 1
    return runs, a

def h12(bs):
    """常駐部の hash と同じ計算。h1 = rol(h1,1) + b、h2 = rol(h2 + b, 3)（16ビット）"""
    h1 = h2 = 0
    for x in bs:
        h1 = (((h1 << 1) | (h1 >> 15)) + x) & 0xFFFF
        h2 = (h2 + x) & 0xFFFF
        h2 = ((h2 << 3) | (h2 >> 13)) & 0xFFFF
    return h1, h2


def pack_list(runs, orig_img):
    """書き換えデータ（常駐部の apply_list が読む形）。元のバイト列の代わりにハッシュ値を入れる"""
    o0 = runs[0][0]
    anchor = bytes(orig_img[o0:o0 + ANCHOR_LEN])
    assert len(anchor) == ANCHOR_LEN
    qsum = sum(anchor[:8]) & 0xFFFF
    af = h12(anchor)
    # 探す方（イメージの先頭から順に、8バイトの合計とハッシュ値で見る）で、最初に当たるのが本当の位置であること
    first = None
    for p in range(len(orig_img) - ANCHOR_LEN):
        if (sum(orig_img[p:p + 8]) & 0xFFFF) == qsum and h12(orig_img[p:p + ANCHOR_LEN]) == af:
            first = p
            break
    if first != o0:
        sys.exit(f'目印が一意ではありません（{o0:x} / {first}）')
    out = bytearray(struct.pack('<HHHHHHHHH', len(runs), o0 >> 4, o0 & 15, (len(orig_img) + 15) // 16,
                                qsum, af[0], af[1], 0xFFFF, 0))
    assert len(out) == HDR
    for o, data in runs:
        rel = o - o0
        h1, h2 = h12(orig_img[o:o + len(data)])
        out += struct.pack('<HHHHH', rel >> 4, rel & 15, len(data), h1, h2) + data
    return bytes(out)

def build(game_dir, tdir, out_path, bdf=DEFAULT_BDF):
    import tempfile
    tmp = tempfile.mkdtemp()
    # 翻訳済み EXE を一時フォルダに作る（エンコーダーの状態も受け取る）
    import apply_translation as at
    from strdb import build_db
    work = []
    for fn in EXES:
        tsv = os.path.join(tdir, fn.replace('.EXE', '') + '.tsv')
        e, db = build_db(os.path.join(game_dir, fn), fn)
        work.append((fn, e, db, at.load_tsv(tsv)))
    enc = jpenc.Encoder([ja for *_, tr in work for (_, _, _, ja) in tr.values()])
    report = []; err = 0
    for fn, e, db, tr in work:
        err += at.apply(e, db, tr, enc, tmp, fn, report)
    print('\n'.join(report))
    if err: sys.exit('翻訳の適用でエラーがありました')
    lists = {}
    for fn in EXES:
        orig = open(os.path.join(game_dir, fn), 'rb').read()
        new = open(os.path.join(tmp, fn), 'rb').read()
        runs, oimg = diff_records(orig, new)
        lists[fn] = pack_list(runs, oimg)
        print(f'{fn}: 書き換え {len(runs)} か所, データ {len(lists[fn])} バイト')

    glyphs = load_bdf(bdf)
    # ---- フォント部（jpenc と同じデータ）----
    pool = {}
    missing = set()
    for (a, b) in enc.pairs:
        for x in (a, b):
            if x is not None and is_jp(x):
                k = x if ord(x) in glyphs else '？'
                if ord(x) not in glyphs: missing.add(x)
                if k not in pool: pool[k] = len(pool)
    if missing: sys.exit('フォントにない文字: ' + ''.join(sorted(missing)))
    qmark = bytes([0x3c, 0x66, 0x06, 0x0c, 0x18, 0x00, 0x18, 0x00])

    def layout(sizes_only):
        kw = dict(jmp_old=FAR_JMP(OLD10), call_old=FAR_CALL(OLD10), LEAD=LEAD, P2=P2,
                  jmp_old21=FAR_JMP(OLD21), call_old21=FAR_CALL(OLD21),
                  PENDING=PENDING, PLIST=PLIST, OLIST=OLIST)
        return kw
    # 1回目: 仮の値で大きさを測る / 2回目: 本当の値で作る
    vals = dict(FONT=0x9000, FONT2=0x9400, SLOT=0x9000, NPAIRS=0x9000, PAIRS=0x9000, QMARK=0x9000, NAMES=0x9000)
    for _ in range(2):
        kw = layout(False); kw.update(vals)
        res10 = _asm(RES10, CODE, kw)
        int21 = CODE + len(res10)
        kw21 = dict(kw)
        kw21['ident_a'] = IDENT.format(u='a', NAMES=vals['NAMES'])
        kw21['ident_b'] = IDENT.format(u='b', NAMES=vals['NAMES'])
        kw21['apply_sub'] = APPLY_SUB.format(LBASE=LBASE, LPTR=LPTR, LSEG=LSEG, LREM=LREM, FORCE=FORCE,
                                             ANCHOR_LEN=ANCHOR_LEN, HDR=HDR)
        res21 = _asm(RES21, int21, kw21)
        p = int21 + len(res21)
        QMARK = p; p += 8
        p = (p + 15) & ~15
        FONT = p; p += 2048
        NPAIRS = p; p += 2
        PAIRS = p; p += 4 * len(enc.pairs)
        GLY = p; p += 8 * len(pool)
        NAMES = p; p += 14 * len(EXES) + 1
        LISTS = {}
        for fn in EXES: LISTS[fn] = p; p += len(lists[fn])
        resident_end = p
        new_vals = dict(FONT=FONT, FONT2=FONT + 0x400, SLOT=FONT + 0xFE * 8, NPAIRS=NPAIRS,
                        PAIRS=PAIRS, QMARK=QMARK, NAMES=NAMES)
        if new_vals == vals: break
        vals = new_vals
    if resident_end > 0xF000: sys.exit('常駐部が大きすぎます')

    def ptr(ch):
        if ch is None: return 0
        if not is_jp(ch): return FONT + ord(ch) * 8
        return GLY + 8 * pool[ch if ord(ch) in glyphs else '？']
    pairs = bytearray()
    for (a, b), idx in sorted(enc.pairs.items(), key=lambda kv: kv[1]):
        pairs += struct.pack('<HH', ptr(a), ptr(b))
    upper = bytearray(1024)
    for ch, code in enc.single.items():
        upper[(code - 0x80) * 8:(code - 0x80) * 8 + 8] = glyphs[ord(ch)]
    names = bytearray()
    for fn in EXES:
        names += fn.encode('ascii').ljust(12, b'\0') + struct.pack('<H', LISTS[fn])
    names += b'\0'

    msg = 'U1JP: Ultima I Japanese patch loaded\r\n$'.encode('ascii')
    ikw = dict(OLD10=OLD10, OLD21=OLD21, FORCE=FORCE, INT10=CODE, INT21=int21, FONT=FONT, FONT2=FONT + 0x400,
               MSG=0x9000, PARAS=(resident_end + 15) // 16)
    init = _asm(INIT, resident_end, ikw)
    ikw['MSG'] = resident_end + len(init)
    init2 = _asm(INIT, resident_end, ikw); assert len(init2) == len(init)

    img = bytearray(b'\xe9' + struct.pack('<H', (resident_end - 0x103) & 0xFFFF))
    img += b'\0' * 4 + b'\0' + b'\0\0'            # old10, lead, p2
    img += b'\0' * 4 + b'\0' + b'\0' + b'\0\0' + b'\0\0'   # old21, pending, pad, plist, olist
    img += b'\0' * 10                                    # force, lbase, lptr, lseg, lrem
    assert 0x100 + len(img) == CODE
    img += res10 + res21 + qmark
    img += bytes(FONT - 0x100 - len(img))
    img += bytes(1024) + upper
    img += struct.pack('<H', len(enc.pairs)) + pairs
    for k in sorted(pool, key=lambda k: pool[k]): img += glyphs[ord(k)]
    img += names
    for fn in EXES: img += lists[fn]
    assert 0x100 + len(img) == resident_end
    img += init2 + msg
    open(out_path, 'wb').write(img)
    print(f'{out_path}: {len(img)} バイト（常駐 {resident_end - 0x100} バイト）')

if __name__ == '__main__':
    build(*sys.argv[1:])
