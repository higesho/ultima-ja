# Akalabeth（Ultima IX 付録の PC 移植版、DJGPP + Allegro 2.2）の日本語版を作る。
#
#   python tools/build_akjp.py <元の AK.EXE> <元の AK.DAT> <出力フォルダ>
#   出力: AKJP.COFF（日本語版の本体）と AJ.DAT（説明書きなどの訳文）。配布用の差分は make_patch.py で作る。
#
# しくみ
#   - AK.EXE は WDOSX の WFSE に入った DJGPP の COFF（4KB ごとに圧縮）。展開して書き換え、圧縮し直す。
#   - 文字は Allegro の textout / textout_centre / text_length の3つを横取りする。
#     日本語の字は 2 バイト（どちらも 0x80 以上）で 1 マス（8 ドット）。字形は美咲ゴシック。
#     字形を内蔵 8x8 フォントの 0xFF 番に写してから、元の textout で 1 字ずつ描く。
#     比例幅フォント（メニュー）の中でも同じ 8x8 の字で描き、高さだけそろえる。
#   - 訳文は元の場所に入れば元の場所へ、入らなければ使われていない SVGA ドライバの領域へ置き、参照を付け替える。
#   - 説明書きとロード・ブリティッシュの台詞は、訳文だけの AJ.DAT（圧縮なし）から読むように変える。
#     フォントの入った元の AK.DAT はそのまま使う。
import os, sys, struct, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wdx, coff, refs, alldat
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

ROOT = os.path.dirname(HERE)
FONT_BDF = os.path.join(ROOT, 'font', 'misaki_gothic_2nd.bdf')

# 元の関数
TEXTOUT, TEXTOUT_CENTRE, TEXT_LENGTH = 0x1c79c, 0x1c8ac, 0x1c9cc
BUILTIN_FONT = 0x52b68          # Allegro 内蔵の FONT（高さ 8）
SLOT = 0x52468 + (0xff - 0x20) * 8  # 内蔵 8x8 フォントの 0xFF 番の字形
FREE_LO, FREE_HI = 0x2a9b8, 0x30424  # 使われない SVGA / Mode-X / VESA ドライバの領域
INSTRUCT_LOAD = 0x3ea7               # 説明書きを読む load_datafile("ak.dat") の push


def load_bdf(path):
    glyphs = {}; cur = None; rows = None; bbx = None; asc = 7
    for line in open(path, encoding='latin1'):
        t = line.split()
        if not t: continue
        if t[0] == 'FONT_ASCENT': asc = int(t[1])
        elif t[0] == 'ENCODING': cur = int(t[1])
        elif t[0] == 'BBX': bbx = list(map(int, t[1:5]))
        elif t[0] == 'BITMAP': rows = []
        elif t[0] == 'ENDCHAR':
            w, h, xo, yo = bbx
            g = [0] * 8; top = asc - (yo + h)
            for i, r in enumerate(rows):
                y = top + i
                if 0 <= y < 8: g[y] = (int(r[:2], 16) >> xo) & 0xFF
            glyphs[cur] = bytes(g); rows = None
        elif rows is not None: rows.append(t[0])
    return glyphs


def is_jp(ch):
    return ord(ch) > 0x7e


class Enc:
    def __init__(self, texts, bdf):
        chars = sorted({ch for t in texts for ch in t if is_jp(ch)})
        self.glyph = load_bdf(bdf)
        missing = [ch for ch in chars if ord(ch) not in self.glyph]
        if missing: raise SystemExit('字形がない字: ' + ''.join(missing))
        self.chars = ['？'] + chars
        self.code = {ch: i for i, ch in enumerate(self.chars)}

    def enc(self, t):
        out = bytearray()
        for ch in t:
            if is_jp(ch):
                i = self.code[ch]
                out += bytes([0x80 | (i >> 7), 0x80 | (i & 0x7f)])
            else:
                out += ch.encode('ascii')
        return bytes(out)

    def glyphs(self):
        return b''.join(self.glyph[ord(ch)] for ch in self.chars)


def cells(t):
    return len(t)


