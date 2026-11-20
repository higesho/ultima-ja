# 用語の管理表を作る（読むだけ）
#   python term_table.py
# 用語集.md の表（| 原文 | 訳 |、A / B の並び）と「Name 訳」の並びから「英語→決定訳」を取り出し、
# 原文にその英語があるのに訳に決定訳がない行を「ずれ候補」として書き出す。
# 出力: translation\管理表_用語.csv、translation\管理表_用語ずれ候補.tsv
import sys, os, re, csv, collections
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from si_uc import read_tsv
from checked import load_checked
sys.stdout.reconfigure(encoding='utf-8')
T = os.path.join(here, '..', 'translation')
tr = read_tsv(os.path.join(T, 'usecode'))
SKIP = {'017b', '0334', '02c5', '00a0', '07ff'}

pairs = {}
def add(e, j):
    e = re.sub(r'（.*?）|\(.*?\)', '', e).strip(); j = re.sub(r'（.*?）|\(.*?\)', '', j).strip()
    if len(e) >= 4 and j and re.search(r'[A-Za-z]', e) and not re.search(r'[A-Za-z]', j) and '○' not in e:
        pairs.setdefault(e, j)
for line in open(os.path.join(T, '用語集.md'), encoding='utf-8'):
    if line.startswith('|') and not line.startswith('|---'):
        c = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(c) >= 2:
            es = [x.strip() for x in c[0].split('/')]; js = [x.strip() for x in c[1].split('/')]
            if len(es) == len(js):
                for e, j in zip(es, js):
                    add(e, j)
    for m in re.finditer(r"([A-Z][A-Za-z'\-]+(?: [A-Z][A-Za-z'\-]+)*) ([ァ-ヶー・]+)", line):
        add(m.group(1), m.group(2))

# 大文字で始まる固有名詞だけを対象にする（一般語は文脈で訳が変わるため）
NOISE = {'I am', 'Mages', 'Master', 'Knighthood', 'Command', 'Truth', 'Order', 'Love', 'Beauty', 'Courage',
         'Balance', 'Chaos', 'Hero', 'Unity', 'Library', 'Shrine', 'Freedom'}
pairs = {e: j for e, j in pairs.items() if e[0].isupper() and e not in NOISE}
checked = load_checked(T); n_checked = 0
stat = collections.defaultdict(lambda: [0, 0]); cands = []
def hit(e, en):
    return re.search(r'(?<![A-Za-z])' + re.escape(e).replace(r'\ of\ ', r'\ of\ (?:the\ )?') + r"(?![a-z])", en)
for fid, items in sorted(tr.items()):
    f = f'{fid:04x}'
    if f in SKIP:
        continue
    for off, (en, ja) in sorted(items.items()):
        if ja == en:
            continue
        for e, j in pairs.items():
            if hit(e, en):
                stat[e][0] += 1
                # 決定訳（・を除いた形も許す）が入っていれば一致
                if j in ja or j.replace('・', '') in ja.replace('・', ''):
                    stat[e][1] += 1
                elif any(e != e2 and e in e2 and hit(e2, en) and j2 in ja for e2, j2 in pairs.items()):
                    stat[e][1] += 1     # 長い用語（Isle of Crypts など）の訳が入っている
                elif (f, off) in checked:
                    stat[e][1] += 1; n_checked += 1
                else:
                    cands.append((f, off, e, j, en, ja))

with open(os.path.join(T, '管理表_用語.csv'), 'w', encoding='utf-8-sig', newline='') as w:
    cw = csv.writer(w)
    cw.writerow(['英語', '決定訳', '原文に出る行数', '決定訳が入っている行数', 'ずれ候補の行数'])
    for e, j in sorted(pairs.items(), key=lambda x: -(stat[x[0]][0] - stat[x[0]][1])):
        n, ok = stat[e]
        if n:
            cw.writerow([e, j, n, ok, n - ok])
with open(os.path.join(T, '管理表_用語ずれ候補.tsv'), 'w', encoding='utf-8', newline='\n') as w:
    w.write('# 関数\t位置\t英語\t決定訳\t原文\t訳\n')
    for c in cands:
        w.write('\t'.join(str(x).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ') for x in c) + '\n')
print(f'用語 {len(pairs)} 組、原文に出る用語 {sum(1 for e in pairs if stat[e][0])}、ずれ候補 {len(cands)} 行（判定済みで外した {n_checked}）')
