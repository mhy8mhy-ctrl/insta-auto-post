"""投稿待ち(queue/)から1本だけInstagramに投稿する。GitHub Actionsから毎日呼ばれる。
queue/YYYY-MM-DD/ に 01.jpg〜 と caption.txt を置く。日付が今日(日本時間)以前で一番古い1本を出す。
リポジトリ直下に PAUSE というファイルがあれば何もしない。"""
import json, os, sys, time, shutil, datetime, urllib.parse, urllib.request, urllib.error
from pathlib import Path

VER = "v27.0"
API = os.environ.get("IG_API") or f"https://graph.facebook.com/{VER}"
IG_ID = os.environ.get("IG_USER_ID") or "17841462905024698"   # @manabirador
ROOT = Path(__file__).parent
JST = datetime.timezone(datetime.timedelta(hours=9))


def call(method, path, **params):
    params["access_token"] = os.environ["IG_TOKEN"]
    data = urllib.parse.urlencode(params)
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data)
    else:
        req = urllib.request.Request(url, data=data.encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"APIエラー {e.code} ({method} {path}): {body}")


def probe():
    """トークンで投稿先のアカウントに届くかを調べる(トークンは表示しない。投稿もしない)。"""
    print("トークンの持ち主:", call("GET", "me", fields="id,name"))
    print("投稿先:", call("GET", IG_ID, fields="username,media_count"))
    print("24時間の投稿数:", call("GET", f"{IG_ID}/content_publishing_limit", fields="quota_usage,config"))


def wait_ready(container_id):
    for _ in range(60):
        st = call("GET", container_id, fields="status_code").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"コンテナ {container_id} が {st}")
        time.sleep(5)
    sys.exit(f"コンテナ {container_id} の準備が終わらない")


def pick():
    today = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    days = sorted(p for p in (ROOT / "queue").iterdir() if p.is_dir() and p.name[:10] <= today)
    return days[0] if days else None


def main():
    if os.environ.get("PROBE") == "1":
        probe(); return
    if (ROOT / "PAUSE").exists():
        print("PAUSEファイルがあるので投稿しない"); return
    d = pick()
    if d is None:
        print("今日までの投稿待ちはない"); return
    images = sorted(d.glob("*.jpg"))
    caption = (d / "caption.txt").read_text(encoding="utf-8").strip()
    if not images:
        sys.exit(f"{d.name} に画像がない")
    if len(images) > 20:
        sys.exit(f"{d.name} の画像が20枚をこえている")
    repo = os.environ["GITHUB_REPOSITORY"]
    ref = os.environ.get("GITHUB_REF_NAME", "main")
    base = f"https://raw.githubusercontent.com/{repo}/{ref}/queue/{urllib.parse.quote(d.name)}"
    print(f"投稿する: {d.name} / {len(images)}枚")
    if os.environ.get("DRY_RUN") == "1":
        for im in images: print("  ", f"{base}/{im.name}")
        print(caption); return

    ig = IG_ID
    if len(images) == 1:
        cid = call("POST", f"{ig}/media", image_url=f"{base}/{images[0].name}", caption=caption)["id"]
    else:
        kids = []
        for im in images:
            k = call("POST", f"{ig}/media", image_url=f"{base}/{im.name}", is_carousel_item="true")["id"]
            wait_ready(k); kids.append(k)
        cid = call("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
    wait_ready(cid)
    media_id = call("POST", f"{ig}/media_publish", creation_id=cid)["id"]
    print("投稿できた media_id =", media_id)

    shutil.move(str(d), str(ROOT / "posted" / d.name))
    with open(ROOT / "posted" / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": d.name, "media_id": media_id, "images": len(images),
                            "posted_at": datetime.datetime.now(JST).isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
