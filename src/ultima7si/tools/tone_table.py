# 人物の管理表を作る（読むだけ。訳ファイルは書きかえない）
#   python tone_table.py
# 出力:
#   translation\管理表_人物.csv      … 関数ごとの一人称・呼び方・口調の実績と、決定（決定_人物.tsv があればそれを使う）
#   translation\管理表_ずれ候補.tsv  … 決定と食いちがう行の一覧（直す候補）
# 決定は translation\決定_人物.tsv（関数<TAB>人物<TAB>一人称<TAB>呼び方<TAB>口調）。ない関数は実績の多数で仮に決める。
# 口調: 丁寧 / 男 / 女 / 老人 / 片言 / 混在（決めない）
import sys, os, re, csv, collections
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from si_uc import read_tsv
from checked import load_checked
sys.stdout.reconfigure(encoding='utf-8')
T = os.path.join(here, '..', 'translation')
tr = read_tsv(os.path.join(T, 'usecode'))

FIRST = ['わたくし', 'わたし', 'わし', 'おれ', 'あたし', 'ぼく', 'わらわ']
SECOND = ['あなた', 'きみ', 'おまえ', 'そなた', 'あんた', 'おぬし', 'きさま']
# 語尾（文の終わり）
RE_END = re.compile(r'([^「」。！？…\s]{1,6})(?=[。！？]|……|」|$)')
POLITE = re.compile(r'(です|ます|でした|ました|ません|でしょう|ましょう|ください|ございます|ませ|さま|様)(よ|ね|か|が|けど|から|わ|の)*$')
FEMALE = re.compile(r'(わ|のよ|かしら|わね|わよ|なのね|ですわ)$')
MALE = re.compile(r'(ぞ|だぜ|ぜ|だな|じゃねえ|だろうが|しろ)$')

# 一人称・二人称は、うしろに助詞や句読点が続く形だけを数える（「くわしい」「けがらわしい」「折れた」「不気味」などを拾わない）
AFTER = r'(?=[はがのをにもとへやでよ、。！？」…\s]|たち|ら|自身|さん|さま|様|$)'
BEFORE = r'(?<![ぁ-んァ-ヶ一-龠])'
def count_words(s, words):
    c = {}
    rest = s
    for w in sorted(words, key=len, reverse=True):
        pat = re.compile(BEFORE + re.escape(w) + AFTER)
        n = len(pat.findall(rest))
        if n:
            c[w] = n
            rest = pat.sub('　', rest)
    return c

def is_talk(ja):
    return '「' in ja or '」' in ja or '@' in ja

# 名前（概要表の自己紹介）と下書きの 1 行目
names = {}
sp = os.path.join(T, 'summary.tsv')
if os.path.exists(sp):
    for line in open(sp, encoding='utf-8'):
        c = line.rstrip('\n').split('\t')
        if len(c) >= 6 and re.fullmatch(r'[0-9a-f]{4}', c[0]):
            m = re.search(r"(?:I am|My name is|name is|I'm) ([A-Z][\w']+(?: [A-Z][\w']+)?)", c[5])
            names[c[0]] = m.group(1) if m else ''
def draft_note(fid):
    p = os.path.join(T, 'draft', f'{fid}.txt')
    if os.path.exists(p):
        for line in open(p, encoding='utf-8-sig'):
            if line.startswith('#'):
                return line.strip('# \n')[:80]
    return ''

decided = {}
dp = os.path.join(T, '決定_人物.tsv')
if os.path.exists(dp):
    for line in open(dp, encoding='utf-8-sig'):
        if line.startswith('#') or not line.strip():
            continue
        c = line.rstrip('\n').split('\t')
        while len(c) < 6:
            c.append('')
        decided[c[0].lower()] = c[1:5]
        decided_state = globals().setdefault('decided_state', {})
        decided_state[c[0].lower()] = c[5] or '決定'

