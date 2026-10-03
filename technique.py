"""Shot/edit measurements per reel: raw/<acc>/video/*.mp4 -> raw/<acc>/technique/<code>.json + sheets/cuts_<code>.jpg.

Every frame is registered to the previous one on background features taken from the outer edges of the frame
(titles, subtitles, overlays, the speaker and her chair sit in the middle). A cut is either a one-frame spike of
change around the speaker's head (jump cut on the same framing) or a jump of that background transform
(punch in/out, reframe, cutaway). What is left inside a shot is camera movement or an animated zoom."""
import json, os, subprocess, sys
import cv2
import numpy as np
import skimage
from skimage.feature import Cascade
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
VID, OUT, SHEETS = os.path.join(RAW, "video"), os.path.join(RAW, "technique"), os.path.join(HERE, "sheets")
os.makedirs(OUT, exist_ok=True)
font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 15)
only = set(sys.argv[2:])
W, H = 270, 480          # change-detection size
RW, RH = 540, 960        # registration size; shifts are reported in 1080-wide pixels (x2)
# OpenCV 5 ships no cascade classifier; scikit-image bundles an LBP frontal-face cascade and its own detector
faces = Cascade(os.path.join(os.path.dirname(skimage.__file__), "data", "lbpcascade_frontalface_opencv.xml"))


