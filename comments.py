"""Public comment previews found in the saved post-page JSON: raw/<acc>/json/<code>.json -> raw/<acc>/comments.json (text only, no usernames)."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)


def walk(o, out):
    if isinstance(o, dict):
        if isinstance(o.get("text"), str) and isinstance(o.get("user"), dict) and ("comment_like_count" in o or "child_comment_count" in o):
            out[str(o.get("pk"))] = {"text": o["text"], "likes": o.get("comment_like_count"), "replies": o.get("child_comment_count"),
                                     "by_owner": o["user"].get("username") == ACC, "at": o.get("created_at")}
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for x in o:
            walk(x, out)


res = {}
for f in sorted(os.listdir(os.path.join(RAW, "json"))):
    if f.startswith("_"):
        continue
    out = {}
    walk(json.load(open(os.path.join(RAW, "json", f), encoding="utf-8")), out)
    res[f[:-5]] = sorted(out.values(), key=lambda c: -(c["likes"] or 0))
    print(f[:-5], len(out))
json.dump(res, open(os.path.join(RAW, "comments.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
