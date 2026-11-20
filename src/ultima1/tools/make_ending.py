# エンディングの日本語版の絵 NIJ.BIN を作る
#   ゲームの NIF.BIN と同じ形（320×168、1 ドット 1 ビット、左が上位ビット、1 行 40 バイト）。
#   原作の絵は使わず、translation/ending_ja.txt の訳を美咲フォントで描くだけ。
#   1 行 40 字、行の間は 1 行（8 ドット）あける。段落の間はさらに 8 ドットあける。
# 使い方: python make_ending.py <出力 NIJ.BIN> [見本の PNG]
import os, sys
from jpenc import load_bdf

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT = os.path.join(HERE, '..', 'translation', 'ending_ja.txt')
BDF = os.path.join(HERE, '..', 'font', 'dl', 'misaki_gothic_2nd.bdf')
W, H, COLS = 320, 168, 40
NO_HEAD = set('、。，．・：；？！ー」』）〕］｝〉》ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々…‥')


def wrap(par):
    """40 字ずつに切る。行の頭に来てはいけない字は、前の行の最後の字ごと次の行へ送る"""
    lines, cur = [], ''
    for ch in par:
        if len(cur) == COLS:
            if ch in NO_HEAD:
                lines.append(cur[:-1]); cur = cur[-1]
            else:
                lines.append(cur); cur = ''
        cur += ch
    if cur: lines.append(cur)
    return lines


def main(out, png=None):
    glyphs = load_bdf(BDF)
    pars = [p.replace('\n', '') for p in open(TEXT, encoding='utf-8').read().strip().split('\n\n')]
    rows = []                         # (y, 行の文字列)
    y = 0
    for i, par in enumerate(pars):
        if i: y += 8
        for line in wrap(par):
            rows.append((y, line)); y += 16
    if y - 8 > H: sys.exit(f'字が多すぎて入らない（{y - 8} ドット）')
    bmp = bytearray(W * H // 8)
    missing = set()
    for y0, line in rows:
        for cx, ch in enumerate(line):
            g = glyphs.get(ord(ch))
            if g is None: missing.add(ch); continue
            for r in range(8):
                bmp[(y0 + r) * (W // 8) + cx] = g[r]
    if missing: sys.exit('美咲フォントにない字: ' + ''.join(sorted(missing)))
    open(out, 'wb').write(bmp)
    print(out, len(bmp), 'バイト、', len(rows), '行、下の端', y - 8, 'ドット')
    for _, l in rows: print('  ' + l)
    if png:
        from PIL import Image
        im = Image.frombytes('1', (W, H), bytes(bmp)).convert('L').resize((W * 3, H * 3), 0)
        im.save(png)


if __name__ == '__main__':
    main(*sys.argv[1:])
