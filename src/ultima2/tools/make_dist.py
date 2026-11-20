# 配布物を作る
#   dist/ウルティマ2日本語化パッチ/ に U2JP.COM、dosboxULTIMA2_single.conf、はじめにお読みください.txt を置き、
#   dist/Ultima2_JP.zip と dist/ウルティマ2日本語化パッチ.zip（どちらもフォルダなしで3ファイル）を作る
# このあと Ultima 1/jp_work/gl/make_dist.py を流して、窓の表示と東雲フォントの DLL を足す
# 使い方: python make_dist.py <ゲームのフォルダ> <U2JP.COM> <説明書の元（UTF-8）> <dist フォルダ>
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, com, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "ウルティマ2日本語化パッチ")
os.makedirs(src, exist_ok=True)

# 起動設定: GOG 版の dosboxULTIMA2_single.conf に、画面の種類（VGA）と U2JP の起動を足す（改行は CRLF のまま）
conf = open(os.path.join(game, "dosboxULTIMA2_single.conf"), "rb").read().decode("latin-1")
assert "\r\nultimaII.exe\r\n" in conf and "[autoexec]" in conf
conf = conf.replace("[autoexec]", "[dosbox]\r\nmachine=svga_s3\r\n\r\n[autoexec]", 1)
conf = conf.replace("\r\nultimaII.exe\r\n", "\r\nU2JP\r\nultimaII.exe\r\n", 1)
open(os.path.join(src, "dosboxULTIMA2_single.conf"), "wb").write(conf.encode("latin-1"))

shutil.copyfile(com, os.path.join(src, "U2JP.COM"))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = ["U2JP.COM", "dosboxULTIMA2_single.conf", "はじめにお読みください.txt"]
for zname in ["Ultima2_JP.zip", "ウルティマ2日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト")
