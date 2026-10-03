"""편집 계획(JSON)대로 자르고 붙이기. 컷마다 얼굴을 찾아 얼굴 중심을 늘 같은 자리(가로 50%, 위 40%)에 둔다.

python cut.py plan.json
plan = {"src": "footage/x.mp4", "out": "x_cut.mov", "sil": "tr/x.sil",
        "segs": [[in, out], ...],          # 쓸 구간(원본 초)
        "zooms": [1.24, 1.32],             # 컷마다 번갈아 쓸 배율(원본 9:16 4K 기준, 1.0 = 화면의 75% 높이)
        "face_y": 0.40,                    # (선택) 얼굴 중심을 둘 높이(위에서 비율)
        "cover": [[x, y, w, h, "0x111111"]],  # (선택) 원본 좌표에서 칠해 가릴 사각형
        "zoom_list": [...]}                # (선택) 컷별 배율을 직접 지정. 원본이 이어지는 곳은 같은 배율로 두면 화면이 바뀌지 않음
segs 안의 0.22초 넘는 쉼은 자동으로 걷어 내고, 그 자리가 컷이 된다. 결과 옆에 <out>.json(컷 목록) 저장.
"""
import json, os, subprocess, sys
import cv2, numpy as np

CAS = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def probe(src):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,color_transfer:stream_side_data=rotation", "-of", "json", src],
                       capture_output=True, text=True).stdout
    s = json.loads(o)["streams"][0]
    w, h = s["width"], s["height"]
    rot = any(abs(int(d.get("rotation", 0))) == 90 for d in s.get("side_data_list", []))
    return ((h, w) if rot else (w, h)), s.get("color_transfer", "")


# 휴대폰 HDR(HLG·PQ) 원본은 SDR BT.709로 톤매핑해서 내보낸다(태그만 HDR로 남으면 앱마다 색이 다르게 보임)
def tonemap(trc):
    if trc not in ("arib-std-b67", "smpte2084"):
        return ""
    return (f"zscale=t=linear:npl=203:tin={trc}:pin=bt2020:min=bt2020nc,format=gbrpf32le,"
            "tonemap=tonemap=mobius:desat=0,zscale=t=bt709:p=bt709:m=bt709:r=tv,")


def gray(src, t, W, H):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-vf", f"scale={W//4}:{H//4}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H // 4, W // 4)


def face_at(src, a, b, W, H):
    pts = []
    for k in range(5):
        g = gray(src, a + (b - a) * (k + .5) / 5, W, H)
        f = CAS.detectMultiScale(g, 1.1, 6, minSize=(W // 40, W // 40))
        if len(f):
            x, y, w, h = max(f, key=lambda r: r[2] * r[3]); pts.append((x + w / 2, y + h / 2, h))
    return (np.median(np.array(pts), axis=0) * 4).tolist() if pts else None


def main():
    plan = json.load(open(sys.argv[1])); base = os.path.dirname(os.path.abspath(sys.argv[1]))
    P = lambda p: os.path.join(base, p)
    src = P(plan["src"]); (W, H), trc = probe(src)
    sil = [tuple(map(float, l.split())) for l in open(P(plan["sil"]))] if plan.get("sil") else []
    pieces = []
    for a, b in plan["segs"]:
        cur = a
        for s, e in sil:
            if s > cur + .85 and e < b - .85 and e - s >= .22:
                pieces.append([cur, s + .12]); cur = e - .05
        pieces.append([cur, b])
    zooms = plan.get("zooms", [1.24, 1.32]); cw0, ch0 = W * .75, H * .75
    tmp = P(plan["out"] + ".parts"); os.makedirs(tmp, exist_ok=True)
    last = None; prev = (0, 0, 0, -9); files = []; shots = []; T = 0
    for i, (a, b) in enumerate(pieces):
        f = face_at(src, a, b, W, H) or last or [W / 2, H * .38, H * .14]; last = f
        z = plan["zoom_list"][i] if "zoom_list" in plan else zooms[i % len(zooms)]
        w = int(cw0 / z) // 2 * 2; h = int(ch0 / z) // 2 * 2
        x = int(max(0, min(W - w, f[0] - w / 2))); y = int(max(0, min(H - h, f[1] - plan.get("face_y", .40) * h)))
        # 숨 한 번 걷어 낸 정도(0.3초 미만)로 이어지는 같은 배율 컷은 직전 화면 위치를 그대로 써서 튀지 않게
        if i and z == prev[0] and 0 <= a - prev[3] < .3:
            x, y = prev[1], prev[2]
        prev = (z, x, y, b)
        d = b - a
        # cover: 원본 좌표 [x, y, w, h, 색] 사각형을 칠해 화면에 걸린 상표 등을 가림(삼각대 고정 촬영 기준)
        cov = "".join(f"drawbox=x={c[0]}:y={c[1]}:w={c[2]}:h={c[3]}:color={c[4]}:t=fill," for c in plan.get("cover", []))
        vf = (f"{cov}crop={w}:{h}:{x}:{y},scale=1080:1920:flags=lanczos,fps=30,{tonemap(trc)}"
              "eq=contrast=1.03:saturation=1.03,unsharp=5:5:0.4,format=yuv420p")
        af = f"afade=t=in:d=0.015,afade=t=out:st={d - .025:.3f}:d=0.025,aresample=48000"
        part = os.path.join(tmp, f"{i:02d}_{a:.2f}_{b:.2f}_{z}_{x}_{y}.mov")
        if not os.path.exists(part):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a}", "-t", f"{d:.3f}", "-i", src, "-vf", vf, "-af", af, "-ac", "2",
                            "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-colorspace", "bt709", "-c:a", "pcm_s16le", part], check=True)
        files.append(part); shots.append({"t0": round(T, 3), "t1": round(T + d, 3), "src": [round(a, 3), round(b, 3)], "z": z}); T += d
    lst = os.path.join(tmp, "list.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in files))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", P(plan["out"])], check=True)
    json.dump({"shots": shots, "total": round(T, 3)}, open(P(plan["out"]) + ".json", "w"), indent=0)
    print(len(shots), "shots", round(T, 2), "s")


if __name__ == "__main__":
    main()
