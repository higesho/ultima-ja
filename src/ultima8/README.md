# ウルティマVIII 日本語化の道具

ウルティマVIII（GOG 版 DOS）の日本語化で、英語版のデータから日本語版のファイルと差分を作る Python の道具です。

- `tools/extract.py` 英語版から訳す文を書き出す
- `tools/u8uc.py`・`u8shape.py` usecode とフォント（shape）の読み書き
- `tools/build_jp.py` 訳から JUSECODE.FLX・字幕・漢字フォント入りの U8FONTS.FLX を組み立てる（`python -I tools/build_jp.py 出力先`）
- `tools/build_jpfont.py` 漢字フォントを作る
- `tools/make_delta.py` 英語版から日本語版を作る差分 u8jp.dlt を作る
- `tools/make_dist.py` 配布物の zip を作る
- そのほか: 訳の検査（`check.py`・`check_draft.py`）、用語集の下書き（`make_glossary.py`）

`build_jp.py` が使う、せりふのページ分けの道具（paginate.py）はここには入っていません。
必要なもの: Python 3、Pillow、PixelMplus10 フォント。
原作のゲームファイルと訳の表は入っていません。ゲームは各自で用意してください。

日本語版を動かすエンジン部分（ScummVM の非公式ビルド）は https://github.com/higesho/scummvm の ja ブランチにあり、
そちらの元のライセンス（GPL）に従います。
