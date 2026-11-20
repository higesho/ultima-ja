# Build JPFONT.COM : a DOS TSR that makes BIOS INT 10h teletype output show Japanese.
#
#  - Hooks INT 10h.
#  - After every mode set (AH=00h) it points INT 43h / INT 1Fh at its own 256-char 8x8 font,
#    so BIOS draws characters with our glyphs in CGA/EGA/Tandy graphics modes.
#    Single-byte 0xA1-0xDF (half-width katakana) get Misaki 8x8 katakana glyphs.
#  - On AH=0Eh (teletype) it handles Shift-JIS: the lead byte is held, and on the trail byte the
#    glyph is copied into slot chars 0xFE/0xFF and printed through the original BIOS.
#    Mode "2" (default): 2 bytes -> 2 cells (glyph doubled horizontally, 16x8).
#    Mode "1" (/1 on the command line): 2 bytes -> 1 cell (plain 8x8 glyph).
#
# usage: python build_jpfont.py <misaki.bdf> <out.com> <charset.txt>...
#   charset files: UTF-8 text; every full-width char in them is put into the kanji table.
import sys, struct, unicodedata
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

def load_bdf(path):
    glyphs = {}; cur = None; rows = None; bbx = None
    asc = 7
    for line in open(path, encoding='latin1'):
        t = line.split()
        if not t: continue
        if t[0] == 'FONT_ASCENT': asc = int(t[1])
        elif t[0] == 'ENCODING': cur = int(t[1])
        elif t[0] == 'BBX': bbx = list(map(int, t[1:5]))
        elif t[0] == 'BITMAP': rows = []
        elif t[0] == 'ENDCHAR':
            w, h, xo, yo = bbx
            g = [0] * 8
            top = asc - (yo + h)
            for i, r in enumerate(rows):
                y = top + i
                if 0 <= y < 8: g[y] = (int(r[:2], 16) >> xo) & 0xFF
            glyphs[cur] = bytes(g); rows = None
        elif rows is not None: rows.append(t[0])
    return glyphs

def halfwidth_glyph(glyphs, code):
    """glyph for single-byte SJIS 0xA1-0xDF, drawn with the full-width Misaki form"""
    ch = bytes([code]).decode('cp932')
    special = {'ﾞ': '゛', 'ﾟ': '゜'}  # dakuten / handakuten
    fw = special.get(ch) or unicodedata.normalize('NFKC', ch)
    return glyphs.get(ord(fw), bytes(8))

FAR_JMP  = lambda a: f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"   # jmp far cs:[a]
SETVEC = '''    push ax
    push ds
    xor ax, ax
    mov ds, ax
    cli
    mov word ptr [0x10c], {FONT}
    mov [0x10e], cs
    mov word ptr [0x7c], {FONT2}
    mov [0x7e], cs
    sti
    pop ds
    pop ax'''
FAR_CALL = lambda a: f".byte 0x2e,0xff,0x1e,{a & 0xff},{a >> 8}"   # call far cs:[a]

# ---- resident part (starts at 0x100) ----
OLD10, LEAD, WIDE = 0x103, 0x107, 0x108
RES = '''
int10:
    cmp ah, 0
    je setmode
    cmp ah, 0x0e
    je tty
chain:
    {jmp_old}
setmode:
    pushf
    {call_old}
{setvec}
    iret
tty:
    cmp byte ptr cs:[{LEAD}], 0
    jne trail
    cmp al, 0x81
    jb chain
    cmp al, 0x9f
    jbe savelead
    cmp al, 0xe0
    jb chain
    cmp al, 0xfc
    ja chain
savelead:
    mov byte ptr cs:[{LEAD}], al
    iret
trail:
    push ax
    push bx
    push cx
    push si
    push di
    push ds
    push es
    mov ah, byte ptr cs:[{LEAD}]
    mov byte ptr cs:[{LEAD}], 0
    push cs
    pop ds
    push cs
    pop es
{setvec}
    mov di, {CODES}
    mov cx, word ptr [{NCODES}]
    cld
    jcxz notfound
    repne scasw
    jne notfound
    sub di, {CODES2}
    shl di, 1
    shl di, 1
    lea si, [di + {GLYPHS}]
    mov di, {SLOT}
    cmp byte ptr [{WIDE}], 1
    je onecell
    mov bx, {DBL}
    mov cx, 8
rowloop:
    lodsb
    mov ah, al
    push cx
    mov cl, 4
    shr al, cl
    pop cx
    xlatb
    mov [di], al
    mov al, ah
    and al, 0x0f
    xlatb
    mov [di + 8], al
    inc di
    loop rowloop
    jmp output
onecell:
    mov cx, 4
    rep movsw
    jmp output
notfound:
    mov si, {QMARK}
    mov di, {SLOT}
    mov cx, 8
    rep movsw
output:
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop bx
    mov ax, 0x0efe
    pushf
    {call_old}
    cmp byte ptr cs:[{WIDE}], 1
    je done
    mov ax, 0x0eff
    pushf
    {call_old}
done:
    pop ax
    iret
'''

