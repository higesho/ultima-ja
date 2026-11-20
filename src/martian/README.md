# Martian Dreams 日本語化の組み立て

GOG 版 Worlds of Ultima: Martian Dreams（DOS）を日本語にするための道具です。常駐プログラム MDJP.COM がゲームの読み込みを横取りして日本語にします。

- `build.sh` … 組み立ての手順。`tools/build_mdjp.py` で MDJP.COM・MDJP.DAT と日本語版の LZC を、
  `tools/make_patch.py` で配布用の差分 MDJP.PAT を、`tools/build_mk.py` で遊ぶ人の所で日本語版のファイルを作る MDJPMK.COM を作る
- `deploy.sh` … 組み立てた物を試験用のフォルダ `game_test` に入れる
- `tools/make_dist.py` … 配布物をまとめる。`check_dist.py` は配布物に原作のデータが入っていないかを調べる
- `tools/u6conv.py`・`mdtalk.py` など … 会話スクリプトの読み書き
- そのほかは解析・試験用の道具です

必要なもの: Python 3、GOG 版のゲームのファイル（build.sh は `../MARTIAN` にあるものとする）、`translation/` の訳の表、美咲フォント。これらはここには入っていないので各自用意してください。
