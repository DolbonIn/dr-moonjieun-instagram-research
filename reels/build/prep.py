"""원본 촬영본 준비: Drive 다운로드 → 오디오 → 받아쓰기(단어 시각) → 쉼 지점 → 프레임 시트.

python prep.py <작업폴더> <이름>=<Drive 파일 ID> [...]
결과: <작업폴더>/footage/<이름>.mp4, tr/<이름>.json(단어), tr/<이름>.sil(쉼), frames/<이름>.jpg(6장 시트)
"""
import json, os, subprocess, sys

PROMPT = ("피부과, 시술, 리프팅, 울쎄라, 써마지, 쎄르프, 슈링크, 온다, 티타늄, 포텐자, 피코토닝, 제네시스, "
          "스킨부스터, 리쥬란, 쥬베룩, 리투오, 스컬트라, 스킨바이브, 물광주사, 필러, 톡신, 에티튜드")


def sh(*a, **k):
    return subprocess.run(a, check=True, **k)


def main():
    root, pairs = sys.argv[1], [p.split("=", 1) for p in sys.argv[2:]]
    for d in ("footage", "tr", "frames"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    todo = []
    for name, fid in pairs:
        mp4 = os.path.join(root, "footage", name + ".mp4")
        if not os.path.exists(mp4) or os.path.getsize(mp4) < 1_000_000:
            sh("curl", "-sSL", "--retry", "4", "-o", mp4,
               f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t")
        if os.path.getsize(mp4) < 1_000_000:
            print(name, "다운로드 실패(공유 권한 확인)"); continue
        wav = os.path.join(root, "tr", name + ".wav")
        sh("ffmpeg", "-v", "error", "-y", "-i", mp4, "-vn", "-ac", "1", "-ar", "16000", wav)
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                                 capture_output=True, text=True).stdout)
        sh("ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", f"fps=6/{d},scale=240:-2,tile=6x1", "-frames:v", "1",
           os.path.join(root, "frames", name + ".jpg"))
        r = subprocess.run(["ffmpeg", "-i", wav, "-af", "silencedetect=noise=-38dB:d=0.1", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        st = [float(l.split("silence_start: ")[1].split()[0]) for l in r.splitlines() if "silence_start" in l]
        en = [float(l.split("silence_end: ")[1].split()[0]) for l in r.splitlines() if "silence_end" in l]
        open(os.path.join(root, "tr", name + ".sil"), "w").write("".join(f"{a} {b}\n" for a, b in zip(st, en)))
        todo.append((name, wav, d))
    if not todo:
        return
    from faster_whisper import WhisperModel
    m = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=os.cpu_count())
    for name, wav, d in todo:
        out = os.path.join(root, "tr", name + ".json")
        if os.path.exists(out):
            continue
        segs, _ = m.transcribe(wav, language="ko", beam_size=5, word_timestamps=True, initial_prompt=PROMPT,
                               condition_on_previous_text=False, vad_filter=True)
        rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                 "words": [{"s": round(w.start, 2), "e": round(w.end, 2), "w": w.word.strip()} for w in s.words]}
                for s in segs]
        json.dump(rows, open(out, "w"), ensure_ascii=False, indent=1)
        print(f"== {name} ({d:.1f}s)")
        for r_ in rows:
            print(f"  {r_['start']:6.2f}-{r_['end']:6.2f} {r_['text']}")


if __name__ == "__main__":
    main()
