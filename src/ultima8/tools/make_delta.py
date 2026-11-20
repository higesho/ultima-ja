# -*- coding: utf-8 -*-
"""英語版のファイルから日本語版のファイルを作るための差分データ（u8jp.dlt）を作る。

差分は「元のファイルの○バイト目から△バイト写す」（COPY）と「新しいバイト列を足す」（INSERT）の並び。
INSERT に入るのは訳と書き換えた数値だけで、元のゲームのデータはほとんど入らない
（12 バイト以上一致する所はすべて COPY にする）。

形式（すべてリトルエンディアン）:
  "U8JPDLT1"  u32 ファイル数
  ファイルごと:
    u16 長さ + 出力の相対パス（UTF-8）  u16 長さ + 元の相対パス（UTF-8）
    u32 元の大きさ  u32 元の CRC32  u32 出力の大きさ  u32 出力の CRC32  u32 命令の数
    命令: u8 0 = COPY  u32 元の位置  u32 長さ
          u8 1 = INSERT  u32 長さ  バイト列

使い方: python -I tools/make_delta.py <出力 .dlt> [一致とみなす長さ]   （先に build_jp.py で test/u8jp を作っておく）
"""
import sys, os, struct, zlib

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SRC = os.path.normpath(os.path.join(ROOT, '..', 'ENGLISH'))
DST = os.path.join(ROOT, 'test', 'u8jp')

# (出力の相対パス, 元の相対パス)
FILES = [
    ('USECODE/JUSECODE.FLX', 'USECODE/EUSECODE.FLX'),
    ('STATIC/EINTRO.SKF', 'STATIC/EINTRO.SKF'),
    ('STATIC/U8FONTS.FLX', 'STATIC/U8FONTS.FLX'),
]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 6      # この長さ以上一致したら COPY にする


def diff(src, dst):
    """貪欲法で COPY / INSERT の並びを作る。"""
    index = {}
    for i in range(0, len(src) - K + 1):
        key = src[i:i + K]
        if key not in index:
            index[key] = i
    ops = []
    lit = bytearray()
    j = 0
    n = len(dst)
    last_src_end = 0
    while j < n:
        best = None
        if j + K <= n:
            # まず直前の COPY の続きを試す（同じ並びが続くことが多い）
            for cand in (last_src_end, index.get(dst[j:j + K])):
                if cand is None or cand + K > len(src) or src[cand:cand + K] != dst[j:j + K]:
                    continue
                L = K
                while j + L < n and cand + L < len(src) and src[cand + L] == dst[j + L]:
                    L += 1
                if best is None or L > best[1]:
                    best = (cand, L)
        if best:
            if lit:
                ops.append((1, bytes(lit)))
                lit = bytearray()
            ops.append((0, best[0], best[1]))
            j += best[1]
            last_src_end = best[0] + best[1]
        else:
            lit.append(dst[j])
            j += 1
    if lit:
        ops.append((1, bytes(lit)))
    return ops


def apply(src, ops):
    out = bytearray()
    for op in ops:
        if op[0] == 0:
            out += src[op[1]:op[1] + op[2]]
        else:
            out += op[1]
    return bytes(out)


def main():
    outpath = sys.argv[1]
    buf = bytearray(b'U8JPDLT1') + struct.pack('<I', len(FILES))
    for dname, sname in FILES:
        src = open(os.path.join(SRC, sname), 'rb').read()
        dst = open(os.path.join(DST, dname), 'rb').read()
        ops = diff(src, dst)
        assert apply(src, ops) == dst
        lit = sum(len(o[1]) for o in ops if o[0] == 1)
        cp = sum(o[2] for o in ops if o[0] == 0)
        print('%s: 命令 %d、写す %d バイト、新しい %d バイト' % (dname, len(ops), cp, lit))
        for s in (dname, sname):
            b = s.encode('utf-8')
            buf += struct.pack('<H', len(b)) + b
        buf += struct.pack('<IIIII', len(src), zlib.crc32(src), len(dst), zlib.crc32(dst), len(ops))
        for op in ops:
            if op[0] == 0:
                buf += struct.pack('<BII', 0, op[1], op[2])
            else:
                buf += struct.pack('<BI', 1, len(op[1])) + op[1]
    open(outpath, 'wb').write(buf)
    print('→ %s（%d バイト）' % (outpath, len(buf)))


main()
