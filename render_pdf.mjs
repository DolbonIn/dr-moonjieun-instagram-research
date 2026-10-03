// Print an HTML file to an A4 PDF with headless Chromium (Playwright).
// usage: node render_pdf.mjs <in.html> <out.pdf> "<footer text>"
import { createRequire } from "module";
import path from "path";
import { pathToFileURL } from "url";
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(process.env.APPDATA, "npm/node_modules/playwright"));

const [html, pdf, footer = ""] = process.argv.slice(2);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(pathToFileURL(path.resolve(html)).href, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await page.pdf({
  path: pdf, format: "A4", printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: `<div style="width:100%;font-family:'Noto Sans KR','Malgun Gothic',sans-serif;font-size:7pt;color:#7a828a;padding:0 13mm;display:flex;justify-content:space-between;"><span>${footer}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  margin: { top: "14mm", bottom: "15mm", left: "13mm", right: "13mm" },
});
await browser.close();
console.log("pdf written:", pdf);
