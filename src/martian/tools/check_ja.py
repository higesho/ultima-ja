"""訳のファイルを英文のファイルと比べて確かめる。
使い方: python tools/check_ja.py <英文 .tsv> <訳 .tsv>
  例: python tools/check_ja.py translation/conv_en/A002.tsv translation/conv_ja/A002.tsv
      python tools/check_ja.py translation/other_en/game.tsv translation/other_ja/game.tsv
「問題なし」と出るまで直すこと。注意（警告）は内容を見て、必要なら直す
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from conv_text import unesc, HL_STOP, is_kana  # noqa: E402
from jpenc import load_bdf  # noqa: E402

BDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "font", "misaki_gothic_2nd.bdf")
MARKS = re.compile(r"\$[A-Z0-9]|#[0-9]|\*")
FMT = re.compile(r"%[-0-9]*[A-Za-z]")
RUNE = re.compile(r"<[^>]*>")
# MD: 書式を使わずに訳してよい行（young %sman の %s は性別の "wo"）
FMT_FREE = {'game:2cc8d', 'game:301e9'}


def read(path):
    rows = {}
    order = []
    for n, line in enumerate(open(path, encoding='utf-8'), 1):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        if '\t' not in line:
            raise SystemExit(f"{path}:{n}: タブがない行: {line[:60]}")
        k, v = line.split('\t', 1)
        if k in rows:
            raise SystemExit(f"{path}:{n}: 番号が重なっている: {k}")
        rows[k] = unesc(v)
        order.append(k)
    return rows, order


def highlights(ja):
    """訳の @…@ の強調を取り出す。戻り値: (語の並び, 問題の並び)"""
    words, errs = [], []
    i = 0
    while True:
        i = ja.find('@', i)
        if i < 0:
            break
        j = i + 1
        while j < len(ja) and ja[j] != '@' and ja[j] not in HL_STOP:
            j += 1
        w = ja[i + 1:j]
        if j < len(ja) and ja[j] == '@':
            words.append(w)
            i = j + 1
        else:
            if any(ord(c) > 0x7e for c in w):
                errs.append(f"日本語の強調「@{w}」に閉じの @ がない")
            else:
                words.append(w)
            i = j
    return words, errs


def edge_nl(s):
    return len(s) - len(s.lstrip('\n')), len(s) - len(s.rstrip('\n'))


def main(enpath, japath):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    en, order = read(enpath)
    ja, _ = read(japath)
    font = load_bdf(BDF)
    errs, warns = [], []
    conv = any(':t' in k or ':k' in k for k in en)
    for k in order:
        if k not in ja:
            errs.append(f"{k}: 訳がない")
    for k in ja:
        if k not in en:
            errs.append(f"{k}: 英文にない番号")
    kw_lines = {}
    hl_words = {}
    for k in order:
        if k not in ja:
            continue
        e, j = en[k], ja[k]
        bad = sorted({c for c in j if ord(c) > 0x7e and ord(c) not in font})
        if bad:
            errs.append(f"{k}: 美咲フォントにない字（別の字か、かなに）: {''.join(bad)}")
        if any('｡' <= c <= 'ﾟ' for c in j):
            errs.append(f"{k}: 半角カナは使わない")
        if conv and ':k' in k:
            items = [x.strip() for x in j.split(',')]
            orig = [x.strip() for x in e.split(',')]
            if items[:len(orig)] != orig:
                errs.append(f"{k}: キーワードの行は、元の英語（{e}）をそのまま先に書き、後ろに「,かな」を足す")
            for x in items[len(orig):]:
                if not is_kana(x):
                    errs.append(f"{k}: 足すキーワードはひらがなかカタカナだけ: {x!r}")
                elif len(x) < 2:
                    errs.append(f"{k}: 足すキーワードは2字以上: {x!r}")
            kw_lines[k] = items[len(orig):]
            continue
        if conv and k.endswith(':name'):
            continue
        if sorted(MARKS.findall(e)) != sorted(MARKS.findall(j)):
            errs.append(f"{k}: 記号（$P #1 * など）が英文と合わない: {sorted(MARKS.findall(e))} → {sorted(MARKS.findall(j))}")
        if RUNE.findall(e) != RUNE.findall(j):
            errs.append(f"{k}: <…>（ルーン文字）の中は英文のまま同じ順に残す")
        if edge_nl(e) != edge_nl(j):
            errs.append(f"{k}: 先頭と末尾の改行（\\n）の数を英文と同じにする（英 {edge_nl(e)} → 訳 {edge_nl(j)}）")
        if conv and ('"' in j or '&' in j):
            errs.append(f"{k}: 引用符 \" と & は残さず「」にする（MD の英文は & が閉じの引用符）")
        if conv and '@(' in e and e[e.index('@('):] not in j:
            errs.append(f"{k}: 説明書の問いの「{e[e.index('@('):]}」は英文のまま残す")
        if e.count('@') and conv:
            ws, he = highlights(j)
            errs += [f"{k}: {x}" for x in he]
            if len(ws) != e.count('@'):
                errs.append(f"{k}: 強調（@）の数が英文と合わない（英 {e.count('@')} → 訳 {len(ws)}）")
            hl_words[k] = ws
        if not conv:
            if sorted(FMT.findall(e)) != sorted(FMT.findall(j)) and k not in FMT_FREE:
                errs.append(f"{k}: 書式（%s %d %c %P など）が英文と合わない")
            if k.startswith(('mdtext:', 'midgame', 'scene:')):
                if '"' in j:
                    errs.append(f"{k}: 引用符 \" は残さず「」にする")
                if j.count('^') != e.count('^'):
                    errs.append(f"{k}: ^（字幕の中の改行）の数を英文と同じにする（英 {e.count('^')} → 訳 {j.count('^')}）")
                if k.startswith('midgame') and '%' in j:
                    errs.append(f"{k}: % は使わない")
                if k.startswith('midgame') and j.count(chr(10)) != e.count(chr(10)):
                    errs.append(f"{k}: 改行の数を英文と同じにする")
                for ab in ('(A)', '(B)', 'A)', 'B)', 'C)'):
                    if k.startswith('scene:') and e.count(ab) != j.count(ab):
                        errs.append(f"{k}: 答えのキー {ab} を英字のまま同じ数だけ残す")
            elif not k.startswith('book:') and not k.startswith('look:') and len(j) > len(e):
                errs.append(f"{k}: 長すぎる（英 {len(e)} 字 → 訳 {len(j)} 字。英語の字数以内に）")
    if conv:
        from conv_text import ALIASES
        # 英語の部分がまったく同じ行（別の場面で同じ一覧を使う）は、同じかながあってよい
        by_eng = {}
        for k, ws in kw_lines.items():
            by_eng.setdefault(en[k], set()).update(ws)
        allkw = [w for ws in by_eng.values() for w in ws]
        dup = sorted({w for w in allkw if allkw.count(w) > 1})
        if dup:
            errs.append(f"同じかなのキーワードが、英語の違う2つの行にある: {dup}")
        # 道具が自動で足す読み（name → なまえ など）も、キーワードとして数える
        for k in kw_lines:
            for x in en[k].split(','):
                if x.lower() in ALIASES:
                    allkw.append(ALIASES[x.lower()])
        for a in set(allkw):
            for b in set(allkw):
                if a != b and b.startswith(a):
                    warns.append(f"キーワード「{a}」が「{b}」の頭と同じ（{b} が打てなくなるおそれ）")
        for k, ws in hl_words.items():
            for w in ws:
                if is_kana(w) and w not in allkw:
                    warns.append(f"{k}: 強調した「{w}」がキーワードの行にない（打っても答えが出ない）")
                elif w and not is_kana(w) and any(ord(c) > 0x7e for c in w):
                    errs.append(f"{k}: 強調する語はかなだけで書く: {w!r}")
    for x in errs:
        print("問題:", x)
    for x in warns:
        print("注意:", x)
    if not errs:
        print(f"問題なし（{len(ja)} 件{'、注意 ' + str(len(warns)) + ' 件' if warns else ''}）")
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
