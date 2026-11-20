# Japanese text encoding for Ultima I + the matching font TSR (JPFONT.COM).
#
# Encoding (1 byte = 1 screen cell, so the game's layout never shifts):
#   0x20-0x7E        ASCII (BIOS ROM font)
#   0x80,0xA0-0xDF,0xFD  "single" codes: one frequent Japanese char each (glyph placed in the font table)
#   lead+trail       lead 0x81-0x9F / 0xE0-0xFC, trail 0x40-0xFF: a PAIR of characters drawn in 2 cells
#                    (a pair may also be one char + filler when no partner exists; then 2 bytes -> 1 cell)
# The TSR hooks INT 10h: after a mode set it points INT 43h/1Fh at its font; on AH=0Eh it decodes pairs,
# copies each glyph into slot 0xFE and prints it through the original BIOS.
import struct, unicodedata
from keystone import Ks, KS_ARCH_X86, KS_MODE_16

SINGLE_CODES = [0x80] + list(range(0xA0, 0xE0)) + [0xFD]
LEADS = list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD))
TRAILS = list(range(0x40, 0x100))
PAIR_ASCII = set(' .,!?:;-()"\'')        # ASCII chars that may share a pair with a Japanese char

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

def is_jp(ch): return ord(ch) > 0x7e

