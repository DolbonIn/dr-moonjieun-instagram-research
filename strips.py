"""Full-frame filmstrips at 2 fps for logging graphics and effects: raw/<acc>/video/*.mp4 -> sheets/strip_<code>_<n>.jpg.
A red bar on a tile's left edge means a detected cut fell in the half second before it (technique/<code>.json)."""
import json, os, sys
import cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
VID, SHEETS = os.path.join(RAW, "video"), os.path.join(HERE, "sheets")
font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 15)
only = set(sys.argv[2:])
COLS, TW, TH, LAB, PER = 10, 216, 384, 18, 60

for name in sorted(os.listdir(VID)):
    code = name[:-4]
    if not name.endswith(".mp4") or (only and code not in only):
        continue
    tf = os.path.join(RAW, "technique", code + ".json")
    cuts = [c["t"] for c in json.load(open(tf, encoding="utf-8"))["cuts"]] if os.path.exists(tf) else []
    cap = cv2.VideoCapture(os.path.join(VID, name))
    fps, n = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    times = [i * 0.5 for i in range(int((n - 1) / fps / 0.5) + 1)]
    pages = [times[i:i + PER] for i in range(0, len(times), PER)]
    for pi, page in enumerate(pages, 1):
        rows = (len(page) + COLS - 1) // COLS
        s = Image.new("RGB", (COLS * TW, rows * (TH + LAB)), "white")
        d = ImageDraw.Draw(s)
        for k, t in enumerate(page):
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(n - 1, round(t * fps)))
            ok, fr = cap.read()
            x, y = (k % COLS) * TW, (k // COLS) * (TH + LAB)
            if ok:
                s.paste(Image.fromarray(cv2.cvtColor(cv2.resize(fr, (TW, TH), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)), (x, y + LAB))
            cut = any(t - 0.5 < c <= t for c in cuts)
            d.text((x + (10 if cut else 3), y), f"{t:.1f}s" + (" ✂" if cut else ""), fill="red" if cut else "black", font=font)
            if cut:
                d.rectangle([x, y + LAB, x + 5, y + LAB + TH], fill="red")
        s.save(os.path.join(SHEETS, f"strip_{code}_{pi}.jpg"), quality=86)
    cap.release()
    print(code, len(times), "tiles", len(pages), "page(s)")
