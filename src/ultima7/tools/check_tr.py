# 訳の機械的な確認
#   使い方: python check_tr.py XXXX [XXXX ...]   （関数の番号。省略すると訳のある関数すべて）
#           python check_tr.py --global          （関数をまたいで比べる語が、どの関数でも同じ訳か）
# 見ること:
#   - 訳し漏れ（訳の列が空の行）
#   - @ ~ * の数が原文と同じか
#   - 訳にタブや半角の " が残っていないか
#   - 同じ関数の中で、同じ原文には同じ訳か（選択肢の照合が崩れないように）
#   - 用語集の「会話の選択肢」の表と合っているか
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
UC = os.path.join(HERE, '..', 'translation', 'usecode')
GLOSS = os.path.join(HERE, '..', 'translation', '用語集.md')

def load_answers():
    """用語集の「会話の選択肢」の表 → {原文: 訳}"""
    ans = {}; on = False
    for line in open(GLOSS, encoding='utf-8'):
        if line.startswith('## '):
            on = '選択肢' in line; continue
        if not on or not line.startswith('|') or '---' in line or '原文' in line:
            continue
        cols = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cols) < 2:
            continue
        en, ja = cols[0], cols[1]
        en = re.sub(r'（.*?）', '', en)
        ens = [e.strip() for e in en.split('/')]; jas = [j.strip() for j in ja.split('/')]
        if len(ens) == len(jas):
            for e, j in zip(ens, jas):
                ans[e] = j
    return ans

# 看板などルーン文字で書かれた文の関数（* などが字の代わり）
RUNE_FUNCS = {'0334', '02cb', '017b'}

_cmp_cache = None

def compared_in(fid):
    """その関数で比べる命令に使う文字列（選択肢のキーワードなど）"""
    global _cmp_cache
    if _cmp_cache is None:
        sys.path.insert(0, HERE)
        from find_xcmp import analyse
        _cmp_cache = {f'{k:04x}': {w.decode('latin-1') for w in v[0]} for k, v in analyse().items()}
    return _cmp_cache.get(fid, set())

def check(fid, answers):
    path = os.path.join(UC, f'{fid}.tsv')
    rows = []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        cols = line.split('\t')
        rows.append((cols[0], cols[1], cols[2] if len(cols) > 2 else '', len(cols)))
    probs = []
    done = [r for r in rows if r[2]]
    if not done:
        return None
    for off, en, ja, nc in rows:
        if not ja:
            if en.strip():    # 原文が空（や空白だけ）の行は訳さなくてよい
                probs.append(f'{off}: 訳がありません: {en[:50]}')
            continue
        if nc > 3:
            probs.append(f'{off}: 訳の中にタブがあります')
        for ch in '@~*':
            if ch == '*' and fid in RUNE_FUNCS:
                continue    # 看板のルーン文字では * は ng を表す字。訳では使わない
            if en.count(ch) != ja.count(ch):
                probs.append(f'{off}: 「{ch}」の数が違います（原文 {en.count(ch)}、訳 {ja.count(ch)}）')
        if '"' in ja:
            probs.append(f'{off}: 訳に半角の " があります')
        if en in answers and ja != answers[en]:
            probs.append(f'{off}: 選択肢「{en}」は用語集では「{answers[en]}」（訳は「{ja}」）')
    same = {}
    for off, en, ja, nc in rows:
        if ja:
            same.setdefault(en, set()).add(ja)
    keys = compared_in(fid)
    for en, jas in same.items():
        # 選択肢として比べる語だけは、同じ関数の中で必ず同じ訳にする（句読点などの断片は場面ごとでよい）
        if len(jas) > 1 and en in keys:
            probs.append(f'同じ原文「{en}」に違う訳（選択肢）: {" / ".join(sorted(jas))}')
    return len(rows), len(done), probs

def compared_words():
    """関数をまたいで比べる語（find_xcmp.py の判定）→ {語: 関わる関数の番号の集まり}"""
    sys.path.insert(0, HERE)
    from find_xcmp import cross_words
    return {w.decode('latin-1'): {f'{x:04x}' for x in fids} for w, fids in cross_words().items()}

def check_global():
    """関数をまたいで比べる語が、関わるすべての関数で同じ訳か。
    片方の関数だけ訳して、もう片方が未訳のときも知らせる（英語と日本語で比べることになるため）。"""
    words = compared_words()
    seen = {}       # 原文 → {訳: {関数}}
    untr = {}       # 原文 → {原文のまま残っている関数}
    for name in sorted(os.listdir(UC)):
        if not name.endswith('.tsv'):
            continue
        fid = name[:4]
        for line in open(os.path.join(UC, name), encoding='utf-8'):
            cols = line.rstrip('\n').split('\t')
            if line.startswith('#') or len(cols) < 2 or cols[1] not in words or fid not in words[cols[1]]:
                continue
            if len(cols) >= 3 and cols[2]:
                seen.setdefault(cols[1], {}).setdefault(cols[2], set()).add(fid)
            else:
                untr.setdefault(cols[1], set()).add(fid)
    bad = 0
    for en, jas in sorted(seen.items()):
        if len(jas) > 1:
            bad += 1
            print(f'「{en}」の訳が違う: ' + ' / '.join(f'{ja}（{" ".join(sorted(f))}）' for ja, f in sorted(jas.items())))
        if en in untr:
            bad += 1
            print(f'「{en}」: 訳した関数（{" ".join(sorted(set().union(*jas.values())))}）と、'
                  f'まだ訳していない関数（{" ".join(sorted(untr[en]))}）がある')
    print(f'関数をまたいで比べる語の問題: {bad} 件')
    return bad

def main(fids):
    if fids == ['--global']:
        sys.exit(1 if check_global() else 0)
    answers = load_answers()
    if not fids:
        fids = sorted(f[:4] for f in os.listdir(UC) if f.endswith('.tsv'))
    bad = 0
    for fid in fids:
        r = check(fid.lower(), answers)
        if r is None:
            continue
        total, done, probs = r
        mark = 'OK' if not probs else f'{len(probs)} 件'
        print(f'{fid}: {done}/{total} 訳済み  確認 {mark}')
        for p in probs:
            print('   ', p)
        bad += bool(probs)
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main(sys.argv[1:])
