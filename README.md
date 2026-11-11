# insta-auto-post

Instagram @manabirador に、毎日21時(日本時間)に1本ずつ自動で投稿する仕組み。

- `specs/日付.json` … 1本分の原稿(7枚の文とキャプション)
- `make_carousel.py` … 原稿から画像を作り、検査に合格したものだけ `queue/日付/` に置く
- `post.py` + `.github/workflows/post.yml` … 毎日、`queue/` の一番古い1本を投稿し `posted/` へ移す
- `reel.py` + `.github/workflows/reel.yml` … 毎朝7時、前の晩に投稿した7枚を約15秒の縦長リール(無音)にして投稿する。記録は `posted/reels.jsonl`
- キャプションにタグがなければ、検索用のタグを末尾に自動で足す(`post.py` の TAGS)
- 止めたいとき … リポジトリ直下に `PAUSE` という名前のファイルを置く。1本だけやめるなら `queue/` のその日付フォルダを消す
- `private/` … 個人名の検査リスト。公開しない(.gitignore)

必要なSecrets: `IG_TOKEN`(Metaのシステムユーザートークン。期限なし)
