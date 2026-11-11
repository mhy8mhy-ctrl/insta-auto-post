"""前の晩に投稿したカルーセルの7枚を、約15秒の縦長リール(無音)にして投稿する。
GitHub Actions(.github/workflows/reel.yml)から毎朝呼ばれる。
  python3 reel.py build  … posted/の一番新しい日付で、まだリールにしていないものの reel.mp4 を作る
  python3 reel.py post   … その reel.mp4 をリールとして投稿し、posted/reels.jsonl に記録する
リポジトリ直下に PAUSE があれば何もしない。"""
import json, os, sys, time, subprocess, urllib.request, urllib.parse
from pathlib import Path

from post import call, IG_ID, JST, ROOT, add_tags

LOG = ROOT / "posted" / "reels.jsonl"
SEC_FIRST = 3.0   # 1枚目(つかみ)は長めに見せる
SEC_EACH = 2.0
BG = "0xF9FDFF"   # 画像の地の色


def done_days():
    if not LOG.exists():
        return set()
    return {json.loads(l)["date"] for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()}


def target():
    days = sorted(p for p in (ROOT / "posted").iterdir() if p.is_dir())
    if not days:
        return None
    d = days[-1]                       # 一番新しい投稿だけ。古い日はさかのぼらない
    return None if d.name in done_days() else d


def build(d):
    imgs = sorted(d.glob("*.jpg"))
    if not imgs:
        sys.exit(f"{d.name} に画像がない")
    args, parts = ["ffmpeg", "-y", "-loglevel", "error"], []
    for i, im in enumerate(imgs):
        args += ["-loop", "1", "-t", str(SEC_FIRST if i == 0 else SEC_EACH), "-i", str(im)]
        parts.append(f"[{i}:v]scale=1080:1350,pad=1080:1920:0:285:color={BG},setsar=1,fps=30,format=yuv420p[v{i}]")
    n = len(imgs)
    args += ["-f", "lavfi", "-t", str(SEC_FIRST + SEC_EACH * (n - 1)), "-i", "anullsrc=r=44100:cl=stereo"]
    filt = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    out = d / "reel.mp4"
    args += ["-filter_complex", filt, "-map", "[v]", "-map", f"{n}:a",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high",
             "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True)
    print("作った:", out, out.stat().st_size // 1024, "KB")


def wait_url(url):
    for _ in range(24):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(5)
    sys.exit(f"動画のURLが見えない: {url}")


def post(d):
    mp4 = d / "reel.mp4"
    if not mp4.exists():
        sys.exit(f"{mp4} がない(buildが先)")
    caption = add_tags((d / "caption.txt").read_text(encoding="utf-8").strip())
    repo = os.environ["GITHUB_REPOSITORY"]
    ref = os.environ.get("GITHUB_REF_NAME", "main")
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/posted/{urllib.parse.quote(d.name)}/reel.mp4"
    if os.environ.get("DRY_RUN") == "1":
        print("投稿しない(DRY_RUN):", url); print(caption); return
    wait_url(url)
    cid = call("POST", f"{IG_ID}/media", media_type="REELS", video_url=url, caption=caption,
               share_to_feed="true")["id"]
    for _ in range(60):                # 動画の処理は時間がかかる(最大10分待つ)
        st = call("GET", cid, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"リールのコンテナが {st}: {call('GET', cid, fields='status')}")
        time.sleep(10)
    else:
        sys.exit("リールの処理が終わらない")
    media_id = call("POST", f"{IG_ID}/media_publish", creation_id=cid)["id"]
    print("リールを投稿できた media_id =", media_id)
    import datetime
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": d.name, "media_id": media_id,
                            "posted_at": datetime.datetime.now(JST).isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")


def main():
    if (ROOT / "PAUSE").exists():
        print("PAUSEファイルがあるので何もしない"); return
    d = target()
    if d is None:
        print("リールにする新しい投稿はない"); return
    {"build": build, "post": post}[sys.argv[1]](d)


if __name__ == "__main__":
    main()
