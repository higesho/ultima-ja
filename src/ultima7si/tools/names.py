# TEXT.FLX の物の名前を「英語の名前ごと」にまとめ、訳の辞書から番号つきの訳に戻す
#   一覧を作る: python names.py list 出力.txt
#       （0〜1023 番と 1280〜1669 番。「a/black pearl//s」は「black pearl」にまとめる）
#   訳を戻す:   python names.py apply 辞書.tsv
#       辞書は「英語の名前<TAB>訳」。translation/text_ja.tsv の名前の行（0〜1023、1280〜1669）を作り直す。
#       1024〜1263 のひとことの行はそのまま残す。
import sys, os, re
here = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding='utf-8')
EN = os.path.join(here, '..', 'translation', 'text_en.tsv')
JA = os.path.join(here, '..', 'translation', 'text_ja.tsv')

def base(name):
    """「a/black pearl//s」→「black pearl」。スラッシュがなければそのまま"""
    if '/' in name:
        parts = name.split('/')
        if len(parts) >= 2:
            return parts[1].strip()
    return name.strip()

def load_en():
    out = []
    for line in open(EN, encoding='utf-8'):
        if line.startswith('#'):
            continue
        c = line.rstrip('\n').split('\t')
        i = int(c[0])
        if i < 1024 or 1280 <= i < 1670:
            out.append((i, c[1]))
    return out

def cmd_list(dst):
    groups = {}
    for i, name in load_en():
        b = base(name)
        if not b:
            continue
        groups.setdefault(b, []).append(i)
    with open(dst, 'w', encoding='utf-8', newline='\n') as w:
        for b, idx in sorted(groups.items(), key=lambda x: x[1][0]):
            w.write(f'{b}\t{",".join(map(str, idx))}\n')
    print(f'{len(groups)} 種類')

def cmd_apply(dic):
    tr = {}
    for line in open(dic, encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        if not line or line.startswith('#'):
            continue
        en, ja = line.split('\t')[:2]
        tr[en] = ja
    keep = []
    for line in open(JA, encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        if line and not line.startswith('#'):
            i = int(line.split('\t')[0])
            if i < 1024 or 1280 <= i < 1670:
                continue    # 名前の行は作り直す
        keep.append(line)
    rows = []; miss = set()
    for i, name in load_en():
        b = base(name)
        if not b:
            continue
        if b in tr:
            rows.append(f'{i}\t{tr[b]}')
        else:
            miss.add(b)
    with open(JA, 'w', encoding='utf-8', newline='\n') as w:
        w.write('\n'.join(keep).rstrip('\n') + '\n')
        w.write('# 0〜1023: 物の名前、1280〜1669: 品物の種類の名前（「a/black pearl//s」の形は外して名前だけにする）\n')
        w.write('\n'.join(rows) + '\n')
    print(f'名前 {len(rows)} 件を書きました。訳のない名前 {len(miss)} 種類')
    for m in sorted(miss):
        print('  未訳:', m)

if __name__ == '__main__':
    if sys.argv[1] == 'list':
        cmd_list(sys.argv[2])
    else:
        cmd_apply(sys.argv[2])
