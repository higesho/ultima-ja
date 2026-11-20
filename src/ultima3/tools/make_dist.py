# 配布物を作る
#   dist/ウルティマ3日本語化パッチ/ に U3JP.COM、dosboxULTIMA3_single.conf、はじめにお読みください.txt を置き、
#   dist/Ultima3_JP.zip と dist/ウルティマ3日本語化パッチ.zip（どちらもフォルダなしで3ファイル）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <U3JP.COM> <説明書の元（UTF-8）> <dist フォルダ>
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, com, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "ウルティマ3日本語化パッチ")
os.makedirs(src, exist_ok=True)

# 起動設定: GOG 版の dosboxULTIMA3_single.conf に、U3JP の起動を足す（改行は CRLF のまま）
#   画面の種類は GOG 版の dosboxULTIMA3.conf がもともと svga_s3 なので変えない
conf = open(os.path.join(game, "dosboxULTIMA3_single.conf"), "rb").read().decode("latin-1")
assert "\r\nultima.com\r\n" in conf
conf = conf.replace("\r\nultima.com\r\n", "\r\nU3JP\r\nultima.com\r\n", 1)
open(os.path.join(src, "dosboxULTIMA3_single.conf"), "wb").write(conf.encode("latin-1"))

shutil.copyfile(com, os.path.join(src, "U3JP.COM"))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = ["U3JP.COM", "dosboxULTIMA3_single.conf", "はじめにお読みください.txt"]
for zname in ["Ultima3_JP.zip", "ウルティマ3日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト")
