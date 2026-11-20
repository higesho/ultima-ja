# エンジン（jp_work/engine）用の原作の文章の訳を作る
# 使い方: python make_engine_ja.py <ゲームのフォルダ> <出力フォルダ（engine/web/src/i18n/ja）>
#   ovl.json  本体（DATA.OVL）の文字列: {"データセグメントの番地（16 進）": 訳}
#   tlk.json  会話: {"TOWNE.TLK": [人ごとの日本語の台本, ...]}（TLK の見出しの順）
#             台本は文字列で、1 字が台本の 1 つ: 0x00〜0xFF は元の台本と同じ意味（英字は最上位ビットを立てる）、
#             0x100 以上は日本語の字。打つ言葉・質問の答え・命令は元のまま
#   dat.json  ほかの文章ファイル: {"SHOPPE.DAT": {"ファイルの位置": 訳}, ...}
#             SIGNS.DAT は {"看板の見出しの位置": [[文字列の中の始まり, 終わり, 訳], ...]}（普通の字のまとまりだけ）
#   訳は translation/data_ja.txt・tlk_ja.txt・dat_ja.txt（import_check.py が作る）から。\n は改行
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")
sys.stdout.reconfigure(encoding="utf-8")


def rows(name):
    for line in open(os.path.join(TR, name), encoding="utf-8"):
        line = line.rstrip("\r\n")
        if line and not line.startswith("#"):
            yield line.split("\t")


def unesc(t):
    return t.replace("\\n", "\n")


def make_ovl(game):
    out = {}
    for off, ja in rows("data_ja.txt"):
        out[format(int(off, 16) - 0x10, "x")] = unesc(ja)
    return out


# ---- 会話 ----

def read_tlk(path):
    d = open(path, "rb").read()
    n = struct.unpack_from("<H", d)[0]
    ent = [struct.unpack_from("<HH", d, 2 + 4 * k) for k in range(n)]
    offs = [o for _, o in ent] + [len(d)]
    return [d[offs[k]:offs[k + 1]].split(b"\0") for k in range(n)]


def encode_field(text):
    """訳を台本の 1 欄にする（文字列、1 字が台本の 1 つ）"""
    out = []
    for part in re.split(r"(\{[0-9a-fA-F]{2}\}|\n)", text):
        if not part:
            continue
        if part == "\n":
            out.append(0x8D)
        elif part.startswith("{"):
            out.append(int(part[1:3], 16))
        else:
            for ch in part:
                c = ord(ch)
                if c < 0x20:
                    raise RuntimeError(f"会話に使えない字: {text!r}")
                out.append(c | 0x80 if c < 0x80 else c)
    return out


ARGS = {0xFE: 2, 0x85: 3, 0x86: 1, 0x8C: 1}   # 引数を取る命令と、その数


def repair(ja, en, translated=False):
    """訳した欄の命令の引数を、英語の台本のとおりにする
    （DOS 版の表で 0x8C の後の 0xFF が {c0} と書かれていた所、訳で引数が文の中へ動いた所を直す）"""
    # DOS 版の表は、命令 0xFF（「興味は？」へ戻る）も {c0} と書いていた。英語の 0xFF の数だけ、余分な 0xC0 を 0xFF に戻す
    if translated and ja.count(0xFF) < en.count(0xFF):
        extra = ja.count(0xC0) - en.count(0xC0)
        need = en.count(0xFF) - ja.count(0xFF)
        ja = list(ja)
        for j, c in enumerate(ja):
            if extra <= 0 or need <= 0:
                break
            if c == 0xC0:
                ja[j] = 0xFF
                extra -= 1
                need -= 1
    want = []
    i = 0
    while i < len(en):
        c = en[i]
        if c in ARGS:
            want.append((c, list(en[i + 1:i + 1 + ARGS[c]])))
            i += 1 + ARGS[c]
        else:
            i += 1
    out, i, w, fixed = [], 0, 0, 0
    while i < len(ja):
        c = ja[i]
        if c in ARGS and w < len(want) and want[w][0] == c:
            args = want[w][1]
            got = ja[i + 1:i + 1 + len(args)]
            out.append(c)
            out += args
            i += 1 + len(args)
            if got != args:
                fixed += 1
                # 引数の代わりに読んだのが訳の字なら、それは戻し、後ろに離れて置かれた引数のほうを除く
                keep = [g for g in got if g >= 0x100 or (0x20 <= (g & 0x7F) and g >= 0xA0 and g not in args)]
                rest = ja[i:]
                for a in args:
                    if a in rest and a not in got:
                        rest.remove(a)
                ja = ja[:i] + keep + rest
            w += 1
            continue
        # 訳に残った辞書の言葉の番号（0x01〜0x80）は英語の単語として出てしまうので除く（引数は上で扱った）
        if translated and 0 < c < 0x81:
            fixed += 1
            i += 1
            continue
        out.append(c)
        i += 1
    return out, fixed


