# BDF の日本語フォントを、改造 Exult が読む jfontN.bin に変える
#   使い方: python mkjfont.py 入力.bdf 出力.bin
# 全角の字（幅がフォントの枠と同じ字）だけを、Unicode の 0x80 以上から取り出す。
# JIS X 0208 の番号で並んだ BDF（東雲フォントなど）は Unicode に直して入れる。
import struct, sys

def read_bdf(path):
    fbb = None; glyphs = {}; cur = None; bitmap = None
    for line in open(path, encoding='latin-1'):
        t = line.split()
        if not t: continue
        k = t[0]
        if k == 'FONTBOUNDINGBOX':
            fbb = tuple(map(int, t[1:5]))
        elif k == 'STARTCHAR':
            cur = {}
        elif k == 'ENCODING' and cur is not None:
            cur['cp'] = int(t[1])
        elif k == 'DWIDTH' and cur is not None:
            cur['dw'] = int(t[1])
        elif k == 'BBX' and cur is not None:
            cur['bbx'] = tuple(map(int, t[1:5]))
        elif k == 'BITMAP':
            bitmap = []
        elif k == 'ENDCHAR':
            cur['rows'] = bitmap; bitmap = None
            if cur.get('cp', -1) >= 0:
                glyphs[cur['cp']] = cur
            cur = None
        elif bitmap is not None:
            bitmap.append(int(k, 16) << (32 - len(k) * 4))   # 左詰めの 32 ビット
    return fbb, glyphs

# EUC-JP の変換表と Windows（CP932）の変換表で番号が違う字。両方で引けるようにする
ALIAS = {0x301C: 0xFF5E, 0x2016: 0x2225, 0x2212: 0xFF0D, 0x00A2: 0xFFE0, 0x00A3: 0xFFE1, 0x00AC: 0xFFE2}

def jis_to_unicode(glyphs):
    out = {}
    for code, g in glyphs.items():
        hi, lo = code >> 8, code & 0xFF
        try:
            ch = bytes([hi | 0x80, lo | 0x80]).decode('euc_jp')
        except UnicodeDecodeError:
            continue
        if len(ch) != 1:
            continue
        cp = ord(ch)
        out[cp] = g
        if cp in ALIAS:
            out[ALIAS[cp]] = g
    return out

def is_jis(path):
    for line in open(path, encoding='latin-1'):
        if line.startswith('CHARSET_REGISTRY') or line.startswith('FONT '):
            if 'JISX0208' in line.upper().replace('.', '').replace(' ', '') or 'JISX0208' in line.upper():
                return True
        if line.startswith('STARTCHAR'):
            break
    return False

def main(src, dst):
    (fw, fh, fx, fy), glyphs = read_bdf(src)
    if is_jis(src):
        glyphs = jis_to_unicode(glyphs)
    bpr = (fw + 7) // 8
    out = []
    for cp in sorted(glyphs):
        g = glyphs[cp]
        if cp < 0x80 or g.get('dw') != fw:
            continue
        bw, bh, bx, by = g['bbx']
        cell = [0] * fh
        # 枠の上端から字の上端までの行数
        top = (fh + fy) - (bh + by)
        for i, row in enumerate(g['rows']):
            y = top + i
            if 0 <= y < fh:
                cell[y] |= (row >> (bx - fx)) if bx >= fx else (row << (fx - bx))
        data = b''.join(((r >> (32 - bpr * 8)) & ((1 << (bpr * 8)) - 1)).to_bytes(bpr, 'big') for r in cell)
        out.append((cp, data))
    if len(out) > 0xFFFF:
        sys.exit('字が多すぎます')
    with open(dst, 'wb') as f:
        f.write(b'U7JF' + struct.pack('<HHBBBB', 1, len(out), fw, fh, bpr, 0))
        for cp, _ in out: f.write(struct.pack('<I', cp))
        for _, d in out: f.write(d)
    print(f'{dst}: {len(out)} 字、{fw}x{fh}')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(sys.argv[1], sys.argv[2])
