"""컷별 얼굴 아래끝(턱) 최댓값 → 자막·그래픽을 그 컷 동안 얼마나 내릴지(px).

python shotface.py <합성 전 영상.mov> <컷 목록 .json> <자막 top px> > shotoff.json
"""
import json, sys
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from qa import facemap

video, shots, top = sys.argv[1], json.load(open(sys.argv[2]))["shots"], int(sys.argv[3])
faces = facemap(video)
out = []
for s in shots:
    b = [r[2] + r[4] for r in faces if s["t0"] <= r[0] < s["t1"]]
    m = max(b) if b else int(np.percentile([r[2] + r[4] for r in faces], 95))
    out.append([s["t0"], s["t1"], int(max(0, m + 40 - top))])
print(json.dumps(out))
