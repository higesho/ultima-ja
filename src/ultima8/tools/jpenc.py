# -*- coding: utf-8 -*-
"""日本語の文をゲーム用の Shift-JIS にする。使えない字（16番フォントに無い字）を見つける。

使える字: 半角英数記号（0x20〜0x7E）、JIS 1区（記号）・3区（全角英数）・4区（ひらがな）・
5区（カタカナ）・16〜47区（第1水準漢字）。それ以外（2区の記号、第2水準など）は使えない。
"""
ALLOWED_KU = {1, 3, 4, 5} | set(range(16, 48))


def bad_chars(text):
    """使えない字の一覧を返す。"""
    bad = []
    for ch in text:
        if ch in '\n\t' or 0x20 <= ord(ch) < 0x7F:
            continue
        try:
            b = ch.encode('euc_jp')
        except UnicodeEncodeError:
            bad.append(ch)
            continue
        if len(b) != 2 or b[0] < 0xA1:
            bad.append(ch)
            continue
        if (b[0] - 0xA0) not in ALLOWED_KU:
            bad.append(ch)
    return bad


def encode(text):
    bad = bad_chars(text)
    if bad:
        raise ValueError('使えない字: %s （%s）' % (''.join(sorted(set(bad))), text))
    return text.encode('cp932')
