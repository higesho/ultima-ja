# -*- coding: utf-8 -*-
"""訳の TSV を読み書きする。

TSV の列: key  en  ja  note
- key: usecode は「クラス番号(16進4桁):通し番号(3桁)」、字幕は「SKF:項目番号」
- en / ja の中のタブ・改行・\\ は \\t \\n \\\\ と書く
- ja には前後の空白を書かなくてよい（英文の前後の空白を組み立てのときに付け直す）
- ja が空なら未訳（英文のまま入る）
"""
import os, csv, io

HEAD = ['key', 'en', 'ja', 'note']


def esc(s):
    return s.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')


def unesc(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            out.append({'t': '\t', 'n': '\n', 'r': '\r', '\\': '\\'}.get(n, '\\' + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def read_tsv(path):
    """[{key, en, ja, note}] を返す（en / ja はエスケープを解いた形）。"""
    rows = []
    with open(path, encoding='utf-8', newline='') as f:
        lines = f.read().split('\n')
    for ln in lines[1:]:
        if not ln.strip():
            continue
        p = ln.rstrip('\r').split('\t')
        p += [''] * (4 - len(p))
        rows.append({'key': p[0], 'en': unesc(p[1]), 'ja': unesc(p[2]), 'note': unesc(p[3])})
    return rows


def write_tsv(path, rows):
    buf = ['\t'.join(HEAD)]
    for r in rows:
        buf.append('\t'.join([r['key'], esc(r['en']), esc(r.get('ja', '')), esc(r.get('note', ''))]))
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(buf) + '\n')


# 英語版の文字は cp437。é などを Shift-JIS に入れると化けるので、英字に寄せる
CP437_ASCII = {'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a',
               'ö': 'o', 'ô': 'o', 'ó': 'o', 'ü': 'u', 'û': 'u', 'ù': 'u', 'ú': 'u', 'ç': 'c',
               'ï': 'i', 'î': 'i', 'í': 'i', 'ñ': 'n', 'Ä': 'A', 'Ö': 'O', 'Ü': 'U', 'É': 'E', 'ß': 'ss'}


def en_from_bytes(b):
    """usecode の英文（cp437）を文字列に。"""
    return b.decode('cp437')


def en_to_game(s):
    """未訳の英文をゲーム用のバイト列に（0x80 以上を残さない）。"""
    s = ''.join(CP437_ASCII.get(c, c) for c in s)
    return s.encode('ascii', 'replace')


def split_space(s):
    """前後の空白（とタブ）を切り分ける: (前, 中身, 後)"""
    core = s.strip(' \t')
    if not core:
        return s, '', ''
    a = s.index(core)
    return s[:a], core, s[a + len(core):]
