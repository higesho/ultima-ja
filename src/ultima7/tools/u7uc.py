# U7（Black Gate）の USECODE を分解・組み直す
#   文字列の書き出し: python u7uc.py dump USECODE 出力.tsv
#   関数ごとに分ける: python u7uc.py split USECODE フォルダ   （フォルダ/XXXX.tsv に「位置<TAB>原文<TAB>訳」）
#   訳を当てる:       python u7uc.py build USECODE フォルダ 出力usecode   （訳のある関数だけを書く）
#   往復の確認:       python u7uc.py roundtrip USECODE
#
# 関数の形（元の形式）: 番号(2) 大きさ(2) 本体
# Exult の拡張形式:     0xFFFF 番号(2) 大きさ(4) 本体  （本体の文字列部の長さが 4 バイトになる）
# 本体: 文字列部の長さ(2 か 4) 文字列部 引数の数(2) 変数の数(2) 外部の数(2) 外部(2×n) 命令
# 文字列部は 0 終端の文字列が並ぶ。命令の中の PUSHS などが文字列部の中の位置を持つ。
import struct, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
OPFILE = os.path.join(HERE, '..', 'exult', 'tools', 'ucxt', 'data', 'u7opcodes.data')
SIZES = {'byte': 1, 'short': 2, 'flag': 2, 'offset': 2, 'dataoffset': 2, 'varoffset': 2, 'extoffset': 2,
         'long': 4, 'offset32': 4, 'dataoffset32': 4}

def load_ops():
    t = open(OPFILE, encoding='utf-8').read()
    t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
    ops = {}
    for b in re.split(r'\n\s*<0x', t)[1:]:
        code = int(b[:b.index('>')], 16)
        name = re.search(r'<name>\s*(\S+)', b).group(1)
        m = re.search(r'<param_types>\s*\{([^}]*)\}', b)
        pt = [x.strip() for x in m.group(1).split(',') if x.strip()] if m else []
        ops[code] = (name, pt)
    return ops

OPS = load_ops()

class Func:
    def __init__(self, fid, ext, data, rest, code_off):
        self.fid = fid          # 関数の番号
        self.ext = ext          # Exult の拡張形式か
        self.data = data        # 文字列部（bytes）
        self.rest = rest        # 文字列部より後ろ（引数の数〜命令の終わり）
        self.code_off = code_off  # rest の中で命令が始まる位置

    def strings(self):
        """[(文字列部の中の位置, bytes)]"""
        out = []; p = 0
        while p < len(self.data):
            e = self.data.index(b'\0', p)
            out.append((p, self.data[p:e])); p = e + 1
        return out

    def data_refs(self):
        """命令の中で文字列部の位置を持つ所: [(rest の中の位置, 大きさ, 値)]"""
        refs = []; code = self.rest; p = self.code_off
        while p < len(code):
            op = code[p]
            if op not in OPS:
                raise ValueError(f'{self.fid:#x}: 知らない命令 {op:#x}（{p - self.code_off:#x}）')
            name, pt = OPS[op]
            q = p + 1
            for t in pt:
                n = SIZES[t]
                if t in ('dataoffset', 'dataoffset32'):
                    v = int.from_bytes(code[q:q + n], 'little')
                    refs.append((q, n, v))
                q += n
            p = q
        return refs

    def encode(self, data=None, rest=None):
        data = self.data if data is None else data
        rest = self.rest if rest is None else rest
        ext = self.ext or len(data) + len(rest) + 2 > 0xFFFF
        if ext:
            body = struct.pack('<I', len(data)) + data + rest
            return struct.pack('<HHI', 0xFFFF, self.fid, len(body)) + body
        body = struct.pack('<H', len(data)) + data + rest
        return struct.pack('<HH', self.fid, len(body)) + body

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

# 文字列の位置を持つ命令の 32 ビット版
DATA_OPS32 = {0x1C: 0x9C, 0x1D: 0x9D, 0x4D: 0xCD}
DATA_TYPES = ('dataoffset', 'dataoffset32')
JUMP_TYPES = ('offset', 'offset32')

