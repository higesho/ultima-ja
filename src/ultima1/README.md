# ウルティマI 日本語化の組み立て

GOG 版ウルティマI（DOS）を日本語にするための道具です。ゲームのファイルは書き換えず、常駐プログラム U1JP.COM が読み込み直後のメモリを書き換えます。

- `tools/build_patch.py <元のゲームのフォルダ> <訳の表のフォルダ> <出力 U1JP.COM>` … 常駐プログラムを作る
- `tools/jpenc.py` … 日本語の文字の符号化とフォントの表（ほかの作品の道具も同じものを使う）
- `tools/make_tables.py`・`apply_translation.py` など … 訳の表を作る・当てる
- `tools/make_ending.py <出力 NIJ.BIN>` … エンディングの日本語の絵を作る
- `gl/` … DOSBox の DOSBOX フォルダに置く opengl32.dll の代わり（窓の大きさの変更と東雲フォントでの描き直し）。
  `python gen.py` で exports.h・glyphs.h・build.bat を作り、`build.bat`（Visual Studio 2022 Build Tools の x86）で `out/opengl32.dll` を組み立てる。
  `ultima_ja.ini` はその設定の見本。この DLL はアカラベス・II〜IV・サベージ・マーシャンの配布物にも入る
- そのほかは解析・試験用の道具です

必要なもの: Python 3（gen.py は pefile も）、GOG 版のゲームのファイル、訳の表、美咲フォント・東雲フォントの BDF。これらはここには入っていないので各自用意してください。
