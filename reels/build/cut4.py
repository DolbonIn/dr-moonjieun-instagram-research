import subprocess, json, os
S=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(S,'..','footage','jm3.mp4')
F=json.load(open(f'{S}/faces.json'))
ZOOMS=[1.24,1.32]          # 컷마다 약 6.5%만 교대, 컷 없는 곳에서는 배율 고정
os.makedirs(f'{S}/seg4',exist_ok=True)
files=[];plan=[];T=0
for i,(a,b,fx,fy,fh) in enumerate(F):
    z=ZOOMS[i%2]; w=int(1620/z)//2*2; h=int(2880/z)//2*2
    x=int(max(0,min(2160-w,fx-w/2))); y=int(max(0,min(3840-h,fy-0.40*h)))   # 얼굴 중심을 매 컷 같은 자리(가로 50%, 위 40%)에
    d=b-a
    vf=f"crop={w}:{h}:{x}:{y},scale=1080:1920:flags=lanczos,fps=30,eq=contrast=1.04:saturation=1.05:brightness=0.012,unsharp=5:5:0.4,format=yuv420p"
    af=f"afade=t=in:d=0.015,afade=t=out:st={d-0.025:.3f}:d=0.025,aresample=48000"
    f=f"{S}/seg4/{i:02d}_{a:.2f}_{b:.2f}_{z}.mov"
    if not os.path.exists(f):
        subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{a}','-t',f'{d:.3f}','-i',SRC,'-vf',vf,'-af',af,'-ac','2',
          '-c:v','libx264','-crf','14','-preset','medium','-c:a','pcm_s16le',f],check=True)
    files.append(f); plan.append({'t0':round(T,3),'t1':round(T+d,3),'z':z}); T+=d
open(f'{S}/seg4/list.txt','w').write(''.join(f"file '{p}'\n" for p in files))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',f'{S}/seg4/list.txt','-c','copy',f'{S}/cut4.mov'],check=True)
json.dump({'shots':plan,'total':round(T,3)},open(f'{S}/cut4.json','w'))
print(len(plan),'shots total',round(T,2))
