# 本体（AVATAR / TITLE）の文字列の元表を作る
#   本当の先頭: 文字列の途中を指す参照（コードの即値・データの中の番地の表）があり、先頭は指されていないとき、
#               指されている一番前の位置を先頭にする（「PThe Honest Inn」の P のような前のバイトを外す）
#   keep: 訳さないもの（ファイル名、プレイヤーが打った言葉と比べる言葉、記号のような並び、C の実行時ライブラリ）
# 使い方: python make_master.py   → translation/master_avatar.tsv, translation/master_title.tsv
#   列: id（A:位置 / T:位置、16進）、最大バイト数、種類（text / keep）、メモ、英文（\n は \\n）
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from u4exe import unpack_avatar, DGROUP  # noqa: E402

GAME = os.path.join(HERE, "..", "..")
OUT = os.path.join(HERE, "..", "translation")

# AVATAR: プレイヤーが打った言葉と比べる表（データの中の位置、間隔、件数）
A_CMP_TABLES = [(0x1FC6, 2, 9),     # 徳の名前と Villager（祠など）
                (0x884, 2, 16),     # 石の色、ダンジョンのファイル名
                (0x434, 4, 10),     # Use の品物
                (0x5F34, 2, 7),     # 探す品物
                (0x8322, 2, 8),     # 真言
                (0x6FF0, 2, 27),    # ロード・ブリティッシュに聞ける言葉
                (0x2A90, 4, 10),    # 会話の決まりの言葉
                (0x161A, 2, 11)]    # 祭壇の言葉（truth〜humility）
A_CMP_DIRECT = [0x1233, 0x147B, 0x152B, 0x15DB, 0x3DF3, 0x3DF8, 0x2C7E, 0x2C81]
A_RUNTIME = 0x85EC                  # ここから後ろは C の実行時ライブラリ
# 先頭の決め方の例外: 前のバイトが番地の表の一部（「<」は 0x3C93 の上位バイト）
A_START_FIX = {0x3F5B: 0x3F5C}
# 実行時ライブラリのエラー文（DOS の画面に出る）。訳さない。先頭は 0x36 と 0x5E
A_KEEP_TEXT = {"Disk error. Press any key to try again.", "isk error. Press any key to try again.",
               "DOS: Fatal System Error!"}
# 記号のような並び（表示はするが文字の並び自体に意味があるもの、データの一部）
KEEP_LITERAL = {">*", "a*", "(HX_", "wg`", "wiaogc`", "<Z", "(#", "BYRGOPWB", "HCVJSHSH", "\n$"}
FILE_RE = re.compile(r"^[%A-Za-z0-9_]*\.[A-Za-z]{3}$|^\.(pic|ega)$|^rune_\d$")
FILE_EXT = (".SAV", ".ULT", ".TLK", ".MAP", ".CON", ".DNG", ".EXE", ".DRV", ".PIC", ".EGA", ".NEW")

T_DGROUP = 0x3FD0


def regions(D):
    out = {}
    for m in re.finditer(rb"[\x20-\x7e\n\x08\x12]{1,}\x00", D):
        out[m.start()] = m.end() - 1        # 先頭 → 0 の位置
    return out


def code_refs(img, ds):
    """Microsoft C が文字列を渡す形だけを拾う: mov ax/dx/si/di,即値（b8/ba/be/bf）、push 即値（68）、
    mov word ptr [番地],即値（c7 06）、mov word ptr [bp+d8],即値（c7 46）"""
    vals = set()
    code = img[:ds]
    for i in range(len(code) - 2):
        op = code[i]
        if op in (0xB8, 0xBA, 0xBE, 0xBF, 0x68):
            vals.add(struct.unpack_from("<H", code, i + 1)[0])
        elif op == 0xC7 and i + 6 <= len(code):
            if code[i + 1] == 0x06:
                vals.add(struct.unpack_from("<H", code, i + 4)[0])
            elif code[i + 1] == 0x46:
                vals.add(struct.unpack_from("<H", code, i + 3)[0])
    return vals


