"""Digest of the per-reel visual logs (raw/<acc>/breakdown/*.json) for writing the common-grammar chapter."""
import json, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
B = os.path.join(HERE, "raw", ACC, "breakdown")
what = sys.argv[2] if len(sys.argv) > 2 else "all"
files = sorted(f for f in os.listdir(B) if f.endswith(".json"))
print(len(files), "logs")
for f in files:
    try:
        d = json.load(open(os.path.join(B, f), encoding="utf-8"))
    except Exception as e:
        print("BAD JSON", f, e); continue
    code = f[:-5]
    subs, gfx, eff = d.get("subtitle_track", []), d.get("graphics_track", []), d.get("effects", [])
    if what in ("all", "counts"):
        print(f"{code}\tsubs={len(subs)} styled={sum(1 for s in subs if s.get('style'))}\tgfx={len(gfx)}\teff={len(eff)}\ttitles={len(d.get('title_track', []))}\tfalse={d.get('false_cuts')}\tmissed={d.get('missed_cuts')}")
    if what in ("all", "shooting"):
        for k, v in (d.get("shooting") or {}).items():
            print(f"  {code} {k}: {v}")
    if what in ("all", "titles"):
        for t in d.get("title_track", []):
            print(f"  {code} title {t.get('t')}: {t.get('text')} | {t.get('style')}")
    if what in ("all", "effects"):
        for e in eff:
            print(f"  {code} effect {e.get('t0')}-{e.get('t1')}: {e.get('what')}")
    if what in ("all", "gfx"):
        for g in gfx:
            print(f"  {code} gfx {g.get('t0')}-{g.get('t1')}: {g.get('what')} | {g.get('where')} | {g.get('how')}")
    if what in ("all", "styles"):
        for s in subs:
            if s.get("style"):
                print(f"  {code} sub {s.get('t')}: {s.get('text')} | {s.get('style')}")
    if what in ("all", "ending"):
        print(f"  {code} ending: {d.get('ending')}")
        print(f"  {code} notes: {d.get('notes')}")
