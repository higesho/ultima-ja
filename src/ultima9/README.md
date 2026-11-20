# ウルティマIX の調べる道具

Ultima IX: Ascension（Steam 版）の動きを調べるための道具です。

- `tools/probe/u9probe.c` メモリの確保・解放を数える DLL（32 ビット）。裏に回ってもゲームを止めない
- `tools/probe/u9run.c` u9probe.dll を読み込ませてゲームを起動する
- `tools/probe/build.bat` 上の 2 つを作る（Visual Studio の x86 ツール）
- `tools/u9_ctl.py` 起動・キー送り・画面の撮影・メモリの計測（ウインドウはプロセス番号で選ぶ）
- `tools/leak_test.py`・`leak_diff.py` 操作を繰り返して、確保の集計の増減を比べる

必要なもの: Python 3、Pillow。
ゲームは各自で用意してください。
