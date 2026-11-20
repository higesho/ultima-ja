# 画像を横 N 枚ずつ並べて1枚にする（確認用）
# 使い方: python tile.py <出力.png> <横の枚数> <画像...>
import sys
from PIL import Image
out, n, files = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
ims = [Image.open(f).convert("RGB") for f in files]
w = max(i.width for i in ims); h = max(i.height for i in ims)
rows = (len(ims) + n - 1) // n
sheet = Image.new("RGB", (w * n, h * rows), (60, 60, 60))
for k, im in enumerate(ims):
    sheet.paste(im, ((k % n) * w, (k // n) * h))
sheet.save(out)
print(sheet.size)
