"""posts.json + transcripts + annotations_<acc>.json -> posts_<acc>.csv, stats_<acc>.json, sheets/{hooks,ends}_<acc>.jpg and the script document."""
import csv, json, os, re, statistics as st, sys
from collections import defaultdict
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
SHEETS = os.path.join(HERE, "sheets")
font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 15)
TYPE = {"clips": "REEL", "carousel_container": "CAR", "feed": "IMG"}
DOW = "월화수목금토일"

posts = json.load(open(os.path.join(RAW, "posts.json"), encoding="utf-8"))
prof = json.load(open(os.path.join(RAW, "profile.json"), encoding="utf-8"))
ann_file = os.path.join(HERE, f"annotations_{ACC}.json")
ANN = json.load(open(ann_file, encoding="utf-8")) if os.path.exists(ann_file) else {}
hooks_file = os.path.expanduser("~/.claude/skills/ig-reel/hooks.json")
HOOKS = {h["id"]: h["name"] for h in json.load(open(hooks_file, encoding="utf-8"))["hooks"]} if os.path.exists(hooks_file) else {}
fetched = datetime.fromisoformat(prof["fetchedAt"].replace("Z", "+00:00")).timestamp()


def fixed(text, code):
    # term-level corrections read off the burned-in subtitles (annotations: fixes = [[heard, shown], ...])
    for a, b in ANN.get(code, {}).get("fixes", []):
        text = text.replace(a, b)
    return text


def transcript(code):
    f = os.path.join(RAW, "transcripts", code + ".fw.json")
    if not os.path.exists(f):
        return None
    t = json.load(open(f, encoding="utf-8"))
    t["segments"] = [s for s in t["segments"] if len(s["text"].strip()) > 1]  # a one-syllable segment is a breath or a cut-off sound
    whole = " ".join(s["text"] for s in t["segments"])
    for a, _ in ANN.get(code, {}).get("fixes", []):
        if not any(a in s["text"] for s in t["segments"]):
            print(f"WARN {code}: fix '{a}' {'spans two segments' if a in whole else 'not found'}")
    for s in t["segments"]:
        s["text"] = fixed(s["text"], code)
    return t


def hook3(t, limit=3.2):
    # what is said in the first three seconds; the cut is moved so a corrected term is never split
    words = [w for s in t["segments"] for w in s["words"]]
    full = "".join(w["word"] for w in words)
    cut = len("".join(w["word"] for w in words if w["end"] <= limit))
    for a, b in ANN.get(t["code"], {}).get("fixes", []):
        p = full.find(a)
        while p != -1:
            if p + len(a) <= cut:
                cut += len(b) - len(a)
            elif p < cut:
                cut = p + len(b)
            full = full[:p] + b + full[p + len(a):]
            p = full.find(a, p + len(b))
    return full[:cut].strip()


plays = [p["play_count"] for p in posts if p.get("play_count")]
med = st.median(plays) if plays else None
rows, T = [], {}
for p in posts:
    t = T[p["code"]] = transcript(p["code"]) if p.get("has_video") else None
    text = " ".join(s["text"] for s in t["segments"]) if t else ""
    cap = p.get("caption") or ""
    dt = datetime.fromtimestamp(p["taken_at"] + 9 * 3600, timezone.utc) if p.get("taken_at") else None
    a = ANN.get(p["code"], {})
    pc, dur = p.get("play_count"), p.get("duration")
    rows.append({
        "code": p["code"], "posted_kst": p.get("posted_kst"), "dow": DOW[dt.weekday()] if dt else None, "hour": dt.hour if dt else None,
        "age_days": round((fetched - p["taken_at"]) / 86400, 1) if p.get("taken_at") else None,
        "type": TYPE.get(p.get("product_type"), p.get("product_type")), "slides": p.get("slides"), "duration": dur,
        "plays": pc, "multiple": round(pc / med, 2) if pc and med else None,
        "likes": None if p.get("like_hidden") else p.get("like_count"), "like_hidden": p.get("like_hidden"),
        "comments": p.get("comment_count"), "comments_per_10k": round(p["comment_count"] / pc * 10000, 1) if pc and p.get("comment_count") is not None else None,
        "like_rate_pct": round(p["like_count"] / pc * 100, 2) if pc and p.get("like_count") and not p.get("like_hidden") else None,
        "pinned": bool(p.get("pinned") or p.get("pinned_reels")),
        "topic": a.get("topic"), "format": a.get("format"), "hook_id": a.get("hook_id"), "hook_name": HOOKS.get(a.get("hook_id")),
        "title_card": a.get("title_card"), "hook_3s": hook3(t) if t else None,
        "chars_per_sec": round(len(re.sub(r"\s", "", text)) / dur, 1) if t and dur else None,
        "setting": a.get("setting"), "cta": a.get("cta"),
        "caption": cap, "cap_len": len(cap), "hashtags": " ".join(re.findall(r"#\w+", cap)), "url": p.get("url"),
    })
