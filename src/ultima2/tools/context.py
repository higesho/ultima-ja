# 埋め込み文字列ごとに、前後で何をしているかを一覧にする（翻訳の手がかり）
# 使い方: python context.py <ULTIMAII.EXE> <出力.txt>
import struct
import sys
import capstone

sys.stdout.reconfigure(encoding="utf-8")
img = open(sys.argv[1], "rb").read()[512:]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
NAMES = {0x4FDF: "文字列", 0x5003: "1文字", 0x53F4: "1文字", 0x53B5: "数値2桁", 0x508C: "表の項目",
         0x507A: "名前", 0x4F4D: "キー", 0x51EB: "位置", 0x51FD: "カーソル", 0x4A1C: "文字画面",
         0x4A3E: "CGA画面", 0x538F: "下2行を消す", 0x53A0: "1行を消す", 0x5380: "待つ", 0x51B0: "数値入力",
         0x505F: "男女", 0x5217: "乱数"}


def desc(ins):
    if ins.mnemonic == "call":
        try:
            t = int(ins.op_str, 16)
        except ValueError:
            return "call " + ins.op_str
        return NAMES.get(t, f"call {t:x}")
    return f"{ins.mnemonic} {ins.op_str}"


out = open(sys.argv[2], "w", encoding="utf-8")
for i in range(len(img) - 3):
    if img[i] == 0xE8 and (i + 3 + struct.unpack_from("<h", img, i + 1)[0]) & 0xFFFF == 0x4FDF:
        s = i + 3
        e = img.index(b"\0", s)
        text = bytes(b & 0x7F for b in img[s:e]).decode("latin-1").replace("\r", "\\n").replace("\n", "\\n")
        pre = [desc(x) for x in md.disasm(img[i - 14:i], i - 14)][-3:]
        post = [desc(x) for x in md.disasm(img[e + 1:e + 16], e + 1)][:3]
        out.write(f"{s:05x}\t{e - s}\t{text}\t前: {' / '.join(pre)}\t後: {' / '.join(post)}\n")
out.close()
