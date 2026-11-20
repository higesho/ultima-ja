# エンジン（jp_work/engine）用の日本語フォントのデータを作る
# 使い方: python make_jfont.py <出力フォルダ（engine/web/public/fonts）>
#   ja-misaki8.bin       美咲ゴシック第2（8×8、1988 年の見た目の 1 マス用）
#   ja-shinonome16.bin   東雲ゴシック 16（16×16、現代風の見た目の 1 マス用）
#   ja-shinonome16m.bin  東雲明朝 16（16×16、現代風の物語のページ用）
# 形（数はリトルエンディアン）: "U5JF"、字の数 u16、字の一辺 u8、1 字のバイト数 u8、
#   字のコード u16 × 字の数（Unicode、昇順）、字の形（1 行 = 一辺/8 バイト、上の行から、左のビットが最上位）× 字の数
#   半角（0x7F まで）は入れない（エンジンの英字の字形を使う）
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "font")
# JIS と Unicode の対応の揺れ: 東雲（JIS → euc_jp）と美咲（Unicode）と訳の文字をそろえる
ALIASES = {0x301C: [0xFF5E], 0x2016: [0x2225], 0x2212: [0xFF0D], 0x00A2: [0xFFE0], 0x00A3: [0xFFE1], 0x00AC: [0xFFE2],
           0x2014: [0x2015]}


def parse_bdf(path):
    """字ごとに (ENCODING, 幅, 高さ, x 位置, y 位置, 行のビット列) を返す。全体の囲み (幅, 高さ, x, y) も返す"""
    lines = open(path, encoding="latin-1").read().splitlines()
    box = None
    glyphs = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("FONTBOUNDINGBOX"):
            box = tuple(int(v) for v in ln.split()[1:5])
        if ln.startswith("STARTCHAR"):
            enc = bbx = None
            rows = []
            i += 1
            while not lines[i].startswith("ENDCHAR"):
                t = lines[i]
                if t.startswith("ENCODING"):
                    enc = int(t.split()[1])
                elif t.startswith("BBX"):
                    bbx = tuple(int(v) for v in t.split()[1:5])
                elif t == "BITMAP":
                    i += 1
                    while not lines[i].startswith("ENDCHAR"):
                        rows.append(int(lines[i], 16))
                        i += 1
                    break
                i += 1
            glyphs.append((enc, bbx, rows))
        i += 1
    return box, glyphs


def cells(box, glyphs, side, to_unicode):
    """一辺 side の升に置いた字の形: {Unicode: bytes}"""
    fw, fh, fx, fy = box
    out = {}
    stride = side // 8
    for enc, bbx, rows in glyphs:
        u = to_unicode(enc)
        if u is None or u < 0x80:
            continue
        w, h, x, y = bbx
        nbytes = (w + 7) // 8
        img = bytearray(stride * side)
        # 升の上端は全体の囲みの上端（fy + fh）。字の上端は y + h
        top = (fy + fh) - (y + h)
        left = x - fx
        for r, bits in enumerate(rows):
            yy = top + r
            if not 0 <= yy < side:
                continue
            for c in range(w):
                if bits & (1 << (nbytes * 8 - 1 - c)):
                    xx = left + c
                    if 0 <= xx < side:
                        img[yy * stride + xx // 8] |= 0x80 >> (xx % 8)
        out[u] = bytes(img)
    for src, dsts in ALIASES.items():
        for d in dsts:
            if src in out and d not in out:
                out[d] = out[src]
            if d in out and src not in out:
                out[src] = out[d]
    return out


def jis_to_unicode(enc):
    hi, lo = enc >> 8, enc & 0xFF
    try:
        s = bytes([hi | 0x80, lo | 0x80]).decode("euc_jp")
    except UnicodeDecodeError:
        return None
    return ord(s) if len(s) == 1 else None


def write(path, side, glyphs):
    codes = sorted(glyphs)
    bpg = side * side // 8
    blob = bytearray(b"U5JF" + struct.pack("<HBB", len(codes), side, bpg))
    blob += struct.pack(f"<{len(codes)}H", *codes)
    for c in codes:
        blob += glyphs[c]
    open(path, "wb").write(blob)
    print(f"{os.path.basename(path)}: {len(codes)} 字、{len(blob)} バイト")


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    box, g = parse_bdf(os.path.join(FONT, "misaki_gothic_2nd.bdf"))
    write(os.path.join(outdir, "ja-misaki8.bin"), 8, cells(box, g, 8, lambda e: e))
    for name, out in [("shnmk16.bdf", "ja-shinonome16.bin"), ("shnmk16min.bdf", "ja-shinonome16m.bin")]:
        box, g = parse_bdf(os.path.join(FONT, "shinonome-0.9.11", "bdf", name))
        write(os.path.join(outdir, out), 16, cells(box, g, 16, jis_to_unicode))


if __name__ == "__main__":
    main(sys.argv[1])
