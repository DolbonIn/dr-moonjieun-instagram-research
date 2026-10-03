// Logged-out Instagram capture for ONE account, driven by a shortcode list (profile grid + reels tab + each post page, with video).
// usage: node scrape_codes.mjs <handle> [codes.json] [--force]
// codes.json (optional, from a logged-in grid pass): [{code, play_count?, views_text?, pinned?}]
// Writes raw/<handle>/{profile.json,posts.json,profile.png,avatar.jpg,media/<code>_NN.jpg,video/<code>.mp4,json/<code>.json}
// Helpers are the same as ../competitors/scrape.mjs (that file runs on import, so they are copied here).
import { createRequire } from "module";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(process.env.APPDATA, "npm/node_modules/playwright"));

const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const force = args.includes("--force");
const [handle, codesFile] = args.filter((a) => !a.startsWith("--"));
const dir = path.join(HERE, "raw", handle), mdir = path.join(dir, "media"), vdir = path.join(dir, "video"), jdir = path.join(dir, "json");
for (const d of [mdir, vdir, jdir]) fs.mkdirSync(d, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MAX_SLIDES = 20;

// walk any JSON and keep the richest object per media code
function collect(obj, out, pred) {
  if (!obj || typeof obj !== "object") return;
  if (Array.isArray(obj)) return obj.forEach((x) => collect(x, out, pred));
  if (pred(obj)) {
    const prev = out.get(obj.code);
    if (!prev || JSON.stringify(obj).length > JSON.stringify(prev).length) out.set(obj.code, obj);
  }
  for (const v of Object.values(obj)) collect(v, out, pred);
}
const isMedia = (o) => typeof o.code === "string" && o.code.length >= 10 && ("taken_at" in o || "display_uri" in o || "image_versions2" in o);
// exact reel view counts sit on the thin reels-tab objects, which never win collect(), so they are gathered separately
function plays(obj, out) {
  if (!obj || typeof obj !== "object") return;
  if (Array.isArray(obj)) return obj.forEach((x) => plays(x, out));
  if (typeof obj.code === "string" && typeof obj.play_count === "number")
    out.set(obj.code, { play_count: obj.play_count, pinned_reels: !!(obj.clips_tab_pinned_user_ids?.length) });
  for (const v of Object.values(obj)) plays(v, out);
}
function findUser(obj, handle, acc = []) {
  if (!obj || typeof obj !== "object") return acc;
  if (Array.isArray(obj)) { obj.forEach((x) => findUser(x, handle, acc)); return acc; }
  if (obj.username === handle && ("follower_count" in obj || "biography" in obj)) acc.push(obj);
  for (const v of Object.values(obj)) findUser(v, handle, acc);
  return acc;
}
const best = (iv) => (iv?.candidates || []).slice().sort((a, b) => b.width - a.width)[0]?.url;
const bestVideo = (vv) => (vv || []).slice().sort((a, b) => (b.width || 0) - (a.width || 0))[0]?.url || null;
const pkTime = (pk) => Number((BigInt(pk) >> 23n) + 1314220021721n) / 1000;
const dashDur = (xml) => {
  const m = /mediaPresentationDuration="PT(?:(\d+)M)?([\d.]+)S"/.exec(xml || "");
  return m ? Math.round(((+m[1] || 0) * 60 + +m[2]) * 10) / 10 : null;
};

async function capture(page, url, scroll = false) {
  const bodies = [];
  const onResp = async (r) => {
    if (!/\/(api\/graphql|graphql\/query|api\/v1\/)/.test(r.url())) return;
    try { bodies.push(await r.json()); } catch {}
  };
  page.on("response", onResp);
  let nav;
  try { const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 }); nav = { status: resp?.status(), finalUrl: page.url() }; }
  catch (e) { nav = { error: String(e).slice(0, 200) }; }
  await sleep(4500);
  if (scroll) {
    // the sign-up prompt blocks scrolling; once it is closed the reels tab keeps paginating without a login (the posts tab does not)
    const close = page.locator('[role="dialog"] [aria-label="닫기"], [role="dialog"] [aria-label="Close"]').first();
    if (await close.count()) { await close.click({ timeout: 3000 }).catch(() => {}); await sleep(800); }
    const count = () => page.$$eval('main a[href*="/reel/"], main a[href*="/p/"]', (as) => new Set(as.map((a) => a.getAttribute("href"))).size).catch(() => 0);
    for (let i = 0, last = -1, stable = 0; i < 40 && stable < 4; i++) {
      await page.mouse.wheel(0, 2500); await sleep(1500);
      const n = await count();
      if (n === last) stable++; else { stable = 0; last = n; }
    }
  }
  const blobs = await page.$$eval('script[type="application/json"]', (ss) => ss.map((s) => s.textContent)).catch(() => []);
  const codes = await page.$$eval('main a[href*="/reel/"], main a[href*="/p/"]', (as) => as.map((a) => (a.getAttribute("href").match(/\/(?:reel|p)\/([^/]+)/) || [])[1]).filter(Boolean)).catch(() => []);
  page.off("response", onResp);
  const json = [...bodies];
  for (const s of blobs) if (s.includes('"code"') || s.includes('"username"')) { try { json.push(JSON.parse(s)); } catch {} }
  return { nav, json, codes: [...new Set(codes)] };
}

