# ステータスの窓（GUMPS.VGA の 42 番）と戦闘の窓（58〜63 番）の見出しを日本語にした絵を作る
#   mkpatch.py から呼ぶ（make_gumps(出力フォルダ, jfont8.bin)）。単独で: python mkgumps.py 出力フォルダ
# 原作の絵は写さない。原作の絵からは形（どの点が枠・升目・字・石か）と色番号だけを読み取り、
#   枠と升目 … 同じ形に色番号を置き直す
#   英語の字 … 升目の塗りの色にする（消す）
#   左右の石の模様 … 自作の模様（同じ系統の灰色を、決まった乱数で散らしたもの）にする
# そのうえで、日本語の見出しを美咲フォント（8×8）で描く。
import os, sys, random, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from u7flex import read_flex, write_flex
from u7shape import read_shape, write_shape
from mkmenu import load_jfont

STATIC = os.path.join(HERE, '..', '..', 'STATIC')
FILL = {214, 216}                       # 升目の塗り
STONE = set(range(120, 132))            # 石の灰色（124〜129 あたり）
INK = 0                                 # 字と外の線の色

# 番号: 見出し（上から順）。ステータスの窓は左寄せ、戦闘の窓は升目の中央
STATS = ['筋力：', '器用：', '知力：', '戦闘：', '魔力：', '体力：', 'マナ：', '経験：', 'レベル：', '訓練：']
CSTATS = ['戦闘', '体力', '作戦', '守り', '魔力', 'マナ']
TARGETS = {42: (STATS, 'left')}
# ステータスの窓で Exult が数字を描く行の上端（gumps/Stats_gump.cc の texty）。見出しもこの行に置く
STATS_Y = [17, 26, 35, 46, 55, 67, 76, 86, 95, 104]
for n in range(58, 64):
    TARGETS[n] = (CSTATS, 'center')

def strip_text(pix):
    """升目の中の字（左右とも塗りにはさまれた黒の並び）を消す。消した点の一覧を返す"""
    rows = collections.defaultdict(dict)
    for (x, y), c in pix.items():
        rows[y][x] = c
    removed = []
    for y, row in rows.items():
        xs = sorted(row)
        i = 0
        while i < len(xs):
            x = xs[i]
            if row[x] != INK:
                i += 1; continue
            j = i
            while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1 and row[xs[j + 1]] == INK:
                j += 1
            left, right = row.get(xs[i] - 1), row.get(xs[j] + 1)
            if left in FILL and right in FILL:
                for k in range(i, j + 1):
                    pix[(xs[k], y)] = left; removed.append((xs[k], y))
            i = j + 1
    return removed

def clusters(points):
    """消した点を、見出しごとのかたまり（行の並びで区切る）にまとめる: [(左, 上, 右, 下)]"""
    ys = sorted({y for _, y in points})
    groups = []; cur = []
    for y in ys:
        if cur and y > cur[-1] + 2:
            groups.append(cur); cur = []
        cur.append(y)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        ps = [(x, y) for x, y in points if g[0] <= y <= g[-1]]
        out.append((min(x for x, _ in ps), g[0], max(x for x, _ in ps), g[-1]))
    return out

def stone(pix, seed):
    """石の点を、自作の模様に置きかえる（同じ系統の灰色を、かたまりができるよう散らす）"""
    rnd = random.Random(seed)
    grays = [124, 125, 126, 127, 128, 129]
    pts = [p for p, c in pix.items() if c in STONE]
    # 5 ドットおきの格子点に明るさを決め、そのあいだをなめらかにつなぎ（双線形）、点ごとに少しゆらす
    grid = {}
    def g(i, j):
        if (i, j) not in grid:
            grid[(i, j)] = rnd.uniform(0, len(grays) - 1)
        return grid[(i, j)]
    for x, y in sorted(pts):
        i, fx = divmod(x, 5); j, fy = divmod(y, 5)
        fx /= 5; fy /= 5
        v = (g(i, j) * (1 - fx) * (1 - fy) + g(i + 1, j) * fx * (1 - fy)
             + g(i, j + 1) * (1 - fx) * fy + g(i + 1, j + 1) * fx * fy)
        v += rnd.uniform(-0.8, 0.8)
        pix[(x, y)] = grays[max(0, min(len(grays) - 1, round(v)))]

def draw(pix, text, x0, y0, font):
    w, h, bpr, glyphs = font
    x = x0
    for ch in text:
        g = glyphs.get(ord(ch))
        if g:
            for yy in range(h):
                row = int.from_bytes(g[yy * bpr:(yy + 1) * bpr], 'big')
                for xx in range(w):
                    if row & (1 << (bpr * 8 - 1 - xx)):
                        pix[(x + xx, y0 + yy)] = INK
        x += w

def text_width(text, font):
    w, h, bpr, glyphs = font
    # 美咲フォントは右と下が 1 ドットあく
    return len(text) * w - 1

def make_gumps(out, jfont8):
    head, ents = read_flex(os.path.join(STATIC, 'GUMPS.VGA'))
    font = load_jfont(jfont8)
    new = [None] * len(ents)
    for idx, (labels, align) in TARGETS.items():
        frames = []
        for k, (xl, ya, w, h, pix) in enumerate(read_shape(ents[idx])):
            pix = dict(pix)
            removed = strip_text(pix)
            if align == 'left':
                l0 = min(x for x, _ in removed)
                boxes = [(l0, y, l0, y + 6) for y in STATS_Y]
            else:
                boxes = clusters(removed)
            if len(boxes) != len(labels):
                raise SystemExit(f'gumps {idx}/{k}: 見出しのかたまりが {len(boxes)} 個（{len(labels)} 個のはず）')
            stone(pix, seed=idx * 16 + k)
            for (l, t, r, b), text in zip(boxes, labels):
                tw = text_width(text, font)
                y = t + (b - t + 1 - 7) // 2
                if align == 'left':
                    x = l
                else:
                    # 升目の左右の端（塗りの続くところ）の中央に置く
                    cy = (t + b) // 2
                    cl = l
                    while pix.get((cl - 1, cy)) in FILL:
                        cl -= 1
                    cr = r
                    while pix.get((cr + 1, cy)) in FILL:
                        cr += 1
                    x = cl + (cr - cl + 1 - tw) // 2
                draw(pix, text, x, y, font)
            frames.append((xl, ya, w, h, pix))
        new[idx] = write_shape(frames)
    title = 'Ultima VII Serpent Isle Japanese gumps'.encode('ascii').ljust(0x50, b'\0')
    write_flex(os.path.join(out, 'gumps.vga'), title + head[0x50:0x80], new)
    return sum(e is not None for e in new)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    out = sys.argv[1]
    n = make_gumps(out, os.path.join(out, 'jfont8.bin'))
    print(f'gumps.vga: {n} 個の絵（ほかは空）')
