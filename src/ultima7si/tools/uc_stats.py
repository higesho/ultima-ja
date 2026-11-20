# USECODE の関数と文字列を数える（BG と SI を比べる）
import struct, sys, re, collections

def parse(path):
    d = open(path, 'rb').read()
    p = 0
    funcs = []
    while p < len(d):
        fid = struct.unpack_from('<H', d, p)[0]
        if fid == 0xFFFF:  # 32 ビット長の形式
            fid, size = struct.unpack_from('<HI', d, p + 2)
            hdr = 8
            dlen = struct.unpack_from('<I', d, p + hdr)[0]; dl = 4
        else:
            size = struct.unpack_from('<H', d, p + 2)[0]
            hdr = 4
            dlen = struct.unpack_from('<H', d, p + hdr)[0]; dl = 2
        body = d[p + hdr:p + hdr + size]
        data = body[dl:dl + dlen]
        strs = [s for s in data.split(b'\0') if s]
        funcs.append((fid, size, dlen, strs, fid == 0xFFFF))
        p += hdr + size
    return d, funcs, p

for path in sys.argv[1:]:
    d, funcs, end = parse(path)
    allstr = [s for f in funcs for s in f[3]]
    nbytes = sum(len(s) for s in allstr)
    words = sum(len(s.split()) for s in allstr)
    hi = sum(1 for s in allstr for b in s if b >= 0x80)
    big = sorted(funcs, key=lambda f: -f[1])[:6]
    sym = collections.Counter()
    for s in allstr:
        for ch in b'@~*':
            sym[chr(ch)] += s.count(ch)
    print(f'== {path}')
    print(f'  ファイル {len(d)} バイト、解析終端 {end}、関数 {len(funcs)}')
    print(f'  文字列 {len(allstr)} 件、{nbytes} バイト、約 {words} 語、80h以上 {hi}')
    print(f'  記号 {dict(sym)}')
    print('  大きい関数: ' + ', '.join(f'{f[0]:#x}={f[1]}' for f in big))
    print(f'  32ビット形式の関数 {sum(1 for f in funcs if f[4])}')
    ids = [f[0] for f in funcs]
    print(f'  関数番号 最小 {min(ids):#x} 最大 {max(ids):#x}')
    over = [f for f in funcs if f[1] > 0xC000]
    print('  48KB 超: ' + ', '.join(f'{f[0]:#x}={f[1]}' for f in over))
