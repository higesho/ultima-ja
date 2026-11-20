# Serpent Isle の USECODE を分解・組み直す（BG 用の u7uc.py をもとに、32 ビット命令への広げを足したもの）
#   往復の確認:       python si_uc.py roundtrip USECODE
#   関数ごとに分ける: python si_uc.py split USECODE フォルダ    （フォルダ/XXXX.tsv に「位置<TAB>原文<TAB>訳」）
#   訳を当てる:       python si_uc.py build USECODE フォルダ 出力usecode   （訳のある関数だけを書く）
#   進み具合:         python si_uc.py stat フォルダ
#
# 関数の形（元の形式）: 番号(2) 大きさ(2) 本体
# Exult の拡張形式:     0xFFFF 番号(2) 大きさ(4) 本体  （本体の文字列部の長さが 4 バイトになる）
# 本体: 文字列部の長さ(2 か 4) 文字列部 引数の数(2) 変数の数(2) 外部の数(2) 外部(2×n) 命令
#
# 日本語にすると文字列部が 64KB を超える関数がある（0x2C1 など）。そのときは
# 文字列を指す命令（PUSHS など）を 32 ビット版に広げ、飛び先を付け直す。
import struct, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
OPFILE = os.path.join(HERE, 'u7opcodes.data')
SIZES = {'byte': 1, 'short': 2, 'flag': 2, 'offset': 2, 'dataoffset': 2, 'varoffset': 2, 'extoffset': 2,
         'long': 4, 'offset32': 4, 'dataoffset32': 4}
WIDE32 = {'offset': 'offset32', 'dataoffset': 'dataoffset32'}

def load_ops():
    t = open(OPFILE, encoding='utf-8').read()
    t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
    ops = {}
    for b in re.split(r'\n\s*<0x', t)[1:]:
        code = int(b[:b.index('>')], 16)
        if code > 0xFF:
            continue    # LABEL などの疑似命令
        name = re.search(r'<name>\s*(\S+)', b).group(1)
        m = re.search(r'<param_types>\s*\{([^}]*)\}', b)
        pt = [x.strip() for x in m.group(1).split(',') if x.strip()] if m else []
        ops[code] = (name, pt)
    return ops

OPS = load_ops()

class Func:
    def __init__(self, fid, ext, data, rest, code_off):
        self.fid = fid            # 関数の番号
        self.ext = ext            # Exult の拡張形式か
        self.data = data          # 文字列部（bytes）
        self.rest = rest          # 文字列部より後ろ（引数の数〜命令の終わり）
        self.code_off = code_off  # rest の中で命令が始まる位置

    def strings(self):
        """[(文字列部の中の位置, bytes)]"""
        out = []; p = 0
        while p < len(self.data):
            e = self.data.index(b'\0', p)
            out.append((p, self.data[p:e])); p = e + 1
        return out

    def decode(self):
        """命令の並び: [(rest の中の位置, 命令, [(型, 値)])]"""
        ins = []; code = self.rest; p = self.code_off
        while p < len(code):
            op = code[p]
            if op not in OPS:
                raise ValueError(f'{self.fid:#x}: 知らない命令 {op:#x}（{p - self.code_off:#x}）')
            q = p + 1; params = []
            for t in OPS[op][1]:
                n = SIZES[t]
                v = int.from_bytes(code[q:q + n], 'little', signed=t in ('offset', 'offset32'))
                params.append((t, v)); q += n
            ins.append((p, op, params)); p = q
        return ins

def ins_len(op):
    return 1 + sum(SIZES[t] for t in OPS[op][1])

def wide_op(op):
    """32 ビット版の命令番号（なければ None）"""
    name, pt = OPS[op]
    for c, (n2, pt2) in OPS.items():
        if n2 == name + '32' and len(pt2) == len(pt):
            return c
    return None

def encode_func(fid, ext, data, rest):
    ext = ext or len(data) + len(rest) + 2 > 0xFFFF
    if ext:
        body = struct.pack('<I', len(data)) + data + rest
        return struct.pack('<HHI', 0xFFFF, fid, len(body)) + body
    body = struct.pack('<H', len(data)) + data + rest
    return struct.pack('<HH', fid, len(body)) + body

def read_usecode(path):
    d = open(path, 'rb').read(); p = 0; funcs = []
    while p < len(d):
        fid = struct.unpack_from('<H', d, p)[0]
        if fid == 0xFFFF:
            fid, size = struct.unpack_from('<HI', d, p + 2); p += 8; ext = True
        elif fid == 0xFFFE:
            fid, size = struct.unpack_from('<iI', d, p + 2); p += 10; ext = True
        else:
            size = struct.unpack_from('<H', d, p + 2)[0]; p += 4; ext = False
        body = d[p:p + size]; p += size
        if ext:
            dl = struct.unpack_from('<I', body, 0)[0]; data = body[4:4 + dl]; rest = body[4 + dl:]
        else:
            dl = struct.unpack_from('<H', body, 0)[0]; data = body[2:2 + dl]; rest = body[2 + dl:]
        nargs, nvars, next_ = struct.unpack_from('<HHH', rest, 0)
        funcs.append(Func(fid, ext, data, rest, 6 + 2 * next_))
    return funcs

