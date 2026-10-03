import subprocess, json, os, math
S=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(S,'..','footage','jm3.mp4')
SEGS=[(1.50,4.30),(4.75,9.80),(15.88,21.85),(22.48,26.85),(27.50,33.48),(33.48,38.42),(40.28,45.06),(46.90,51.05),(51.60,52.85),(54.15,57.66),(58.12,61.04),(62.35,67.08),(67.95,73.06)]
sil=[tuple(map(float,l.split())) for l in open(f'{S}/sil.txt')]
pieces=[];marks=[]   # pieces: contiguous audio; marks: zoom-change times (source)
for a,b in SEGS:
    cur=a
    for s,e in sil:
        if s>cur+0.85 and e<b-0.85:
            if e-s>=0.22: pieces.append([cur,s+0.12]); cur=e-0.05
            else: marks.append((s+e)/2)
    pieces.append([cur,b])
ZOOMS=[1.18,1.26,1.34]
FACE=(1140,1470)
def crop(z):
    w=int(1620/z)//2*2; h=int(2880/z)//2*2
    x=max(0,min(2160-w,FACE[0]-w//2)); y=max(0,min(3840-h,int(FACE[1]-h*0.40))); return f"crop={w}:{h}:{x}:{y}"
os.makedirs(f'{S}/seg3',exist_ok=True)
files=[];plan=[];zi=0;T=0
for pi,(a,b) in enumerate(pieces):
    cuts=[a]+[m for m in marks if a+0.6<m<b-0.6]+[b]
    sub=[]
    for i in range(len(cuts)-1):            # split long sub-shots evenly (~1.5s)
        x0,x1=cuts[i],cuts[i+1]; n=max(1,round((x1-x0)/1.6))
        sub+= [(x0+(x1-x0)*k/n, x0+(x1-x0)*(k+1)/n) for k in range(n)]
    d=b-a; fc=[]; labs=[]
    for k,(x0,x1) in enumerate(sub):
        z=ZOOMS[zi%3]; zi+=1
        fc.append(f"[0:v]trim={x0-a:.3f}:{x1-a:.3f},setpts=PTS-STARTPTS,{crop(z)},scale=1080:1920:flags=lanczos[v{k}]"); labs.append(f"[v{k}]")
        plan.append({'t0':round(T+x0-a,3),'t1':round(T+x1-a,3),'z':z,'src':[round(x0,2),round(x1,2)]})
    fc.append(''.join(labs)+f"concat=n={len(sub)}:v=1:a=0,fps=30,eq=contrast=1.04:saturation=1.05:brightness=0.012,unsharp=5:5:0.4,format=yuv420p[v]")
    fc.append(f"[0:a]afade=t=in:d=0.015,afade=t=out:st={d-0.025:.3f}:d=0.025,aresample=48000[a]")
    f=f"{S}/seg3/{pi:02d}_{a:.2f}_{b:.2f}_{len(sub)}_{zi}.mov"
    if not os.path.exists(f):
        subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{a}','-t',f'{d:.3f}','-i',SRC,'-filter_complex',';'.join(fc),'-map','[v]','-map','[a]','-ac','2',
          '-c:v','libx264','-crf','14','-preset','medium','-c:a','pcm_s16le',f],check=True)
    files.append(f); T+=d
open(f'{S}/seg3/list.txt','w').write(''.join(f"file '{p}'\n" for p in files))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',f'{S}/seg3/list.txt','-c','copy',f'{S}/cut3.mov'],check=True)
json.dump({'shots':plan,'total':round(T,3)},open(f'{S}/cut3.json','w'),indent=0)
L=[p['t1']-p['t0'] for p in plan]; print(len(pieces),'pieces',len(plan),'shots total',round(T,2),'avg',round(sum(L)/len(L),2))
