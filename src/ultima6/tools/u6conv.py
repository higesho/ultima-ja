"""ウルティマVI の会話スクリプト（CONVERSE.A/B の1人分）を構文どおりに読む・書き戻す。

構文は本編 GAME.EXE の会話の処理から読み取ったもの（調査メモ「会話スクリプトの構文」）:
- 文の位置で 0x0A / 0x20〜0x7F が来たら文章（0x80 以上か 0 の手前まで）。0ECB:1C45 が 0x7A13 で1字ずつ出す
- 0x9C〜0xDF の文（0ECB:153B の表）。式は 0ECB:050E が読み、A7 か A8 で終わる。式の中の D2/D3/D4 は後ろ 4/2... バイトの値
- 0xE0 以上は会話の本体（0ECB:1E23）が扱う: F7 質問、F9/FB/FC 入力、F8 キーの一覧、EF キーワード、FF 人物 など
- スクリプト内の位置（先頭からのバイト数）を持つもの: B0 の飛び先、B5/A6 の D2 の後ろ、式の中で B4/B7/C3 が使う D2 の値
"""
import struct

# 文: 値 → 式の数（None は特別な形）
STMT_EXPRS = {0x9C: 1, 0x9E: 0, 0xA1: 1, 0xA2: 0, 0xA3: 0, 0xA4: 2, 0xA5: 2, 0xA7: 0,
              0xB6: 0, 0xB9: 4, 0xBA: 4, 0xBE: 1, 0xBF: 1, 0xC4: 1, 0xC5: 1, 0xC8: 2, 0xC9: 4,
              0xCB: 0, 0xCD: 2, 0xD0: 1, 0xD6: 1, 0xD8: 1, 0xD9: 1, 0xDB: 1, 0xDF: 1}
SPECIAL_STMT = {0xA6, 0xB0, 0xB5}
TOP_NOARG = {0xEE, 0xF1, 0xF2, 0xF3, 0xF6, 0xF7, 0xFA}
ADDR_OPS = {0xB4, 0xB7, 0xC3}          # 式の中で、上から2番目の値（D2）を位置として使う演算子
# 式の演算子が取る値の数（0ECB:0614 の表の各処理が参照するスタックの深さ）。表にない値は数として積まれる
ARITY = {0x81: 2, 0x82: 2, 0x83: 2, 0x84: 2, 0x85: 2, 0x86: 2, 0x90: 2, 0x91: 2, 0x92: 2, 0x93: 2,
         0x94: 1, 0x95: 2, 0x9A: 1, 0x9B: 2, 0x9D: 1, 0x9F: 3, 0xA0: 2, 0xAB: 2, 0xB2: 1, 0xB3: 1,
         0xB4: 2, 0xB7: 2, 0xBB: 2, 0xBC: 2, 0xBD: 2, 0xC0: 0, 0xC1: 1, 0xC2: 1, 0xC3: 2, 0xC6: 1,
         0xC7: 2, 0xCA: 1, 0xCC: 1, 0xD7: 1, 0xDA: 1, 0xDC: 1, 0xDD: 2, 0xE0: 2, 0xE1: 2, 0xE2: 2,
         0xE3: 2, 0xE4: 2}


class ParseError(Exception):
    pass


TEXT_MAX = 0x9B   # 日本語の符号（会話の組のリード・トレイル）は 0x80〜0x9B。本編の判定を 9Ch に書き換えて文章として通す


def is_text(b):
    # 0x0A 以外の制御文字はゲームではエラー表示になるが、元のスクリプトにある（B49 のタブ）ので文章に含めて残す。
    # 元のスクリプトでは 0x80〜0x9B が文の先頭に来ることはない（9C と 9E は文として使われている）
    return 0x01 <= b <= TEXT_MAX


