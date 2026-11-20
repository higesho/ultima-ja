# ウルティマVI 日本語化の道具

DOS 版ウルティマVI（GOG 版・Steam 版）の日本語化パッチを組み立てる Python の道具です。

- `tools/build_u6jp.py` 常駐部 U6JP.COM を作る（`python build_u6jp.py ゲームのフォルダ 本編の文字列の訳 出力U6JP.COM`）
- `tools/conv_text.py`・`u6conv.py` 会話スクリプト（CONVERSE.A/B）の文章の書き出しと訳の取り込み
- `tools/make_patch.py` 組み立てた会話・本から差分 U6JPMK.DAT を作る
- `tools/build_mk.py` 遊ぶ人の DOSBox で差分を当てる U6JPMK.COM を作る
- `tools/make_dist.py` 配布物の zip を作る
- そのほか: EXEPACK の展開（`unexepack.py`）、U6 の LZW と lib 形式（`u6fmt.py`）、訳の検査（`check_ja.py` など）

必要なもの: Python 3、keystone-engine、capstone、美咲フォントの BDF。
原作のゲームファイルと訳の表は入っていません。ゲームは各自で用意してください。
