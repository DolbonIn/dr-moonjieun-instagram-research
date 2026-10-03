import cv2, subprocess, json, numpy as np, os
exec(open('cut3.py').read().split('ZOOMS=')[0].replace("S=os.path.dirname(os.path.abspath(__file__))","S='.'"))
cas=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
def frame(t):
    raw=subprocess.run(['ffmpeg','-v','error','-ss',f'{t:.3f}','-i','../footage/jm3.mp4','-frames:v','1','-vf','scale=540:960','-f','rawvideo','-pix_fmt','gray','-'],capture_output=True).stdout
    return np.frombuffer(raw,np.uint8).reshape(960,540)
res=[]
for a,b in pieces:
    pts=[]
    for k in range(5):
        g=frame(a+(b-a)*(k+0.5)/5)
        f=cas.detectMultiScale(g,1.1,6,minSize=(60,60))
        if len(f): x,y,w,h=max(f,key=lambda r:r[2]*r[3]); pts.append((x+w/2,y+h/2,h))
    p=np.median(np.array(pts),axis=0)*4 if pts else None
    res.append([a,b]+([round(v,1) for v in p] if p is not None else [None]*3)); print(res[-1],len(pts))
json.dump(res,open('faces.json','w'))