class Script:
    """nodes: ('text', 位置, bytes) / ('code', 位置, bytes) / ('name', 位置, bytes) / ('kw', 位置, bytes)
               ('keys', 位置, bytes) / ('table', 位置, [文字列...], 残り) / ('numtable', 位置, bytes)
       refs: [(バイト列の中の位置, 指す位置, 種類)]（4バイトの位置の値）
       文章は飛び先の位置で分ける（答えのあと、次の質問の前の改行などに飛んでくる）"""

    def __init__(self, raw):
        self.raw = raw
        self.tables = {}           # 位置 → 'str' / 'num'
        self.match_tables = set()  # B7（INDEXOF）が使う表の位置
        self.targets = set()       # B0 の飛び先
        # 表の位置と飛び先は、それより後ろの参照で初めてわかることがある。変わらなくなるまで読み直す
        for _ in range(4):
            before = (dict(self.tables), set(self.targets))
            self.nodes = []
            self.refs = []
            err = None
            try:
                self.parse()
            except ParseError as e:
                err = e
            self.targets |= {t for _, t, k in self.refs if k == 'code'}
            if err is None and before == (self.tables, self.targets):
                break
        else:
            raise err or ParseError("読み直しても定まらない 0x0")
        if err:
            raise err

    # ---- 読む ----
    def expr(self, p):
        """式を読む。戻り値: 次の位置、[(トークンの位置, 値)]"""
        r = self.raw
        toks = []
        while True:
            if p >= len(r):
                raise ParseError(f"式の途中で終わり {p:#x}")
            b = r[p]
            if b in (0xA7, 0xA8):
                toks.append((p, b))
                return p + 1, toks
            if b == 0xD2:
                toks.append((p, ('D2', struct.unpack_from("<I", r, p + 1)[0])))
                p += 5
            elif b == 0xD3:
                toks.append((p, ('D3', r[p + 1])))
                p += 2
            elif b == 0xD4:
                toks.append((p, ('D4', struct.unpack_from("<H", r, p + 1)[0])))
                p += 3
            else:
                toks.append((p, b))
                p += 1

    def expr_refs(self, toks, implicit=False):
        """式のスタックをたどり、B4/B7/C3 の上から2番目が D2 の値なら、それを位置として登録する。
        implicit: 表を引く処理（D2 <位置> の後ろの番号の式）。位置はもう読まれていて、式の中の B4 などは空振り"""
        st = [[-1]] if implicit else []           # 各要素 = その値を作ったトークンの番号の並び
        for i, (p, t) in enumerate(toks[:-1]):    # 最後は A7/A8
            if isinstance(t, int) and t in ARITY:
                a = ARITY[t]
                if len(st) < a:
                    raise ParseError(f"式のスタックが足りない {t:#x} {p:#x}")
                args = st[len(st) - a:] if a else []
                del st[len(st) - a:]
                if t in ADDR_OPS and args[0] != [-1]:
                    base = args[0]
                    if len(base) != 1 or not (isinstance(toks[base[0]][1], tuple) and toks[base[0]][1][0] == 'D2'):
                        raise ParseError(f"位置を使う演算子 {t:#x} の位置が D2 でない {p:#x}")
                    q, (_, v) = toks[base[0]]
                    self.add_ref(q + 1, v, {0xB4: 'num', 0xB7: 'str', 0xC3: 'num'}[t])
                    if t == 0xB7:
                        self.match_tables.add(v)   # B7: 入力した言葉を表から探す（訳すと照合できなくなる）
                st.append([j for a_ in args for j in a_] + [i])
            else:
                st.append([i])

    def add_ref(self, at, target, kind):
        if not (0 <= target < len(self.raw)):
            raise ParseError(f"位置が範囲外 {target:#x}（{at:#x}）")
        self.refs.append((at, target, kind))
        if kind in ('str', 'num'):
            if self.tables.get(target, kind) != kind:
                raise ParseError(f"表の種類が合わない {target:#x}")
            self.tables[target] = kind

    def dataref(self, p, kind):
        """D2 <位置4> (B1 | 式)。p は D2 の次"""
        self.add_ref(p, struct.unpack_from("<I", self.raw, p)[0], kind)
        p += 4
        if self.raw[p] == 0xB1:
            return p + 1
        p, toks = self.expr(p)
        self.expr_refs(toks, implicit=True)
        return p

    def stmt(self, p):
        """文を1つ読み、次の位置を返す（p は文の値の位置）"""
        r = self.raw
        op = r[p]
        p += 1
        if op in STMT_EXPRS:
            for _ in range(STMT_EXPRS[op]):
                p, toks = self.expr(p)
                self.expr_refs(toks)
            return p
        if op == 0xB0:
            self.add_ref(p, struct.unpack_from("<I", r, p)[0], 'code')
            return p + 4
        if op == 0xB5:
            if r[p] == 0xD2:
                return self.dataref(p + 1, 'str')
            if r[p] == 0xD5:
                return p + 1
            if r[p + 1] == 0xB3:
                return p + 3
            raise ParseError(f"B5 の形が読めない {p:#x}")
        if op == 0xA6:
            if r[p] == 0xD2:
                p = self.dataref(p + 1, 'num')
                # 番号の式の終わり（A8）を A6 がもう一度読む
                if r[p - 1] != 0xA8:
                    raise ParseError(f"A6 D2 の後ろに A8 がない {p:#x}")
                p, toks = self.expr(p)
                self.expr_refs(toks)
                return p
            typ = r[p + 1]
            if r[p + 2] != 0xA8:
                raise ParseError(f"A6 の後ろに A8 がない {p:#x}")
            p += 3
            if typ == 0xB2:
                p, toks = self.expr(p)
                self.expr_refs(toks)
                return p
            if typ == 0xB3:
                if r[p] == 0xD2:
                    return self.dataref(p + 1, 'str')
                if r[p + 1] == 0xB3:
                    return p + 2
            raise ParseError(f"A6 の形が読めない {p:#x}")
        raise ParseError(f"知らない文 {op:#x} {p - 1:#x}")

    def parse(self):
        r = self.raw
        n = len(r)
        if r[0] != 0xFF:
            raise ParseError("先頭が 0xFF でない")
        e = r.index(0xF1, 2)
        self.nodes.append(('code', 0, r[0:2]))
        self.nodes.append(('name', 2, r[2:e]))
        p = e
        while p < n:
            if p in self.tables:          # 表: 次の表か、次の飛び先か、末尾まで
                p = self.parse_table(p)
                continue
            b = r[p]
            if is_text(b):
                q = p + 1
                while q < n and is_text(r[q]) and q not in self.targets:
                    q += 1
                self.nodes.append(('text', p, r[p:q]))
                p = q
                continue
            if b == 0x00:
                self.nodes.append(('code', p, r[p:p + 1]))
                p += 1
                continue
            if b == 0xEF:
                q = r.index(0xF6, p + 1)
                self.nodes.append(('code', p, r[p:p + 1]))
                self.nodes.append(('kw', p + 1, r[p + 1:q]))
                p = q
                continue
            if b == 0xF8:
                q = r.index(0xEF, p + 1)
                self.nodes.append(('code', p, r[p:p + 1]))
                self.nodes.append(('keys', p + 1, r[p + 1:q]))
                p = q
                continue
            if b in (0xF9, 0xFB, 0xFC):
                q = p + 3
            elif b in TOP_NOARG:
                q = p + 1
            elif 0x9C <= b <= 0xDF:
                q = self.stmt(p)
            else:
                raise ParseError(f"知らない値 {b:#x} {p:#x}")
            self.nodes.append(('code', p, r[p:q]))
            p = q


    def parse_table(self, a):
        """a からの表を1つ読み、次の位置を返す。終わりは次の表か、次の飛び先か、末尾。
        'str' は 0 区切りの文字列、'num' は 2バイトの数"""
        r = self.raw
        b = min([t for t in self.tables if t > a] + [t for t in self.targets if t > a] + [len(r)])
        kind = self.tables[a]
        body = r[a:b]
        if kind == 'str':
            # 0 で終わる文字列の並び＋最後の 0 のあとに残ったバイト（B101 では表の間に 0xB8 が1バイト挟まっている）
            parts = body.split(b"\0")
            self.nodes.append(('table', a, parts[:-1], parts[-1]))
        else:
            if len(body) % 2:
                raise ParseError(f"数の表の長さが奇数 {a:#x}")
            self.nodes.append(('numtable', a, body))
        return b


