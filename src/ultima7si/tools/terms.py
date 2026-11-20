# 各束の NN_terms.tsv を集めて、同じ英語に別の訳がついているものを洗い出す
#   python terms.py 出力.txt
import sys, os, re, collections
here = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding='utf-8')
B = os.path.join(here, '..', 'translation', 'bundles')
G = os.path.join(here, '..', 'translation', '用語集.md')
N = os.path.join(here, '..', 'translation', 'names_ja.tsv')

def norm(s):
    return re.sub(r'（.*?）|\(.*?\)', '', s).strip()

terms = collections.defaultdict(lambda: collections.defaultdict(set))
for name in sorted(os.listdir(B)):
    m = re.fullmatch(r'(\d\d)_terms\.tsv', name)
    if not m:
        continue
    for line in open(os.path.join(B, name), encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        if not line or line.startswith('#') or '\t' not in line:
            continue
        en, ja = line.split('\t')[:2]
        terms[en.strip().lower()][norm(ja)].add(m.group(1))

# 用語集の表から「原文 | 訳」を拾う（表の行と、「A 訳 / B 訳」の並び）
gloss = {}
for line in open(G, encoding='utf-8'):
    if line.startswith('|') and not line.startswith('|---'):
        c = [x.strip() for x in line.strip('|\n').split('|')]
        if len(c) >= 2:
            ens = [x.strip() for x in c[0].split('/')]
            jas = [x.strip() for x in c[1].split('/')]
            if len(ens) == len(jas):
                for e, j in zip(ens, jas):
                    gloss[e.lower()] = norm(j)
    for m in re.finditer(r'([A-Z][A-Za-z\'\-]+(?: [A-Z][A-Za-z\'\-]+)?) ([ァ-ヶー・]+)', line):
        gloss.setdefault(m.group(1).lower(), m.group(2))
for line in open(N, encoding='utf-8'):
    if '\t' in line and not line.startswith('#'):
        e, j = line.rstrip('\n').split('\t')[:2]
        gloss.setdefault(e.lower(), j)

with open(sys.argv[1], 'w', encoding='utf-8', newline='\n') as w:
    w.write('# 束のあいだで訳が分かれた語（英語<TAB>訳:束,束 ／ 訳:束）\n')
    n1 = n2 = 0
    for en, js in sorted(terms.items()):
        if len(js) > 1:
            w.write(en + '\t' + ' ／ '.join(f'{j}:{",".join(sorted(b))}' for j, b in js.items()) + '\n'); n1 += 1
    w.write('\n# 用語集・物の名前とちがう訳（英語<TAB>束の訳<TAB>用語集の訳）\n')
    for en, js in sorted(terms.items()):
        if en in gloss:
            for j in js:
                if j and gloss[en] and j != gloss[en] and gloss[en] not in j:
                    w.write(f'{en}\t{j}\t{gloss[en]}\n'); n2 += 1
print(f'束のあいだのゆれ {n1} 語、用語集とのちがい {n2} 件、束の語の総数 {len(terms)}')
