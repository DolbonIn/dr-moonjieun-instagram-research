"""영상별 오버레이 명세(spec.json, 원본 시각) + 컷 목록(<cut>.json) + 컷별 내림 값 → tpl.html 이 읽는 data.json

python build_data.py spec.json cut.mov.json shotoff.json > data.json
spec = {"HEAD": [[s0, s1, html], ...], "SUB": [[s0, s1, line, ...], ...], "GFX": [[s0, s1, "=face(['jaw'])"], ...], "TITLE_TOP": 205}
시각 자리에 "END"를 쓰면 영상 끝.
"""
import json, sys
spec, cut, off = (json.load(open(p)) for p in sys.argv[1:4])
spec["SHOTS"] = cut["shots"]; spec["END"] = cut["total"]; spec["SHOTOFF"] = off
print(json.dumps(spec, ensure_ascii=False))
