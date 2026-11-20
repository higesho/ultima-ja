# ウルティマV 日本語化の道具

DOS 版ウルティマV（GOG 版・Steam 版）の日本語化パッチを組み立てる Python の道具です。

- `tools/build_u5jp.py` 常駐部 U5JP.COM を作る（`python build_u5jp.py 訳のファイル 出力U5JP.COM`）
- `tools/build_tlj.py` 会話の日本語版 *.TLJ を作る
- `tools/make_patch.py` 組み立てた日本語版のファイルから差分 U5JP.DAT を作る
- `tools/build_mk.py` 遊ぶ人の DOSBox で U5JP.DAT を当てる U5JPMK.COM を作る
- `tools/make_dist.py` 配布物の zip を作る
- そのほか: 原作の文章の書き出し（`tlk_extract.py`・`data_extract.py` など）と訳の検査（`import_check.py`・`review_check.py`）

必要なもの: Python 3、keystone-engine、capstone、美咲フォントの BDF。
原作のゲームファイルと訳の表は入っていません。ゲームは各自で用意してください。

`make_engine_ja.py`・`make_jfont.py`・`merge_ui.py` は新エンジン版の日本語データを作る道具です。
新エンジン版の本体は https://github.com/higesho/ultima5 にあり、そちらのライセンスに従います。