def make_tlk(game):
    tr = {}
    for f, npc, field, ja in rows("tlk_ja.txt"):
        tr[(f.upper(), int(npc), int(field))] = unesc(ja)
    out = {}
    fixes = 0
    for name in ["TOWNE.TLK", "DWELLING.TLK", "CASTLE.TLK", "KEEP.TLK"]:
        scripts = []
        for k, fields in enumerate(read_tlk(os.path.join(game, name))):
            orig = [bytes(f) for f in fields]
            new = [encode_field(tr[(name, k, i)]) if (name, k, i) in tr else list(f) for i, f in enumerate(orig)]
            for i, f in enumerate(orig):
                new[i], n_fixed = repair(new[i], list(f), (name, k, i) in tr)
                fixes += n_fixed
            who = bytes(b & 0x7F for b in orig[0] if b >= 0xA0).decode("latin-1")
            # Weblock: GORN の答えが "hass"、その次の欄が 0x87 で始まる（二つが入れ替わっている）
            if who == "Weblock":
                for i in range(len(orig) - 2):
                    if orig[i] == bytes([0xE7, 0xEF, 0xF2, 0xEE]) and orig[i + 1] == bytes([0xE8, 0xE1, 0xF3, 0xF3]) and orig[i + 2][:1] == b"\x87":
                        new[i + 1], new[i + 2] = [0x87], new[i + 1] + new[i + 2][1:]
                        fixes += 1
                        break
            # Sir Arbuthnot: "Oh." の後に、聞き取るはずの y が抜けている
            if who == "Sir Arbuthnot":
                for i in range(len(orig) - 1):
                    if orig[i] == bytes([0xCF, 0xE8, 0xAE]) and orig[i + 1][:2] == bytes([0xA7, 0xD4]):
                        new.insert(i + 1, [0xF9])
                        fixes += 1
                        break
            # Thrud: 渡す品物 0x1c は 0x28（宝石の剣）の書き違い
            if who == "Thrud":
                for f in new:
                    for j in range(len(f) - 3):
                        if f[j:j + 4] == [0x86, 0x08, 0x86, 0x1C]:
                            f[j + 3] = 0x28
                            fixes += 1
            codes = []
            for i, f in enumerate(new):
                if i:
                    codes.append(0)
                codes += f
            scripts.append("".join(chr(c) for c in codes))
        out[name] = scripts
    print(f"会話: {sum(len(v) for v in out.values())} 人、訳 {len(tr)} 欄、元の台本の直し {fixes} か所")
    return out


def make_tlk_fields():
    """配る会話の訳: {"TOWNE.TLK": {"人（見出しの順）": {"欄": 訳}}}。訳だけで、原作の台本は入れない。
    エンジン（gameText.ts tlkScript）が、遊ぶ人の TLK とこれから日本語の台本を組み立てる（命令の直しも、make_tlk と同じ）"""
    out = {}
    for f, npc, field, ja in rows("tlk_ja.txt"):
        out.setdefault(f.upper(), {}).setdefault(npc, {})[field] = unesc(ja)
    return out


# ---- ほかの文章ファイル ----

def split_offsets(d):
    """0 区切りの何番目かと、そのファイルの位置"""
    offs, pos = [], 0
    for s in d.split(b"\0"):
        offs.append(pos)
        pos += len(s) + 1
    return offs


def sign_runs(txt):
    runs, i = [], 0
    while i < len(txt):
        if txt[i] & 0x80 and (txt[i] & 0x7F) >= 0x20:
            j = i
            while j < len(txt) and txt[j] & 0x80 and (txt[j] & 0x7F) >= 0x20:
                j += 1
            if any(chr(c & 0x7F).isalnum() for c in txt[i:j]):
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


STORY_FILES = {"STORY.DAT", "QUESTION.DAT", "END.DAT", "ENDMSG.DAT"}