with open(os.path.join(HERE, f"posts_{ACC}.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

reels = [r for r in rows if r["plays"]]


def group(key, rs=reels):
    g = defaultdict(list)
    for r in rs:
        g[key(r)].append(r)
    return {str(k): {"n": len(v), "median_multiple": round(st.median(x["multiple"] for x in v), 2), "mean_multiple": round(st.mean(x["multiple"] for x in v), 2),
                     "min": min(x["multiple"] for x in v), "max": max(x["multiple"] for x in v), "codes": [x["code"] for x in v]} for k, v in sorted(g.items(), key=lambda kv: -st.median(x["multiple"] for x in kv[1]))}


bucket = lambda d: "<15s" if d < 15 else "15-30s" if d < 30 else "30-40s" if d < 40 else ">40s"
ts = sorted(p["taken_at"] for p in posts if p.get("product_type") == "clips")
stats = {
    "account": ACC, "fetched": prof["fetchedAt"], "followers": prof.get("followers"), "posts_collected": len(posts), "reels": len(reels),
    "median_plays": med, "mean_plays": round(st.mean(plays)), "min_plays": min(plays), "max_plays": max(plays), "total_plays": sum(plays),
    "median_over_followers": round(med / prof["followers"], 1) if prof.get("followers") else None,
    "first_reel": min(r["posted_kst"] for r in reels), "last_reel": max(r["posted_kst"] for r in reels),
    "reels_per_week": round(len(ts) / ((ts[-1] - ts[0]) / 86400) * 7, 2),
    "gaps_days": sorted(((round((b - a) / 86400, 1)) for a, b in zip(ts, ts[1:])), reverse=True)[:5],
    "likes_hidden": sum(1 for r in reels if r["like_hidden"]), "like_rate_median_pct": st.median(r["like_rate_pct"] for r in reels if r["like_rate_pct"]),
    "comments_per_10k_median": st.median(r["comments_per_10k"] for r in reels),
    "duration_median": st.median(r["duration"] for r in reels), "chars_per_sec_median": st.median(r["chars_per_sec"] for r in reels),
    "upload_hours": sorted({r["hour"] for r in reels}), "hashtags_median": st.median(len(r["hashtags"].split()) for r in reels), "cap_len_median": st.median(r["cap_len"] for r in reels),
    "by_topic": group(lambda r: r["topic"]), "by_format": group(lambda r: (r["format"] or "").split("(")[0]), "by_hook": group(lambda r: f"{r['hook_id']} {r['hook_name']}"),
    "by_duration": group(lambda r: bucket(r["duration"])), "by_dow": group(lambda r: r["dow"]), "by_month": group(lambda r: r["posted_kst"][:7]),
    "by_like_hidden": group(lambda r: "hidden" if r["like_hidden"] else "shown"),
}
json.dump(stats, open(os.path.join(HERE, f"stats_{ACC}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def tile(path, size):
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return Image.new("RGB", size, "#ddd")
    im.thumbnail(size, Image.LANCZOS)
    bg = Image.new("RGB", size, "white")
    bg.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return bg


def frame_sheet(which, out, cols=6, cw=360, ch=640, lab=40):
    fdir = os.path.join(RAW, "frames")
    have = [r for r in rows if os.path.isdir(fdir) and any(f.startswith(r["code"] + "_") for f in os.listdir(fdir))]
    if not have:
        return
    s = Image.new("RGB", (cols * cw, ((len(have) + cols - 1) // cols) * (ch + lab)), "white")
    d = ImageDraw.Draw(s)
    for i, r in enumerate(have):
        fs = sorted(f for f in os.listdir(fdir) if f.startswith(r["code"] + "_"))
        x, y = (i % cols) * cw, (i // cols) * (ch + lab)
        s.paste(tile(os.path.join(fdir, fs[0] if which == "first" else fs[-1]), (cw - 4, ch - 4)), (x + 2, y + lab))
        d.text((x + 4, y + 2), f"{(r['posted_kst'] or '')[2:10]} {r['code']}", fill="black", font=font)
        d.text((x + 4, y + 20), f"{(r['plays'] or 0) / 10000:.1f}만 x{r['multiple']} {r['duration']}s 댓글{r['comments']}", fill="#555", font=font)
    s.save(out, quality=86)


os.makedirs(SHEETS, exist_ok=True)
frame_sheet("first", os.path.join(SHEETS, f"hooks_{ACC}.jpg"))
frame_sheet("last", os.path.join(SHEETS, f"ends_{ACC}.jpg"))

# script document: machine transcript (faster-whisper large-v3) with subtitle-checked term fixes
first_line = lambda c: c.splitlines()[0] if c else ""
n_video = sum(1 for p in posts if p.get("has_video"))
L = [f"# @{ACC} 릴스 대본 ({n_video}개)", "",
     f"- 수집일 {prof.get('fetchedAt', '')[:10]} · 팔로워 {prof.get('followers'):,} · 릴스 조회수 중앙값 {int(med):,}",
     f"- 이 계정의 영상은 릴스 {n_video}개가 전부입니다(릴스 탭을 끝까지 확인). 프로필에 표시된 게시물 수와의 차이는 사진·캐러셀 게시물이며, 그쪽은 대본이 없습니다.",
     "- 만든 방법: 음성 인식(faster-whisper large-v3)으로 받아쓴 뒤, 0.5초 간격으로 뽑은 화면 자막과 대조해 잘못 들린 단어(시술명·브랜드명·숫자 등)만 고쳤습니다. 화면 자막은 말을 줄여 쓴 것이라, 자막에 없는 조사·어미는 받아쓴 그대로입니다.",
     "- `[화면]`은 말하지 않고 화면에만 나온 글자, 앞의 숫자는 시작 시각(초)입니다.",
     "- 내부 분석용입니다. 외부로 옮기거나 그대로 가져다 쓰지 않습니다.", "",
     "| # | 날짜 | 조회수 | 배수 | 길이 | 제목 카드 | 캡션 첫 줄 |", "|---|---|---|---|---|---|---|"]
for i, r in enumerate(rows, 1):
    L.append(f"| {i} | {(r['posted_kst'] or '')[:10]} | {r['plays']:,} | x{r['multiple']} | {r['duration']}s | {r['title_card'] or ''} | {first_line(r['caption'])} |" if r["plays"]
             else f"| {i} | {(r['posted_kst'] or '')[:10]} | — | — | {r['type']} {r['slides']}장 | — | {first_line(r['caption'])} |")
for i, r in enumerate(rows, 1):
    p = next(x for x in posts if x["code"] == r["code"])
    a = ANN.get(r["code"], {})
    L += ["", "---", "", f"## {i}. {(r['posted_kst'] or '')[:10]} · {a.get('title_card') or first_line(r['caption']) or r['code']}", "",
          f"- 링크: {r['url']}",
          f"- 형식: {r['type']}" + (f" · {r['duration']}초 · {a.get('format') or ''}" if r["duration"] else f" · {r['slides']}장"),
          (f"- 조회수 {r['plays']:,} (계정 중앙값의 {r['multiple']}배)" + (" · 릴스 탭 고정" if p.get("pinned_reels") else "")) if r["plays"] else "- 조회수: 릴스 아님",
          f"- 좋아요 {'숨김' if r['like_hidden'] else r['likes']} · 댓글 {r['comments']}",
          f"- 캡션: {r['caption'].replace(chr(10), ' / ')}"]
    if a.get("title_card"):
        L.append(f"- [화면] 제목 카드: {a['title_card']}")
    t = T.get(r["code"])
    if t:
        L += ["", "**대본**", ""] + [f"- `{s['start']:04.1f}` {s['text']}" for s in t["segments"]]
    elif r["type"] == "REEL":
        L += ["", "(영상 파일 없음)"]
    else:
        L += ["", "(영상이 아닌 게시물이라 대본이 없습니다.)"]
    if a.get("onscreen"):
        L += ["", "**[화면] 말 없이 화면에만 나온 것**", ""] + [f"- {x}" for x in a["onscreen"]]
    if a.get("uncertain"):
        L += ["", "**확인 못 한 부분**", ""] + [f"- {x}" for x in a["uncertain"]]
open(os.path.join(HERE, f"대본_{ACC}.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

print(f"posts={len(rows)} reels={len(reels)} median={med} mean={stats['mean_plays']} total={stats['total_plays']}")
for r in sorted(reels, key=lambda r: -r["multiple"]):
    print(f"{r['multiple']}\t{r['plays']}\t{r['duration']}\t{r['comments']}\t{r['comments_per_10k']}\t{r['like_rate_pct']}\t{r['dow']}{r['hour']}\t{r['age_days']}\t{r['code']}\t{r['topic']}\t{r['hook_id']}\t{r['title_card']}")
for k in ("by_topic", "by_format", "by_hook", "by_duration", "by_dow", "by_month", "by_like_hidden"):
    print(k, {g: (v["n"], v["median_multiple"], v["mean_multiple"]) for g, v in stats[k].items()})
print({k: stats[k] for k in ("reels_per_week", "gaps_days", "likes_hidden", "like_rate_median_pct", "comments_per_10k_median", "duration_median", "chars_per_sec_median", "upload_hours", "hashtags_median", "cap_len_median", "median_over_followers")})