INIT = '''
    mov si, 0x81
    mov cl, byte ptr [0x80]
    xor ch, ch
    jcxz noargs
argloop:
    lodsb
    cmp al, 0x31
    jne nextarg
    mov byte ptr [{WIDE}], 1
nextarg:
    loop argloop
noargs:
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
    push ds
    mov ax, 0x1130
    mov bh, 4
    int 0x10
    push es
    pop ds
    mov si, bp
    push cs
    pop es
    mov di, {FONT2}
    mov cx, 0x200
    rep movsw
    pop ds
    mov si, {KANA}
    mov di, {KANADST}
    mov cx, {KANAWORDS}
    rep movsw
    mov ax, 0x3510
    int 0x21
    mov word ptr [{OLD10}], bx
    mov word ptr [{OLD10}+2], es
    mov ax, 0x2510
    mov dx, {INT10}
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

def asm(src, addr, **kw):
    if 'FONT2' in kw: kw = dict(kw, setvec=SETVEC.format(**kw))
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    enc, _ = ks.asm(src.format(**kw), addr)
    return bytes(enc)

def build(bdf, out, charsets):
    glyphs = load_bdf(bdf)
    chars = set()
    for p in charsets:
        for ch in open(p, encoding='utf-8').read():
            try: b = ch.encode('cp932')
            except UnicodeEncodeError: continue
            if len(b) == 2: chars.add(ch)
    chars = sorted(chars, key=lambda c: c.encode('cp932'))
    missing = [c for c in chars if ord(c) not in glyphs]
    if missing: print('no glyph:', ''.join(missing))
    codes = b''.join(struct.pack('<H', int.from_bytes(c.encode('cp932'), 'big')) for c in chars)
    gdata = b''.join(glyphs.get(ord(c), bytes(8)) for c in chars)
    kana = b''.join(halfwidth_glyph(glyphs, c) for c in range(0xA1, 0xE0))
    dbl = bytes(sum(((n >> b) & 1) * (3 << (2 * b)) for b in range(4)) for n in range(16))
    qmark = bytes([0x3c, 0x66, 0x06, 0x0c, 0x18, 0x00, 0x18, 0x00]) * 2

    header_len = 3 + 4 + 1 + 1 + 3   # jmp(3) old10(4) lead(1) wide(1) pad(3) -> int10 at 0x10c
    INT10 = 0x100 + header_len
    kw = dict(jmp_old=FAR_JMP(OLD10), call_old=FAR_CALL(OLD10), LEAD=LEAD, WIDE=WIDE,
              FONT=0x9000, FONT2=0x9400, CODES=0x9000, CODES2=0x9002, NCODES=0x9000,
              GLYPHS=0x9000, SLOT=0x9000, DBL=0x9000, QMARK=0x9000)
    res = asm(RES, INT10, **kw)
    # lay out resident data after the handler
    p = INT10 + len(res)
    DBL = p; p += 16
    QMARK = p; p += 16
    p = (p + 15) & ~15
    FONT = p; p += 2048
    NCODES = p; p += 2
    CODES = p; p += len(codes)
    GLYPHS = p; p += len(gdata)
    resident_end = p
    kw.update(FONT=FONT, FONT2=FONT + 0x400, CODES=CODES, CODES2=CODES + 2, NCODES=NCODES,
              GLYPHS=GLYPHS, SLOT=FONT + 0xFE * 8, DBL=DBL, QMARK=QMARK)
    res2 = asm(RES, INT10, **kw)
    assert len(res2) == len(res), 'resident size changed between passes'
    msg = ('JPFONT: Japanese font TSR installed ({} kanji, mode {})\r\n$'
           .format(len(chars), '1/2').encode('ascii'))
    INIT_AT = resident_end
    ikw = dict(WIDE=WIDE, OLD10=OLD10, INT10=INT10, FONT=FONT, FONT2=FONT + 0x400,
               KANA=0x9000, KANADST=FONT + 0xA1 * 8, KANAWORDS=len(kana) // 2,
               MSG=0x9000, PARAS=(resident_end + 15) // 16)
    init = asm(INIT, INIT_AT, **ikw)
    ikw.update(KANA=INIT_AT + len(init), MSG=INIT_AT + len(init) + len(kana))
    init2 = asm(INIT, INIT_AT, **ikw)
    assert len(init2) == len(init)

    img = bytearray()
    img += b'\xe9' + struct.pack('<h', INIT_AT - 0x103)   # jmp init
    img += b'\0\0\0\0'          # old10
    img += b'\0'                # lead
    img += b'\2'                # wide
    img += b'JPF'               # signature / pad
    assert 0x100 + len(img) == INT10
    img += res2
    img += dbl + qmark
    img += bytes(FONT - 0x100 - len(img))
    img += bytes(2048)
    img += struct.pack('<H', len(chars)) + codes + gdata
    assert 0x100 + len(img) == INIT_AT
    img += init2 + kana + msg
    open(out, 'wb').write(img)
    print(f'{out}: {len(img)} bytes, resident {resident_end - 0x100} bytes, {len(chars)} kanji/kana')

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3:])