HOOK = '''
    .byte 0xe9
    .long my_textout - . - 4
    .byte 0xe9
    .long my_text_length - . - 4
    .byte 0xe9
    .long my_textout_centre - . - 4
my_textout:
    mov eax, dword ptr [esp + 12]
t_scan:
    mov cl, byte ptr [eax]
    test cl, cl
    jz t_plain
    test cl, 0x80
    jnz t_jp
    inc eax
    jmp t_scan
t_plain:
    jmp tr_textout
t_jp:
    push ebp
    push esi
    push edi
    push ebx
    mov ebp, esp
    mov esi, dword ptr [ebp + 28]
    mov edi, dword ptr [ebp + 32]
t_loop:
    mov al, byte ptr [esi]
    test al, al
    jz t_done
    test al, 0x80
    jnz t_char
    mov ebx, {RUNBUF}
t_copy:
    mov byte ptr [ebx], al
    inc ebx
    inc esi
    mov al, byte ptr [esi]
    test al, al
    jz t_endrun
    test al, 0x80
    jz t_copy
t_endrun:
    mov byte ptr [ebx], 0
    push dword ptr [ebp + 40]
    push dword ptr [ebp + 36]
    push edi
    push {RUNBUF}
    push dword ptr [ebp + 24]
    push dword ptr [ebp + 20]
    call tr_textout
    add esp, 24
    push {RUNBUF}
    push dword ptr [ebp + 24]
    call tr_text_length
    add esp, 8
    add edi, eax
    jmp t_loop
t_char:
    movzx eax, byte ptr [esi]
    movzx ecx, byte ptr [esi + 1]
    test ecx, ecx
    jz t_done
    add esi, 2
    and eax, 0x7f
    and ecx, 0x7f
    shl eax, 7
    or eax, ecx
    cmp eax, {NGLYPH}
    jb t_gok
    xor eax, eax
t_gok:
    lea eax, [{GLYPHS} + eax * 8]
    mov ecx, dword ptr [eax]
    mov dword ptr [{SLOT}], ecx
    mov ecx, dword ptr [eax + 4]
    mov dword ptr [{SLOT} + 4], ecx
    mov edx, dword ptr [ebp + 24]
    xor ecx, ecx
    cmp dword ptr [edx], 8
    je t_y
    mov ecx, 4
    cmp dword ptr [edx], 16
    je t_y
    mov ecx, dword ptr [edx + 4]
    mov ecx, dword ptr [ecx]
    mov ecx, dword ptr [ecx + 4]
    shr ecx, 1
    sub ecx, 3
t_y:
    add ecx, dword ptr [ebp + 36]
    push dword ptr [ebp + 40]
    push ecx
    push edi
    push {ONECHAR}
    push {BUILTIN_FONT}
    push dword ptr [ebp + 20]
    call tr_textout
    add esp, 24
    add edi, 8
    jmp t_loop
t_done:
    pop ebx
    pop edi
    pop esi
    pop ebp
    ret

my_text_length:
    mov eax, dword ptr [esp + 8]
l_scan:
    mov cl, byte ptr [eax]
    test cl, cl
    jz l_plain
    test cl, 0x80
    jnz l_jp
    inc eax
    jmp l_scan
l_plain:
    jmp tr_text_length
l_jp:
    push ebp
    push esi
    push edi
    push ebx
    mov ebp, esp
    mov esi, dword ptr [ebp + 24]
    xor edi, edi
l_loop:
    mov al, byte ptr [esi]
    test al, al
    jz l_done
    test al, 0x80
    jz l_run
    cmp byte ptr [esi + 1], 0
    je l_done
    add esi, 2
    add edi, 8
    jmp l_loop
l_run:
    mov ebx, {RUNBUF}
l_copy:
    mov byte ptr [ebx], al
    inc ebx
    inc esi
    mov al, byte ptr [esi]
    test al, al
    jz l_endrun
    test al, 0x80
    jz l_copy
l_endrun:
    mov byte ptr [ebx], 0
    push {RUNBUF}
    push dword ptr [ebp + 20]
    call tr_text_length
    add esp, 8
    add edi, eax
    jmp l_loop
l_done:
    mov eax, edi
    pop ebx
    pop edi
    pop esi
    pop ebp
    ret

my_textout_centre:
    push ebp
    mov ebp, esp
    push dword ptr [ebp + 16]
    push dword ptr [ebp + 12]
    call my_text_length
    add esp, 8
    mov edx, eax
    shr edx, 31
    add eax, edx
    sar eax, 1
    mov ecx, dword ptr [ebp + 20]
    sub ecx, eax
    push dword ptr [ebp + 28]
    push dword ptr [ebp + 24]
    push ecx
    push dword ptr [ebp + 16]
    push dword ptr [ebp + 12]
    push dword ptr [ebp + 8]
    call my_textout
    add esp, 24
    pop ebp
    ret

tr_textout:
    sub esp, 12
    push ebp
    push edi
    jmp {TEXTOUT5}
tr_text_length:
    push edi
    mov eax, dword ptr [esp + 8]
    jmp {TEXTLEN5}
'''


