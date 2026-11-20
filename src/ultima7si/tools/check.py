# 訳の点検（読むだけ。ファイルは書きかえない）
#   python check.py
# 調べること:
#   1. 記号 @ * の数が原文と訳で合っているか、~ が消えていないか
#   2. 同じ関数の中で、同じ英語の 1 語〜数語の行（選択肢らしいもの）が同じ訳になっているか
#   3. 日本語フォント（test\patch\jfont8.bin）にない文字を使っていないか
#   4. 訳の中に英字だけの行が残っていないか（開発用の文は除く）
import sys, os, struct, collections, re
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from si_uc import read_tsv
sys.stdout.reconfigure(encoding='utf-8')
W = os.path.join(here, '..')
tr = read_tsv(os.path.join(W, 'translation', 'usecode'))

# フォントの字
d = open(os.path.join(W, 'test', 'patch', 'jfont8.bin'), 'rb').read()
n = struct.unpack_from('<H', d, 6)[0]
font = set(struct.unpack_from(f'<{n}I', d, 12))

bad_sym = []; bad_ans = []; missing = collections.Counter(); where = {}; eng = []
for fid, items in sorted(tr.items()):
    seen = {}
    for off, (en, ja) in items.items():
        for ch in '@*':
            if en.count(ch) != ja.count(ch):
                bad_sym.append(f'{fid:04x} {off}: 「{ch}」 原文 {en.count(ch)} 訳 {ja.count(ch)}')
        if '~' in en and '~' not in ja:
            bad_sym.append(f'{fid:04x} {off}: ~ が消えている')
        if re.fullmatch(r"[A-Za-z][A-Za-z' ?!\-]{0,30}", en) and en == en.strip():
            if en in seen and seen[en] != ja:
                bad_ans.append(f'{fid:04x} 「{en}」: {seen[en]} ／ {ja}')
            seen.setdefault(en, ja)
        for ch in ja:
            if ord(ch) >= 0x80 and ord(ch) not in font:
                missing[ch] += 1
                where.setdefault(ch, f'{fid:04x} {off}')
        if ja == en and re.search(r'[a-z]{3}', en) and not re.search(r'Error|failed|Usecode|push|pop', en):
            eng.append(f'{fid:04x} {off}: {en[:60]}')

print(f'== 記号の数のずれ: {len(bad_sym)} 件')
for x in bad_sym[:60]: print('  ', x)
print(f'== 同じ関数の中で選択肢の訳がそろっていない: {len(bad_ans)} 件')
for x in bad_ans[:60]: print('  ', x)
print(f'== フォントにない文字: {len(missing)} 種類')
for ch, c in missing.most_common(80): print(f'   {ch} U+{ord(ch):04X} {c} 回（例 {where[ch]}）')
print(f'== 原文のまま残っている英文: {len(eng)} 件')
for x in eng[:40]: print('  ', x)
