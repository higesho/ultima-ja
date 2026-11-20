"""UW の日本語化の共通部分: 美咲フォントの読み込み、字の符号、keystone の 16 ビットの直し。
符号: 日本語の字（0x7F より上の字すべて）を 2 バイトにする。1 バイト目 0xC0〜0xFF、2 バイト目 0x80〜0xBF（64×64 = 4,096 字）。
英数字・記号（0x20〜0x7E）はそのまま 1 バイトで、ゲームのフォントで描く。"""
import os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, '..', 'font', 'misaki_gothic_2nd.bdf')


def load_bdf(path=BDF):
    """{Unicode: 8 行の絵（1 行 1 バイト、左が上位ビット）}"""
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


# 美咲フォントにない字を、ある字に置き換える
SUBST = {'～': '〜', '−': '－', '‐': '－', '–': '－', '—': '―', '･': '・', '“': '「', '”': '」', '‘': '’'}


# 行の頭に来てはいけない字（この前では切らない）と、行の終わりに来てはいけない字（この後では切らない）
NO_START = set('。、．，・：；？！）」』】〕｝〉》ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ…‥々〜～ゝゞヽヾ')
NO_END = set('（「『【〔｛〈《')


def is_jp(ch): return ord(ch) > 0x7e


def add_breaks(text, every=1):
    """日本語の字と字の間に空白を入れて、折り返しの切れ目にする（常駐部はこの空白を幅 0 にして描かない）。
    行頭禁則・行末禁則の所には入れない。every 字ごと（2 以上なら空白を減らす）"""
    out = []; run = 0
    for i, ch in enumerate(text):
        if i > 0:
            a = text[i - 1]
            if is_jp(a) and is_jp(ch) and ch not in NO_START and a not in NO_END:
                if run >= every:
                    out.append(' '); run = 0
        out.append(ch)
        run += 1
    return ''.join(out)


class Encoder:
    """singles: 1 バイトで書く字のバイト（0x80〜0xBF のうち、本編の文字の種類の表が 0 のもの）。
    残りの 0x80〜0xBF は組の 2 バイト目。字の番号: 1 バイトの字 i → i、組 → len(singles) + (1 バイト目 - 0xC0) × 2 バイト目の数 + 2 バイト目の番号"""
    def __init__(self, texts, glyphs, singles):
        freq = {}
        for t in texts:
            for ch in t:
                ch = SUBST.get(ch, ch)
                if ord(ch) > 0x7e: freq[ch] = freq.get(ch, 0) + 1
        self.missing = sorted(ch for ch in freq if ord(ch) not in glyphs)
        chars = sorted((ch for ch in freq if ord(ch) in glyphs), key=lambda c: (-freq[c], c))
        self.singles = list(singles)
        self.trails = [b for b in range(0x80, 0xC0) if b not in self.singles]
        cap = len(self.singles) + 64 * len(self.trails)
        if len(chars) > cap: raise RuntimeError('字が多すぎる: %d > %d' % (len(chars), cap))
        self.chars = chars
        self.index = {ch: i for i, ch in enumerate(chars)}
        # 美咲フォントは 8×8 の下 1 行が空き。巻物の 1 行目の上が切れないように 1 行下げる
        self.glyphs = b''.join(bytes(1) + glyphs[ord(ch)][:7] for ch in chars)

    def table(self):
        """常駐部の 256 バイトの表: 1 バイトの字 → 0x80 + 番号、組の 2 バイト目 → 番号（0〜63）、ほか 0xFF"""
        t = bytearray([0xFF] * 256)
        for i, b in enumerate(self.singles): t[b] = 0x80 + i
        for i, b in enumerate(self.trails): t[b] = i
        return bytes(t)

    def encode(self, text):
        out = bytearray()
        ns, nt = len(self.singles), len(self.trails)
        for ch in text:
            ch = SUBST.get(ch, ch)
            o = ord(ch)
            if o < 0x7f: out.append(o)
            elif ch in self.index:
                n = self.index[ch]
                if n < ns: out.append(self.singles[n])
                else:
                    n -= ns; out += bytes([0xC0 + n // nt, self.trails[n % nt]])
            else:
                out.append(0x3f)        # フォントにない字は ?
        return bytes(out)


def fix16(code, addr):
    """keystone が 16 ビットコードに混ぜてしまう 32 ビット形式の命令を、同じ長さの 16 ビット形式に直す
    （Martian Dreams の jpenc.py と同じもの）"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    b = bytearray(code)
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    pos = 0
    while pos < len(b):
        ins = next(md.disasm(bytes(b[pos:]), addr + pos), None)
        if ins is None: break
        x = bytes(b[pos:pos + ins.size])
        if x[0] == 0x66:
            if x[1] in (0xe9, 0xe8) and len(x) == 6:
                rel = struct.unpack_from('<i', x, 2)[0] + 3
                b[pos:pos + 6] = bytes([x[1]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[1] == 0x0f and 0x80 <= x[2] <= 0x8f and len(x) == 7:
                rel = struct.unpack_from('<i', x, 3)[0] + 3
                b[pos:pos + 7] = bytes([0x0f, x[2]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[1] in (0xca, 0xc2) and len(x) == 4:
                b[pos:pos + 4] = x[1:] + b'\x90'
            elif x[1] in (0xc3, 0xcb) and len(x) == 2:
                b[pos:pos + 2] = x[1:] + b'\x90'
            else:
                raise RuntimeError(f'直せない 32 ビット命令: {x.hex()} at {addr + pos:#x}')
        pos += ins.size
    return bytes(b)