def asm(src, addr):
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def label_addr(src, addr, label):
    """label までのコードの長さから番地を求める。"""
    head = src.split('\n' + label + ':')[0]
    return addr + len(asm(head, addr)) if head.strip() else addr


def jmp_rel(frm, to):
    return b'\xe9' + struct.pack('<i', to - (frm + 5))


def read_ja(path):
    rows = []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'): continue
        va, ja = line.split('\t', 1)
        rows.append((int(va, 16), ja))
    return rows


def prop_widths(dat):
    """AK.DAT の ARIAL_BLACK の字幅（32 番から）。"""
    p = 8; n = struct.unpack_from('>I', dat, 4)[0]
    for k in range(n):
        name = None
        while dat[p:p + 4] == b'prop':
            t = dat[p + 4:p + 8]; L = struct.unpack_from('>I', dat, p + 8)[0]
            if t == b'NAME': name = dat[p + 12:p + 12 + L]
            p += 12 + L
        s1 = struct.unpack_from('>I', dat, p + 4)[0]
        body = dat[p + 12:p + 12 + s1]; p += 12 + s1
        if name == b'ARIAL_BLACK':
            q = 2; ws = []
            for c in range(224):
                w, h = struct.unpack_from('>hh', body, q); q += 4 + w * h; ws.append(w)
            return ws
    raise SystemExit('ARIAL_BLACK がない')


