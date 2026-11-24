# ウルティマ アンダーワールド 日本語化の道具

DOS 版 Ultima Underworld（GOG 版）の日本語化パッチを組み立てる道具です。
ウルティマ アンダーワールド2 も同じ道具で作ります（`--game=uw2` などで切り替え）。

- `tools/build_uwjp.py` 常駐部 UWJP.COM と日本語の文字列 UWJP.DAT を作る（`python build_uwjp.py 訳のファイル 出力フォルダ`）
- `tools/uwjpenc.py`・`uwexe.py` 文字の符号と、EXE を読む部分
- `tools/make_dist.py` 配布物の zip を作る（`python make_dist.py [--game=uw2]`）
- `glu/` 配布物に入れている opengl32.dll（32 ビットと 64 ビット。DOSBox の版を問わない）。画面の美咲フォントの字を東雲 12 ドットで描き直す
  - `build.bat`（Visual Studio 2022 Build Tools）で、`gen_fwd.py` が本物の opengl32.dll へつなぐ部分を作ってから組み立てる。
    アンダーワールドは `out32/`・`out64/`、アンダーワールドII は `out32_uw2/`・`out64_uw2/`（違いはバージョン情報 `ver/<作品>.rc` だけ）
  - 字の表 glyphs.h は `gl64/` のものを使う（入っていない）
- `gl64/` 前の 64 ビットだけの opengl32.dll（dosbox-staging 用）。画面の美咲フォントの字を東雲 12 ドットで描き直す
  - `gen.py` で本物の opengl32.dll へつなぐ部分（exports.def・exports.h・stubs.asm）を作り、`gen_glyphs.py` で字の表 glyphs.h を作ってから `build.bat`（Visual Studio の x64 ツール）
  - `gen_glyphs.py` はウルティマI の道具（`../ultima1`）の gen.py を使います。字の表 glyphs.h は入っていません

必要なもの: Python 3、keystone-engine、capstone、pefile、美咲フォントと東雲フォントの BDF。
原作のゲームファイルと訳の表は入っていません。ゲームは各自で用意してください。
