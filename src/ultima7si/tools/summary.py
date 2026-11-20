# 関数ごとの概要（文字列の量、自己紹介らしい文、地名の出現）を書き出す
#   使い方: python summary.py 出力.tsv
import sys, os, re
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from si_uc import read_tsv
tr = read_tsv(os.path.join(here, '..', 'translation', 'usecode'), with_empty=True)
places = ['Monitor', 'Fawn', 'Sleeping Bull', 'Moonshade', 'Furnace', 'Spinebreaker', 'Monk Isle', 'Skullcrusher', 'Gorlab', 'Shamino\'s Castle', 'Gwani', 'Vasculio', 'Bull Tower', 'Dark Path', 'Mad Mage', 'Silver Seed']
with open(sys.argv[1], 'w', encoding='utf-8', newline='\n') as w:
    w.write('関数\t文字列数\t原文バイト\t訳済\t地名\t自己紹介\n')
    for fid, items in sorted(tr.items()):
        texts = [en for en, ja in items.values()]
        n = sum(len(t) for t in texts)
        done = sum(1 for en, ja in items.values() if ja)
        allt = ' '.join(texts)
        pl = ','.join(f'{p}:{allt.count(p)}' for p in places if allt.count(p))
        intro = ''
        for t in texts:
            m = re.search(r'(I am [A-Z][a-z]+[^."!?]*|[Mm]y name is [A-Z][a-z]+[^."!?]*|They call me [A-Z][a-z]+)', t)
            if m:
                intro = m.group(1)[:60]; break
        if not intro:
            intro = next((t[:60] for t in texts if t.startswith('"')), texts[0][:60] if texts else '')
        w.write(f'{fid:04x}\t{len(items)}\t{n}\t{done}\t{pl}\t{intro}\n')
print('ok')
