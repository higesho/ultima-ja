"""かな → ローマ字（会話のキーワード用）。打ち方の揺れを吸収するため、いくつかの書き方をまとめて返す。
  variants("しごと")  → ['shigoto', 'sigoto']
  variants("ぼうけん") → ['bouken', 'boken']
ヘボン式と訓令式、長音（おう・うう・ー）を詰めた形。っ は次の子音を重ねる。ん は n
"""
BASE = {
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': ('shi', 'si'), 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': ('chi', 'ti'), 'つ': ('tsu', 'tu'), 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': ('fu', 'hu'), 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo',
    'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'を': ('o', 'wo'), 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': ('ji', 'zi'), 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': ('ji', 'di'), 'づ': ('zu', 'du'), 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o', 'ゔ': 'vu',
}
YOON = {  # き+ゃ など（ヘボン式, 訓令式）
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo', 'しゃ': ('sha', 'sya'), 'しゅ': ('shu', 'syu'), 'しょ': ('sho', 'syo'),
    'ちゃ': ('cha', 'tya'), 'ちゅ': ('chu', 'tyu'), 'ちょ': ('cho', 'tyo'), 'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo', 'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo', 'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'じゃ': ('ja', 'zya'), 'じゅ': ('ju', 'zyu'), 'じょ': ('jo', 'zyo'), 'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo',
    'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo', 'ふぁ': ('fa', 'fa'), 'ふぃ': ('fi', 'fi'), 'ふぇ': ('fe', 'fe'),
    'ふぉ': ('fo', 'fo'), 'てぃ': ('ti', 'ti'), 'でぃ': ('di', 'di'), 'うぃ': ('wi', 'wi'), 'うぇ': ('we', 'we'),
    'しぇ': ('she', 'sye'), 'じぇ': ('je', 'zye'), 'ちぇ': ('che', 'tye'), 'ゔぁ': 'va', 'ゔぃ': 'vi', 'ゔぇ': 've', 'ゔぉ': 'vo',
}


def hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _two(v):
    return v if isinstance(v, tuple) else (v, v)


def convert(kana, style, dash=True):
    """style 0 = ヘボン式、1 = 訓令式。dash: ー を前の母音を重ねて書く（False なら書かない）"""
    s = hira(kana)
    out = []
    i = 0
    sokuon = False
    while i < len(s):
        if s[i] == 'っ':
            sokuon = True
            i += 1
            continue
        if s[i] == 'ー':
            if out and dash:
                v = next((c for c in reversed(out[-1]) if c in 'aiueo'), '')
                out.append(v)
            i += 1
            continue
        if s[i:i + 2] in YOON:
            r = _two(YOON[s[i:i + 2]])[style]
            i += 2
        elif s[i] in BASE:
            r = _two(BASE[s[i]])[style]
            i += 1
        else:
            raise ValueError(f"ローマ字にできない字: {s[i]!r}（{kana}）")
        if sokuon:
            r = ('t' + r) if r.startswith('ch') else (r[0] + r)
            sokuon = False
        out.append(r)
    return ''.join(out)


def shorten(r):
    """長音を詰める: ou → o、uu → u、oo → o、ei はそのまま"""
    for a, b in (('ou', 'o'), ('uu', 'u'), ('oo', 'o')):
        r = r.replace(a, b)
    return r


def variants(kana):
    vs = []
    for style in (0, 1):
        for dash in ((True, False) if 'ー' in kana else (True,)):
            r = convert(kana, style, dash)
            for x in (r, shorten(r)):
                if x not in vs:
                    vs.append(x)
    return vs


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    for w in sys.argv[1:] or ['しごと', 'ぼうけん', 'なまえ', 'さようなら', 'ちゃっと', 'がーごいる', 'ひめぎみ', 'せいはい']:
        print(w, variants(w))