checked = load_checked(T); n_checked = 0
rows = []; cands = []
for fid, items in sorted(tr.items()):
    f = f'{fid:04x}'
    talk = [(off, en, ja) for off, (en, ja) in sorted(items.items()) if ja != en and is_talk(ja)]
    if len(talk) < 8:
        continue    # 会話の少ない関数は表に入れない
    fc = collections.Counter(); sc = collections.Counter()
    ends = collections.Counter()
    for off, en, ja in talk:
        fc.update(count_words(ja, FIRST)); sc.update(count_words(ja, SECOND))
        for m in RE_END.finditer(ja.replace('　', '')):
            e = m.group(1)
            if POLITE.search(e): ends['丁寧'] += 1
            elif FEMALE.search(e): ends['女'] += 1
            elif MALE.search(e): ends['男'] += 1
            else: ends['普通'] += 1
    tot_end = sum(ends.values()) or 1
    top_first = fc.most_common(1)[0][0] if fc else ''
    top_second = sc.most_common(1)[0][0] if sc else ''
    pol = ends['丁寧'] / tot_end; fem = ends['女'] / tot_end; mal = ends['男'] / tot_end
    auto_tone = '丁寧' if pol > 0.45 else ('女' if fem > 0.12 and fem > mal else ('男' if mal > 0.08 else '普通'))
    name, d_first, d_second, d_tone = (decided.get(f) or [names.get(f, ''), '', '', ''])
    d_first = d_first or top_first; d_second = d_second or top_second; d_tone = d_tone or auto_tone
    # 「－」は決めない（話し手の多い関数）
    d_first = '' if d_first == '－' else d_first; d_second = '' if d_second == '－' else d_second
    # ずれ候補: 決定と別の一人称・呼び方を使う行、口調の逆（男⇔女、丁寧の人の普通体）
    n_c = 0
    for off, en, ja in talk:
        why = []
        fw = count_words(ja, FIRST); sw = count_words(ja, SECOND)
        if d_first and any(w != d_first for w in fw) and d_first not in fw:
            why.append('一人称:' + '/'.join(fw))
        if d_second and any(w != d_second for w in sw) and d_second not in sw:
            why.append('呼び方:' + '/'.join(sw))
        e_list = [m.group(1) for m in RE_END.finditer(ja.replace('　', ''))]
        if d_tone == '男' and any(FEMALE.search(e) for e in e_list):
            why.append('男なのに女言葉')
        if d_tone == '女' and any(MALE.search(e) for e in e_list):
            why.append('女なのに男言葉')
        if d_tone == '丁寧' and e_list and not any(POLITE.search(e) for e in e_list) and not re.search(r'(です|ます|ません|ください|ましょう|ございま)', ja) and len(ja) > 12:
            why.append('丁寧語でない')
        if why and (f, off) in checked:
            n_checked += 1; why = []
        if why:
            n_c += 1
            cands.append((f, off, name, d_first, d_second, d_tone, ' '.join(why), en, ja))
    rows.append([f, name, draft_note(f), len(talk),
                 ' '.join(f'{w}{n}' for w, n in fc.most_common(4)),
                 ' '.join(f'{w}{n}' for w, n in sc.most_common(4)),
                 f'{pol:.0%}', f'{fem:.0%}', f'{mal:.0%}',
                 d_first, d_second, d_tone, globals().get('decided_state', {}).get(f, '仮'), n_c])

with open(os.path.join(T, '管理表_人物.csv'), 'w', encoding='utf-8-sig', newline='') as w:
    cw = csv.writer(w)
    cw.writerow(['関数', '人物', '下書きのメモ', '会話の行数', '一人称の実績', '呼び方の実績',
                 '丁寧語の割合', '女言葉の割合', '男言葉の割合', '決定_一人称', '決定_呼び方', '決定_口調', '決定の状態', 'ずれ候補の行数'])
    cw.writerows(rows)
with open(os.path.join(T, '管理表_ずれ候補.tsv'), 'w', encoding='utf-8', newline='\n') as w:
    w.write('# 関数\t位置\t人物\t決定_一人称\t決定_呼び方\t決定_口調\tずれ\t原文\t訳\n')
    for c in cands:
        w.write('\t'.join(str(x).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ') for x in c) + '\n')
print(f'人物の表 {len(rows)} 関数、ずれ候補 {len(cands)} 行、判定済みで外した {n_checked} 行（決定済み {sum(1 for r in rows if r[12] == "決定")} 関数）')
