"""ゲーム部の文字列と、それを指す命令（imm32）を洗い出す。"""
import sys, re, struct, bisect, capstone
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coff

GAME_LO, GAME_HI = 0x10a8, 0x1a000

def load(path):
    return coff.Coff(open(path, 'rb').read())

def game_strings(c):
    n, va, size, ptr, _ = c.secs[0]
    out = []
    for m in re.finditer(rb'[\x20-\x7e\n\r\t]{2,}\x00', bytes(c.d[ptr:ptr + size])):
        a = va + m.start()
        if not (GAME_LO <= a < GAME_HI): continue
        s = m.group()[:-1]
        if re.search(rb'[A-Za-z?!=]', s):
            out.append((a, s.decode('latin1')))
    return out

def find_refs(c, targets):
    """targets: set of VA. 戻り値 {va: [(命令の va, imm の位置(ファイル), 命令文字列)]}"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    n, va, size, ptr, _ = c.secs[0]
    code = bytes(c.d[ptr:ptr + size])
    refs = {t: [] for t in targets}
    for t in targets:
        pat = struct.pack('<I', t)
        p = code.find(pat)
        while p >= 0:
            ok = None
            for s in range(max(0, p - 8), p):
                ins = next(md.disasm(code[s:s + 16], va + s, 1), None)
                if ins and s + ins.size == p + 4 and ('0x%x' % t) in ins.op_str:
                    ok = (va + s, ptr + p, ins.mnemonic + ' ' + ins.op_str); break
            if ok: refs[t].append(ok)
            p = code.find(pat, p + 1)
    # .text 内のポインタ表（4 バイト境界で、隣も文字列を指す）
    for t in targets:
        pat = struct.pack('<I', t)
        p = code.find(pat)
        while p >= 0:
            refs[t] = [x for x in refs[t] if not (x[1] == ptr + p and x[2].split()[0] not in ('push', 'mov'))]
            if (va + p) % 4 == 0 and not any(x[1] == ptr + p for x in refs[t]):
                nb = [struct.unpack_from('<I', code, q)[0] for q in (p - 4, p + 4) if 0 <= q <= len(code) - 4]
                if any(v in targets or (GAME_LO <= v < GAME_HI and code[v - va - 1] == 0 and 0x20 <= code[v - va] < 0x7f) for v in nb):
                    refs[t].append((va + p, ptr + p, 'table'))
            p = code.find(pat, p + 1)
    # データ部
    n2, va2, size2, ptr2, _ = c.secs[1]
    for i in range(0, size2, 4):
        v = struct.unpack_from('<I', c.d, ptr2 + i)[0]
        if v in refs: refs[v].append((va2 + i, ptr2 + i, 'data'))
    return refs

if __name__ == '__main__':
    c = load(sys.argv[1])
    ss = game_strings(c)
    refs = find_refs(c, {a for a, s in ss})
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for a, s in ss:
        r = refs[a]
        print('%06x %r  refs=%s' % (a, s, ' '.join('%06x:%s' % (x[0], x[2].split()[0]) for x in r)))
