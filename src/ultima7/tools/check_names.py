# 固有名詞の訳が訳文に入っているかを調べる
#   使い方: python check_names.py XXXX [XXXX ...]   （関数の番号。--batch 06 なら組の関数）
# 原文に translation/固有名詞.tsv の語（4字以上）が単語として出てくるのに、
# 訳文にその訳が無い行を挙げる。言い換えで正しいこともあるので、目で確かめる用。
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')

def load_gloss():
    gl = {}
    for line in open(os.path.join(TR, '固有名詞.tsv'), encoding='utf-8-sig'):
        c = line.rstrip('\r\n').split('\t')
        if line.startswith('#') or len(c) < 2 or not c[1]:
            continue
        if len(c[0]) >= 4 and (len(c) < 3 or c[2] not in ('呪文・魔法',)):
            gl[c[0]] = c[1]
    # 長い語から当てる（Lord British を British より先に）
    return sorted(gl.items(), key=lambda x: -len(x[0]))

def check(fid, gl):
    out = []
    for line in open(os.path.join(TR, 'usecode', f'{fid}.tsv'), encoding='utf-8'):
        c = line.rstrip('\n').split('\t')
        if line.startswith('#') or len(c) < 3 or not c[2]:
            continue
        en, ja = c[1], c[2]
        used = en
        for term, tr in gl:
            if re.search(r'(?<![A-Za-z])' + re.escape(term) + r'(?![A-Za-z])', used):
                used = used.replace(term, ' ')
                # 訳に「・」の有無などの違いは許す
                if tr not in ja and tr.replace('・', '') not in ja.replace('・', ''):
                    out.append(f'{fid} {c[0]}: {term} → 「{tr}」が訳に無い: {ja[:60]}')
    return out

def main(args):
    if args and args[0] == '--batch':
        fids = []
        for line in open(os.path.join(TR, 'batches.tsv'), encoding='utf-8'):
            c = line.rstrip('\n').split('\t')
            if not line.startswith('#') and c[0] in args[1:]:
                fids += c[1].split()
    else:
        fids = args
    gl = load_gloss(); n = 0
    for f in fids:
        for p in check(f, gl):
            print(p); n += 1
    print(f'固有名詞が訳に無い行: {n}')

if __name__ == '__main__':
    main(sys.argv[1:])
