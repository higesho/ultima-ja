# ウルティマVII 第2部 サーペントアイル 日本語化の道具

ウルティマVII 第2部 Serpent Isle（Silver Seed 入り、GOG 版）の日本語化で、訳の表やフォント・絵を
改造版 Exult のパッチフォルダの形に組み立てる Python の道具です。

- `tools/si_uc.py` USECODE の分解・組み直し（64KB を超える関数は 32 ビット命令に広げる）
- `tools/mkpatch.py` パッチフォルダの中身を作る（`python mkpatch.py 出力フォルダ`）
- `tools/mkgumps.py`・`mkmenu.py` 日本語の絵を作る
- `tools/mkdist.py` 配布物の zip を作る
- そのほか: 訳の検査（`check.py`）、物の名前・用語・口調の表（`names.py`・`term_table.py`・`tone_table.py`）

フォントや一部の道具はウルティマVII（`../ultima7`）のものを使います。
必要なもの: Python 3、Pillow。
原作のゲームファイルと訳の表は入っていません。ゲームは各自で用意してください。

日本語を表示するエンジン部分（改造版 Exult）は https://github.com/higesho/exult の ja ブランチにあり、
そちらの元のライセンス（GPL）に従います。