def shape(en, ja, pw):
    """{c} {.} と、消し用の空白の処理。"""
    def width(t):
        return sum(8 if is_jp(ch) else pw[ord(ch) - 32] for ch in t)
    if ja.startswith('{c}'):
        ja = ja[3:]
        room = cells(en) - cells(ja)
        if room > 0:
            ja = ' ' * (room // 2) + ja + ' ' * (room - room // 2)
    if '{.}' in ja:
        head, tail = ja.split('{.}')
        ja = head
        while cells(ja + tail) < cells(en.rstrip(' ')):
            ja += '.'
        ja += tail
    if cells(ja) < cells(en):        # 前に出ていた長い文を消すため、英語と同じマス数まで空白で埋める
        ja += ' ' * (cells(en) - cells(ja))
    return ja


def main():
    exe_path, dat_path, outdir = sys.argv[1:4]
    exe = open(exe_path, 'rb').read()
    c = coff.Coff(wdx.unpack_exe(exe))
    dat = alldat.read_dat(dat_path)
    pw = prop_widths(dat)
    tr = os.path.join(ROOT, 'translation')
    ss = dict(refs.game_strings(c))
    rows = []
    for va, ja in read_ja(os.path.join(tr, 'ja.tsv')):
        if va not in ss:
            raise SystemExit('その番地に文字列がない: %06x' % va)
        rows.append((va, ss[va], shape(ss[va], ja, pw)))
    with open(os.path.join(ROOT, 'build', 'strings_en.tsv'), 'w', encoding='utf-8') as f:
        for va, en, ja in rows:
            f.write('%06x\t%s\t%s\n' % (va, en, ja))
    datnames = ['akins', 'aklb1', 'aklb2', 'aklb3']
    dattexts = {}
    for n in datnames:
        lines = open(os.path.join(tr, n + '.txt'), encoding='utf-8').read().rstrip('\n').split('\n')
        for l in lines:
            if cells(l) > 40: raise SystemExit('%s: 40 マスを超える行: %s' % (n, l))
        dattexts[n] = ';'.join(lines)
    enc = Enc([ja for _, _, ja in rows] + list(dattexts.values()), FONT_BDF)

    # 文字列の配置
    rf = refs.find_refs(c, {va for va, _, _ in rows})
    free = bytearray()
    FREE_DATA = FREE_LO + 0x400          # 先頭 1KB はコード
    moved = 0
    for va, en, ja in rows:
        b = enc.enc(ja)
        off = c.va2off(va)
        n = len(en)
        if len(b) <= n:
            c.d[off:off + n] = b + bytes(n - len(b))
            continue
        new = FREE_DATA + len(free)
        free += b + bytes(1)
        game_refs = [r for r in rf[va] if 0x1550 <= r[0] < refs.GAME_HI
                     and (r[2] == 'table' or r[2].split()[0] in ('push', 'mov'))]
        if not game_refs:
            raise SystemExit('参照が見つからない: %06x %r' % (va, en))
        for rva, roff, _ in game_refs:
            assert struct.unpack_from('<I', c.d, roff)[0] == va
            struct.pack_into('<I', c.d, roff, new)
        moved += 1

    # 説明書きとロード・ブリティッシュの文は、訳文だけの AJ.DAT から読む（フォントは元の AK.DAT のまま）
    ajname = FREE_DATA + len(free); free += b'aj.dat'+bytes(1)
    o = c.va2off(INSTRUCT_LOAD)
    assert c.d[o] == 0x68 and struct.unpack_from('<I', c.d, o + 1)[0] == 0x3cc8
    struct.pack_into('<I', c.d, o + 1, ajname)
    o = c.va2off(0x62c8)
    assert bytes(c.d[o:o + 7]) == b'ak.dat'+bytes(1)
    c.d[o:o + 7] = b'aj.dat'+bytes(1)

    # 字形と作業用の領域
    if len(free) % 8: free += b'\0' * (8 - len(free) % 8)
    glyph_va = FREE_DATA + len(free)
    free += enc.glyphs()
    runbuf = FREE_DATA + len(free); free += b'\0' * 256
    onechar = FREE_DATA + len(free); free += b'\xff\0\0\0'
    end = FREE_DATA + len(free)
    if end > FREE_HI:
        raise SystemExit('空き領域が足りない: %d バイト超過' % (end - FREE_HI))
    c.d[c.va2off(FREE_DATA):c.va2off(FREE_DATA) + len(free)] = free

    # 横取り部
    src = HOOK.format(RUNBUF=runbuf, NGLYPH=len(enc.chars), GLYPHS=glyph_va, SLOT=SLOT,
                      ONECHAR=onechar, BUILTIN_FONT=BUILTIN_FONT,
                      TEXTOUT5=TEXTOUT + 5, TEXTLEN5=TEXT_LENGTH + 5)
    code = asm(src, FREE_LO)
    assert len(code) <= 0x400, len(code)
    c.d[c.va2off(FREE_LO):c.va2off(FREE_LO) + len(code)] = code
    # 先頭の 3 つの入口（jmp rel32 の 5 バイトずつ）
    for k in range(3):
        assert code[5 * k] == 0xe9, code[:15].hex()
    a_out, a_len, a_centre = FREE_LO, FREE_LO + 5, FREE_LO + 10
    # 元の関数の頭を確かめてから飛び先を書く
    for frm, head in ((TEXTOUT, '83ec0c5557'), (TEXTOUT_CENTRE, '83ec0c5557'), (TEXT_LENGTH, '578b442408')):
        assert bytes(c.d[c.va2off(frm):c.va2off(frm) + 5]) == bytes.fromhex(head)
    for frm, to in ((TEXTOUT, a_out), (TEXTOUT_CENTRE, a_centre), (TEXT_LENGTH, a_len)):
        c.d[c.va2off(frm):c.va2off(frm) + 5] = jmp_rel(frm, to)

    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, 'AKJP.COFF'), 'wb').write(bytes(c.d))
    open(os.path.join(outdir, 'AJ.DAT'), 'wb').write(text_dat([enc.enc(dattexts[n]) + b'\0' for n in datnames]))
    print('文字列 %d（移した分 %d）、字 %d、空き残り %d バイト'
          % (len(rows), moved, len(enc.chars), FREE_HI - end))


def text_dat(bodies):
    """DATA オブジェクトだけのデータファイル（圧縮なし）。"""
    out = bytearray(b'slh.ALL.' + struct.pack('>I', len(bodies)))
    for b in bodies:
        out += b'DATA' + struct.pack('>II', len(b), len(b)) + b
    return bytes(out)


def replace_dat_texts(d, texts):
    """ALL. データファイルの DATA オブジェクト（名前で指定）の中身を入れ替える。"""
    assert d[:4] == b'ALL.'
    n = struct.unpack_from('>I', d, 4)[0]
    out = bytearray(d[:8]); p = 8
    for k in range(n):
        q = p; name = None
        while d[p:p + 4] == b'prop':
            t = d[p + 4:p + 8]; L = struct.unpack_from('>I', d, p + 8)[0]
            if t == b'NAME': name = d[p + 12:p + 12 + L].decode()
            p += 12 + L
        typ = d[p:p + 4]; s1 = struct.unpack_from('>I', d, p + 4)[0]
        body = d[p + 12:p + 12 + s1]
        if typ == b'DATA' and name in texts:
            body = texts[name]
        out += d[q:p] + typ + struct.pack('>II', len(body), len(body)) + body
        p += 12 + s1
    out += d[p:]
    return bytes(out)


if __name__ == '__main__':
    main()
