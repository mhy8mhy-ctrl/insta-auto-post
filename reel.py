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


NOON_MIN_QUEUE = 4   # 昼の枠は、明日以降の在庫がこれ以上あるときだけ出す


def target():
    if os.environ.get("REEL_SLOT") == "noon":
        # 昼の枠(2026-11-12 フォロワー1,000人の施策):queue/ の一番先の日付を先にリールで出す。
        # 在庫が少ない日は出さない(夜のカルーセル・朝のリールの分を食わないため)
        import datetime
        today = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        done = done_days()
        future = sorted(p for p in (ROOT / "queue").iterdir() if p.is_dir() and p.name[:10] > today)
        if len(future) < NOON_MIN_QUEUE:
            return None
        cand = [p for p in future if p.name not in done]
        return cand[-1] if cand else None
    days = sorted(p for p in (ROOT / "posted").iterdir() if p.is_dir() and not p.name.endswith("-reel"))
    if not days:
        return None
    d = days[-1]                       # 一番新しい投稿だけ。古い日はさかのぼらない
    return None if d.name in done_days() else d


def build(d):
    imgs = sorted(d.glob("*.jpg"))
    if not imgs:
        sys.exit(f"{d.name} に画像がない")
    end = ROOT / "assets" / "end_card.jpg"   # 最後にフォローを呼びかける1枚(2026-11-13 追加、見た人をプロフィールへ)
    if end.exists():
        imgs.append(end)
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
    rel = d.relative_to(ROOT).as_posix()          # posted/日付 または queue/日付(昼の枠)
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{urllib.parse.quote(rel)}/reel.mp4"
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
    if d.parent.name == "queue":       # 昼の枠はリール専用。カルーセルには回さず posted/日付-reel へ移す
        import shutil
        shutil.move(str(d), str(ROOT / "posted" / (datetime.datetime.now(JST).strftime("%Y-%m-%d") + "-reel")))


def recently_posted(minutes):
    """直近 minutes 分にリールを出していれば True(予備の予約で二重に出さないため)"""
    import datetime
    if not LOG.exists():
        return False
    lines = [l for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return False
    last = datetime.datetime.fromisoformat(json.loads(lines[-1])["posted_at"])
    return datetime.datetime.now(JST) - last < datetime.timedelta(minutes=minutes)


def main():
    if (ROOT / "PAUSE").exists():
        print("PAUSEファイルがあるので何もしない"); return
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and recently_posted(90):
        print("直近90分にリールを出したので、今回は何もしない"); return
    d = target()
    if d is None:
        print("リールにする新しい投稿はない"); return
    {"build": build, "post": post}[sys.argv[1]](d)


if __name__ == "__main__":
    main()
