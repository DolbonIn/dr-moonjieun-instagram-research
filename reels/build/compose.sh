#!/bin/bash
# 합성: 컷 영상 + 오버레이 PNG → 업로드용 mp4
# compose.sh <컷.mov> <오버레이 폴더> <길이 초> <출력.mp4> [쿠션 흐림 시작 초(없으면 -)] [첫 화면 밀어 넣기 초(없으면 0)]
# - 첫 화면 밀어 넣기: 0초에 108%에서 시작해 지정한 시간 동안 100%로(첫 프레임부터 화면이 움직이게)
# - 소리: 고역 통과 → 약한 압축 → -14 LUFS → 리미터 (잡음 제거는 약한 자음을 깎아서 쓰지 않음)
set -e
IN=$1; OV=$2; DUR=$3; OUT=$4; CBT=${5:--}; PUSH=${6:-0}
VF="setsar=1"
if [ "$PUSH" != "0" ]; then
  Z="if(lt(t\,$PUSH)\,1.08-0.08*t/$PUSH\,1)"
  VF="scale=w='trunc(1080*$Z/2)*2':h='trunc(1920*$Z/2)*2':eval=frame:flags=lanczos,crop=1080:1920:'(iw-1080)/2':'(ih-1920)*0.40',setsar=1"
fi
if [ "$CBT" != "-" ]; then
  VF="$VF,split[m][c];[c]crop=230:380:0:1540,gblur=sigma=22,format=yuva420p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='255*clip(min((W-X)/60\,Y/60)\,0\,1)'[cb];[m][cb]overlay=0:1540:enable='gte(t,$CBT)'"
fi
ffmpeg -v error -y -i "$IN" -framerate 30 -i "$OV/%05d.png" -filter_complex \
 "[0:v]$VF[b];[b][1:v]overlay=eof_action=pass,format=yuv420p,trim=duration=$DUR[v];[0:a]highpass=f=80,acompressor=threshold=-22dB:ratio=2:attack=10:release=150,loudnorm=I=-14:TP=-2:LRA=9,volume=0.6dB,alimiter=limit=0.79:level=false,aresample=48000,atrim=duration=$DUR[a]" \
 -map "[v]" -map "[a]" -c:v libx264 -profile:v high -preset slow -crf 19 -r 30 -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
 -c:a aac -b:a 192k -movflags +faststart "$OUT"
ffmpeg -i "$OUT" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|Peak):" | tail -2