def decode(f):
    """命令を並べる: [(始まり, 命令, [[型, 値], ...], 終わり)]、命令部の長さ
    飛び幅は「命令の終わり＋値」へ飛ぶ（Exult の ucinternal.cc と同じ）。飛び幅は符号つきで読む。"""
    code = f.rest[f.code_off:]; p = 0; out = []
    while p < len(code):
        op = code[p]
        if op not in OPS:
            raise ValueError(f'{f.fid:#x}: 知らない命令 {op:#x}（{p:#x}）')
        q = p + 1; args = []
        for t in OPS[op][1]:
            n = SIZES[t]
            args.append([t, int.from_bytes(code[q:q + n], 'little', signed=t in JUMP_TYPES)])
            q += n
        out.append((p, op, args, q)); p = q
    return out, len(code)

def rebuild(f, new_strings, pad=0):
    """new_strings: {元の位置: 新しい bytes}。文字列部を作り直し、命令を並べ直す。
    64KB より後ろの文字列を指す命令は 32 ビット版に置き換え、飛び先を付け直す。
    pad: 試験用。文字列部の先頭に、どこからも指されない詰め物をこのバイト数だけ入れる。"""
    data = bytearray(); remap = {}
    if pad:
        data += b'\x7f' * (pad - 1) + b'\0'
    for off, s in f.strings():
        remap[off] = len(data)
        data += new_strings.get(off, s) + b'\0'

    def new_pos(v):
        if v in remap:
            return remap[v]
        base = max(o for o in remap if o <= v)    # 文字列の途中を指す命令（ほぼ無い）
        return remap[base] + (v - base)

    ins, code_len = decode(f)
    index = {p: i for i, (p, _, _, _) in enumerate(ins)}
    index[code_len] = len(ins)
    targets = []
    for p, op, args, end in ins:
        tg = None
        for t, v in args:
            if t in JUMP_TYPES:
                if end + v not in index:
                    raise ValueError(f'{f.fid:#x}: 飛び先 {end + v:#x} が命令の切れ目ではありません')
                tg = index[end + v]
        targets.append(tg)

    new = []
    for p, op, args, end in ins:
        nargs = []
        for t, v in args:
            if t in DATA_TYPES:
                v = new_pos(v)
                if t == 'dataoffset' and v > 0xFFFF:
                    if op not in DATA_OPS32:
                        raise ValueError(f'{f.fid:#x}: 命令 {op:#x} には 32 ビット版がありません')
                    op = DATA_OPS32[op]; t = 'dataoffset32'
            nargs.append([t, v])
        new.append([op, nargs])

    # 命令の長さが変わるので、飛び幅が落ち着くまで計算し直す
    for _ in range(10):
        addr = [0]
        for op, nargs in new:
            addr.append(addr[-1] + 1 + sum(SIZES[t] for t, _ in nargs))
        changed = False
        for i, (op, nargs) in enumerate(new):
            if targets[i] is None:
                continue
            off = addr[targets[i]] - addr[i + 1]
            for arg in nargs:
                if arg[0] in JUMP_TYPES:
                    arg[1] = off
                    if arg[0] == 'offset' and not -0x8000 <= off <= 0x7FFF:
                        op32 = op | 0x80
                        if op32 not in OPS or 'offset32' not in OPS[op32][1]:
                            raise ValueError(f'{f.fid:#x}: 命令 {op:#x} の飛び幅が 16 ビットに入りません')
                        new[i][0] = op32; arg[0] = 'offset32'; changed = True
        if not changed:
            break
    else:
        raise ValueError(f'{f.fid:#x}: 飛び幅が落ち着きません')

    code = bytearray()
    for op, nargs in new:
        code.append(op)
        for t, v in nargs:
            code += v.to_bytes(SIZES[t], 'little', signed=t in JUMP_TYPES)
    return bytes(data), bytes(f.rest[:f.code_off]) + bytes(code)

