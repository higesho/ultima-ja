# オープニングの後半（ガーディアンが消えたあと）の字幕の絵を、日本語の字の絵に作り替える
#   使い方: mkpatch.py から呼ぶ（make_intro_shapes() が {番号: シェイプ} を返す）
#           python mkintro.py 見本.png   で見本の絵を書き出す
# 元の絵は ENDSHAPE.FLX の 0x15〜0x1C（0x1B は空）。どれも 320×47、原点は (160, 0)、
# 色は 2 色（字が 11、まわり 1 ドットの縁取りが 0）。1 行の文は下半分、2 行の文は全体に描かれている。
# 字は東雲フォント 16 ドット（translation/endshape_ja.tsv の訳）で描く。
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mkjfont import read_bdf, jis_to_unicode
from u7shape import write_shape

W = os.path.join(HERE, '..')
BDF_DIR = os.path.join(W, 'font', 'dl_shinonome', 'shinonome-0.9.11', 'bdf')
FONT = 'shnmk16minb.bdf'
TSV = os.path.join(W, 'translation', 'endshape_ja.tsv')
INK, EDGE = 11, 0
SW, SH, ORG = 320, 47, 160
TOPS = {1: [28], 2: [5, 27]}      # 行の数ごとの、字の上端の位置


def load_font(name=FONT):
    fbb, glyphs = read_bdf(os.path.join(BDF_DIR, name))
    return fbb, jis_to_unicode(glyphs)


def load_texts(path=TSV):
    """{番号: [行, ...]}。1行「番号(16進)<TAB>行1|行2<TAB>原文」"""
    out = {}
    for line in open(path, encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        if not line or line.startswith('#'):
            continue
        k, ja = line.split('\t')[:2]
        out[int(k, 16)] = ja.split('|')
    return out


def draw_line(text, font, pix, top):
    fbb, glyphs = font
    fw, fh = fbb[0], fbb[1]
    width = fw * len(text)
    x0 = (SW - width) // 2
    for i, ch in enumerate(text):
        g = glyphs.get(ord(ch))
        if g is None:
            raise SystemExit(f'フォントに無い字: {ch!r}（{text}）')
        bw, bh, bx, by = g['bbx']
        gy0 = top + (fh + fbb[3]) - (bh + by)    # 上端をそろえる
        for r, bits in enumerate(g['rows']):
            for c in range(bw):
                if bits & (1 << (31 - c)):
                    pix[(x0 + i * fw + bx + c, gy0 + r)] = INK


def render(lines, font):
    pix = {}
    for text, top in zip(lines, TOPS[len(lines)]):
        draw_line(text, font, pix, top)
    edge = {}
    for (x, y) in pix:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                p = (x + dx, y + dy)
                if p not in pix and 0 <= p[0] < SW and 0 <= p[1] < SH:
                    edge[p] = EDGE
    pix.update(edge)
    assert all(0 <= x < SW and 0 <= y < SH for x, y in pix), lines
    return pix


def make_intro_shapes(font_name=FONT):
    font = load_font(font_name)
    return {idx: write_shape([(ORG, 0, SW, SH, render(lines, font))])
            for idx, lines in load_texts().items()}


def preview(out_png, font_name=FONT):
    """元の絵と日本語の絵を並べた見本（パレットは INTROPAL の 1 番）"""
    from PIL import Image
    from u7flex import read_flex
    from u7shape import read_shape
    static = os.path.join(W, '..', 'STATIC')
    _, ents = read_flex(os.path.join(static, 'ENDSHAPE.FLX'))
    _, pals = read_flex(os.path.join(static, 'INTROPAL.DAT'))
    pal = pals[1]
    new = make_intro_shapes(font_name)
    rows = []
    for idx in sorted(new):
        for data in (ents[idx], new[idx]):
            _, _, w, h, pix = read_shape(data)[0]
            im = Image.new('RGB', (w, h), (0, 0, 0))
            for (x, y), v in pix.items():
                im.putpixel((x, y), tuple(min(255, c * 4) for c in pal[v * 3:v * 3 + 3]))
            rows.append(im.resize((w * 2, h * 2), Image.NEAREST))
    c = Image.new('RGB', (SW * 2, sum(r.height + 4 for r in rows)), (90, 90, 90))
    y = 0
    for r in rows:
        c.paste(r, (0, y)); y += r.height + 4
    c.save(out_png)


if __name__ == '__main__':
    preview(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else FONT)
