"""会話スクリプトの文章を書き出す・訳を取り込む。

書き出し: python conv_text.py export <ゲームのフォルダ> <出力 conv_en.tsv>
  1行 =「番号<TAB>英文」。番号は
    A002:name          人物の名前（スクリプト先頭の 0xFF 番号 名前 0xF1）
    A002:t0012         文章（部品の番号。飛び先の位置で分けてある）
    A002:s0034.2       文字列の表（部品 34 の 2 番目）
  英字を含まない文章（改行だけ、記号だけ）は書き出さない（そのまま残す）。
  改行は \\n、タブは \\t、\\ は \\\\ と書く。人物ごとに「# A002 Dupre」の行を入れる
  キーワード（EF〜F6）は参考として「# kw A002 name,job」の形でコメントに入れる（今は訳さない）

取り込み: apply_translation(ゲームのフォルダ, 訳の辞書, 符号に直す関数) → {('A' or 'B', 番号): 新しいスクリプト}
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from u6conv import Script, build  # noqa: E402
from mdtalk import load_items  # noqa: E402

FILES = (('T', 'TALK.LZC'),)   # Martian Dreams は会話が1つのファイル。番号は T002:name など
CHECK_MARKS = re.compile(r"\$[A-Z0-9]|#[0-9]|@|\*")

# ---- キーワード（入力はローマ字。英語のキーワードも残す）----
KW_MAX = 25              # MD: キーワードを写す場所（DS:0xEC8E）は 26バイト（入力は 0xECA8）。U6 は 9 だった
ALIASES = {'name': 'なまえ', 'job': 'しごと', 'bye': 'さようなら', 'join': 'なかま', 'leav': 'わかれ',
           'buy': 'かう', 'sell': 'うる', 'y': 'はい', 'n': 'いいえ'}
HL_STOP = set(" ,.:;!?'-\"\n")   # @ の強調を止める字（MD の本編の DS:0x1CAD。U6 と同じ並び）
HL_END = '\x7f'                   # 訳で閉じの @ を書くと 0x7F。常駐部が強調を止め、字は描かない


def is_kana(s):
    return all('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヶ' or c == 'ー' for c in s) and s != ''


def keyword_list(items, warn, where):
    """キーワードの一覧（文字列の並び）を、ゲームに入れる形（ASCII の並び）にする"""
    from romaji import variants
    out = []

    def add(w):
        w = w[:KW_MAX]
        if w and w not in out:
            out.append(w)
    for w in items:
        w = w.strip()
        if not w:
            continue
        if is_kana(w):
            for r in variants(w):
                add(r)
        elif all(0x20 <= ord(c) < 0x7f for c in w):    # 元のキーワードには空白入りのものもある（B059 の "au r"）
            add(w.lower() if w != '*' else w)
            if w.lower() in ALIASES:
                for r in variants(ALIASES[w.lower()]):
                    add(r)
        else:
            warn(f"{where}: キーワードはかなか英字で書く: {w!r}")
    return out


def check_shadow(lists, added, warn, where):
    """先に調べられる一覧の語が、後ろの一覧の語の先頭と一致して、後ろを隠してしまうものを探す（足した語が関わるものだけ）"""
    for i, a_list in enumerate(lists):
        for a in a_list:
            if a == '*':
                continue
            for j in range(i + 1, len(lists)):
                # 後ろの一覧の元の語がもう a に隠されているなら、元からの動きなので言わない
                if a not in added and any(x.startswith(a) for x in lists[j] if x not in added):
                    continue
                for b in lists[j]:
                    if b != a and b.startswith(a) and (a in added or b in added):
                        warn(f"{where}: 「{a}」が後ろの一覧の「{b}」を隠す")


def mark_highlight(ja, warn, where):
    """訳の @ の強調: 閉じの @ を 0x7F にする。閉じがなく、日本語のまま区切りの字で終わっていたら注意"""
    out = []
    open_ = False
    jp_in = False
    for c in ja:
        if c == '@':
            if open_:
                out.append(HL_END)
                open_ = False
                continue
            open_ = True
            jp_in = False
            out.append(c)
            continue
        if open_:
            if c in HL_STOP:
                if jp_in:
                    warn(f"{where}: 日本語の強調に閉じの @ がない")
                open_ = False
            elif ord(c) > 0x7e:
                jp_in = True
        out.append(c)
    if open_ and jp_in:
        warn(f"{where}: 日本語の強調に閉じの @ がない（文の終わりまで）")
    return ''.join(out)


def encode_text(ja, encode, warn, where):
    """閉じの @（0x7F）で区切って符号にする（組が 0x7F をまたがないように）"""
    return HL_END.encode('latin1').join(encode(part) for part in mark_highlight(ja, warn, where).split(HL_END))


def esc(b):
    s = b.decode('latin1')
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def unesc(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            out.append({'n': '\n', 't': '\t', '\\': '\\'}.get(s[i + 1], '\\' + s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def has_letters(b):
    return re.search(rb'[A-Za-z]', b) is not None


def units(gamedir):
    """[(番号, 英文 bytes, (ファイルの記号, 項目, 部品, 表の中の番号 or None))]"""
    for tag, fname in FILES:
        for k, raw in load_items(os.path.join(gamedir, fname)):
            if raw is None:
                continue
            s = Script(raw)
            pid = f"{tag}{k:03d}"
            for i, nd in enumerate(s.nodes):
                if nd[0] == 'name':
                    yield f"{pid}:name", nd[2], (tag, k, i, None)
                elif nd[0] == 'kw':
                    yield f"{pid}:k{i:04d}", nd[2], (tag, k, i, None)
                elif nd[0] == 'text' and has_letters(nd[2]):
                    yield f"{pid}:t{i:04d}", nd[2], (tag, k, i, None)
                elif nd[0] == 'table' and nd[1] not in s.match_tables:   # 照合に使う表（B7）は訳さない
                    for j, x in enumerate(nd[2]):
                        if has_letters(x):
                            yield f"{pid}:s{i:04d}.{j}", x, (tag, k, i, j)


def export(gamedir, out):
    n = 0
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write("# Martian Dreams 会話の英文（番号<TAB>英文）。訳は同じ番号で「番号<TAB>訳」と書く\n")
        for tag, fname in FILES:
            for k, raw in load_items(os.path.join(gamedir, fname)):
                if raw is None:
                    continue
                s = Script(raw)
                pid = f"{tag}{k:03d}"
                name = next(nd[2] for nd in s.nodes if nd[0] == 'name')
                f.write(f"# {pid} {esc(name)}\n")
                kws = [esc(nd[2]) for nd in s.nodes if nd[0] == 'kw']
                f.write(f"# kw {pid} {' | '.join(kws)}\n")
                for i, nd in enumerate(s.nodes):
                    if nd[0] == 'name':
                        f.write(f"{pid}:name\t{esc(nd[2])}\n"); n += 1
                    elif nd[0] == 'kw':
                        f.write(f"{pid}:k{i:04d}\t{esc(nd[2])}\n"); n += 1
                    elif nd[0] == 'text' and has_letters(nd[2]):
                        f.write(f"{pid}:t{i:04d}\t{esc(nd[2])}\n"); n += 1
                    elif nd[0] == 'table' and nd[1] not in s.match_tables:   # 照合に使う表（B7）は訳さない
                        for j, x in enumerate(nd[2]):
                            if has_letters(x):
                                f.write(f"{pid}:s{i:04d}.{j}\t{esc(x)}\n"); n += 1
    print(f"{out}: {n} 件")


def read_tsv(path):
    tr = {}
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        key, val = line.split('\t', 1)
        tr[key] = unesc(val)
    return tr


def apply_translation(gamedir, tr, make_encoder, encode_name, warn=print):
    """訳を取り込んだスクリプトを作る。
    make_encoder(人物の記号 'A002', 人物の番号, その人物の訳文の並び) → encode(str) → bytes（文章・表用、人物ごとの表）
    encode_name(str) → bytes（名前用、常に持つ表）
    戻り値: {(ファイルの記号, 項目): 新しいスクリプト bytes}（変えた人物だけ）"""
    en = {key: b for key, b, _ in units(gamedir)}
    for key in tr:
        if key not in en:
            warn(f"英文にない番号: {key}")
    out = {}
    for tag, fname in FILES:
        for k, raw in load_items(os.path.join(gamedir, fname)):
            if raw is None:
                continue
            pid = f"{tag}{k:03d}"
            mine = {key: v for key, v in tr.items() if key.startswith(pid + ':')}
            if not mine:
                continue
            s = Script(raw)
            # その人物の文章と表の訳（閉じの @ で区切った部品）で、人物ごとの符号器を作る
            texts = []
            for key, v in mine.items():
                if ':t' in key or ':s' in key:
                    texts += mark_highlight(v, lambda _: None, key).split(HL_END)
            encode = make_encoder(pid, raw[1], texts)
            new = {}
            kw_lists = []
            kw_added = set()
            for i, nd in enumerate(s.nodes):
                if nd[0] == 'code' and nd[2][:1] == b'\xee':
                    # 答えの並びの終わり。照合はここで区切られるので、隠し合いもここまでで調べる
                    check_shadow(kw_lists, kw_added, warn, pid)
                    kw_lists = []
                if nd[0] == 'name' and f"{pid}:name" in tr:
                    new[i] = encode_name(tr[f"{pid}:name"])
                elif nd[0] == 'kw':
                    key = f"{pid}:k{i:04d}"
                    orig = nd[2].decode('latin1').split(',')
                    items = tr[key].split(',') if key in tr else orig
                    lst = keyword_list(items, warn, key)
                    kw_added |= set(lst) - set(orig)
                    kw_lists.append(lst)
                    new[i] = ','.join(lst).encode('latin1')
                elif nd[0] == 'text' and f"{pid}:t{i:04d}" in tr:
                    key = f"{pid}:t{i:04d}"
                    ja = tr[key]
                    e = nd[2].decode('latin1')
                    m = mark_highlight(ja, lambda _: None, key)
                    if sorted(CHECK_MARKS.findall(e)) != sorted(CHECK_MARKS.findall(m)):
                        warn(f"{key}: 記号（$P # @ *）が英文と合わない: {CHECK_MARKS.findall(e)} → {CHECK_MARKS.findall(m)}")
                    b = encode_text(ja, encode, warn, key)
                    for c in b:
                        if c == 0 or c > 0x9B:
                            raise ValueError(f"{key}: 会話の文章に置けない値 {c:#x}")
                    new[i] = b
                elif nd[0] == 'table':
                    strs = list(nd[2])
                    hit = False
                    for j in range(len(strs)):
                        key = f"{pid}:s{i:04d}.{j}"
                        if key in tr:
                            strs[j] = encode_text(tr[key], encode, warn, key)
                            if 0 in strs[j]:
                                raise ValueError(f"{key}: 表の文字列に 0 は置けない")
                            hit = True
                    if hit:
                        new[i] = strs
            check_shadow(kw_lists, kw_added, warn, pid)
            out[(tag, k)] = build(s, new)
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1] == 'export':
        export(sys.argv[2], sys.argv[3])
