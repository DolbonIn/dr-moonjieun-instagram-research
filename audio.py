"""Sound measurements per reel: raw/<acc>/video/*.mp4 -> raw/<acc>/technique/<code>.audio.json.

Voice and everything else are separated with Demucs (two stems), then compared: a steady bed under the voice is
background music, short bursts are sound effects. Speech pacing comes from the word timestamps in <code>.fw.json."""
import json, os, subprocess, sys, tempfile
import numpy as np
import soundfile as sf
import torch
import pyloudnorm as pyln
import librosa
from demucs.pretrained import get_model
from demucs.apply import apply_model

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = sys.argv[1] if len(sys.argv) > 1 else "dr.moonjieun_"
RAW = os.path.join(HERE, "raw", ACC)
VID, OUT, TR = os.path.join(RAW, "video"), os.path.join(RAW, "technique"), os.path.join(RAW, "transcripts")
os.makedirs(OUT, exist_ok=True)
only = set(sys.argv[2:])
SR = 44100
model = get_model("htdemucs").cuda().eval()
VOC = model.sources.index("vocals")


def db(x):
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-9))


def frames_db(x, hop=0.1):
    n = int(SR * hop)
    k = len(x) // n
    return np.array([db(x[i * n:(i + 1) * n]) for i in range(k)])


for name in sorted(os.listdir(VID)):
    code = name[:-4]
    if not name.endswith(".mp4") or (only and code not in only):
        continue
    wav = os.path.join(tempfile.gettempdir(), f"{code}.wav")
    subprocess.run(["ffmpeg", "-y", "-i", os.path.join(VID, name), "-ar", str(SR), "-ac", "2", wav], capture_output=True)
    x, _ = sf.read(wav, dtype="float32")
    os.remove(wav)
    mix = torch.from_numpy(x.T).unsqueeze(0).cuda()
    with torch.no_grad():
        src = apply_model(model, mix, shifts=1, split=True, overlap=0.25)[0].cpu().numpy()
    voice = src[VOC].mean(0)
    rest = np.delete(src, VOC, axis=0).sum(0).mean(0)
    mono = x.mean(1)
    lufs = float(pyln.Meter(SR).integrated_loudness(x))
    v, r = frames_db(voice), frames_db(rest)
    # the bed is "on" in a 0.1 s frame when it is louder than -50 dBFS; music stays on, effects come in bursts
    on = r > -50
    cover = float(on.mean())
    runs, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            runs.append((round(i * 0.1, 1), round(j * 0.1, 1)))
            i = j
        else:
            i += 1
    bursts = [(a, b) for a, b in runs if b - a <= 1.5]
    tempo = None
    if cover > 0.6:
        t, _ = librosa.beat.beat_track(y=rest, sr=SR)
        tempo = round(float(np.atleast_1d(t)[0]))
    # music is tonal (sustained harmonics), room tone and voice residue are not
    Hh, Pp = librosa.effects.hpss(rest)
    tonal = float(np.sum(Hh ** 2) / (np.sum(Pp ** 2) + 1e-12))
    words = []
    f = os.path.join(TR, code + ".fw.json")
    if os.path.exists(f):
        words = [w for s in json.load(open(f, encoding="utf-8"))["segments"] for w in s["words"]]
    gaps = [round(b["start"] - a["end"], 2) for a, b in zip(words, words[1:])]
    dur = len(mono) / SR
    res = {"code": code, "lufs": round(lufs, 1), "peak_db": round(float(20 * np.log10(np.abs(x).max() + 1e-9)), 1),
           "voice_db": round(db(voice), 1), "bed_db": round(db(rest), 1), "bed_minus_voice_db": round(db(rest) - db(voice), 1),
           "bed_cover": round(cover, 2), "bed_runs": len(runs), "bed_longest_s": round(max((b - a for a, b in runs), default=0), 1),
           "bursts": bursts[:60], "n_bursts": len(bursts), "tempo_bpm": tempo,
           "tonal_ratio": round(tonal, 1),
           "bgm": "likely" if cover >= 0.6 and tonal >= 8 else "unclear" if cover >= 0.6 and tonal >= 2.5 else "none",
           "first_word_s": words[0]["start"] if words else None, "last_word_end_s": words[-1]["end"] if words else None, "tail_s": round(dur - words[-1]["end"], 2) if words else None,
           "n_words": len(words), "words_per_s": round(len(words) / dur, 2), "gap_median_s": float(np.median(gaps)) if gaps else None,
           "gaps_over_0.3s": sum(g > 0.3 for g in gaps), "gap_max_s": max(gaps) if gaps else None, "speech_share": round(sum(w["end"] - w["start"] for w in words) / dur, 2)}
    json.dump(res, open(os.path.join(OUT, code + ".audio.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{code}\tLUFS {res['lufs']}\tvoice {res['voice_db']} bed {res['bed_db']} ({res['bed_minus_voice_db']})\tcover {res['bed_cover']} longest {res['bed_longest_s']}s bursts {res['n_bursts']}\tbgm={res['bgm']} tonal={res['tonal_ratio']} bpm={tempo}\tfirst word {res['first_word_s']}s tail {res['tail_s']}s gaps>0.3s {res['gaps_over_0.3s']} max {res['gap_max_s']}")
