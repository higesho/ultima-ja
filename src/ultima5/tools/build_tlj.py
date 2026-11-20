# 会話ファイル（*.TLK）の日本語版（*.TLJ）を作る（試作）
# 使い方: python build_tlj.py <訳のファイル> <出力フォルダ>
#   訳のファイル: 「ファイル名<TAB>人の番号<TAB>欄の番号<TAB>訳」
#     人の番号: TLK の見出しに並ぶ順（0 から）。欄: 台本を 0 で区切った何番目か（0 名前、1 見た目、2 あいさつ、3 仕事、4 別れ …）
#     訳の中の {8d} などは命令のバイトをそのまま入れる。\n は 0x8D（改行）
# 訳のない人・欄は元のバイト列をそのまま使う。常駐部は TLK を開くときに TLJ に差し替える
#
# 文字の符号は build_u5jp.py と同じ（会話の文字は最上位ビットを立てて入れる。ゲームが下位7ビットにしてから書く）
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import build_u5jp as B  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def read_tlk(path):
    d = open(path, "rb").read()
    n = struct.unpack_from("<H", d)[0]
    ent = [struct.unpack_from("<HH", d, 2 + 4 * k) for k in range(n)]
    offs = [o for _, o in ent] + [len(d)]
    npcs = []
    for k in range(n):
        npcs.append((ent[k][0], d[offs[k]:offs[k + 1]].split(b"\0")))
    return npcs


def write_tlk(path, npcs):
    head = struct.pack("<H", len(npcs))
    body = bytearray()
    base = 2 + 4 * len(npcs)
    for num, fields in npcs:
        head += struct.pack("<HH", num, base + len(body))
        body += b"\0".join(fields)
    if base + len(body) > 0xFFFF:
        raise RuntimeError(f"{path}: 64KB を超えました")
    open(path, "wb").write(head + body)


RUNMAX = 16      # TALK.OVL は単語を 16 バイトまでしかためられない（17 バイト目は捨てられる）
WARN = []        # 英字の直後に区切りが入って空白が見えてしまう所（組み立ての後に表示する）


def encode_field(enc, text):
    """訳を TLK のバイト列にする。日本語が続いて 16 バイトを超える前に、目に見えない区切り（半角空白）を入れる"""
    out = bytearray()
    run = 1          # 返事の先頭には、ゲームが " を付けて同じ入れ物に入れる
    prev_jp = False
    for part in re.split(r"(\{[0-9a-fA-F]{2}\}|\n)", B.norm(text)):
        if not part:
            continue
        if part == "\n":
            out.append(0x8D)
            run = 0
            prev_jp = False
        elif part.startswith("{"):
            c = int(part[1:3], 16)
            # 0x8D（改行）は区切りになる。0x81（主人公の名前、最大 8 バイト）の前は、日本語の直後なら区切っておく
            if c == 0x81:
                if prev_jp:
                    out.append(0xA0)
                    run = 0
                run += 8
                prev_jp = False
            elif c == 0x8D:
                run = 0
                prev_jp = False
            # ほかの命令は字を書かないので、「直前の字が日本語か」はそのまま引き継ぐ
            out.append(c)
        else:
            for ci, ch in enumerate(part):
                e = enc.encode(ch)
                if prev_jp and ord(ch) <= 0x7E and ch != " ":
                    # 日本語から英字に変わる所: 英字のまとまりが入らなければ、ここで区切る（日本語の直後なので描かれない）
                    m = re.match(r"[!-~]+", part[ci:])
                    if m and run + len(m.group()) > RUNMAX:
                        out.append(0xA0)
                        run = 0
                if any(b < 0x20 for b in e):
                    raise RuntimeError(f"会話に使えない字: {part!r}")
                jp = ord(ch) > 0x7E
                if ch == " ":
                    run = -1
                elif run + len(e) > RUNMAX:
                    # 区切りの半角空白は、日本語の字の直後なら常駐部が描かずに捨てる。そうでなければ空白として見える
                    if not (jp or prev_jp):
                        WARN.append(f"見える空白が入る: {text[:40]!r}")
                    out.append(0xA0)
                    run = 0
                out += bytes(b | 0x80 for b in e)
                run += len(e)
                prev_jp = jp
    return bytes(out)


def main(trfile, outdir, enc=None):
    game = os.path.join(B.HERE, "..", "game_test")
    items = []
    for line in open(trfile, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        f, npc, field, ja = line.split("\t", 3)
        items.append((f.upper(), int(npc), int(field), ja.replace("\\n", "\n")))
    if enc is None:
        enc = B.Enc([re.sub(r"\{..\}", "", ja) for *_, ja in items])
    os.makedirs(outdir, exist_ok=True)
    for name in sorted({f for f, *_ in items}):
        npcs = read_tlk(os.path.join(game, name))
        for f, npc, field, ja in items:
            if f == name:
                npcs[npc][1][field] = encode_field(enc, ja)
        out = os.path.join(outdir, name[:-4] + ".TLJ")
        write_tlk(out, npcs)
        print("書き出し:", out, len(open(out, "rb").read()), "バイト")
    if WARN:
        print("見える空白が入る所:", len(WARN))
        for w in WARN[:10]:
            print("  ", w)
    return enc


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
