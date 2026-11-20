"""全員のスクリプトを u6conv で読み、読めない所をまとめる"""
import sys, collections, re, os
sys.path.insert(0, os.path.dirname(__file__))
from u6conv import Script, load_items, ParseError
def run(gamedir, show=8):
    ok = 0; errs = collections.Counter(); ex = []
    for f in ('CONVERSE.A', 'CONVERSE.B'):
        for k, raw in load_items(os.path.join(gamedir, f)):
            if raw is None: continue
            try: Script(raw); ok += 1
            except ParseError as e:
                msg = str(e); errs[re.sub(r' 0x[0-9a-f]+', '', msg)] += 1; ex.append((f, k, msg, raw))
    print('読めた', ok, '読めない', len(ex)); print(errs.most_common())
    for f, k, msg, raw in ex[:show]:
        p = int(re.findall(r'0x[0-9a-f]+', msg)[-1], 16)
        print(f, k, msg, '|', raw[max(0, p - 20):p].hex(' '), '>', raw[p:p + 16].hex(' '))
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8)
