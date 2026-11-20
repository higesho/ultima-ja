"""解析結果の整合性を確かめる: 元に戻るか、飛び先・表の参照が部品の先頭を指すか、文の先頭の値"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
from u6conv import Script, load_items
def join(s):
    out = bytearray()
    for nd in s.nodes:
        if nd[0] == 'table': out += b''.join(x + b'\0' for x in nd[2]) + nd[3]
        else: out += nd[2]
    return bytes(out)
def run(gamedir):
    bad = []; stmt_first = collections.Counter(); kinds = collections.Counter(); nb = collections.Counter()
    for f in ('CONVERSE.A', 'CONVERSE.B'):
        for k, raw in load_items(os.path.join(gamedir, f)):
            if raw is None: continue
            s = Script(raw)
            if join(s) != raw: bad.append((f, k, '元に戻らない'))
            starts = {nd[1]: nd[0] for nd in s.nodes}
            for at, tgt, kind in s.refs:
                want = ('code', 'text') if kind == 'code' else (('table',) if kind == 'str' else ('numtable',))
                if starts.get(tgt) not in want: bad.append((f, k, f'{kind} {tgt:#x} → {starts.get(tgt)}'))
            for nd in s.nodes:
                kinds[nd[0]] += 1
                nb[nd[0]] += len(nd[2]) if nd[0] != 'table' else sum(len(x) for x in nd[2])
                if nd[0] == 'code' and nd[2]: stmt_first[nd[2][0]] += 1
    print('おかしい所', len(bad)); [print('  ', b) for b in bad[:15]]
    print('部品の数', dict(kinds)); print('バイト数', dict(nb))
    print('文の先頭が 0x80〜0x9F:', {('%02X' % b): n for b, n in sorted(stmt_first.items()) if 0x80 <= b < 0xA0})
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8'); run(sys.argv[1])
