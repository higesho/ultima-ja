# ウルティマIV 日本語化の組み立て

GOG 版・Steam 版ウルティマIV（DOS）を日本語にするための Python の道具です。ゲームのファイルは書き換えず、常駐プログラム U4JP.COM が文字の描画を横取りし、文字列を置き換えます。Ultima IV Upgrade の 256 色表示にも対応します。

- `tools/make_master.py` … 訳す英文の元表を作る
- `tools/build_u4jp.py <ゲームのフォルダ> <訳のファイル> <出力 U4JP.COM>` … 常駐プログラム U4JP.COM、表 U4JP.DAT、町ごとの会話 .TLJ を作る
- `tools/make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元> <dist フォルダ>` … 配布物をまとめる
- `tools/check_ja.py`・`check_tlk.py` … 訳の検査
- そのほかは解析・試験用の道具です

必要なもの: Python 3、GOG 版のゲームのファイル、訳の表、美咲フォント・BIZ UD 明朝。これらはここには入っていないので各自用意してください。