function slim(base, full, handle) {
  const m = { ...base, ...(full || {}) };
  const car = (m.carousel_media || []).map((c) => ({
    media_type: { 1: "image", 2: "video" }[c.media_type] || c.media_type,
    img: best(c.image_versions2) || c.display_uri || null,
    alt: c.accessibility_caption || null,
  }));
  const taken = m.taken_at || (m.pk ? Math.round(pkTime(m.pk)) : null);
  return {
    account: handle,
    owner: m.user?.username || m.owner?.username || null,
    code: m.code,
    url: `https://www.instagram.com/${m.product_type === "clips" ? "reel" : "p"}/${m.code}/`,
    taken_at: taken,
    posted_kst: taken ? new Date((taken + 9 * 3600) * 1000).toISOString().slice(0, 16).replace("T", " ") : null,
    media_type: { 1: "image", 2: "video", 8: "carousel" }[m.media_type] || m.media_type,
    product_type: m.product_type,
    pinned: !!(m.timeline_pinned_user_ids?.length),
    slides: m.carousel_media_count || car.length || 1,
    like_count: m.like_count ?? null,
    like_hidden: m.like_and_view_counts_disabled ?? null,
    comment_count: m.comment_count ?? null,
    play_count: m.play_count ?? m.ig_play_count ?? m.view_count ?? null,
    duration: m.video_duration ?? dashDur(m.video_dash_manifest),
    caption: m.caption?.text ?? null,
    accessibility_caption: m.accessibility_caption || null,
    usertags: (m.usertags?.in || []).map((u) => u.user?.username).filter(Boolean),
    coauthors: (m.coauthor_producers || []).map((u) => u.username),
    location: m.location?.name || null,
    audio: m.clips_metadata?.music_info?.music_asset_info?.title || m.clips_metadata?.original_sound_info?.original_audio_title || null,
    audio_type: m.clips_metadata?.audio_type || null,
    cover: best(m.image_versions2) || m.display_uri || car[0]?.img || null,
    video_url: bestVideo(m.video_versions),
    slide_media: car,
    w: m.original_width ?? null, h: m.original_height ?? null,
    detail: !!full,
  };
}

async function dl(url, file) {
  if (!url || fs.existsSync(file)) return;
  try { const r = await fetch(url); if (r.ok) fs.writeFileSync(file, Buffer.from(await r.arrayBuffer())); } catch {}
}

const postsFile = path.join(dir, "posts.json");
const prev = new Map((fs.existsSync(postsFile) ? JSON.parse(fs.readFileSync(postsFile, "utf8")) : []).map((p) => [p.code, p]));
const extra = codesFile ? JSON.parse(fs.readFileSync(codesFile, "utf8")) : [];

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  locale: "ko-KR", viewport: { width: 1280, height: 1400 },
  userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
});
const page = await ctx.newPage();

const grid = await capture(page, `https://www.instagram.com/${handle}/`, true);
if (/accounts\/login|challenge/.test(grid.nav.finalUrl || "")) { console.log(`${handle}\tLOGIN WALL ${grid.nav.finalUrl}`); await browser.close(); process.exit(1); }
const meta = await page.evaluate(() => ({
  title: document.title,
  description: document.querySelector('meta[name="description"]')?.content || null,
  header: document.querySelector("header")?.innerText || null,
  main: (document.querySelector("main")?.innerText || "").slice(0, 800),
})).catch(() => ({}));
await page.screenshot({ path: path.join(dir, "profile.png") }).catch(() => {});
await sleep(2500);
const reels = await capture(page, `https://www.instagram.com/${handle}/reels/`, true);