def node_bytes(nd):
    if nd[0] == 'table':
        return b"".join(x + b"\0" for x in nd[2]) + nd[3]
    return nd[2]


def build(script, new=None):
    """部品を書き戻す。new: {部品の番号: 新しい中身}（文章・名前は bytes、文字列の表は [bytes...]）。
    飛び先と表の位置（4バイト）は、指している部品の新しい位置に付け直す"""
    new = new or {}
    nodes = []
    for i, nd in enumerate(script.nodes):
        if i in new:
            if nd[0] == 'table':
                nd = (nd[0], nd[1], list(new[i]), nd[3])
            else:
                nd = (nd[0], nd[1], bytes(new[i]))
        nodes.append(nd)
    pos = {}
    p = 0
    for nd in nodes:
        pos[nd[1]] = p
        p += len(node_bytes(nd))
    out = bytearray()
    # 元の位置 → (部品の元の先頭, 部品の新しい先頭) で、参照の置き場所を引く
    refs_in = {}
    for at, tgt, kind in script.refs:
        refs_in[at] = tgt
    for nd in nodes:
        b = bytearray(node_bytes(nd))
        if nd[0] == 'code':
            for at in range(nd[1], nd[1] + len(b)):
                if at in refs_in:
                    tgt = refs_in[at]
                    if tgt not in pos:
                        raise ParseError(f"付け直す先が部品の先頭でない {tgt:#x}")
                    struct.pack_into("<I", b, at - nd[1], pos[tgt])
        out += b
    return bytes(out)


def save_items(path, items):
    """CONVERSE.A/B を書く。items: [(番号, スクリプト or None, 圧縮済みの元の項目 or None)]
    中身が元と同じ項目は元の圧縮のまま、変えた項目は圧縮なし（先頭4バイト 0）で入れる"""
    body = bytearray()
    offs = []
    base = 4 * len(items)
    for k, raw, orig in items:
        if raw is None:
            offs.append(0)
            continue
        if len(raw) > 0x2800:
            raise ValueError(f"#{k}: スクリプトが読み込み先（10,240 バイト）より大きい: {len(raw)}")
        it = orig if orig is not None else b"\0\0\0\0" + raw
        offs.append(base + len(body))
        body += it
    open(path, "wb").write(b"".join(struct.pack("<I", o) for o in offs) + body)


def load_raw_items(path):
    """CONVERSE.A/B の圧縮されたままの項目: {番号: bytes}"""
    from u6fmt import lib
    return {k: it for k, it in enumerate(lib(open(path, "rb").read(), 4)) if it is not None}


def load_items(path):
    """CONVERSE.A/B を読む: [(番号, 展開したスクリプト or None)]"""
    from u6fmt import lib, lzw
    out = []
    for k, it in enumerate(lib(open(path, "rb").read(), 4)):
        if it is None:
            out.append((k, None))
            continue
        raw = it[4:] if struct.unpack("<I", it[:4])[0] == 0 else lzw(it)[0]
        out.append((k, raw))
    return out
