"""Shooting/editing script book: measurements + visual logs + corrected transcripts -> book/<name>.html -> PDF.

Inputs per reel: raw/<acc>/technique/<code>.json (cuts, shots, zoom), <code>.audio.json (loudness, pacing),
raw/<acc>/breakdown/<code>.json (subtitle/graphics/effects/shooting log), transcripts/<code>.fw.json (+ term fixes
from annotations_<acc>.json). Part 1 (the common grammar) is book_part1.html with {placeholders} filled from the
aggregates computed here."""
import base64, csv, html, json, os, re, statistics as st, subprocess, sys
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
BOOK = os.path.join(HERE, "book")
os.makedirs(BOOK, exist_ok=True)
E = html.escape

ANN = json.load(open(os.path.join(HERE, f"annotations_{ACC}.json"), encoding="utf-8"))
posts = json.load(open(os.path.join(RAW, "posts.json"), encoding="utf-8"))
prof = json.load(open(os.path.join(RAW, "profile.json"), encoding="utf-8"))
rows = {r["code"]: r for r in csv.DictReader(open(os.path.join(HERE, f"posts_{ACC}.csv"), encoding="utf-8-sig"))}
geo_f = os.path.join(RAW, "technique", "_text_geometry.json")
GEO = json.load(open(geo_f)) if os.path.exists(geo_f) else {}
hold_f = os.path.join(RAW, "technique", "_title_hold.json")
HOLD = json.load(open(hold_f)) if os.path.exists(hold_f) else {}
# camera support judged by eye on first/last-frame overlays of the longest shot (the automatic measure is fooled by
# gesturing hands and the chair in desk shots)
HANDHELD = {"DZ4uc9OPPGq", "DZH3aSRB6Kf", "DZXPvvpP0dH", "DZpSg_iBRW4", "DaIKmAcxiek", "DbLEN_MTuHQ", "DcLi-FyzLyS"}
BGM = {"likely": "아주 작게 깔린 배경 음악이 있는 것으로 보임", "unclear": "배경음이 이어지지만 음악인지 현장음인지 불분명", "none": "배경 음악 없음(말소리만)"}


def load(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


JARGON = re.compile(r"strip|subs|cuts_|false_cuts|missed_cuts|타일|시트|shot1|zoom-vs|inlier|jump로|검출기|감지된|감지 컷|컷 목록|샷 목록|breakdown", re.I)


def clean(text, sentences=None, maxlen=None):
    """review notes for print: drop remarks about the working sheets, keep the first few sentences"""
    if not text:
        return text
    text = re.sub(r"\([^()]*\)", lambda m: "" if JARGON.search(m.group(0)) else m.group(0), str(text))
    text = re.sub(r"^\s*(편집 습관|메모)\s*[:：]\s*", "", text)
    parts = [s.strip() for s in re.split(r"(?<=\.)\s+", text) if s.strip()]
    parts = [s for s in parts if not JARGON.search(s)]
    if sentences:
        parts = parts[:sentences]
    out = " ".join(parts).strip()
    if maxlen and len(out) > maxlen:
        out = out[:maxlen].rsplit(" ", 1)[0] + "…"
    return out


def fixed_stream(words, code):
    """corrected speech as (character, time) pairs, so a term fix that straddles a cut still lands in one shot"""
    chars = [(ch, (w["start"] + w["end"]) / 2) for w in words for ch in w["word"]]
    for a, b in ANN.get(code, {}).get("fixes", []):
        text = "".join(c for c, _ in chars)
        p = text.find(a)
        while p != -1:
            chars[p:p + len(a)] = [(ch, chars[p][1]) for ch in b]
            text = "".join(c for c, _ in chars)
            p = text.find(a, p + len(b))
    return chars


def frame_b64(cap, fps, t, w=300):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, round(t * fps)))
    ok, fr = cap.read()
    if not ok:
        return None
    h = round(fr.shape[0] * w / fr.shape[1])
    ok, buf = cv2.imencode(".jpg", cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 78])
    return base64.b64encode(buf).decode()