// how each tab's pagination ended: has_next_page=false means the list is complete, an "Unauthorized logged out query" error means it was cut off
const ends = (json) => {
  const out = [];
  const walk = (o, key) => {
    if (!o || typeof o !== "object") return;
    if (Array.isArray(o)) return o.forEach((x) => walk(x, key));
    if (o.page_info && typeof o.page_info.has_next_page === "boolean") out.push(`${key}:${o.page_info.has_next_page ? "more" : "end"}`);
    if (Array.isArray(o.errors)) out.push(`error:${o.errors[0]?.message}`);
    for (const [k, v] of Object.entries(o)) walk(v, k);
  };
  walk(json, "root");
  return out;
};
console.log("grid pagination:", ends(grid.json).join(" | "));
console.log("reels pagination:", ends(reels.json).join(" | "));
fs.writeFileSync(path.join(jdir, "_reels_tab.json"), JSON.stringify(reels.json));

const base = new Map(), playMap = new Map();
collect([grid.json, reels.json], base, isMedia);
plays([grid.json, reels.json], playMap);
let users = [];
for (const j of grid.json) users = users.concat(findUser(j, handle));
const u = users.sort((a, b) => Object.keys(b).length - Object.keys(a).length)[0] || {};
const profile = {
  username: handle, fetchedAt: new Date().toISOString(), nav: grid.nav, meta,
  full_name: u.full_name ?? null, biography: u.biography ?? null,
  followers: u.follower_count ?? null, following: u.following_count ?? null, media_count: u.media_count ?? null,
  category: u.category ?? u.category_name ?? null, external_url: u.external_url ?? null,
  bio_links: (u.bio_links || []).map((l) => ({ title: l.title, url: l.url })),
  is_verified: u.is_verified ?? null, pic: u.hd_profile_pic_url_info?.url || u.profile_pic_url || null,
  grid_codes: grid.codes, reels_codes: reels.codes,
};
fs.writeFileSync(path.join(dir, "profile.json"), JSON.stringify(profile, null, 1));
await dl(profile.pic, path.join(dir, "avatar.jpg"));

const extraMap = new Map(extra.map((e) => [e.code, e]));
const codes = [...new Set([...grid.codes, ...reels.codes, ...extra.map((e) => e.code), ...prev.keys()])];
console.log(`${handle}\tgrid=${grid.codes.length}\treels=${reels.codes.length}\textra=${extra.length}\ttotal=${codes.length}\tfollowers=${profile.followers}\tmedia_count=${profile.media_count}`);

const posts = [];
for (const code of codes) {
  const had = prev.get(code);
  const mp4 = path.join(vdir, `${code}.mp4`);
  let p;
  if (!force && had?.detail && (had.media_type !== "video" || fs.existsSync(mp4))) p = had;
  else {
    await sleep(2500 + Math.random() * 2500);
    const r = await capture(page, `https://www.instagram.com/p/${code}/`);
    fs.writeFileSync(path.join(jdir, `${code}.json`), JSON.stringify(r.json));
    const full = new Map();
    collect(r.json, full, (o) => o.code === code && "taken_at" in o);
    p = slim(base.get(code) || { code }, full.get(code), handle);
    p.nav = r.nav.finalUrl || r.nav.error || null;
    p.og_description = await page.evaluate(() => document.querySelector('meta[property="og:description"]')?.content || null).catch(() => null);
    await dl(p.cover, path.join(mdir, `${code}_00.jpg`));
    for (let i = 0; i < Math.min(p.slide_media.length, MAX_SLIDES); i++) await dl(p.slide_media[i].img, path.join(mdir, `${code}_${String(i + 1).padStart(2, "0")}.jpg`));
    await dl(p.video_url, mp4);
  }
  // view counts: reels tab (exact) > logged-in pass > whatever the post page had
  const pm = playMap.get(code), ex = extraMap.get(code);
  p.play_count = pm?.play_count ?? ex?.play_count ?? p.play_count ?? null;
  p.views_text = ex?.views_text ?? p.views_text ?? null;
  p.pinned_reels = pm?.pinned_reels ?? ex?.pinned ?? p.pinned_reels ?? false;
  p.has_video = fs.existsSync(mp4);
  posts.push(p);
  console.log([p.code, p.posted_kst, p.product_type, `plays=${p.play_count}`, `likes=${p.like_count}${p.like_hidden ? "(hidden)" : ""}`, `c=${p.comment_count}`, `dur=${p.duration}`, `mp4=${p.has_video}`, `detail=${p.detail}`].join("\t"));
  fs.writeFileSync(postsFile, JSON.stringify(posts.concat([...prev.values()].filter((x) => !posts.some((y) => y.code === x.code))).sort((a, b) => (b.taken_at || 0) - (a.taken_at || 0)), null, 1));
}
posts.sort((a, b) => (b.taken_at || 0) - (a.taken_at || 0));
fs.writeFileSync(postsFile, JSON.stringify(posts, null, 1));
console.log(`done\tposts=${posts.length}\tdetail=${posts.filter((p) => p.detail).length}\tvideo=${posts.filter((p) => p.has_video).length}`);
await browser.close();
