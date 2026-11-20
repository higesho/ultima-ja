# 配布物を作る
#   dist/アカラベス日本語化パッチ/ に AKJPMK.COM、AKJP.PAT、AJ.DAT、dosboxAkalabeth_single.conf、
#   はじめにお読みください.txt を置き、dist/Akalabeth_JP.zip と dist/アカラベス日本語化パッチ.zip（どちらもフォルダなし）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
#   起動設定は GOG 版の dosboxAkalabeth_single.conf の「ak」の行を、
#   AKJPMK（AKJP.EXE を作る）→ AKJP.EXE があればそれを、なければ元の AK を起動、の3行にしたもの
#   AKJP.EXE は配らない（原作のプログラムを含むため）。遊ぶ人の所で AKJPMK.COM が作る
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "アカラベス日本語化パッチ")
if os.path.isdir(src):
    shutil.rmtree(src)
os.makedirs(src)

conf = open(os.path.join(game, "dosboxAkalabeth_single.conf"), "rb").read().decode("latin-1")
assert conf.count("\r\nak\r\n") == 1 and "AKJP" not in conf
conf = conf.replace("\r\nak\r\n", "\r\nAKJPMK\r\nif exist AKJP.EXE AKJP\r\nif not exist AKJP.EXE AK\r\n", 1)
open(os.path.join(src, "dosboxAkalabeth_single.conf"), "wb").write(conf.encode("latin-1"))

names = ["AKJPMK.COM", "AKJP.PAT", "AJ.DAT"]
for n in names:
    shutil.copyfile(os.path.join(build, n), os.path.join(src, n))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

files = names + ["dosboxAkalabeth_single.conf", "はじめにお読みください.txt"]
for zname in ["Akalabeth_JP.zip", "アカラベス日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in files:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト、", len(files), "ファイル")