def cut_label(c):
    if c is None:
        return "시작"
    if c.get("eye"):
        return "컷(눈으로 확인)"
    if c["kind"] == "scene":
        return "화면 전환"
    if c["kind"] == "zoom":
        p = round((c["scale"] - 1) * 100)
        return f"확대 +{p}%" if p > 0 else f"축소 −{abs(p)}%"
    return "점프컷"


def reel(p):
    code = p["code"]
    t = load(os.path.join(RAW, "technique", code + ".json"))
    au = load(os.path.join(RAW, "technique", code + ".audio.json")) or {}
    bd = load(os.path.join(RAW, "breakdown", code + ".json")) or {}
    fw = load(os.path.join(RAW, "transcripts", code + ".fw.json"))
    words = [w for s in fw["segments"] for w in s["words"]]
    false = bd.get("false_cuts") or []
    # a "cut" in the first two frames is the opening zoom ramp, not a splice
    opening = next((c for c in t["cuts"] if c["t"] < 0.2), None)
    cuts = [c for c in t["cuts"] if c["t"] >= 0.2 and not any(abs(c["t"] - f) <= 0.15 for f in false)]
    # cuts the detector missed but the frame-by-frame review found; their zoom amount was not measured
    for x in bd.get("missed_cuts") or []:
        if all(abs(c["t"] - x) > 0.3 for c in cuts) and 0.2 < x < t["duration"] - 0.2:
            cuts.append({"t": float(x), "kind": "jump", "scale": 1.0, "eye": True})
    cuts = [dict(c) for c in sorted(cuts, key=lambda c: c["t"])]
    bounds = [0.0] + [c["t"] for c in cuts] + [t["duration"]]
    stream = fixed_stream(words, code)

    def level_at(x):
        # zoom level measured directly on the detector's shots (against the first shot of the scene)
        s = next((s for s in t["shots"] if s["start"] <= x < s["end"]), t["shots"][-1])
        return s["zoom"] or 1.0

    shots = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        c = cuts[i - 1] if i else None
        level = level_at((a + b) / 2)
        if c and c["kind"] != "scene":
            ratio = level / shots[-1]["zoom"]
            c["scale"], c["kind"] = ratio, ("zoom" if abs(round((ratio - 1) * 100)) >= 3 else "jump")
        said = "".join(ch for ch, tm in stream if a <= tm < b).strip()
        shots.append({"n": i + 1, "start": a, "end": b, "dur": b - a, "cut": c, "label": cut_label(c), "zoom": level, "said": said, "subs": [], "gfx": []})

    def shot_at(x):
        return next((s for s in shots if s["start"] <= x < s["end"]), shots[-1])

    subs = bd.get("subtitle_track") or []
    for s in subs:
        # the subtitle strips were sampled about 0.2 s after their label, so a subtitle logged at t was first seen at t+0.2
        shot_at(min(t["duration"] - 0.01, s["t"] + 0.2))["subs"].append(s)
    gfx = bd.get("graphics_track") or []
    for g in gfx:
        shot_at(g["t0"])["gfx"].append(("g", g))
    for e in bd.get("effects") or []:
        shot_at(e["t0"])["gfx"].append(("e", e))
    zc = [c for c in cuts if c["kind"] == "zoom"]
    runs, run = [], 0   # staircase: consecutive zoom-ins
    for c in cuts:
        run = run + 1 if c["kind"] == "zoom" and c["scale"] > 1 else 0
        runs.append(run)
    durs = [s["dur"] for s in shots]
    r = rows[code]
    m = {
        "code": code, "p": p, "row": r, "a": ANN.get(code, {}), "t": t, "au": au, "bd": bd, "shots": shots, "cuts": cuts, "subs": subs, "gfx": gfx,
        "n_cuts": len(cuts), "asl": st.mean(durs), "shot_med": st.median(durs), "shot_max": max(durs),
        "n_jump": sum(c["kind"] == "jump" for c in cuts), "n_zoom": len(zc), "n_scene": sum(c["kind"] == "scene" for c in cuts),
        "zoom_in": sum(c["scale"] > 1 for c in zc), "zoom_out": sum(c["scale"] < 1 for c in zc),
        "zoom_med": st.median(abs(c["scale"] - 1) * 100 for c in zc) if zc else None, "zoom_max": max((abs(c["scale"] - 1) * 100 for c in zc), default=None),
        "stair": max(runs, default=0), "n_subs": len(subs), "n_gfx": len(gfx), "first_gfx": min((g["t0"] for g in gfx), default=None),
        "handheld": code in HANDHELD, "false": len(false), "geo": GEO.get(code, {}), "hold": HOLD.get(code, {}).get("title_hold_s"),
        "opening": bool(opening),
        "n_eff": len(bd.get("effects") or []), "n_styled": sum(1 for s in subs if s.get("style")),
    }
    return m


