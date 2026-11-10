"""specs/*.json から 1080x1350 のカルーセル画像(JPEG)と caption.txt を作り、queue/<日付>/ に置く。
使い方: python make_carousel.py specs/2026-11-11.json [--out _preview]
タイトル・本文の記法:  [[ピンクの下線]]  {{赤字}}
検査(1つでも不合格なら何も置かない): 文字のはみ出し / 個人名(private/ng_names.txt) / 名義 / 枚数 / キャプションの長さ"""
import json, re, sys, html, shutil, argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
W, H = 1080, 1350
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@500;700;900&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{width:1080px;height:1350px;font-family:'Zen Maru Gothic',sans-serif;color:#1f2a44;
 background-color:#fcfdfe;
 background-image:linear-gradient(#d3e0ea 1px,transparent 1px),linear-gradient(90deg,#d3e0ea 1px,transparent 1px);
 background-size:54px 54px;position:relative;overflow:hidden}
#safe{position:absolute;left:96px;right:96px;top:120px;bottom:190px;display:flex;flex-direction:column;justify-content:center}
.kicker{color:#d0392b;font-weight:700;font-size:34px;letter-spacing:.06em;margin-bottom:44px}
.bar{width:120px;height:10px;border-radius:5px;background:#d0392b;margin-bottom:56px}
.title{font-weight:900;font-size:var(--ts);line-height:1.42;letter-spacing:.04em}
.title div{white-space:nowrap;width:max-content}
.body{margin-top:60px;font-weight:500;font-size:44px;line-height:1.85;letter-spacing:.03em}
.body div{white-space:nowrap;width:max-content}
.mk{background:linear-gradient(transparent 58%,#fad7d4 58%)}
.rd{color:#d0392b}
#foot{position:absolute;left:96px;right:70px;bottom:52px;display:flex;justify-content:space-between;
 font-size:26px;font-weight:500;color:#5a6478;letter-spacing:.04em}
"""


def mark(s):
    s = html.escape(s)
    s = re.sub(r"\[\[(.+?)\]\]", r'<span class="mk">\1</span>', s)
    return re.sub(r"\{\{(.+?)\}\}", r'<span class="rd">\1</span>', s)


def page(sl, i, n, account, tag):
    title = sl["title"]
    longest = max(len(re.sub(r"\[\[|\]\]|\{\{|\}\}", "", t)) for t in title)
    ts = sl.get("size") or (96 if longest <= 8 else 84 if longest <= 10 else 72 if longest <= 12 else 62)
    p = []
    if sl.get("kicker"): p.append(f'<div class="kicker">{mark(sl["kicker"])}</div>')
    if sl.get("bar"): p.append('<div class="bar"></div>')
    p.append(f'<div class="title" style="--ts:{ts}px">' + "".join(f"<div>{mark(t)}</div>" for t in title) + "</div>")
    if sl.get("body"):
        p.append('<div class="body">' + "".join(f"<div>{mark(t)}</div>" for t in sl["body"]) + "</div>")
    return (f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><body><div id="safe">{"".join(p)}</div>'
            f'<div id="foot"><span>{account}　{tag}</span><span>{i} / {n}</span></div></body>')


def ng_hits(text):
    f = ROOT / "private" / "ng_names.txt"
    hits = []
    if not f.exists():
        return ["private/ng_names.txt がない(個人名検査ができない)"]
    for line in f.read_text(encoding="utf-8").splitlines():
        w = line.strip()
        if not w or w.startswith("#"):
            continue
        if w.startswith("~"):          # かなの短い名前: 敬称つき、または前後がかなでないときだけ
            w = w[1:]
            if re.search(rf"{re.escape(w)}(くん|君|さん|ちゃん)", text) or \
               re.search(rf"(?<![ぁ-んァ-ヶー]){re.escape(w)}(?![ぁ-んァ-ヶー])", text):
                hits.append(w)
        elif w in text:
            hits.append(w)
    return hits


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("--out", default="queue")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    slides, caption = spec["slides"], spec["caption"].strip()
    account, tag = spec.get("account", "@manabirador"), spec.get("tag", "中学受験算数")
    errs = []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", spec["date"]): errs.append("dateは YYYY-MM-DD")
    if not 2 <= len(slides) <= 10: errs.append(f"枚数 {len(slides)} (2〜10枚)")
    if len(caption) > 2000: errs.append(f"キャプション {len(caption)}字 (2000字まで)")
    if caption.count("#") > 20: errs.append("ハッシュタグは20個まで")
    alltext = caption + "\n" + json.dumps(slides, ensure_ascii=False)
    for w in ("吉行", "元八塾", "ヒロユキ"):
        if w in alltext: errs.append(f"名義の決まりに反する語: {w}")
    hits = ng_hits(alltext)
    if hits: errs.append("個人名の疑い: " + "、".join(hits))

    tmp = ROOT / "_preview" / ("_tmp_" + spec["date"]); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": W, "height": H})
        for i, sl in enumerate(slides, 1):
            pg.set_content(page(sl, i, len(slides), account, tag), wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            if not pg.evaluate("document.fonts.check(\"900 40px 'Zen Maru Gothic'\")"):
                errs.append("フォント Zen Maru Gothic が読みこめていない")
            over = pg.evaluate("""() => {const s=document.getElementById('safe').getBoundingClientRect();
              return [...document.querySelectorAll('#safe div')].filter(e=>{const r=e.getBoundingClientRect();
              return r.right>s.right+1||r.left<s.left-1||r.top<s.top-1||r.bottom>s.bottom+1}).map(e=>e.textContent.slice(0,20))}""")
            if over: errs.append(f"{i}枚目 はみ出し: {over}")
            pg.screenshot(path=str(tmp / f"{i:02d}.jpg"), type="jpeg", quality=92)
        b.close()
    if errs:
        shutil.rmtree(tmp, ignore_errors=True)
        print("不合格:"); [print("  -", e) for e in dict.fromkeys(errs)]; sys.exit(1)
    out = ROOT / a.out / spec["date"]; shutil.rmtree(out, ignore_errors=True); out.parent.mkdir(exist_ok=True)
    shutil.move(str(tmp), str(out))
    (out / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    print(f"合格: {out} に {len(slides)}枚 / 個人名チェック：済")


if __name__ == "__main__":
    main()