def table_refs(D, reg):
    """データの中の番地の表: 文字列の先頭を指す 2 バイトが 2 つ以上並んでいる所だけ"""
    inside = set()
    for s, e in reg.items():
        inside.update(range(s, e + 1))
    starts = set(reg)
    text = set()
    for s, e in reg.items():
        text.update(range(s, e))
    vals = set()
    for step in (2, 4):
        for i in range(len(D) - 2 * step):
            if i in inside:
                continue
            a = struct.unpack_from("<H", D, i)[0]
            b = struct.unpack_from("<H", D, i + step)[0]
            # 2 つとも文字列の中を指し、少なくとも一方は文字列の先頭
            if a in text and b in text and (a in starts or b in starts):
                vals.add(a)
                vals.add(b)
    return vals


def build(img, ds, prefix, keep_offs, runtime):
    D = img[ds:]
    reg = regions(D)
    refs = code_refs(img, ds) | table_refs(D, reg)
    rows = []
    for s, e in sorted(reg.items()):
        kp = sorted(v for v in keep_offs if s <= v < e)
        hits = sorted(v for v in refs if s <= v < e)
        if kp:
            start = kp[0]
        else:
            start = s if (s in refs or not hits) else hits[0]
        if prefix == "A":
            start = A_START_FIX.get(start, start)
        text = D[start:e].decode("latin1")
        if not text.strip():
            continue
        if len(text) < 2 and start not in refs:
            continue
        kind, note = "text", ""
        if start in keep_offs:
            kind, note = "keep", "打った言葉と比べる"
        elif FILE_RE.match(text) or text.upper().endswith(FILE_EXT):
            kind, note = "keep", "ファイル名"
        elif text in KEEP_LITERAL or (prefix == "A" and text in A_KEEP_TEXT):
            kind, note = "keep", "記号の並び"
        elif runtime is not None and start >= runtime:
            kind, note = "keep", "実行時ライブラリ"
        elif start not in refs:
            note = "参照が見つからない"
        rows.append((f"{prefix}:{start:04X}", e - start, kind, note, text))
    return rows


def keep_offsets_avatar(D):
    keep = set(A_CMP_DIRECT)
    for base, step, n in A_CMP_TABLES:
        for i in range(n):
            v = struct.unpack_from("<H", D, base + i * step)[0]
            if v:
                keep.add(v)
    return keep


def esc(t):
    """表に書くときの書き方: 改行は \n、入力欄の制御バイトは \x12（右へ）と \x08（戻る）"""
    return t.replace("\n", "\\n").replace("\x12", "\\x12").replace("\x08", "\\x08")


def write(rows, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# id\t最大バイト\t種類\tメモ\t英文\n")
        for r in rows:
            f.write("\t".join([r[0], str(r[1]), r[2], r[3], esc(r[4])]) + "\n")
    print(os.path.basename(path), len(rows), "件、うち訳す", sum(1 for r in rows if r[2] == "text"), "件",
          sum(r[1] for r in rows if r[2] == "text"), "バイト")


def main():
    img = unpack_avatar(os.path.join(GAME, "AVATAR.EXE"))
    write(build(img, DGROUP, "A", keep_offsets_avatar(img[DGROUP:]), A_RUNTIME), os.path.join(OUT, "master_avatar.tsv"))
    t = open(os.path.join(GAME, "TITLE.EXE"), "rb").read()
    timg = t[struct.unpack_from("<H", t, 8)[0] * 16:]
    tD = timg[T_DGROUP:]
    rt = tD.find(b";C_FILE_INFO")
    write(build(timg, T_DGROUP, "T", set(), rt if rt > 0 else None), os.path.join(OUT, "master_title.tsv"))


if __name__ == "__main__":
    main()
