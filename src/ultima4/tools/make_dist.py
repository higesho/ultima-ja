# 配布物を作る
#   dist/ウルティマ4日本語化パッチ/ に U4JP.COM、U4JP.DAT、町ごとの .TLJ（16 個）、dosboxULTIMA4_single.conf、
#   はじめにお読みください.txt を置き、dist/Ultima4_JP.zip と dist/ウルティマ4日本語化パッチ.zip（どちらもフォルダなし）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
#   起動設定は GOG 版の dosboxULTIMA4_single.conf の ultima.com の前に U4JP を足したもの（Steam 版も同じ conf を読む）
import glob
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "ウルティマ4日本語化パッチ")
if os.path.isdir(src):
    shutil.rmtree(src)
os.makedirs(src)

conf = open(os.path.join(game, "dosboxULTIMA4_single.conf"), "rb").read().decode("latin-1")
assert conf.count("\r\nultima.com\r\n") == 1 and "U4JP" not in conf
conf = conf.replace("\r\nultima.com\r\n", "\r\nU4JP\r\nultima.com\r\n", 1)
open(os.path.join(src, "dosboxULTIMA4_single.conf"), "wb").write(conf.encode("latin-1"))

names = ["U4JP.COM", "U4JP.DAT"]
tljs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(build, "*.TLJ")))
assert len(tljs) == 16, tljs
for n in names + tljs:
    shutil.copyfile(os.path.join(build, n), os.path.join(src, n))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

files = names + tljs + ["dosboxULTIMA4_single.conf", "はじめにお読みください.txt"]
for zname in ["Ultima4_JP.zip", "ウルティマ4日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in files:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト、", len(files), "ファイル")
