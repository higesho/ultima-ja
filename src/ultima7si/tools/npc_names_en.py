# 原作の INITGAME.DAT の npc.dat から NPC の英語の名前を拾い、translation/npc_names_en.txt に書く（読むだけ）
#   python npc_names_en.py
# 人物の記録は長さが変わるので、名前らしい欄（大文字で始まり 0 で終わる英字）をすべて拾う。
# 名前のあとの 0 から先は、前の名前の残りのごみのことがある。余計なものを拾っても、訳のない名前は表に入らない。
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from u7flex import read_flex
head, ents = read_flex(os.path.join(here, '..', '..', 'STATIC', 'INITGAME.DAT'))
npc = None
for e in ents:
    if e and e[:13].rstrip(b'\0').lower() == b'npc.dat':
        npc = e[13:]
if npc is None:
    sys.exit('npc.dat が見つかりません')
names = []
for m in re.finditer(rb"([A-Z][A-Za-z' .\-]{1,15})\0", npc):
    n = m.group(1).decode('latin-1').strip()
    if n not in names:
        names.append(n)
open(os.path.join(here, '..', 'translation', 'npc_names_en.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(sorted(names)) + '\n')
print(f'npc.dat {len(npc)} バイト、名前 {len(names)} 個')
print(' / '.join(sorted(names)))
