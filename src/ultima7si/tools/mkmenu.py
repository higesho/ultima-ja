# MAINSHP.FLX のメニューの絵（英語の字の絵）を、日本語の字の絵に作り替える
#   使い方: mkpatch.py から呼ぶ（make_menu_shapes(ents) が ents を書き換える）
# 元の絵は高さ 8 ドット。日本語は jfont8.bin（美咲フォント 8×8）で描く。
# 色は元の絵から取る: 行ごとにいちばん多い色を字の色にし、元の絵の影の色で右下に影を付ける。
import os, struct, collections
HERE = os.path.dirname(os.path.abspath(__file__))
from u7shape import read_shape, write_shape

# 番号: [枚ごとの日本語]
MENU = {
    0x04: ['オープニングを見る'] * 2,
    0x05: ['新しく始める'] * 2,
    0x08: ['旅を続ける'] * 2,
    0x06: ['スタッフを見る'] * 2,
    0x11: ['名言集を見る'] * 2,
    0x12: ['エンディングを見る'] * 2,
    0x07: ['メニューに戻る'] * 2,
    0x0C: ['名前：'] * 2,
    0x0A: ['性別：'] * 2,
    0x0B: ['男', '女'],
    0x19: ['顔：'] * 2,      # サーペントアイルのキャラクター作成（BG の写しに足した）
}

def load_jfont(path):
    d = open(path, 'rb').read()
    n, w, h, bpr = struct.unpack_from('<HBBB', d, 6)
    cps = struct.unpack_from(f'<{n}I', d, 12)
    base = 12 + 4 * n
    glyphs = {cp: d[base + i * h * bpr: base + (i + 1) * h * bpr] for i, cp in enumerate(cps)}
    return w, h, bpr, glyphs

def render(text, font, row_colors, shadow):
    w, h, bpr, glyphs = font
    pix = {}
    x0 = 0
    for ch in text:
        g = glyphs.get(ord(ch))
        if g:
            for y in range(h):
                row = int.from_bytes(g[y * bpr:(y + 1) * bpr], 'big')
                for x in range(w):
                    if row & (1 << (bpr * 8 - 1 - x)):
                        # 影（右下）を先に置き、字で上書きする
                        if shadow is not None and (x0 + x + 1, y + 1) not in pix and y + 1 < h:
                            pix[(x0 + x + 1, y + 1)] = shadow
                        pix[(x0 + x, y)] = row_colors[min(y, len(row_colors) - 1)]
        x0 += w
    width = max((x for x, _ in pix), default=0) + 1
    return width, pix

def colors_of(pix, h):
    """行ごとにいちばん多い色と、全体で2番目に多い系統（影）の色"""
    rows = []
    for y in range(h):
        c = collections.Counter(v for (px, py), v in pix.items() if py == y)
        rows.append(c.most_common(1)[0][0] if c else rows[-1] if rows else 0)
    allc = collections.Counter(pix.values()).most_common()
    main = set(rows)
    shadow = next((c for c, _ in allc if c not in main), None)
    return rows, shadow

def make_menu_shapes(ents, jfont_path, pal=None):
    """pal（6 ビットの 768 バイト）を渡すと、影の色を「字の色でない、いちばん暗い色」にする（SI で足した）"""
    font = load_jfont(jfont_path)
    for idx, texts in MENU.items():
        frames = read_shape(ents[idx])
        new = []
        for k, (xl, ya, w, h, pix) in enumerate(frames):
            text = texts[k] if k < len(texts) else texts[-1]
            rows, shadow = colors_of(pix, h)
            if pal is not None:
                others = [c for c in set(pix.values()) if c not in rows[:-1]]
                if others:
                    shadow = min(others, key=lambda c: sum(pal[c * 3:c * 3 + 3]))
            width, jp = render(text, font, rows, shadow)
            new.append((0, ya, width, h, jp))
        ents[idx] = write_shape(new)
    return len(MENU)
