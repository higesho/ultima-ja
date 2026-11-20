# ウルティマ0 アカラベス 日本語化の組み立て

GOG 版 Akalabeth（AK.EXE、DJGPP + Allegro）を日本語にするための Python の道具です。

- `tools/build_akjp.py <元の AK.EXE> <元の AK.DAT> <出力フォルダ>` … 日本語版の本体 AKJP.COFF と訳文の AJ.DAT を作る
- `tools/make_patch.py <元の AK.EXE> <AKJP.COFF> <出力 AKJP.PAT>` … 配布用の差分（変えたバイトだけ）を作る
- `tools/build_mk.py <出力 AKJPMK.COM>` … 遊ぶ人の所で AKJP.EXE を組み立てる DOS のプログラムを作る
- `tools/make_dist.py` … 配布物をまとめる。`check_dist.py` は配布物に原作のデータが入っていないかを調べる
- そのほかは解析・試験用の道具です

必要なもの: Python 3、GOG 版のゲームのファイル、訳の表、美咲フォント。これらはここには入っていないので各自用意してください。
