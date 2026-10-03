"""Per-reel text sheet for the visual logging pass: what is already measured (shots, cuts, zoom, speech per shot)
so the reviewer only has to add what can only be seen. raw/<acc>/breakdown_in/<code>.txt"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
OUT = os.path.join(RAW, "breakdown_in")
os.makedirs(OUT, exist_ok=True); os.makedirs(os.path.join(RAW, "breakdown"), exist_ok=True)
ANN = json.load(open(os.path.join(HERE, f"annotations_{ACC}.json"), encoding="utf-8"))
posts = {p["code"]: p for p in json.load(open(os.path.join(RAW, "posts.json"), encoding="utf-8"))}


def fixed(text, code):
    for a, b in ANN.get(code, {}).get("fixes", []):
        text = text.replace(a, b)
    return text


for f in sorted(os.listdir(os.path.join(RAW, "technique"))):
    if not f.endswith(".json") or f.endswith(".audio.json"):
        continue
    code = f[:-5]
    t = json.load(open(os.path.join(RAW, "technique", f), encoding="utf-8"))
    fw = json.load(open(os.path.join(RAW, "transcripts", code + ".fw.json"), encoding="utf-8"))
    words = [w for s in fw["segments"] for w in s["words"]]
    a = ANN.get(code, {})
    L = [f"code: {code}", f"posted: {posts[code]['posted_kst']} KST   duration: {t['duration']}s   {t['width']}x{t['height']} {t['fps']}fps",
         f"title card (already read): {a.get('title_card')}", f"caption: {(posts[code].get('caption') or '').splitlines()[0]}",
         f"already noted on-screen items: {' | '.join(a.get('onscreen', []))}", "",
         f"detected cuts: {t['n_cuts']}  (jump = same framing, zoom = scale change at the cut, scene = unrelated picture)", "",
         "shot  start-end(s)   cut-in        zoom-vs-shot1  speech in this shot"]
    for i, s in enumerate(t["shots"]):
        c = t["cuts"][i - 1] if i else None
        cut = "start" if not c else f"{c['kind']}" + (f" x{c['scale']:.2f}" if c["scale"] and c["kind"] == "zoom" else "")
        said = fixed("".join(w["word"] for w in words if s["start"] <= (w["start"] + w["end"]) / 2 < s["end"]).strip(), code)
        L.append(f"{i + 1:>3}  {s['start']:>5.2f}-{s['end']:<5.2f}  {cut:<12}  {('%.2f' % s['zoom']) if s['zoom'] else '-':<6}  {said}")
    open(os.path.join(OUT, code + ".txt"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(code, len(t["shots"]), "shots")
