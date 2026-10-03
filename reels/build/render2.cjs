const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs=require('fs'),path=require('path');
const [mode,...rest]=process.argv.slice(2);
(async()=>{
 const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1080,height:1920}});
 await p.goto('file://'+path.resolve(process.env.OV||'overlay.html')); await p.evaluate(()=>document.fonts.ready);
 await p.waitForTimeout(500);
 if(mode==='preview'){ for(const t of rest){ await p.evaluate(t=>render(t),+t); await p.evaluate(()=>Promise.all([...document.images].map(i=>i.complete?1:new Promise(r=>i.onload=i.onerror=r)))); await p.screenshot({path:`prev_${t}.png`,omitBackground:true}); } }
 else { const fps=30,dur=+rest[0]; fs.mkdirSync(process.env.OD||'ov',{recursive:true}); let prev='',prevFile='';
   const n=Math.round(dur*fps);
   for(let i=0;i<n;i++){ const t=i/fps; const key=await p.evaluate(t=>render(t),t); await p.evaluate(()=>Promise.all([...document.images].map(i=>i.complete?1:new Promise(r=>i.onload=i.onerror=r)))); const f=`${process.env.OD||'ov'}/${String(i).padStart(5,'0')}.png`;
     if(key===prev){ fs.copyFileSync(prevFile,f);} else { await p.screenshot({path:f,omitBackground:true}); prev=key; prevFile=f; } }
   console.log('frames',n); }
 await b.close();})();
