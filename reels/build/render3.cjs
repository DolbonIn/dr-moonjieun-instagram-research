// 공통 틀(tpl.html) + 영상별 데이터(JSON)로 오버레이 PNG를 30fps로 렌더
// DATA=data.json OD=ov node render3.cjs full <초>   |   DATA=data.json node render3.cjs preview <초...> (prev_<t>.png)
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs = require('fs'), path = require('path');
const [mode, ...rest] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.addInitScript(`window.DATA=${fs.readFileSync(process.env.DATA, 'utf8')};`);
  await p.goto('file://' + path.resolve(__dirname, process.env.OV || 'tpl.html'));
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
  const waitImgs = () => p.evaluate(() => Promise.all([...document.images].map(i => i.complete ? 1 : new Promise(r => i.onload = i.onerror = r))));
  const OD = process.env.OD || 'ov';
  if (mode === 'preview') {
    for (const t of rest) { await p.evaluate(t => render(t), +t); await waitImgs(); await p.screenshot({ path: path.join(OD, `prev_${t}.png`), omitBackground: true }); }
  } else {
    fs.mkdirSync(OD, { recursive: true }); let prev = '', prevFile = ''; const n = Math.round(+rest[0] * 30);
    for (let i = 0; i < n; i++) {
      const key = await p.evaluate(t => render(t), i / 30); await waitImgs();
      const f = path.join(OD, `${String(i).padStart(5, '0')}.png`);
      if (key === prev) fs.copyFileSync(prevFile, f); else { await p.screenshot({ path: f, omitBackground: true }); prev = key; prevFile = f; }
    }
    console.log('frames', n);
  }
  await b.close();
})();