def rhythm_svg(m):
    d = m["t"]["duration"]
    X = lambda x: round(x / d * 1000, 1)
    out = ['<svg class="rhythm" viewBox="0 0 1000 104" preserveAspectRatio="none">']
    for s in m["shots"]:
        c = s["cut"]
        col = "#adb5bd" if c is None or c["kind"] == "jump" else "#e8590c" if c["kind"] == "scene" else "#0b7285" if c["scale"] > 1 else "#74b3bf"
        h = max(10, min(46, 12 + (s["zoom"] - 0.8) / 0.5 * 34))
        out.append(f'<rect x="{X(s["start"]) + 0.8}" y="{58 - h:.1f}" width="{max(1.5, X(s["dur"]) - 1.6)}" height="{h:.1f}" fill="{col}" rx="1.5"/>')
    for g in m["gfx"]:
        out.append(f'<rect x="{X(g["t0"])}" y="68" width="{max(4, X(min(d, g["t1"] + 0.5) - g["t0"]))}" height="12" fill="#f08c00" rx="2"/>')
    for s in m["subs"]:
        out.append(f'<rect x="{X(s["t"])}" y="88" width="2.2" height="12" fill="#495057"/>')
    out.append("</svg>")
    # the picture is stretched to the page width, so the time labels are laid out in HTML instead of inside it
    ticks = "".join(f'<span style="left:{k / d * 100:.2f}%">{k}초</span>' if k / d < 0.95 else f'<span style="right:0">{k}초</span>' for k in range(0, int(d) + 1, 5))
    return "".join(out) + f'<div class="axis">{ticks}</div>'


