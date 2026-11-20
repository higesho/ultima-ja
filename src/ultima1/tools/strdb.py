# Build a string database for one EXE: every string, every reference to it, and whether it can be moved.
#
# Rules
#  - code reference = "mov reg, imm16 ; push reg" whose next call goes to a function that takes strings
#    (a function that receives known strings as arguments at least twice).
#  - table reference = 2+ consecutive data words pointing at string starts.
#  - movable = has references, every reference is one of the above, nothing else points inside it.
#    Anything ambiguous (single data word, mov to memory, ...) -> fixed (rewrite in place only).
import struct, re
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from u1exe import Exe

def sweep(code):
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    ins = []; pos = 0
    while pos < len(code):
        n0 = len(ins)
        for i in md.disasm(code[pos:], pos): ins.append(i)
        pos = ins[-1].address + ins[-1].size if len(ins) > n0 else pos + 1
    return ins

REGS = ('ax', 'bx', 'cx', 'dx', 'si', 'di')

def build_db(path, name):
    e = Exe(path, name)
    data = e.data(); code = e.code()
    ins = sweep(code)
    heur = set(o for o, _ in e.strings())
    runs = [(m.start(1), m.end(1)) for m in re.finditer(rb'([\x20-\x7e\r\n]+)\x00', data)]
    run_of = {}
    for a, b in runs:
        for x in range(a, b): run_of[x] = (a, b)

    # mov reg,imm ; push reg ; ... call target
    args = []   # (value, imm_file_off, target)
    movs = {}   # value -> count of other movs with imm (ambiguous uses)
    for k, i in enumerate(ins[:-1]):
        if i.mnemonic != 'mov': continue
        parts = i.op_str.split(', ')
        if len(parts) != 2 or not parts[1].startswith('0x'): continue
        try: v = int(parts[1], 16)
        except ValueError: continue
        if v > 0xffff or i.size < 3: continue
        if struct.unpack_from('<H', code, i.address + i.size - 2)[0] != v: continue
        nxt = ins[k + 1]
        if parts[0] in REGS and nxt.mnemonic == 'push' and nxt.op_str == parts[0]:
            tgt = None; pos = 0
            for j in ins[k + 2:k + 20]:
                if j.mnemonic == 'push': pos += 1
                if j.mnemonic == 'call':
                    t = int(j.op_str, 16) & 0xffff if j.op_str.startswith('0x') else j.op_str
                    tgt = (t, pos); break
                if j.mnemonic in ('ret', 'retf', 'jmp'): break
            args.append((v, e.hdr + i.address + i.size - 2, tgt))
        elif v in run_of:
            movs[v] = movs.get(v, 0) + 1
    # functions that take strings
    cnt = {}
    for v, fo, t in args:
        if v in heur and t: cnt[t] = cnt.get(t, 0) + 1
    sfuncs = {t for t, n in cnt.items() if n >= 2}          # (function, argument position)
    cntf = {}
    for v, fo, t in args:
        if v in heur and t: cntf[t[0]] = cntf.get(t[0], 0) + 1
    sfunc_any = {f for f, n in cntf.items() if n >= 2}       # functions that take a string somewhere
    code_refs = {}
    weak = set()     # values passed to a string-taking function at a non-string position: maybe a pointer
    for v, fo, t in args:
        if not t or v not in run_of: continue
        if t in sfuncs: code_refs.setdefault(v, []).append(fo)
        elif t[0] in sfunc_any: weak.add(v)

    # pointer tables: 2+ consecutive words (stride 2) whose values point at the start of text
    # (byte before is NUL, or the pointed text directly follows the table itself)
    n = len(data)
    def word(i): return struct.unpack_from('<H', data, i)[0]
    def textstart(v):
        return v in run_of and (v == 0 or data[v - 1] == 0 or v in code_refs)
    def plausible(i, v):
        # a word inside printable text counts only when it points at a string close by
        # (e.g. "$(*(.(Fighter"); otherwise text like "      " would look like pointers 0x2020
        return i not in run_of or abs(v - i) < 0x200
    cand = {}
    for i in range(n - 1):
        v = word(i)
        if v != i and textstart(v) and plausible(i, v): cand[i] = v
    # text that directly follows a table (e.g. "...$(*(Fighter"): repeat until stable
    changed = True
    while changed:
        changed = False
        for i in range(n - 1):
            v = word(i)
            if i in cand or v not in run_of or v == i or not plausible(i, v): continue
            # v starts right after a candidate table word
            if (v - 2) in cand or (v - 1) in cand:
                cand[i] = v; changed = True
    table_refs, single_refs, seen = {}, {}, set()
    for i in sorted(cand):
        if i in seen: continue
        j = i
        while j in cand: seen.add(j); j += 2
        if j - i >= 4:
            for k in range(i, j, 2): table_refs.setdefault(cand[k], []).append(e.dbase + k)
        else:
            single_refs.setdefault(cand[i], []).append(e.dbase + i)
    # table words themselves are not text: cut runs at the end of each table
    table_bytes = set()
    for v, lst in table_refs.items():
        for fo in lst: table_bytes.update((fo - e.dbase, fo - e.dbase + 1))
    starts = heur | set(code_refs) | set(table_refs)
    starts = {x for x in starts if x not in table_bytes}
    ptr_starts = set(code_refs) | set(table_refs)

    db = []
    for off in sorted(starts):
        if off not in run_of: continue
        a, b = run_of[off]
        a = max([a] + [x + 1 for x in table_bytes if a <= x < off])
        text = data[off:b]
        inner = [s for s in ptr_starts if off < s < b]
        outer = [s for s in ptr_starts if a <= s < off]
        refs = code_refs.get(off, []) + table_refs.get(off, [])
        weakin = [w for w in weak if off <= w < b]
        movable = bool(refs) and off not in single_refs and off not in movs and not inner and not outer \
            and not weakin
        db.append(dict(off=off, text=text, cap=len(text), refs=refs,
                       ncode=len(code_refs.get(off, [])), ntable=len(table_refs.get(off, [])),
                       single=off in single_refs, mov=off in movs, inner=inner, outer=outer,
                       weak=bool(weakin), movable=movable))
    return e, db

def why(s):
    w = []
    if not s['refs']: w.append('no-ref')
    if s['single']: w.append('single')
    if s['mov']: w.append('mov')
    if s['inner']: w.append('inner')
    if s['outer']: w.append('tail')
    if s.get('weak'): w.append('weak')
    return ','.join(w)

if __name__ == '__main__':
    import sys
    for fn in sys.argv[2:]:
        e, db = build_db(sys.argv[1] + '/' + fn, fn)
        tr = [s for s in db if sum(chr(c).isalpha() for c in s['text']) >= 2]
        mv = [s for s in tr if s['movable']]
        print(f"{fn}: strings {len(db)} (text {len(tr)}), movable {len(mv)}, fixed {len(tr) - len(mv)}, "
              f"text bytes {sum(s['cap'] for s in tr)}")
        for s in tr:
            if not s['movable']: print(f"   fixed {s['off']:#06x} {why(s):14s} {s['text'][:40]!r}")
