# 2026-11-24 の版（DLL にバージョン情報を入れた版）の更新履歴を、説明書（dist_src）とリリースの文（release）に足す
#   python -I tools/add_history_20261124.py   一度だけ使う（もう足してあれば何もしない）
import os, sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.normpath(os.path.join(HERE, '..'))
DATE = '2026-11-24'
NOTE = 'ウイルス対策ソフトに誤検知されにくいよう、DLL にバージョン情報を入れました。訳文は前の版と同じです。'
NOTE_TXT = ['ウイルス対策ソフトに誤検知されにくいよう、DLL にバージョン情報を入れました。',
            '訳文は前の版と同じです。']
GAMES = [('はじめにお読みください.txt', 'underworld', 'v1.4', 'v1.5'),
         ('uw2_はじめにお読みください.txt', 'underworld2', 'v1.3', 'v1.4')]

for readme, tag, old, new in GAMES:
    p = os.path.join(WORK, 'dist_src', readme)
    raw = open(p, 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    t = raw.decode('utf-8-sig')
    nl = '\r\n' if '\r\n' in t else '\n'
    ls = t.replace('\r\n', '\n').split('\n')
    if any(f'{new}（{DATE}）' in l for l in ls):
        print('もう足してある:', p)
    else:
        entry = [f'  {new}（{DATE}）'] + ['    ' + l for l in NOTE_TXT]
        if any(l.startswith('■ 更新履歴') for l in ls):
            k = next(i for i, l in enumerate(ls) if l.startswith('■ 更新履歴'))
            ls[k + 1:k + 1] = entry
        else:
            k = next(i for i, l in enumerate(ls) if l.startswith('■ 最新版'))
            ls[k:k] = ['■ 更新履歴'] + entry + ['']
        out = '\n'.join(ls).replace('\n', nl)
        open(p, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + out.encode('utf-8'))
        print('説明書に足した:', p)
    # リリースの文: 前の版の文の先頭に「## <新しい版> の変更」を足す
    src = os.path.join(WORK, 'release', f'{tag}-{old}.md')
    dst = os.path.join(WORK, 'release', f'{tag}-{new}.md')
    if os.path.exists(dst):
        print('もうある:', dst)
        continue
    t = open(src, encoding='utf-8').read()
    open(dst, 'w', encoding='utf-8', newline='\n').write(f'## {new} の変更\n\n- {NOTE}\n\n' + t)
    print('リリースの文:', dst)