def verify(f, new_strings, data, rest):
    """組み直した関数が元と同じ動きか確かめる。合わなければ例外"""
    g = Func(f.fid, True, data, rest, f.code_off)
    a, alen = decode(f); b, blen = decode(g)
    if len(a) != len(b):
        raise ValueError(f'{f.fid:#x}: 命令の数が違います')
    old_str = dict(f.strings())
    ia = {p: i for i, (p, *_) in enumerate(a)}; ia[alen] = len(a)
    ib = {p: i for i, (p, *_) in enumerate(b)}; ib[blen] = len(b)
    for (pa, oa, aa, ea), (pb, ob, ab, eb) in zip(a, b):
        if oa != ob and oa | 0x80 != ob:
            raise ValueError(f'{f.fid:#x}: 命令が違います {oa:#x} → {ob:#x}')
        for (ta, va), (tb, vb) in zip(aa, ab):
            if ta in DATA_TYPES:
                want = new_strings.get(va, old_str[va]) if va in old_str else None
                got = data[vb:data.index(b'\0', vb)]
                if want is not None and got != want:
                    raise ValueError(f'{f.fid:#x}: 文字列の指し先が違います（{pa:#x}）')
            elif ta in JUMP_TYPES:
                if ia[ea + va] != ib[eb + vb]:
                    raise ValueError(f'{f.fid:#x}: 飛び先が違います（{pa:#x}）')
            elif va != vb:
                raise ValueError(f'{f.fid:#x}: 引数が違います（{pa:#x}）')

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

def cmd_dump(src, dst):
    with open(dst, 'w', encoding='utf-8', newline='\n') as w:
        w.write('# 関数\t位置\t原文\t訳\n')
        for f in read_usecode(src):
            for off, s in f.strings():
                w.write(f'{f.fid:#06x}\t{off}\t{esc(s)}\t\n')
    print(f'{dst} に書き出しました')

def read_tsv(folder):
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
            if len(cols) < 3 or not cols[2]:
                continue
            ja = '' if cols[2] == '{空}' else unesc(cols[2])    # 「{空}」は空の文字列にする
            tr.setdefault(fid, {})[int(cols[0])] = (unesc(cols[1]), ja)
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

def cmd_build(src, tsv, dst, pad=0):
    tr = read_tsv(tsv); out = bytearray(); n = 0; big = []
    funcs = {f.fid: f for f in read_usecode(src)}
    for fid, items in sorted(tr.items()):
        f = funcs[fid]; strs = dict(f.strings()); new = {}
        for off, (en, ja) in items.items():
            if off not in strs or strs[off].decode('latin-1') != en:
                sys.exit(f'{fid:#x} 位置 {off}: 原文が合いません')
            new[off] = ja.encode('utf-8'); n += 1
        data, rest = rebuild(f, new, pad)
        verify(f, new, data, rest)
        if len(data) > 0xFFFF:
            big.append(f'{fid:#x}（文字列部 {len(data)} バイト）')
        out += f.encode(data, rest)
    open(dst, 'wb').write(out)
    print(f'{dst}: 関数 {len(tr)}、文字列 {n} 件を訳しました')
    if big:
        print('64KB を超えて 32 ビットの命令にした関数:', '、'.join(big))

def cmd_roundtrip(src):
    d = open(src, 'rb').read(); out = bytearray(); nrefs = 0
    for f in read_usecode(src):
        data, rest = rebuild(f, {})
        nrefs += len(f.data_refs())
        out += f.encode(data, rest)
    print('一致' if bytes(out) == d else '不一致', f'（文字列を指す命令 {nrefs} 個）')
    # 全部の文字列を 2 倍の長さにしても組み直せるか
    bad = 0; over = 0
    for f in read_usecode(src):
        new = {o: s * 2 for o, s in f.strings()}
        try:
            data, rest = rebuild(f, new)
            verify(f, new, data, rest)
            over += len(data) > 0xFFFF
            # 全部を 64KB より後ろに置いても組み直せるか
            data, rest = rebuild(f, {}, pad=0x10000)
            verify(f, {}, data, rest)
            if f.data_refs() and rest == f.rest:
                raise ValueError(f'{f.fid:#x}: 64KB より後ろに置いたのに命令が変わっていません')
        except ValueError as e:
            bad += 1; print('  ', e)
    print(f'文字列を 2 倍にしたとき: 64KB 超え {over} 関数、組み直せない関数 {bad}')

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    c = sys.argv[1]
    if c == 'dump': cmd_dump(sys.argv[2], sys.argv[3])
    elif c == 'split': cmd_split(sys.argv[2], sys.argv[3])
    elif c == 'build': cmd_build(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[5] == '--pad' else 0)
    elif c == 'roundtrip': cmd_roundtrip(sys.argv[2])
