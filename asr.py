"""Second-opinion transcript with faster-whisper large-v3 (word timestamps): raw/<acc>/video/*.mp4 -> raw/<acc>/transcripts/<code>.fw.json."""
import json, os, sys
from faster_whisper import WhisperModel

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
VID, TR = os.path.join(RAW, "video"), os.path.join(RAW, "transcripts")
PROMPT = "피부과, 시술, 필러, 보톡스, 스킨부스터, 울쎄라, 써마지, 리프팅, 탈모, 흉터, 지방분해, 오블리브"
os.makedirs(TR, exist_ok=True)
only = set(sys.argv[2:])

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
for name in sorted(os.listdir(VID)):
    code = name[:-4]
    out = os.path.join(TR, code + ".fw.json")
    if not name.endswith(".mp4") or (only and code not in only) or os.path.exists(out):
        continue
    segs, info = model.transcribe(os.path.join(VID, name), language="ko", beam_size=5, word_timestamps=True, initial_prompt=PROMPT, condition_on_previous_text=False)
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
             "words": [{"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word} for w in (s.words or [])]} for s in segs]
    json.dump({"code": code, "duration": round(info.duration, 2), "segments": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(code, f"{info.duration:.1f}s", " ".join(r["text"] for r in rows)[:90])