def probe(mp4):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", mp4], capture_output=True, text=True, encoding="utf-8")
    j = json.loads(r.stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    num, den = (int(x) for x in v["avg_frame_rate"].split("/"))
    return {"width": v["width"], "height": v["height"], "fps": round(num / den, 2), "vcodec": v["codec_name"], "v_kbps": round(int(v.get("bit_rate", 0)) / 1000),
            "acodec": a.get("codec_name"), "a_hz": int(a.get("sample_rate", 0) or 0), "a_ch": a.get("channels"), "a_kbps": round(int(a.get("bit_rate", 0) or 0) / 1000),
            "duration": round(float(j["format"]["duration"]), 2), "size_mb": round(int(j["format"]["size"]) / 1e6, 1)}


def bg_masks(h, w):
    # two background samples: beside the head, and the outer edges. Either can be polluted (chair back beside the
    # head, gesturing hands at the edges), so camera movement is read from whichever moves less.
    a = np.zeros((h, w), np.uint8)
    a[int(.27 * h):int(.52 * h), :int(.28 * w)] = 255
    a[int(.27 * h):int(.52 * h), int(.72 * w):] = 255
    b = np.zeros((h, w), np.uint8)
    b[int(.03 * h):int(.97 * h), :int(.14 * w)] = 255
    b[int(.03 * h):int(.97 * h), int(.86 * w):] = 255
    b[:int(.09 * h), :] = 255
    return a, b


orb = cv2.ORB_create(1500)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def transform(fa, fb):
    """similarity transform a -> b from background features: (scale, dx, dy, inliers) or None"""
    (pa, da), (pb, db) = fa, fb
    if da is None or db is None or len(pa) < 12 or len(pb) < 12:
        return None
    m = bf.match(da, db)
    if len(m) < 12:
        return None
    a = np.float32([pa[x.queryIdx] for x in m]); b = np.float32([pb[x.trainIdx] for x in m])
    M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if M is None or inl is None or int(inl.sum()) < 10:
        return None
    return float(np.hypot(M[0, 0], M[1, 0])), float(M[0, 2]), float(M[1, 2]), int(inl.sum())


def face_at(cap, f):
    """largest face in the speaker zone of frame f -> (center y, box height, center x) as fractions, or None"""
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ok, fr = cap.read()
    if not ok:
        return None
    rgb = cv2.cvtColor(cv2.resize(fr, (W, H)), cv2.COLOR_BGR2RGB)
    det = faces.detect_multi_scale(img=rgb, scale_factor=1.15, step_ratio=1, min_size=(24, 24), max_size=(200, 200))
    det = [b for b in det if .2 < (b["r"] + b["height"] / 2) / H < .62 and .25 < (b["c"] + b["width"] / 2) / W < .75]
    if not det:
        return None
    b = max(det, key=lambda b: b["width"] * b["height"])
    return round((b["r"] + b["height"] / 2) / H, 3), round(b["height"] / H, 3), round((b["c"] + b["width"] / 2) / W, 3)


def analyse(code, mp4):
    info = probe(mp4)
    cap = cv2.VideoCapture(mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or info["fps"]
    masks = bg_masks(RH, RW)
    feats, dface, dfull, prev = ([], []), [0.0], [0.0], None
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g2 = cv2.cvtColor(cv2.resize(fr, (RW, RH), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g2, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
        if prev is not None:
            d = np.abs(g - prev)
            dface.append(float(d[int(.27 * H):int(.50 * H), int(.32 * W):int(.68 * W)].mean())); dfull.append(float(d.mean()))
        prev = g
        for fl, m in zip(feats, masks):
            kp, de = orb.detectAndCompute(g2, m)
            fl.append((np.float32([k.pt for k in kp]), de))
    n = len(feats[0])
    dface, dfull = np.array(dface), np.array(dfull)
    TT = [[None] + [transform(fl[i - 1], fl[i]) for i in range(1, n)] for fl in feats]
    # per frame, the better-supported of the two background transforms
    T = [max((t for t in (TT[0][i], TT[1][i]) if t), key=lambda t: t[3], default=None) for i in range(n)]
    tracked = sum(t is not None for t in T[1:]) / max(1, n - 1)
    sc = np.array([abs(t[0] - 1) if t else np.nan for t in T])
    shifts = [np.array([np.hypot(t[1], t[2]) if t else np.nan for t in tt]) for tt in TT]
    cuts = []
    for t in range(2, n - 1):
        lo, hi = max(1, t - 15), min(n, t + 16)
        base = np.median(np.delete(dface[lo:hi], t - lo)); basef = np.median(np.delete(dfull[lo:hi], t - lo))
        strong = dface[t] > max(4.0 * base, 6.0) or dfull[t] > max(5.0 * basef, 9.0)
        # a cut always moves the speaker; a background scale jump alone only lowers the bar (hands at the frame edge fake shifts)
        weak = dface[t] > max(2.2 * base, 3.0) and T[t] is not None and sc[t] >= 0.015
        # a punch-in made while she holds still: both background samples jump in scale by the same amount in one frame
        a_, b_ = TT[0][t], TT[1][t]
        weak = weak or bool(a_ and b_ and abs(a_[0] - 1) >= 0.02 and abs(b_[0] - 1) >= 0.02 and (a_[0] - 1) * (b_[0] - 1) > 0 and abs(a_[0] - b_[0]) < 0.02)
        if (strong or weak) and (not cuts or t - cuts[-1] > 3):
            cuts.append(t)
    bounds = [0] + cuts + [n]
    mids = [(a + b) // 2 for a, b in zip(bounds, bounds[1:])]

    def reg(i, j):
        """best-supported background transform from frame i to frame j over both samples"""
        return max((t for t in (transform(fl[i], fl[j]) for fl in feats) if t), key=lambda t: t[3], default=None)

    # zoom level of every shot against the first shot of its scene, measured on the shots' middle frames.
    # (Measuring only across the cut frame misses the two-frame zoom ramps that often follow a cut.)
    levels, scene_of, refs = [1.0], [0], [0]
    for k in range(1, len(mids)):
        got = None
        for r in refs:
            d = reg(mids[r], mids[k])
            if d and d[3] >= 15:
                got = (r, d[0]); break
        if got:
            levels.append(round(got[1], 3)); scene_of.append(got[0])
        else:
            w = reg(bounds[k] - 1, min(bounds[k] + 2, bounds[k + 1] - 1))
            if w:      # no reference reachable: chain from the previous shot
                levels.append(round(levels[-1] * w[0], 3)); scene_of.append(scene_of[-1])
            else:      # unrelated picture: this shot starts a scene of its own
                levels.append(1.0); scene_of.append(k); refs.append(k)
    out_cuts = []
    for k, t in enumerate(cuts, 1):
        tr = T[t]
        ratio = None if scene_of[k] != scene_of[k - 1] else levels[k] / levels[k - 1]
        kind = "scene" if ratio is None else "zoom" if abs(ratio - 1) >= 0.025 else "jump"
        out_cuts.append({"t": round(t / fps, 2), "frame": t, "kind": kind, "scale": round(ratio, 3) if ratio else None,
                         "shift_px": round(float(np.hypot(tr[1], tr[2])) * 2, 1) if tr else None, "inliers": tr[3] if tr else 0,
                         "dface": round(float(dface[t]), 1), "dfull": round(float(dfull[t]), 1)})
    shots = []
    for k, (a, b) in enumerate(zip(bounds, bounds[1:])):
        level = levels[k]
        # camera movement inside the shot = the calmer of the two background samples
        cand = []
        for fl, sh in zip(feats, shifts):
            steps = sh[a + 1:b]; steps = steps[np.isfinite(steps)]
            dd = transform(fl[a], fl[b - 1]) if b - a >= 6 else None
            if dd is not None and len(steps):
                cand.append((float(np.median(steps)) * 2, dd))
        if cand:
            step_px, d = min(cand, key=lambda c: c[0] + np.hypot(c[1][1], c[1][2]) / 10)
            zoomed = all(abs(c[1][0] - 1) >= 0.025 for c in cand)
            motion = "zoom_anim" if zoomed else "handheld" if step_px >= 0.5 or np.hypot(d[1], d[2]) * 2 >= 12 else "static"
        else:
            step_px, d, motion = None, None, "unknown"
        f = face_at(cap, (a + b) // 2)
        shots.append({"start": round(a / fps, 2), "end": round(b / fps, 2), "dur": round((b - a) / fps, 2), "zoom": level, "new_scene": k > 0 and out_cuts[k - 1]["kind"] == "scene",
                      "motion": motion, "in_shot_scale": round(d[0], 3) if d else None, "step_px": round(step_px, 2) if step_px is not None else None,
                      "net_px": round(float(np.hypot(d[1], d[2])) * 2, 1) if d else None,
                      "face_cy": f[0] if f else None, "face_h": f[1] if f else None, "face_cx": f[2] if f else None})
    durs = [s["dur"] for s in shots]
    tot = sum(durs)
    fh = [s["face_h"] for s in shots if s["face_h"]]; fy = [s["face_cy"] for s in shots if s["face_cy"]]
    zs = [c["scale"] for c in out_cuts if c["kind"] == "zoom"]
    res = {"code": code, **info, "frames": n, "bg_tracked": round(tracked, 2), "cuts": out_cuts, "shots": shots, "n_cuts": len(cuts), "n_shots": len(shots),
           "asl": round(float(np.mean(durs)), 2), "shot_median": round(float(np.median(durs)), 2), "shot_min": min(durs), "shot_max": max(durs),
           "kinds": {k: sum(1 for c in out_cuts if c["kind"] == k) for k in ("jump", "zoom", "scene")},
           "zoom_in": sum(1 for z in zs if z > 1), "zoom_out": sum(1 for z in zs if z < 1), "zoom_step_median_pct": round(float(np.median([abs(z - 1) for z in zs])) * 100, 1) if zs else None,
           "zoom_step_max_pct": round(max(abs(z - 1) for z in zs) * 100, 1) if zs else None, "zoom_range": [min(s["zoom"] for s in shots), max(s["zoom"] for s in shots)],
           "motion_share": {m: round(sum(s["dur"] for s in shots if s["motion"] == m) / tot, 2) for m in ("static", "handheld", "zoom_anim", "unknown")},
           "step_px_median": round(float(np.median([s["step_px"] for s in shots if s["step_px"] is not None] or [0])), 2),
           "face_shots": len(fh), "face_h_median": round(float(np.median(fh)), 3) if fh else None, "face_h_range": [min(fh), max(fh)] if fh else None,
           "face_cy_median": round(float(np.median(fy)), 3) if fy else None}
    json.dump(res, open(os.path.join(OUT, code + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if cuts:  # cut sheet: frame before | frame after, for checking the detector by eye
        cols, tw, th, lab = 6, 180, 320, 20
        rows = (len(cuts) + cols - 1) // cols
        s = Image.new("RGB", (cols * tw * 2 + (cols - 1) * 8, rows * (th + lab)), "white")
        dr = ImageDraw.Draw(s)
        for k, c in enumerate(out_cuts):
            x, y = (k % cols) * (tw * 2 + 8), (k // cols) * (th + lab)
            for j, fno in enumerate((c["frame"] - 1, c["frame"])):
                cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
                ok, fr = cap.read()
                if ok:
                    s.paste(Image.fromarray(cv2.cvtColor(cv2.resize(fr, (tw, th)), cv2.COLOR_BGR2RGB)), (x + j * tw, y + lab))
            dr.text((x + 3, y), f"{c['t']:.2f}s {c['kind']} {c['scale'] or ''}", fill="black", font=font)
        s.save(os.path.join(SHEETS, f"cuts_{code}.jpg"), quality=85)
    cap.release()
    return res


for name in sorted(os.listdir(VID)):
    code = name[:-4]
    if not name.endswith(".mp4") or (only and code not in only):
        continue
    r = analyse(code, os.path.join(VID, name))
    print(f"{code}\t{r['duration']}s\tcuts={r['n_cuts']} {r['kinds']}\tASL={r['asl']}\tzoom in/out={r['zoom_in']}/{r['zoom_out']} step={r['zoom_step_median_pct']}% max={r['zoom_step_max_pct']}% range={r['zoom_range']}\tmotion={r['motion_share']} step={r['step_px_median']}px\tface h={r['face_h_median']} {r['face_h_range']} cy={r['face_cy_median']} ({r['face_shots']}/{r['n_shots']})\ttracked={r['bg_tracked']}")
