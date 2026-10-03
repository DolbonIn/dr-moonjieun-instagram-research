"""오버레이가 얼굴을 가리는지, 인스타그램 UI 영역에 들어가는지 모든 프레임에서 검사.

python qa.py <합성 전 영상.mov> <오버레이 PNG 폴더>
얼굴 = 얼굴 검출 상자에 좌우 10px, 위 15px, 아래 40px(턱)을 더한 영역. 하단 UI = y>=1632, 오른쪽 버튼 = x>=960 & 1150<=y<1700.
"""
import json, subprocess, sys
import cv2, numpy as np

W, H = 1080, 1920
CAS = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def facemap(video):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", "fps=4,scale=540:960", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         stdout=subprocess.PIPE)
    rows, i = [], 0
    while len(b := p.stdout.read(540 * 960)) == 540 * 960:
        f = CAS.detectMultiScale(np.frombuffer(b, np.uint8).reshape(960, 540), 1.08, 6, minSize=(80, 80))
        if len(f):
            x, y, w, h = max(f, key=lambda r: r[2] * r[3]); rows.append((i / 4, x * 2, y * 2, w * 2, h * 2))
        i += 1
    med = np.median([r[2] + r[4] for r in rows])
    return [r for r in rows if r[2] + r[4] < med + 60]       # 손·옷깃 오검출 제거


def main():
    video, od = sys.argv[1], sys.argv[2]
    faces = facemap(video)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-framerate", "30", "-i", f"{od}/%05d.png", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                         stdout=subprocess.PIPE)
    bad, ui, right, low, i = [], 0, 0, 0, 0
    while len(b := p.stdout.read(W * H * 4)) == W * H * 4:
        a = np.frombuffer(b, np.uint8).reshape(H, W, 4)[:, :, 3] > 60
        t = i / 30; _, x, y, w, h = min(faces, key=lambda r: abs(r[0] - t))
        n = int(a[max(0, y - 15):y + h + 40, max(0, x - 10):x + w + 10].sum())
        if n: bad.append((round(t, 2), n))
        ui += bool(a[1632:].any()); right += bool(a[1150:1700, 960:].any())
        ys = np.where(a.any(axis=1))[0]; low = max(low, int(ys.max()) if len(ys) else 0); i += 1
    print(json.dumps({"frames": i, "face_overlap_frames": len(bad), "first": bad[:5], "bottom_ui_frames": ui,
                      "right_button_frames": right, "lowest_overlay_y": low,
                      "face_bottom_p95": int(np.percentile([r[2] + r[4] for r in faces], 95))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
