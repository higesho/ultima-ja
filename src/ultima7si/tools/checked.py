# 統一作業の判定（translation\統一作業\NN_結果.tsv）を読む。直さないと判定した行を、管理表の候補から外すのに使う
import os, re
def load_checked(T):
    D = os.path.join(T, '統一作業'); done = {}
    if not os.path.isdir(D):
        return done
    for name in os.listdir(D):
        if re.fullmatch(r'\d\d_結果\.tsv', name):
            for l in open(os.path.join(D, name), encoding='utf-8-sig'):
                p = l.rstrip('\n').split('\t')
                if len(p) >= 3 and re.fullmatch(r'[0-9a-f]{4}', p[0].strip().lower()) and p[1].strip().isdigit():
                    if p[2].strip() != '直した':
                        done[(p[0].strip().lower(), int(p[1]))] = p[2].strip()
    return done