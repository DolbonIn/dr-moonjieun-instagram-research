"""Per-reel frames, contact sheet and Korean transcript: raw/<acc>/video/*.mp4 -> raw/<acc>/{frames,transcripts}/ + sheets/reel_<code>.jpg."""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
VID, FR, TR = (os.path.join(RAW, d) for d in ("video", "frames", "transcripts"))
SHEETS = os.path.join(HERE, "sheets")
WHISPER = os.path.expandvars(r"%USERPROFILE%\.local\whisper.cpp\Release\whisper-cli.exe")
MODEL = os.path.expandvars(r"%USERPROFILE%\.cache\whisper.cpp\ggml-large-v3-turbo-q5_0.bin")
# vocabulary hint only; whisper drifts if the prompt reads like a sentence it could continue
PROMPT = "피부과, 시술, 필러, 보톡스, 스킨부스터, 울쎄라, 써마지, 리프팅, 탈모, 흉터, 지방분해, 오블리브"
font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 18)
for d in (FR, TR, SHEETS):
    os.makedirs(d, exist_ok=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(mp4):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", mp4]).stdout
    return float(json.loads(out)["format"]["duration"])


def sheet(code, mp4, dur, cols=6, tw=360, th=640, lab=26):
    # first row is the hook (0-3s plus two more), second row walks the rest of the reel
    rest = [round(5 + (dur - 5.3) * i / 6, 1) for i in range(1, 7)] if dur > 8 else []
    times = [t for t in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0] + rest if t < dur - 0.1]
    rows = (len(times) + cols - 1) // cols
    s = Image.new("RGB", (cols * tw, rows * (th + lab)), "white")
    d = ImageDraw.Draw(s)
    for i, t in enumerate(times):
        f = os.path.join(FR, f"{code}_{t:05.1f}.jpg")
        if not os.path.exists(f):
            run(["ffmpeg", "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=decrease", "-q:v", "3", f])
        x, y = (i % cols) * tw, (i // cols) * (th + lab)
        try:
            im = Image.open(f).convert("RGB")
            s.paste(im, (x + (tw - im.width) // 2, y + lab))
        except Exception:
            pass
        d.text((x + 6, y + 2), f"{t:.1f}s", fill="black", font=font)
    s.save(os.path.join(SHEETS, f"reel_{code}.jpg"), quality=88)


def transcribe(code, mp4):
    base = os.path.join(TR, code)
    if os.path.exists(base + ".json"):
        return
    wav = base + ".wav"
    run(["ffmpeg", "-y", "-i", mp4, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
    r = run([WHISPER, "-m", MODEL, "-f", wav, "-l", "ko", "--prompt", PROMPT, "-osrt", "-otxt", "-oj", "-of", base])
    if not os.path.exists(base + ".json"):
        print("  whisper failed:", (r.stderr or r.stdout)[-400:])
    if os.path.exists(wav):
        os.remove(wav)


only = set(sys.argv[2:])
for name in sorted(os.listdir(VID)):
    code = name[:-4]
    if not name.endswith(".mp4") or (only and code not in only):
        continue
    mp4 = os.path.join(VID, name)
    dur = probe(mp4)
    if not os.path.exists(os.path.join(SHEETS, f"reel_{code}.jpg")):
        sheet(code, mp4, dur)
    transcribe(code, mp4)
    txt = os.path.join(TR, code + ".txt")
    # whisper.cpp can split a multi-byte character across tokens, leaving invalid UTF-8 in its output
    n = len(open(txt, encoding="utf-8", errors="replace").read()) if os.path.exists(txt) else 0
    print(f"{code}\t{dur:.1f}s\ttranscript_chars={n}")
