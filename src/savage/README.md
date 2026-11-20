# The Savage Empire 日本語化の組み立て

GOG 版 Worlds of Ultima: The Savage Empire（DOS）を日本語にするための道具です。常駐プログラム SEJP.COM がゲームの読み込みを横取りして日本語にします。

- `build.sh` … 組み立ての手順。`tools/build_sejp.py` で SEJP.COM・SEJP.DAT と日本語版の LZC を、
  `tools/make_patch_se.py` で配布用の差分 SEJP.PAT を、`tools/build_mk_se.py` で遊ぶ人の所で日本語版のファイルを作る SEJPMK.COM を作る
- `tools/make_dist_se.py` … 配布物をまとめる。`check_dist_se.py` は配布物に原作のデータが入っていないかを調べる
- `tools/seconv.py`・`u6conv.py` など … 会話スクリプトの読み書き
- そのほかは解析・試験用の道具です

必要なもの: Python 3、GOG 版のゲームのファイル（build.sh は `../SAVAGE` にあるものとする）、`translation/` の訳の表、美咲フォント。これらはここには入っていないので各自用意してください。