def make_dat(game):
    items = {}
    for f, k, ja in rows("dat_ja.txt"):
        items.setdefault(f.upper(), []).append((k, unesc(ja)))
    out = {}
    for name, its in items.items():
        d = open(os.path.join(game, name), "rb").read()
        m = {}
        if name == "LOOK2.DAT":
            uniq = sorted(set(struct.unpack_from("<512H", d, 0)))
            for k, ja in its:
                m[str(uniq[int(k)])] = ja
        elif name == "SIGNS.DAT":
            table = struct.unpack_from("<33H", d, 0)
            tr = {tuple(map(int, k.split(":"))): ja for k, ja in its}
            pos, rec = 66, 0
            while pos < len(d):
                if d[pos] == 0xFF or pos + 4 > len(d):
                    pos += 1
                    continue
                j = d.index(b"\0", pos + 4)
                segs = []
                for seg, (a, b) in enumerate(sign_runs(d[pos + 4:j])):
                    if (rec, seg) in tr:
                        segs.append([a, b, tr[(rec, seg)]])
                if segs:
                    m[str(pos)] = segs
                pos = j + 1
                rec += 1
        else:
            offs = split_offsets(d)
            for k, ja in its:
                # 物語のページ（読み物）の、日本語の字にはさまれた空白は除く（DOS 版の書き方の名残）
                if name in STORY_FILES:
                    ja = re.sub(r"(?<=[　-￿]) +(?=[　-￿])", "", ja)
                m[str(offs[int(k)])] = ja
        out[name] = m
        print(f"{name}: {len(m)}")
    return out


# ---- 会話の言葉の一覧の見出し ----

KANJI = re.compile(r"[一-鿿゠-ヿー々・]")
HIRA = re.compile(r"[぀-ゟ]")


def label_before(text, i):
    """text[i] が「(」のとき、その前の日本語の語（漢字・カタカナのまとまり）"""
    j = i
    while j > 0 and KANJI.match(text[j - 1]):
        j -= 1
    if j < i:
        return text[j:i]
    # 送りがなの後の印（「暮らして(LIVI)」）: ひらがな 4 字までさかのぼり、その前に漢字があればそこから。
    # ひらがなだけの語は見出しにしない（英語の見出しのまま）
    while j > 0 and HIRA.match(text[j - 1]) and i - j < 4:
        j -= 1
    k = j
    while k > 0 and KANJI.match(text[k - 1]):
        k -= 1
    return text[k:i] if k < j else ""


def make_kw(game):
    """会話の言葉（英語の打つ言葉）ごとの日本語の見出し: {"ファイル:人の番号:言葉": 見出し}
    訳の中の「心(SPIR)」の印から、その人の欄で最初に見つかったもの"""
    tr = {}
    for f, npc, field, ja in rows("tlk_ja.txt"):
        tr.setdefault((f.upper(), int(npc)), []).append(unesc(ja))
    out = {}
    for fi, name in enumerate(["TOWNE.TLK", "DWELLING.TLK", "CASTLE.TLK", "KEEP.TLK"]):
        d = open(os.path.join(game, name), "rb").read()
        n = struct.unpack_from("<H", d)[0]
        for k in range(n):
            npc_id = struct.unpack_from("<H", d, 2 + 4 * k)[0]
            for text in tr.get((name, k), []):
                for m in re.finditer(r"\(([A-Z][A-Z' ]{0,7})\)", text):
                    stub = m.group(1).strip()
                    key = f"{fi}:{npc_id}:{stub}"
                    if key in out:
                        continue
                    lab = label_before(text, m.start())
                    if lab:
                        out[key] = lab
    print(f"言葉の見出し: {len(out)}")
    return out


def main(game, outdir):
    os.makedirs(outdir, exist_ok=True)
    # 組み立てた台本の完成形は、手元の照合用（試験 tests/jatlk.test.ts の JA_TLK_REF）。配らない
    ref = os.path.join(HERE, "..", "test", "tlk_ref.json")
    json.dump(make_tlk(game), open(ref, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for fname, data in [("ovl.json", make_ovl(game)), ("tlk.json", make_tlk_fields()), ("dat.json", make_dat(game)),
                        ("kw.json", make_kw(game))]:
        p = os.path.join(outdir, fname)
        json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print("書き出し:", p, os.path.getsize(p), "バイト")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
