# 配布用の差分 AKJP.PAT を作る。原作のデータは入れず、日本語版で変えたバイトだけを入れる。
#
#   python tools/make_patch.py <元の AK.EXE> <build/AKJP.COFF> <出力 AKJP.PAT> [<手本の AKJP.EXE>]
#
# AK.EXE の本体は WDOSX の WFSE に入っていて、4KB ごとに圧縮されている。
# 遊ぶ人の所で AKJPMK.COM が、変えたブロックだけ展開して差分を当て、圧縮せずにそのまま書く
# （WDOSX は「圧縮後の大きさ＝展開後の大きさ」のブロックを無圧縮として写す）。
# 変えていないブロックは元の圧縮のまま写す。apply() はその手本で、AKJPMK.COM と同じ結果を作る。
#
# AKJP.PAT の形（数はすべてリトルエンディアン）
#   "AKJPPAT1"
#   u32 元の AK.EXE の大きさ / u32 展開後の大きさ / u16 ブロック数 / u16 変えたブロック数
#   変えたブロックごとに: u16 ブロック番号 / u16 元のブロックの検算値 / u16 記録数 /
#                          記録ごとに u16 ブロック内の位置 / u8 長さ(1-255) / 新しいバイト
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wdx

BLK = 0x1000
HEAD = wdx.WFSE_AT + 0x20


def checksum(b):
    """元のブロックの検算値（足し算と回転）。AKJPMK.COM と同じ計算。"""
    s = 0
    for x in b:
        s = ((s << 1) | (s >> 15)) & 0xffff
        s = (s + x) & 0xffff
    return s


def literal_block(b):
    """圧縮せず、全部「そのままのバイト」で書く形。"""
    out = bytearray([b[0]])
    rest = b[1:]
    for i in range(0, len(rest), 8):
        out.append(0)
        out += rest[i:i + 8]
    return bytes(out)


def table(exe):
    total, usize = struct.unpack_from('<II', exe, wdx.WFSE_AT + 4)
    nblk = (usize + BLK - 1) // BLK
    tab = [struct.unpack_from('<I', exe, HEAD + 4 * i)[0] for i in range(nblk)]
    base = HEAD + 4 * nblk
    ends = tab[1:] + [total - 0x20 - 4 * nblk]
    return usize, nblk, base, tab, ends


def make(exe, new):
    orig = wdx.unpack_exe(exe)
    assert len(orig) == len(new)
    usize, nblk, base, tab, ends = table(exe)
    out = bytearray(b'AKJPPAT1' + struct.pack('<IIHH', len(exe), usize, nblk, 0))
    nchg = 0
    for i in range(nblk):
        a, b = orig[i * BLK:(i + 1) * BLK], new[i * BLK:(i + 1) * BLK]
        if a == b: continue
        recs = []
        k = 0
        while k < len(a):
            if a[k] == b[k]:
                k += 1; continue
            j = k
            while j < len(a) and a[j] != b[j] and j - k < 255:
                j += 1
            recs.append((k, b[k:j])); k = j
        out += struct.pack('<HHH', i, checksum(a), len(recs))
        for off, d in recs:
            out += struct.pack('<HB', off, len(d)) + d
        nchg += 1
    struct.pack_into('<H', out, 8 + 4 + 4 + 2, nchg)
    return bytes(out)


def apply(exe, pat):
    """AKJPMK.COM の手本。元の AK.EXE と AKJP.PAT から AKJP.EXE を作る。"""
    assert pat[:8] == b'AKJPPAT1'
    size, usize, nblk, nchg = struct.unpack_from('<IIHH', pat, 8)
    assert len(exe) == size and exe[wdx.WFSE_AT:wdx.WFSE_AT + 4] == b'WFSE'
    u2, n2, base, tab, ends = table(exe)
    assert (u2, n2) == (usize, nblk)
    chg = {}
    p = 20
    for _ in range(nchg):
        i, ck, nrec = struct.unpack_from('<HHH', pat, p); p += 6
        recs = []
        for _ in range(nrec):
            off, n = struct.unpack_from('<HB', pat, p); p += 3
            recs.append((off, pat[p:p + n])); p += n
        chg[i] = (ck, recs)
    blocks = []
    for i in range(nblk):
        comp = exe[base + tab[i]:base + ends[i]]
        if i not in chg:
            blocks.append(comp); continue
        n = min(BLK, usize - i * BLK)
        dec, _ = wdx.unpack(comp, 0, n)
        ck, recs = chg[i]
        if checksum(dec) != ck:
            raise ValueError('ブロック %d が元と違う' % i)
        dec = bytearray(dec)
        for off, d in recs:
            dec[off:off + len(d)] = d
        blocks.append(bytes(dec))
    head = bytearray(exe[:HEAD])
    newtab = bytearray(); pos = 0
    for b in blocks:
        newtab += struct.pack('<I', pos); pos += len(b)
    struct.pack_into('<I', head, wdx.WFSE_AT + 4, 0x20 + 4 * nblk + pos)
    return bytes(head) + bytes(newtab) + b''.join(blocks)


if __name__ == '__main__':
    exe = open(sys.argv[1], 'rb').read()
    new = open(sys.argv[2], 'rb').read()
    pat = make(exe, new)
    open(sys.argv[3], 'wb').write(pat)
    res = apply(exe, pat)
    assert wdx.unpack_exe(res) == new
    print('AKJP.PAT %d バイト、できる AKJP.EXE %d バイト' % (len(pat), len(res)))
    if len(sys.argv) > 4:
        open(sys.argv[4], 'wb').write(res)
