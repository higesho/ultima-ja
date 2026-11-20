# 絵に描かれた文字を日本語にした CREATE.LZC を作る
#   0 番の束: タイトルのメニュー 5 項目（1〜10 = 普通の色 6 と選んだ色 14、どちらも黒い影つき。11〜15 = 影なしの色 14）
#   4 番の束: キャラクター作成の徳の板（1 = Courage 赤 39、4 = Truth 青 119、6 = Love 緑 106。地は 72）
# 使い方: python se_graphics.py <ゲームのフォルダ> <出力フォルダ>
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sefmt import lzc_items, lzc_raw, save_lzc  # noqa: E402
from seshape import sub_items, decode, encode, pack_items  # noqa: E402

FONT_MENU = os.path.join(HERE, "..", "font", "k8x12.bdf")      # Unicode、全角 8×12
FONT_PLATE = os.path.join(HERE, "..", "font", "shnmk14b.bdf")  # 東雲 14 ドット太字、JIS X 0208

# メニューの並び（0 番の束の 1・3・5・7・9 と 11〜15）
MENU = ["新しい人物を作る",            # Create New Character
        "旅を続ける",                  # Journey Onward
        "これまでの物語",              # The Story So Far...
        "前の人物を取り込む",          # Import Old Character
        "サベージ・エンパイアとは"]    # About The Savage Empire
# 徳の板: (束の中の番号, 字の色, 訳)
PLATES = [(1, 39, "勇気"), (4, 119, "真実"), (6, 106, "愛")]
PLATE_BG = 72
PLATE_X0 = 22          # 板の左の目の絵の右（字はここから右の幅の真ん中に置く）


def load_bdf(path, jis=False):
    """BDF → {文字: (幅, 高さ, 左, 下, 行の並び)}"""
    out = {}
    cur = bbx = rows = None
    dw = 8
    for line in open(path, encoding="latin1"):
        t = line.split()
        if not t:
            continue
        if t[0] == "ENCODING":
            cur = int(t[1])
        elif t[0] == "DWIDTH":
            dw = int(t[1])
        elif t[0] == "BBX":
            bbx = list(map(int, t[1:5]))
        elif t[0] == "BITMAP":
            rows = []
        elif t[0] == "ENDCHAR":
            if jis:
                try:
                    ch = bytes([(cur >> 8) | 0x80, (cur & 0xFF) | 0x80]).decode("euc_jp")
                except UnicodeDecodeError:
                    ch = None
            else:
                ch = chr(cur)
            if ch:
                out[ch] = (bbx, [int(r, 16) for r in rows], len(rows[0]) * 4 if rows else 8, dw)
            rows = None
        elif rows is not None:
            rows.append(t[0])
    return out


def render(font, text, asc, gap=0):
    """文字列 → 点の集合 {(x, y)}（1字の送りは DWIDTH + gap。asc は基準線の上の高さ）"""
    pts = set()
    x = 0
    for ch in text:
        (w, h, xo, yo), rows, bits, dw = font[ch]
        top = asc - (yo + h)
        for i, r in enumerate(rows):
            for b in range(w):
                if r >> (bits - 1 - b) & 1:
                    pts.add((x + xo + b, top + i))
        x += dw + gap
    return pts


def bold(pts):
    return pts | {(x + 1, y) for x, y in pts}


def menu_shapes():
    font = load_bdf(FONT_PLATE, jis=True)
    shapes = {}
    for k, text in enumerate(MENU):
        body = render(font, text, 12)            # 東雲 14 ドット太字（基準線の上 12）
        shadow = {(x + 1, y + 1) for x, y in body} - body
        w = max(x for x, _ in body | shadow) + 1
        h = max(y for _, y in body | shadow) + 1
        for col, j in ((6, 1 + 2 * k), (14, 2 + 2 * k)):
            px = {p: col for p in body}
            px.update({p: 0 for p in shadow})
            shapes[j] = encode(w, h, 0, 0, px)
        shapes[11 + k] = encode(w, h, 0, 0, {p: 14 for p in body})
    return shapes


def plate_shapes(old):
    font = load_bdf(FONT_PLATE, jis=True)
    shapes = {}
    for j, col, text in PLATES:
        w, h, hx, hy, px = decode(old[j])
        px = {p: (PLATE_BG if c == col else c) for p, c in px.items()}   # 英語の字を地の色で消す
        pts = render(font, text, 12)
        tw = max(x for x, _ in pts) + 1
        th = max(y for _, y in pts) + 1
        ox = PLATE_X0 + (w - PLATE_X0 - tw) // 2
        oy = (h - th) // 2
        for x, y in pts:
            if (ox + x, oy + y) in px:
                px[(ox + x, oy + y)] = col
        shapes[j] = encode(w, h, hx, hy, px)
    return shapes


def build(gamedir, outdir):
    path = os.path.join(gamedir, "CREATE.LZC")
    rows = lzc_raw(open(path, "rb").read())
    items = lzc_items(open(path, "rb").read())
    for idx, make in ((0, lambda old: menu_shapes()), (4, plate_shapes)):
        old = sub_items(items[idx][1])
        new = list(old)
        for j, s in make(old).items():
            new[j] = s
        data = pack_items(new)
        if len(data) > len(items[idx][1]):
            sys.exit(f"CREATE.LZC {idx}: 元より大きい {len(data)} > {len(items[idx][1])}")
        rows[idx] = (2, data)
    save_lzc(os.path.join(outdir, "CREATE.LZC"), rows)
    print("CREATE.LZC: メニュー 5 項目と徳の板 3 枚を日本語にした")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