def rebuild(f, new_strings, force_wide=False):
    """new_strings: {元の位置: 新しい bytes}。文字列部を作り直し、命令の位置を付け直す。
    戻り値: (文字列部, rest, 広げたか)"""
    data = bytearray(); remap = {}
    for off, s in f.strings():
        remap[off] = len(data)
        data += new_strings.get(off, s) + b'\0'

    def new_data_off(v):
        if v in remap:
            return remap[v]
        base = max(o for o in remap if o <= v)    # 文字列の途中を指す命令（ほぼ無い）
        return remap[base] + (v - base)

    ins = f.decode()
    wide_data = force_wide or len(data) > 0xFFFF
    if not wide_data:
        # 命令の長さは変えずに、文字列の位置だけを書き換える
        rest = bytearray(f.rest)
        for p, op, params in ins:
            q = p + 1
            for t, v in params:
                n = SIZES[t]
                if t == 'dataoffset':
                    rest[q:q + n] = new_data_off(v).to_bytes(n, 'little')
                q += n
        return bytes(data), bytes(rest), False

    # 広げる: 文字列を指す命令を 32 ビット版にし、飛び先を付け直す。
    # 飛び先が 16 ビットに入らない飛び命令も 32 ビット版にする（決まるまで繰り返す）。
    ends = {p: p + ins_len(op) for p, op, _ in ins}
    targets = {}    # (命令の位置, 何番目の引数) -> 元の飛び先（rest の中の位置）
    for p, op, params in ins:
        for k, (t, v) in enumerate(params):
            if t in ('offset', 'offset32'):
                targets[(p, k)] = ends[p] + v
    newop = {}
    for p, op, params in ins:
        if any(t == 'dataoffset' for t, _ in params):
            w = wide_op(op)
            if w is None:
                raise ValueError(f'{f.fid:#x}: {OPS[op][0]} の 32 ビット版がありません')
            newop[p] = w
        else:
            newop[p] = op
    while True:
        pos = {}; cur = f.code_off
        for p, op, params in ins:
            pos[p] = cur; cur += ins_len(newop[p])
        pos[len(f.rest)] = cur    # 命令の終わり（飛び先になりうる）
        grew = False
        for (p, k), tgt in targets.items():
            if tgt not in pos:
                raise ValueError(f'{f.fid:#x}: 飛び先 {tgt:#x} が命令の区切りではありません')
            t = OPS[newop[p]][1][k]
            rel = pos[tgt] - (pos[p] + ins_len(newop[p]))
            if t == 'offset' and not -0x8000 <= rel <= 0x7FFF:
                w = wide_op(newop[p])
                if w is None:
                    raise ValueError(f'{f.fid:#x}: 飛び命令を広げられません')
                newop[p] = w; grew = True
        if not grew:
            break
    rest = bytearray(f.rest[:f.code_off])
    for p, op, params in ins:
        nop = newop[p]; rest.append(nop)
        for k, (t, v) in enumerate(params):
            nt = OPS[nop][1][k]; n = SIZES[nt]
            if t in ('dataoffset', 'dataoffset32'):
                val = new_data_off(v)
            elif t in ('offset', 'offset32'):
                val = pos[targets[(p, k)]] - (pos[p] + ins_len(nop))
            else:
                val = v
            rest += val.to_bytes(n, 'little', signed=t in ('offset', 'offset32'))
    return bytes(data), bytes(rest), True

# ---- 文字列の書き出し・訳の読み込み ----
def esc(b):
    s = b.decode('latin-1')
    return s.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')

def unesc(s):
    out = []; i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            out.append({'n': '\n', 't': '\t', 'r': '\r', '\\': '\\'}.get(s[i + 1], s[i + 1])); i += 2
        else:
            out.append(s[i]); i += 1
    return ''.join(out)

def read_tsv(folder, with_empty=False):
    """フォルダの XXXX.tsv を読んで {関数: {位置: (原文, 訳)}} を返す（訳が空の行は飛ばす）"""
    tr = {}
    for name in sorted(os.listdir(folder)):
        m = re.fullmatch(r'([0-9a-fA-F]{4})\.tsv', name)
        if not m:
            continue
        fid = int(m.group(1), 16)
        for line in open(os.path.join(folder, name), encoding='utf-8-sig'):
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            cols = line.split('\t')
            ja = cols[2] if len(cols) > 2 else ''
            if not ja and not with_empty:
                continue
            tr.setdefault(fid, {})[int(cols[0])] = (unesc(cols[1]), unesc(ja))
    return tr

