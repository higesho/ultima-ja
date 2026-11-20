# NPC の名前の対応表（Exult の <PATCH>/npc_names.txt）を作る
#   使い方: python mknames.py 出力npc_names.txt
# translation/npc_names_en.txt の名前を、translation/固有名詞.tsv（原文<TAB>訳<TAB>…）で引く。
# 一覧に無い名前は最後に挙げる（その名前は英語のまま表示される）。
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')

def main(dst):
    table = {}
    for line in open(os.path.join(TR, '固有名詞.tsv'), encoding='utf-8-sig'):
        if line.startswith('#') or '\t' not in line:
            continue
        cols = line.rstrip('\r\n').split('\t')
        if len(cols) >= 2 and cols[1]:
            table.setdefault(cols[0], cols[1])
    names = [l.strip() for l in open(os.path.join(TR, 'npc_names_en.txt'), encoding='utf-8') if l.strip()]
    missing = []
    with open(dst, 'w', encoding='utf-8', newline='\n') as w:
        w.write('# NPC の名前の訳（英語<TAB>日本語）。tools/mknames.py が作る\n')
        for n in names:
            if n == 'Avatar':
                continue    # プレイヤーの名前は訳さない
            if n in table:
                w.write(f'{n}\t{table[n]}\n')
            else:
                missing.append(n)
    print(f'{dst}: {len(names) - len(missing)} 人')
    if missing:
        print('一覧に無い名前:', ' / '.join(missing))

if __name__ == '__main__':
    main(sys.argv[1])