class Encoder:
    def __init__(self, texts):
        freq = {}
        for t in texts:
            for ch in t:
                if is_jp(ch): freq[ch] = freq.get(ch, 0) + 1
        top = sorted(freq, key=lambda c: (-freq[c], c))[:len(SINGLE_CODES)]
        self.single = {ch: SINGLE_CODES[i] for i, ch in enumerate(top)}
        self.pairs = {}          # (a, b) -> code index ; b may be None
        self.freq = freq

    def segment(self, t):
        """DP: list of units; unit = ('a', ch) ascii / ('s', ch) single / ('p', a, b) pair"""
        n = len(t); INF = (1 << 30,)
        best = [None] * (n + 1); best[n] = ((0, 0, 0), None)
        for i in range(n - 1, -1, -1):
            ch = t[i]; opts = []
            def add(cost, unit, j):
                c2 = best[j][0]
                opts.append(((cost[0] + c2[0], cost[1] + c2[1], cost[2] + c2[2]), (unit, j)))
            nxt = t[i + 1] if i + 1 < n else None
            if not is_jp(ch):
                add((0, 0, 0), ('a', ch), i + 1)
                if ch in PAIR_ASCII and nxt is not None and is_jp(nxt):
                    add((0, 1, 1), ('p', ch, nxt), i + 2)
            else:
                if ch in self.single: add((0, 0, 0), ('s', ch), i + 1)
                if nxt is not None and (is_jp(nxt) or nxt in PAIR_ASCII):
                    add((0, 0 if is_jp(nxt) else 1, 1), ('p', ch, nxt), i + 2)
                add((1, 0, 1), ('p', ch, None), i + 1)
            best[i] = min(opts, key=lambda o: o[0])
        units = []; i = 0
        while i < n:
            unit, j = best[i][1]; units.append(unit); i = j
        return units

    def encode(self, t):
        out = bytearray()
        for u in self.segment(t):
            if u[0] == 'a': out += u[1].encode('latin1')
            elif u[0] == 's': out.append(self.single[u[1]])
            else:
                key = (u[1], u[2])
                if key not in self.pairs: self.pairs[key] = len(self.pairs)
                idx = self.pairs[key]
                if idx >= len(LEADS) * len(TRAILS): raise RuntimeError('too many pairs')
                out += bytes([LEADS[idx // len(TRAILS)], TRAILS[idx % len(TRAILS)]])
        return bytes(out)

# ---------------------------------------------------------------- TSR
FAR_JMP = lambda a: f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"
FAR_CALL = lambda a: f".byte 0x2e,0xff,0x1e,{a & 0xff},{a >> 8}"
OLD10, LEAD, P2 = 0x103, 0x107, 0x108          # dword, byte, word
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
COPY = '''    mov di, {SLOT}
    mov cx, 4
    cld
    rep movsw'''
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
    cmp al, 0x40
    jb notfound
    mov cl, al
    mov al, ah
    sub al, 0x81
    cmp al, 0x1f
    jb leadok
    sub al, 0x40
leadok:
    mov bl, 0xc0
    mul bl
    sub cl, 0x40
    xor ch, ch
    add ax, cx
    cmp ax, word ptr [{NPAIRS}]
    jae notfound
    shl ax, 1
    shl ax, 1
    mov si, ax
    add si, {PAIRS}
    mov ax, word ptr [si + 2]
    mov word ptr [{P2}], ax
    mov si, word ptr [si]
    jmp render
notfound:
    mov si, {QMARK}
    mov word ptr [{P2}], 0
render:
{copy}
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop bx
    mov ax, 0x0efe
    pushf
    {call_old}
    cmp word ptr cs:[{P2}], 0
    je done
    push cx
    push si
    push di
    push ds
    push es
    push cs
    pop ds
    push cs
    pop es
    mov si, word ptr [{P2}]
{copy}
    pop es
    pop ds
    pop di
    pop si
    pop cx
    mov ax, 0x0efe
    pushf
    {call_old}
done:
    pop ax
    iret
'''
INIT = '''
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

def _asm(src, addr, kw):
    kw = dict(kw)
    if 'SLOT' in kw:
        kw['setvec'] = SETVEC.format(**kw)
        kw['copy'] = COPY.format(**kw)
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src.format(**kw), addr)
    return fix16(bytes(enc), addr)

def fix16(code, addr):
    """keystone が 16ビットコードに混ぜてしまう 32ビット形式の命令を、同じ長さの 16ビット形式に直す"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    b = bytearray(code)
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    pos = 0
    while pos < len(b):
        ins = next(md.disasm(bytes(b[pos:]), addr + pos), None)
        if ins is None: break
        x = bytes(b[pos:pos + ins.size])
        if x[0] == 0x66:
            if x[1] in (0xe9, 0xe8) and len(x) == 6:            # jmp/call near rel32
                rel = struct.unpack_from('<i', x, 2)[0] + 3
                b[pos:pos + 6] = bytes([x[1]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[1] == 0x0f and 0x80 <= x[2] <= 0x8f and len(x) == 7:   # jcc near rel32
                rel = struct.unpack_from('<i', x, 3)[0] + 3
                b[pos:pos + 7] = bytes([0x0f, x[2]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[1] in (0xca, 0xc2) and len(x) == 4:          # retf/ret imm16
                b[pos:pos + 4] = x[1:] + b'\x90'
            elif x[1] in (0xc3, 0xcb) and len(x) == 2:          # ret/retf
                b[pos:pos + 2] = x[1:] + b'\x90'
            else:
                raise RuntimeError(f'直せない 32ビット命令: {x.hex()} at {addr + pos:#x}')
        pos += ins.size
    return bytes(b)

def build_tsr(enc, glyphs, out_path):
    missing = set()
    def g(ch):
        if ch is None: return None
        if not is_jp(ch): return ('rom', ord(ch))
        if ord(ch) not in glyphs: missing.add(ch); return ('jp', '？')
        return ('jp', ch)
    # glyph pool
    pool = {}
    for (a, b) in enc.pairs:
        for x in (a, b):
            if x is not None and is_jp(x):
                k = x if ord(x) in glyphs else '？'
                if ord(x) not in glyphs: missing.add(x)
                if k not in pool: pool[k] = len(pool)
    qmark = bytes([0x3c, 0x66, 0x06, 0x0c, 0x18, 0x00, 0x18, 0x00])
    INT10 = 0x10c
    kw = dict(jmp_old=FAR_JMP(OLD10), call_old=FAR_CALL(OLD10), LEAD=LEAD, P2=P2,
              FONT=0x9000, FONT2=0x9400, SLOT=0x9000, NPAIRS=0x9000, PAIRS=0x9000, QMARK=0x9000)
    res = _asm(RES, INT10, kw)
    p = INT10 + len(res)
    QMARK = p; p += 8
    p = (p + 15) & ~15
    FONT = p; p += 2048
    NPAIRS = p; p += 2
    PAIRS = p; p += 4 * len(enc.pairs)
    GLY = p; p += 8 * len(pool)
    resident_end = p
    if resident_end > 0xF000: raise RuntimeError('TSR too big')
    kw.update(FONT=FONT, FONT2=FONT + 0x400, SLOT=FONT + 0xFE * 8, NPAIRS=NPAIRS, PAIRS=PAIRS, QMARK=QMARK)
    res2 = _asm(RES, INT10, kw)
    assert len(res2) == len(res)
    def ptr(ch):
        if ch is None: return 0
        if not is_jp(ch): return FONT + ord(ch) * 8
        k = ch if ord(ch) in glyphs else '？'
        return GLY + 8 * pool[k]
    pairs = bytearray()
    for (a, b), idx in sorted(enc.pairs.items(), key=lambda kv: kv[1]):
        pairs += struct.pack('<HH', ptr(a), ptr(b))
    upper = bytearray(1024)
    for ch, code in enc.single.items():
        gl = glyphs.get(ord(ch))
        if gl is None: missing.add(ch); gl = qmark
        upper[(code - 0x80) * 8:(code - 0x80) * 8 + 8] = gl
    msg = f'JPFONT: Japanese text TSR ({len(enc.single)} single, {len(enc.pairs)} pairs)\r\n$'.encode()
    ikw = dict(OLD10=OLD10, INT10=INT10, FONT=FONT, FONT2=FONT + 0x400, MSG=0x9000,
               PARAS=(resident_end + 15) // 16)
    init = _asm(INIT, resident_end, ikw)
    ikw['MSG'] = resident_end + len(init)
    init2 = _asm(INIT, resident_end, ikw); assert len(init2) == len(init)

    img = bytearray(b'\xe9' + struct.pack('<h', resident_end - 0x103))
    img += b'\0' * 4 + b'\0' + b'\0\0' + b'JP'     # old10, lead, p2, pad -> 0x10c
    assert 0x100 + len(img) == INT10
    img += res2 + qmark
    img += bytes(FONT - 0x100 - len(img))
    img += bytes(1024) + upper
    img += struct.pack('<H', len(enc.pairs)) + pairs
    for k in sorted(pool, key=lambda k: pool[k]): img += glyphs[ord(k)]
    assert 0x100 + len(img) == resident_end
    img += init2 + msg
    open(out_path, 'wb').write(img)
    return dict(size=len(img), resident=resident_end - 0x100, pairs=len(enc.pairs),
                glyphs=len(pool), missing=''.join(sorted(missing)))
