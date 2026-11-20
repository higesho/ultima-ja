# -*- coding: utf-8 -*-
"""16番の漢字フォントを作り、英語版の U8FONTS.FLX に足して書き出す。

ScummVM の shiftjis_to_ultima8 に合わせたフレーム番号に字を置く:
  0〜127   半角英数（そのままの番号）
  33区（記号）   257−34+点     35区（英数）   365−48+点
  36区（ひらがな）444−33+点    37区（カタカナ）538−33+点
  48〜79区（第1水準漢字） 632−33+(区−48)×94+点
色番号 3 が字の本体（ScummVM が場面ごとの色に塗り替える）、縁取りは 0（黒）。
'@' は会話の選択肢の印（色番号 1〜3）。

使い方: python -I build_jpfont.py <英語版 U8FONTS.FLX> <出力 U8FONTS.FLX> <フォント>
  フォントの書き方: bdf:<ファイル>  または  ttf:<ファイル>:<大きさ>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from u8shape import read_flex, write_flex, write_shape, Frame

BODY, EDGE = 3, 0
NFRAMES = 632 - 33 + 31 * 94 + 126 + 1      # 79区126点まで


class BDF:
    """BDF を読む。glyph(ch) は (送り幅, 基準線から見た点の一覧) を返す。"""

    def __init__(self, path):
        self.g = {}
        self.ascent = self.descent = 0
        lines = open(path, encoding='latin1').read().split('\n')
        i = 0
        while i < len(lines):
            t = lines[i].split()
            if t and t[0] == 'FONT_ASCENT':
                self.ascent = int(t[1])
            elif t and t[0] == 'FONT_DESCENT':
                self.descent = int(t[1])
            elif t and t[0] == 'STARTCHAR':
                enc = dw = None
                bbx = None
                bits = []
                i += 1
                while not lines[i].startswith('ENDCHAR'):
                    u = lines[i].split()
                    if u[0] == 'ENCODING':
                        enc = int(u[1])
                    elif u[0] == 'DWIDTH':
                        dw = int(u[1])
                    elif u[0] == 'BBX':
                        bbx = list(map(int, u[1:5]))
                    elif u[0] == 'BITMAP':
                        i += 1
                        while not lines[i].startswith('ENDCHAR'):
                            bits.append(int(lines[i], 16))
                            i += 1
                        break
                    i += 1
                w, h, xo, yo = bbx
                nb = ((w + 7) // 8) * 8
                pts = []
                for r, v in enumerate(bits):
                    for x in range(w):
                        if v >> (nb - 1 - x) & 1:
                            # 基準線から上がマイナス
                            pts.append((xo + x, -(yo + h - 1 - r) - 1))
                self.g[enc] = (dw, pts)
            i += 1

    def glyph(self, ch):
        return self.g.get(ord(ch))


class TTF:
    """ドットの形をした TTF を、そのドットの大きさで描く（ぼかしなし）。"""

    def __init__(self, path, size):
        from PIL import ImageFont
        self.font = ImageFont.truetype(path, size)
        self.ascent, self.descent = self.font.getmetrics()
        self.size = size

    def glyph(self, ch):
        from PIL import Image, ImageDraw
        if self.font.getmask(ch).size == (0, 0) and ch != ' ':
            return None
        adv = int(round(self.font.getlength(ch)))
        W, H = adv + 8, self.ascent + self.descent + 8
        img = Image.new('1', (W, H), 0)
        ImageDraw.Draw(img).text((2, 2 + self.ascent), ch, font=self.font, fill=1, anchor='ls')
        px = img.load()
        pts = [(x - 2, y - 2 - self.ascent) for y in range(H) for x in range(W) if px[x, y]]
        return adv, pts


def make_frame(adv, pts, asc, h):
    """点の一覧から、縁取り付きのフレームを作る。送り幅は adv+1（縁取りの分）。"""
    w = adv + 1
    on = set((x + 1, y + 1 + asc) for x, y in pts)     # フレームの中の位置（左と上に縁取り 1 ドット）
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            if (x, y) in on:
                row.append(BODY)
            elif any((x + dx, y + dy) in on for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                row.append(EDGE)
            else:
                row.append(None)
        rows.append(row)
    return Frame(w, h, 0, asc + 1, rows)


def bullet(asc, h):
    """会話の選択肢の印（英語版の '@' と同じ 3×3 の印）。"""
    w = 7
    rows = [[None] * w for _ in range(h)]
    mid = (asc + 1) - max(2, asc // 3)      # 字の真ん中あたり
    pat = [[1, 2, 1], [2, 3, 2], [1, 2, 1]]
    for y in range(5):
        for x in range(5):
            inner = 1 <= y <= 3 and 1 <= x <= 3
            rows[mid - 2 + y][x] = pat[y - 1][x - 1] if inner else EDGE
    return Frame(w, h, 0, asc + 1, rows)


def frame_index(ku, ten):
    if ku == 33:
        return 257 - 34 + ten
    if ku == 35:
        return 365 - 48 + ten
    if ku == 36:
        return 444 - 33 + ten
    if ku == 37:
        return 538 - 33 + ten
    if 48 <= ku <= 79:
        return 632 - 33 + (ku - 48) * 94 + ten
    return None


def jis_char(ku, ten):
    try:
        return bytes([ku + 0x80, ten + 0x80]).decode('euc_jp')
    except UnicodeDecodeError:
        return None


def load_font(spec):
    kind, rest = spec.split(':', 1)
    if kind == 'bdf':
        return BDF(rest)
    path, size = rest.rsplit(':', 1)
    return TTF(path, int(size))


def build(src, dst, spec):
    f = load_font(spec)
    missing = []
    glyphs = {}      # フレーム番号 -> (送り幅, 点)
    for c in range(0x20, 0x7F):
        g = f.glyph(chr(c))
        if g:
            glyphs[c] = g
    for ku in [33, 35, 36, 37] + list(range(48, 80)):
        for ten in range(33, 127):
            ch = jis_char(ku, ten)
            i = frame_index(ku, ten)
            if ch is None or i is None:
                continue
            g = f.glyph(ch)
            if not g:
                missing.append(ch)
                continue
            glyphs[i] = g
    # 実際に字がある範囲で、基準線の上と下の高さを決める（フォントの余白は使わない）
    ys = [y for adv, pts in glyphs.values() for x, y in pts]
    asc, desc = -min(ys), max(ys) + 1
    h = asc + desc + 2
    frames = [None] * NFRAMES
    for i, (adv, pts) in glyphs.items():
        frames[i] = make_frame(adv, pts, asc, h)
    frames[ord('@')] = bullet(asc, h)
    count = sum(1 for i in glyphs if i >= 256)
    full_adv = f.glyph('漢')[0]
    empty = Frame(4, h, 0, asc + 1, [[None] * 4 for _ in range(h)])
    frames = [fr or empty for fr in frames]
    raw = open(src, 'rb').read()
    entries = read_flex(raw)
    assert len(entries) == 16
    entries.append(write_shape(bytes([(full_adv or 8) + 1, 0, h, 0]), frames))
    open(dst, 'wb').write(write_flex(raw[:0x80], entries))
    print('%s: 全角 %d 字（無い字 %d）、行の高さ %d → %s' % (spec, count, len(missing), h, dst))
    if missing:
        print('  無い字の例:', ''.join(missing[:40]))


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3])
