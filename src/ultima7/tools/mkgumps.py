# 窓の絵（GUMPS.VGA）の英字を、日本語の字に描き替える
#   使い方: mkpatch.py から呼ぶ（make_gump_shapes(元の項目の一覧, jfont8.bin) が {番号: シェイプ} を返す）
#           python mkgumps.py jfont8.bin 見本.png   で見本の絵を書き出す
# ・能力の窓（0x2F）: 項目名（Strength: など 10 個）。無地（色 216）の枠に黒（色 0）で描かれている。
#   数字は Exult が右寄せで書く（Stats_gump の texty と同じ高さ）。
# ・持ち物の窓（0x39〜0x3F、0x41〜0x44 の 11 人分）: 「CARRYING」「STONES」。茶色（色 11）の地に黒。
#   間の重さの数字（例 6/36）は Exult が y+120 に書く（7 ドット）。
# 字は美咲フォント 8 ドット（字の部分は 7×7）。英字を地の色で消してから描く。
import os, sys, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from u7shape import read_shape, write_shape

STATS = 0x2F
STATS_LABELS = ['腕力：', '器用さ：', '知力：', '戦闘：', '魔法：', '体力：', 'マナ：', '経験：', 'レベル：', '訓練：']
STATS_TOPS = [17, 26, 35, 46, 55, 66, 75, 86, 95, 104]    # 英字の上端（Stats_gump の texty とほぼ同じ）
STATS_X = 32
BODIES = list(range(0x39, 0x40)) + list(range(0x41, 0x45))
CARRY_TOP, CARRY_TEXT = 112, '所持'          # 足元の絵の間（横 66〜88）に収め、数字との間を 1 ドット空ける
STONE_TOP, STONE_TEXT = 127, 'ストーン'      # 数字（120〜126）の下、縁（134）の上
BOX_X, BOX_W = 28, 102                       # Actor_gump が数字を中央に置く範囲
INK = 0


def load_jfont(path):
    d = open(path, 'rb').read()
    n, w, h, bpr = struct.unpack_from('<HBBB', d, 6)
    cps = struct.unpack_from(f'<{n}I', d, 12)
    base = 12 + 4 * n
    return w, h, bpr, {cp: d[base + i * h * bpr: base + (i + 1) * h * bpr] for i, cp in enumerate(cps)}


def draw(pix, text, font, x0, top, color=INK):
    w, h, bpr, glyphs = font
    for i, ch in enumerate(text):
        g = glyphs.get(ord(ch))
        if g is None:
            raise SystemExit(f'フォントに無い字: {ch!r}（{text}）')
        for y in range(h):
            row = int.from_bytes(g[y * bpr:(y + 1) * bpr], 'big')
            for x in range(w):
                if row & (1 << (bpr * 8 - 1 - x)):
                    pix[(x0 + i * w + x, top + y)] = color


def erase(pix, x0, x1, y0, y1, bg, colors=(INK,)):
    """範囲の中の英字の色（黒と、ふちのぼかしの色）を地の色にする"""
    n = 0
    for (x, y), v in list(pix.items()):
        if x0 <= x <= x1 and y0 <= y <= y1 and v in colors:
            pix[(x, y)] = bg; n += 1
    return n


def stats_shape(data, font):
    (xl, ya, w, h, pix), = read_shape(data)
    assert erase(pix, 30, 125, 16, 111, 216) > 300
    for text, top in zip(STATS_LABELS, STATS_TOPS):
        draw(pix, text, font, STATS_X, top)
    return write_shape([(xl, ya, w, h, pix)])


def body_shape(data, font):
    (xl, ya, w, h, pix), = read_shape(data)
    assert erase(pix, 40, 120, 114, 133, 11, (INK, 12)) > 100    # 英字は黒（0）とぼかし（12）
    fw = font[0]
    for text, top in ((CARRY_TEXT, CARRY_TOP), (STONE_TEXT, STONE_TOP)):
        draw(pix, text, font, BOX_X + (BOX_W - fw * len(text)) // 2, top)
    return write_shape([(xl, ya, w, h, pix)])


def make_gump_shapes(ents, jfont8):
    font = load_jfont(jfont8)
    out = {STATS: stats_shape(ents[STATS], font)}
    for i in BODIES:
        out[i] = body_shape(ents[i], font)
    return out


def preview(jfont8, out_png):
    """元の絵と描き替えた絵を並べた見本（数字は見本用に描き足す）"""
    from PIL import Image
    from u7flex import read_flex
    static = os.path.join(HERE, '..', '..', 'STATIC')
    _, pals = read_flex(os.path.join(static, 'PALETTES.FLX'))
    pal = [p for p in pals if p][0]
    _, ents = read_flex(os.path.join(static, 'GUMPS.VGA'))
    new = make_gump_shapes(ents, jfont8)
    ims = []
    for i in (STATS, 0x39, 0x42):
        for data in (ents[i], new[i]):
            (_, _, w, h, pix), = read_shape(data)
            im = Image.new('RGB', (w, h), (255, 0, 255))
            for (x, y), v in pix.items():
                im.putpixel((x, y), tuple(min(255, c * 4) for c in pal[v * 3:v * 3 + 3]))
            ims.append(im.resize((w * 3, h * 3), Image.NEAREST))
    c = Image.new('RGB', (sum(im.width + 6 for im in ims[:2]), sum(im.height + 6 for im in ims[::2])), (60, 60, 60))
    for k, im in enumerate(ims):
        c.paste(im, ((k % 2) * (ims[0].width + 6), (k // 2) * (im.height + 6)))
    c.save(out_png)


if __name__ == '__main__':
    preview(sys.argv[1], sys.argv[2])