def reel_html(i, m):
    p, r, a, t, au, bd = m["p"], m["row"], m["a"], m["t"], m["au"], m["bd"]
    code = m["code"]
    cap = cv2.VideoCapture(os.path.join(RAW, "video", code + ".mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS)
    d = t["duration"]
    picks = [0.3] + sorted({round(g["t0"] + 0.3, 1) for g in m["gfx"]})[:10]
    picks += [d * k / 6 for k in range(1, 6)]
    chosen = []
    for x in sorted(picks) + [d - 0.3]:
        if 0 <= x < d and all(abs(x - y) >= d / 9 for y in chosen):
            chosen.append(x)
    chosen = sorted(chosen[:5] + [d - 0.3]) if len(chosen) > 6 else sorted(chosen)
    chosen = sorted(set(chosen))[:6]
    figs = "".join(f'<figure><img src="data:image/jpeg;base64,{frame_b64(cap, fps, x)}"><figcaption>{x:.1f}초</figcaption></figure>' for x in chosen)
    cap.release()
    sh = bd.get("shooting") or {}
    geo = m["geo"]
    like = "숨김" if r["like_hidden"] == "True" else f'{int(r["likes"]):,}'
    chips = [("조회수", f'{int(r["plays"]):,}'), ("계정 중앙값 대비", f'{float(r["multiple"]):.2f}배'), ("길이", f'{d:.1f}초'), ("좋아요", like), ("댓글", r["comments"]),
             ("주제", a.get("topic") or ""), ("형식", a.get("format") or "")]
    stats = [("컷", f'{m["n_cuts"]}개'), ("평균 샷 길이", f'{m["asl"]:.2f}초'), ("확대·축소 컷", f'{m["n_zoom"]}개' + (f' · {m["zoom_med"]:.0f}%' if m["zoom_med"] else "")),
             ("화면 자막", f'{m["n_subs"]}개' if m["n_subs"] else "—"), ("삽입 그래픽", f'{m["n_gfx"]}개' if bd else "—"),
             ("말 속도", f'{float(r["chars_per_sec"]):.1f}자/초'), ("소리 크기", f'{au.get("lufs", "—")} LUFS')]
    face = next((s for s in t["shots"] if s.get("face_h")), None)
    sh = {k: clean(v) for k, v in sh.items()}
    shoot_rows = [
        ("장소·배경", sh.get("location")), ("구도", sh.get("framing")), ("카메라", sh.get("camera")),
        ("카메라 지지", "손에 든 카메라(샷 안에서 화면이 조금씩 흔들림)" if m["handheld"] else "고정(삼각대). 샷 안에서 배경이 움직이지 않음"),
        ("얼굴 위치·크기", f'얼굴 중심이 화면 위에서 {t["face_cy_median"] * 100:.0f}% 지점, 얼굴 높이가 화면의 {t["face_h_median"] * 100:.0f}%' + (f' (샷에 따라 {t["face_h_range"][0] * 100:.0f}~{t["face_h_range"][1] * 100:.0f}%)' if t.get("face_h_range") else "") if t.get("face_h_median") else None),
        ("조명", sh.get("lighting")), ("의상·헤어", sh.get("wardrobe")), ("소품", sh.get("props")), ("마이크", sh.get("mic")), ("몸짓", sh.get("performance")),
        ("화질", f'9:16 세로, {t["fps"]:.0f}fps (게시 원본 {p.get("w")}×{p.get("h")}, 분석본 {t["width"]}×{t["height"]})'),
    ]
    titles = bd.get("title_track") or []
    hold = f'처음 {m["hold"]:.1f}초 동안 노출 후 사라짐' if m["hold"] else "끝까지 노출"
    title_txt = " → ".join((f'{x["t"]:.1f}초 ' if x["t"] else "") + (f'「{x["text"]}」' if x.get("text") and x["text"] != "(없음)" else "사라짐") for x in titles) or f'「{a.get("title_card") or ""}」'
    title_txt = f"{hold}. {title_txt}" + (f'. 모양: {clean(titles[0].get("style"), sentences=2, maxlen=150)}' if titles and titles[0].get("style") else "")
    zoom_txt = (f'{m["n_cuts"]}컷, 평균 {m["asl"]:.2f}초마다 한 번(가장 긴 샷 {m["shot_max"]:.1f}초). 같은 구도 점프컷 {m["n_jump"]}개, 확대·축소를 동반한 컷 {m["n_zoom"]}개'
                + (f'(확대 {m["zoom_in"]} · 축소 {m["zoom_out"]}, 한 번에 중앙값 {m["zoom_med"]:.0f}%, 최대 {m["zoom_max"]:.0f}%)' if m["n_zoom"] else "")
                + (f', 다른 화면으로 넘어가는 전환 {m["n_scene"]}개' if m["n_scene"] else "") + "."
                + (f' 확대가 {m["stair"]}번 연달아 이어지는 계단식 줌인 구간이 있음.' if m["stair"] >= 3 else "")
                + (" 시작하자마자 첫 2프레임 동안 화면을 조금 당기며 엶." if m["opening"] else ""))
    sub_txt = None
    if m["n_subs"]:
        styled = [s for s in m["subs"] if s.get("style")]
        sub_txt = f'{m["n_subs"]}개, 평균 {d / m["n_subs"]:.1f}초마다 교체. 강조·변형 자막 {len(styled)}개.'
        if geo.get("sub_cy"):
            sub_txt += f' 위치는 화면 위에서 {geo["sub_cy"] * 100:.0f}% 지점, 글자 높이는 화면의 {geo["sub_h"] * 100:.1f}%.'
    gfx_txt = f'{m["n_gfx"]}개' + (f', 첫 그래픽 {m["first_gfx"]:.1f}초' if m["first_gfx"] is not None else "") + "." if bd else None
    snd = f'{au.get("lufs")} LUFS. {BGM.get(au.get("bgm"), "")}' + (f'(말소리보다 {abs(au["bed_minus_voice_db"]):.0f}dB 낮음)' if au.get("bgm") in ("likely", "unclear") else "") + \
          f'. 첫 단어 {au.get("first_word_s", 0):.1f}초, 마지막 단어 뒤 {au.get("tail_s", 0):.2f}초에 끝남. 0.3초 넘는 말 사이 공백 {au.get("gaps_over_0.3s", 0)}번.' if au else None
    edit_rows = [("제목 카드", title_txt), ("컷 편집", zoom_txt), ("화면 자막", sub_txt), ("삽입 그래픽", gfx_txt), ("소리·말", snd), ("끝맺음", clean(bd.get("ending"), sentences=2)),
                 ("편집 습관", clean(bd.get("notes"), sentences=4, maxlen=420))]
    tbl = lambda rr: "".join(f"<tr><th>{E(k)}</th><td>{E(str(v))}</td></tr>" for k, v in rr if v)
    trs = []
    for s in m["shots"]:
        note = lambda v, n: clean(v, sentences=1, maxlen=n)
        subs = " <span class=\"sep\">▸</span> ".join(E(x["text"]) + (f' <span class="st">({E(note(x["style"], 46))})</span>' if x.get("style") and note(x["style"], 46) else "") for x in s["subs"])
        span = lambda x: f'{x["t0"]:.1f}초' if x["t1"] <= x["t0"] else f'{x["t0"]:.1f}~{x["t1"]:.1f}초'
        gf = "<br>".join((f'<span class="tg g">그래픽</span> {span(x)} {E(note(x["what"], 90) or clean(x["what"], maxlen=90))}' + (f' <span class="st">· {E(note(x["where"], 44))}</span>' if x.get("where") and note(x["where"], 44) else "")
                          + (f' <span class="st">· {E(note(x["how"], 56))}</span>' if x.get("how") and note(x["how"], 56) else ""))
                         if k == "g" else f'<span class="tg e">효과</span> {span(x)} {E(clean(x["what"], sentences=2, maxlen=130))}'
                         for k, x in s["gfx"] if clean(x.get("what")))
        cls = "" if s["cut"] is None else s["cut"]["kind"] + (" in" if s["cut"]["kind"] == "zoom" and s["cut"]["scale"] > 1 else "")
        trs.append(f'<tr><td class="n">{s["n"]}</td><td class="tm">{s["start"]:.1f}–{s["end"]:.1f}</td><td class="ct {cls}">{s["label"]}<br><span class="st">배율 {s["zoom"] * 100:.0f}%</span></td>'
                   f'<td class="say">{E(s["said"])}</td><td class="sub">{subs}</td><td class="gf">{gf}</td></tr>')
    cap_line = (p.get("caption") or "").replace("\n", " / ")
    return f'''
<section class="reel">
 <div class="rh"><div class="no">{i:02d}</div><div><h2>{E(a.get("title_card") or "")}</h2>
  <div class="meta">{p["posted_kst"]} 게시 · <span class="url">{E(p["url"])}</span></div></div></div>
 <div class="chips">{"".join(f"<span><b>{E(k)}</b>{E(str(v))}</span>" for k, v in chips if v)}</div>
 <div class="cap"><b>캡션</b> {E(cap_line)}</div>
 <div class="frames">{figs}</div>
 <div class="stats">{"".join(f"<div><b>{E(v)}</b><span>{E(k)}</span></div>" for k, v in stats)}</div>
 <div class="two"><div><h3>촬영</h3><table class="kv">{tbl(shoot_rows)}</table></div>
  <div><h3>편집</h3><table class="kv">{tbl(edit_rows)}</table></div></div>
 <h3>컷 리듬 <span class="lg"><i style="background:#adb5bd"></i>점프컷 <i style="background:#0b7285"></i>확대 <i style="background:#74b3bf"></i>축소 <i style="background:#e8590c"></i>화면 전환 <i style="background:#f08c00"></i>삽입 그래픽 <i style="background:#495057"></i>자막 교체 · 막대 높이 = 확대 정도</span></h3>
 {rhythm_svg(m)}
 <h3>편집 대본 <span class="lg">샷 단위. 대사는 말한 그대로, 화면 자막은 화면에 적힌 그대로</span></h3>
 <table class="tl"><thead><tr><th>#</th><th>시간(초)</th><th>컷</th><th>대사</th><th>화면 자막</th><th>그래픽·효과</th></tr></thead><tbody>{"".join(trs)}</tbody></table>
</section>'''


reels = [reel(p) for p in sorted((p for p in posts if p.get("has_video")), key=lambda p: p["taken_at"])]
med = lambda xs: st.median([x for x in xs if x is not None])
allc = [c for m in reels for c in m["cuts"]]
zc = [c for c in allc if c["kind"] == "zoom"]
done = [m for m in reels if m["bd"]]
AG = {
    "n": len(reels), "n_logged": len(done), "followers": f'{prof["followers"]:,}', "fetched": prof["fetchedAt"][:10],
    "dur_med": f'{med([m["t"]["duration"] for m in reels]):.0f}', "dur_min": f'{min(m["t"]["duration"] for m in reels):.0f}', "dur_max": f'{max(m["t"]["duration"] for m in reels):.0f}',
    "cuts_med": f'{med([m["n_cuts"] for m in reels]):.0f}', "cuts_min": min(m["n_cuts"] for m in reels), "cuts_max": max(m["n_cuts"] for m in reels),
    "asl_med": f'{med([m["asl"] for m in reels]):.2f}', "asl_min": f'{min(m["asl"] for m in reels):.2f}', "asl_max": f'{max(m["asl"] for m in reels):.2f}',
    "zoom_share": f'{len(zc) / len(allc) * 100:.0f}', "jump_share": f'{sum(c["kind"] == "jump" for c in allc) / len(allc) * 100:.0f}', "scene_share": f'{sum(c["kind"] == "scene" for c in allc) / len(allc) * 100:.0f}',
    "zoom_med": f'{st.median(abs(c["scale"] - 1) * 100 for c in zc):.0f}', "zoom_p90": f'{sorted(abs(c["scale"] - 1) * 100 for c in zc)[int(len(zc) * 0.9)]:.0f}',
    "zoom_in_share": f'{sum(c["scale"] > 1 for c in zc) / len(zc) * 100:.0f}', "stair_reels": sum(m["stair"] >= 3 for m in reels), "total_cuts": len(allc),
    "subs_med": f'{med([m["n_subs"] for m in done]):.0f}' if done else "—", "subs_int": f'{med([m["t"]["duration"] / m["n_subs"] for m in done if m["n_subs"]]):.1f}' if done else "—",
    "gfx_med": f'{med([m["n_gfx"] for m in done]):.0f}' if done else "—", "gfx_first": sum(1 for m in done if m["first_gfx"] is not None and m["first_gfx"] <= 1.0), "gfx_total": sum(m["n_gfx"] for m in done),
    "cps_med": f'{med([float(m["row"]["chars_per_sec"]) for m in reels]):.1f}', "lufs_min": min(m["au"]["lufs"] for m in reels), "lufs_max": max(m["au"]["lufs"] for m in reels),
    "tail_med": f'{med([m["au"]["tail_s"] for m in reels]):.2f}', "gaps_total": sum(m["au"]["gaps_over_0.3s"] for m in reels),
    "bgm_likely": sum(m["au"]["bgm"] == "likely" for m in reels), "bgm_unclear": sum(m["au"]["bgm"] == "unclear" for m in reels), "bgm_none": sum(m["au"]["bgm"] == "none" for m in reels),
    "handheld": sum(m["handheld"] for m in reels), "tripod": sum(not m["handheld"] for m in reels),
    "face_cy": f'{med([m["t"]["face_cy_median"] for m in reels]) * 100:.0f}', "face_h": f'{med([m["t"]["face_h_median"] for m in reels]) * 100:.0f}',
    "face_h_lo": f'{min(m["t"]["face_h_median"] for m in reels) * 100:.0f}', "face_h_hi": f'{max(m["t"]["face_h_median"] for m in reels) * 100:.0f}',
    "sub_cy": f'{med([m["geo"].get("sub_cy") for m in reels]) * 100:.0f}', "sub_h": f'{med([m["geo"].get("sub_h") for m in reels]) * 100:.1f}',
    "plays_med": f'{int(st.median(int(m["row"]["plays"]) for m in reels)):,}',
    "hold_med": f'{med([m["hold"] for m in reels]):.1f}', "hold_min": f'{min(m["hold"] for m in reels if m["hold"]):.1f}', "hold_max": f'{max(m["hold"] for m in reels if m["hold"]):.1f}',
    "hold_all": sum(1 for m in reels if not m["hold"]), "subs_total": sum(m["n_subs"] for m in done), "styled_share": f'{sum(m["n_styled"] for m in done) / max(1, sum(m["n_subs"] for m in done)) * 100:.0f}',
    "eff_total": sum(m["n_eff"] for m in done), "false_total": sum(m["false"] for m in done),
    "open_zoom": sum(1 for m in reels if m["opening"]),
}
# tallies over the visual logs: effect kinds, graphic kinds, section sub-titles
EFF = {"snap": r"스냅 줌|펀치인|순간 줌|줌인|줌 인|확대", "comp": r"배경 교체|배경이 .*바뀜|배경 .*바꿈|합성|뒤 레이어", "fade": r"페이드|디졸브|서서히", "pop": r"팝|튕김",
       "motion": r"불꽃|연기|물줄기|유리|움직이는|애니메이션|폭죽|회전|떨어|흩날|스크롤", "shift": r"재배치|밀린|밀고|분할", "list": r"한 줄씩|한 칸씩"}
GFX = {"device": r"장비|제품|약병|앰플|병 |기기|바이알|상자|튜브|크림|오일", "diagram": r"일러스트|도식|단면|다이어그램|아이콘|그림", "logo": r"로고", "capture": r"캡처|스크린|댓글|지도|쇼핑|질문 스티커",
       "emoji": r"이모지|스티커|체크", "photo": r"연예인|인물 사진|본인|여성 사진|사진", "clip": r"영상|클립"}
ec, er = {k: 0 for k in EFF}, {k: set() for k in EFF}
gc, gdur = {k: 0 for k in list(GFX) + ["other"]}, []
for m in done:
    for e in m["bd"].get("effects") or []:
        for k, pat in EFF.items():
            if re.search(pat, e["what"]):
                ec[k] += 1; er[k].add(m["code"]); break
    for g in m["gfx"]:
        gdur.append(g["t1"] - g["t0"] + 0.5)
        gc[next((k for k, pat in GFX.items() if re.search(pat, g["what"])), "other")] += 1
for k in EFF:
    AG[f"eff_{k}"], AG[f"eff_{k}_reels"] = ec[k], len(er[k])
for k, v in gc.items():
    AG[f"gfx_{k}"] = v
real = lambda x: x.get("text") and x["text"] != "(없음)"
AG["gfx_dur"] = f"{st.median(gdur):.1f}" if gdur else "—"
AG["subtitle_reels"] = sum(1 for m in done if any(real(x) and x["t"] > 0 for x in m["bd"].get("title_track") or []))
AG["subs_min"] = min((m["n_subs"] for m in done), default=0)
AG["subs_max"] = max((m["n_subs"] for m in done), default=0)
json.dump(AG, open(os.path.join(BOOK, "aggregates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

toc = "".join(f'<tr><td>{i:02d}</td><td>{m["p"]["posted_kst"][:10]}</td><td>{E(m["a"].get("title_card") or "")}</td><td class="r">{int(m["row"]["plays"]):,}</td><td class="r">{float(m["row"]["multiple"]):.2f}배</td>'
              f'<td class="r">{m["t"]["duration"]:.0f}초</td><td class="r">{m["n_cuts"]}</td><td class="r">{m["asl"]:.2f}초</td><td class="r">{m["n_zoom"]}</td><td class="r">{m["n_subs"] or "—"}</td><td class="r">{m["n_gfx"] if m["bd"] else "—"}</td>'
              f'<td>{"손" if m["handheld"] else "고정"}</td></tr>' for i, m in enumerate(reels, 1))
part1 = open(os.path.join(HERE, "book_part1.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "book_part1.html")) else "<section><h1>공통 문법</h1><p>(작성 중)</p></section>"
body_f = os.path.join(HERE, "book_part1_body.html")
part1 = part1.replace("{part1_body}", open(body_f, encoding="utf-8").read() if os.path.exists(body_f) else "")
for k, v in AG.items():
    part1 = part1.replace("{" + k + "}", str(v))
part1 = part1.replace("{toc}", toc)


def thumb(path_or_cap, t=None, w=150):
    if t is None:
        im = cv2.imdecode(np.fromfile(path_or_cap, dtype=np.uint8), cv2.IMREAD_COLOR)   # cv2.imread cannot open non-ASCII paths on Windows
        h = round(im.shape[0] * w / im.shape[1])
        return base64.b64encode(cv2.imencode(".jpg", cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 76])[1]).decode()
    cap = cv2.VideoCapture(path_or_cap)
    b = frame_b64(cap, cap.get(cv2.CAP_PROP_FPS), t, w)
    cap.release()
    return b


part1 = part1.replace("{covergrid}", "".join(f'<img src="data:image/jpeg;base64,{thumb(os.path.join(RAW, "video", m["code"] + ".mp4"), 0.3)}">' for m in reels))
part3 = open(os.path.join(HERE, "book_part3.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "book_part3.html")) else ""
# the confirmed photo post: first four slides only (the fifth is a photo of a booking screen)
car = next((p for p in posts if p.get("product_type") == "carousel_container"), None)
if car:
    slides = [os.path.join(RAW, "media", f"{car['code']}_{k:02d}.jpg") for k in range(1, 5)]
    part3 = part3.replace("{carousel}", "".join(f'<img src="data:image/jpeg;base64,{thumb(s, w=220)}">' for s in slides if os.path.exists(s)))
css = open(os.path.join(HERE, "book.css"), encoding="utf-8").read()
doc = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>@{ACC} 릴스 촬영·편집 대본집</title><style>{css}</style></head><body>{part1}{"".join(reel_html(i, m) for i, m in enumerate(reels, 1))}{part3}</body></html>'
out_html = os.path.join(BOOK, f"촬영편집_대본집_{ACC}.html")
open(out_html, "w", encoding="utf-8").write(doc)
out_pdf = os.path.join(HERE, f"촬영편집_대본집_{ACC}.pdf")
print(json.dumps(AG, ensure_ascii=False))
print("reels", len(reels), "with visual log", len(done), "| html", round(os.path.getsize(out_html) / 1e6, 1), "MB")
if "--no-pdf" not in sys.argv:
    subprocess.run(["node", os.path.join(HERE, "render_pdf.mjs"), out_html, out_pdf, f"@{ACC} 릴스 촬영·편집 대본집 · 내부 분석용"], check=True)