def cmd_split(src, folder):
    os.makedirs(folder, exist_ok=True); n = 0
    for f in read_usecode(src):
        path = os.path.join(folder, f'{f.fid:04x}.tsv')
        if os.path.exists(path):
            continue    # 訳しかけのファイルは上書きしない
        with open(path, 'w', encoding='utf-8', newline='\n') as w:
            w.write('# 位置\t原文\t訳\n')
            for off, s in f.strings():
                w.write(f'{off}\t{esc(s)}\t\n')
        n += 1
    print(f'{folder} に {n} 個の関数を書き出しました')

def cmd_build(src, tsv, dst, force=()):
    """force: 試験のため、文字列部が小さくても 32 ビット命令に広げる関数"""
    tr = read_tsv(tsv); out = bytearray(); n = 0; wide = []
    funcs = {f.fid: f for f in read_usecode(src)}
    for fid, items in sorted(tr.items()):
        f = funcs[fid]; strs = dict(f.strings()); new = {}
        for off, (en, ja) in items.items():
            if off not in strs or strs[off].decode('latin-1') != en:
                sys.exit(f'{fid:#x} 位置 {off}: 原文が合いません')
            new[off] = ja.encode('utf-8'); n += 1
        data, rest, w = rebuild(f, new, force_wide=fid in force)
        if w:
            wide.append(fid)
        out += encode_func(fid, f.ext, data, rest)
    open(dst, 'wb').write(out)
    print(f'{dst}: 関数 {len(tr)}、文字列 {n} 件を訳しました' +
          (f'（32 ビット命令に広げた関数: {", ".join(hex(x) for x in wide)}）' if wide else ''))

def cmd_roundtrip(src):
    d = open(src, 'rb').read(); out = bytearray(); nrefs = 0
    funcs = read_usecode(src)
    for f in funcs:
        data, rest, _ = rebuild(f, {})
        nrefs += sum(1 for _, _, ps in f.decode() for t, _ in ps if t == 'dataoffset')
        out += encode_func(f.fid, f.ext, data, rest)
    print('そのまま組み直し:', '一致' if bytes(out) == d else '不一致', f'（関数 {len(funcs)}、文字列を指す命令 {nrefs} 個）')
    # 全部の文字列を 3 倍の長さにして、広げが必要な関数でも組み直せるか
    big = []
    for f in funcs:
        data, rest, w = rebuild(f, {o: s * 3 for o, s in f.strings()})
        if w:
            big.append(f.fid)
            # 広げた結果を読み直し、文字列の指す先が正しいか確かめる
            g = Func(f.fid, True, data, rest, f.code_off)
            old = [s for _, _, ps in f.decode() for t, v in ps if t == 'dataoffset' for s in [v]]
            new = [v for _, _, ps in g.decode() for t, v in ps if t == 'dataoffset32']
            so = dict(f.strings()); sn = dict(g.strings())
            for a, b in zip(old, new):
                assert sn[b] == so[a] * 3, (hex(f.fid), a, b)
            assert len(old) == len(new)
            # 飛び命令の数と並びが変わっていないか
            assert [OPS[op][0].rstrip('32') for _, op, _ in f.decode()] == \
                   [OPS[op][0].rstrip('32') for _, op, _ in g.decode()]
    print('文字列を 3 倍にして 32 ビット命令に広げた関数:', len(big), '（読み直しの確認も通った）')

def cmd_stat(folder):
    tr = read_tsv(folder, with_empty=True)
    tot = done = 0; tb = db = 0; fdone = 0
    for fid, items in tr.items():
        n = len(items); d = sum(1 for en, ja in items.values() if ja)
        tot += n; done += d
        tb += sum(len(en) for en, ja in items.values())
        db += sum(len(en) for en, ja in items.values() if ja)
        if n and d == n:
            fdone += 1
    print(f'文字列 {done}/{tot}（原文の量で {db * 100 / max(tb, 1):.1f}%）、訳し終えた関数 {fdone}/{len(tr)}')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    c = sys.argv[1]
    if c == 'split': cmd_split(sys.argv[2], sys.argv[3])
    elif c == 'build': cmd_build(sys.argv[2], sys.argv[3], sys.argv[4], [int(x, 16) for x in sys.argv[5:]])
    elif c == 'roundtrip': cmd_roundtrip(sys.argv[2])
    elif c == 'stat': cmd_stat(sys.argv[2])
