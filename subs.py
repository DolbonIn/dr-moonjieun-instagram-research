"""Burned-in subtitle strips at 2 fps, used to check the ASR text: raw/<acc>/video/*.mp4 -> sheets/subs_<code>.jpg.
Frames are taken by seeking to the labelled time (ffmpeg's fps filter picked frames about 0.2 s late)."""
import os, sys
import cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
VID = os.path.join(HERE, "raw", ACC, "video")
SHEETS = os.path.join(HERE, "sheets")
STEP, TW, COLS, LAB = 0.5, 360, 6, 18
# the account's template keeps the spoken-line subtitle in the middle band of the frame
Y0, Y1 = 0.50, 0.70
font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 14)
os.makedirs(SHEETS, exist_ok=True)
only = set(sys.argv[2:])

for name in sorted(os.listdir(VID)):
    code = name[:-4]
    out = os.path.join(SHEETS, f"subs_{code}.jpg")
    if not name.endswith(".mp4") or (only and code not in only) or os.path.exists(out):
        continue
    cap = cv2.VideoCapture(os.path.join(VID, name))
    fps, n = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    tiles = []
    for i in range(int((n - 1) / fps / STEP) + 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(n - 1, round(i * STEP * fps)))
        ok, fr = cap.read()
        if not ok:
            break
        h, w = fr.shape[:2]
        band = cv2.resize(fr[int(Y0 * h):int(Y1 * h)], (TW, round((Y1 - Y0) * h * TW / w)), interpolation=cv2.INTER_AREA)
        tiles.append((i * STEP, Image.fromarray(cv2.cvtColor(band, cv2.COLOR_BGR2RGB))))
    cap.release()
    if not tiles:
        print(code, "no frames")
        continue
    th = tiles[0][1].height
    rows = (len(tiles) + COLS - 1) // COLS
    s = Image.new("RGB", (COLS * TW, rows * (th + LAB)), "white")
    d = ImageDraw.Draw(s)
    for i, (t, im) in enumerate(tiles):
        x, y = (i % COLS) * TW, (i // COLS) * (th + LAB)
        s.paste(im, (x, y + LAB))
        d.text((x + 4, y), f"{t:.1f}s", fill="black", font=font)
    s.save(out, quality=88)
    print(code, len(tiles), "tiles", s.size)
