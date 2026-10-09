// Escritorio 3D do Cryptoscan (Three.js). Os agentes e o seu estado vem da
// pagina (window.OFAPI): quem esta a trabalhar senta-se a secretaria, quem
// esta em pausa anda pelo cafe, pela sala de reuniao e pelos servidores, e de
// noite dorme no sofa. Os baloes mostram o trabalho real de cada agente.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const API = () => window.OFAPI;
const V = (x, z) => new THREE.Vector3(x, 0, z);

// ---------- planta ----------
const ZONES = {
  ops: { name: "Mesa de operações", c: "#4FD1C5", x: [-19, -3], z: [-12, -2], door: V(-2.6, -7) },
  lab: { name: "Pesquisa", c: "#B794F4", x: [-19, -3], z: [0, 12], door: V(-2.6, 6) },
  meet: { name: "Sala de reunião", c: "#68D391", x: [3, 13], z: [-12, -4], door: V(2.6, -8) },
  cafe: { name: "Café", c: "#F6C453", x: [3, 13], z: [-2, 4], door: V(2.6, 1) },
  ctrl: { name: "Controlo", c: "#FF6FB5", x: [3, 13], z: [6, 12], door: V(2.6, 9) },
  srv: { name: "Servidores", c: "#63B3ED", x: [15, 19.5], z: [-12, 12], door: V(2.6, -1) },
};
// secretaria de cada agente: zona, centro e para onde olha o agente
const DESK = {
  scan: { z: "ops", p: V(-10.5, -9.5), f: -1 }, mon: { z: "ops", p: V(-10.5, -4.8), f: -1 },
  afin: { z: "lab", p: V(-10.5, 2.5), f: -1 }, inv: { z: "lab", p: V(-10.5, 6.2), f: -1 },
  juiz: { z: "lab", p: V(-10.5, 9.9), f: -1 },
  vig: { z: "ctrl", p: V(6, 7.4), f: 1 }, news: { z: "ctrl", p: V(6, 10.4), f: 1 },
  aud: { z: "ctrl", p: V(10.5, 8.9), f: 1 },
};
const SPOTS = [
  { z: "cafe", p: V(11.4, -0.8), k: "cafe" }, { z: "cafe", p: V(11.4, 0.6), k: "cafe" },
  { z: "cafe", p: V(6.0, -0.4), k: "mesa", sit: 1 }, { z: "cafe", p: V(7.4, -0.4), k: "mesa", sit: 1 },
  { z: "cafe", p: V(5.2, 3.2), k: "sofa", sit: 1, r: Math.PI }, { z: "cafe", p: V(6.4, 3.2), k: "sofa", sit: 1, r: Math.PI },
  { z: "cafe", p: V(7.6, 3.2), k: "sofa", sit: 1, r: Math.PI },
  { z: "meet", p: V(6.5, -9.3), k: "reuniao", sit: 1, r: 0 }, { z: "meet", p: V(8.5, -9.3), k: "reuniao", sit: 1, r: 0 },
  { z: "meet", p: V(6.5, -6.7), k: "reuniao", sit: 1, r: Math.PI }, { z: "meet", p: V(8.5, -6.7), k: "reuniao", sit: 1, r: Math.PI },
  { z: "srv", p: V(14.2, -6), k: "servidores", r: Math.PI / 2 }, { z: "srv", p: V(14.2, 5), k: "servidores", r: Math.PI / 2 },
];
const LOOK = {
  scan: ["#2b1b12", "#f1c27d"], mon: ["#d9a441", "#e0ac69"], vig: ["#666", "#c68642"],
  news: ["#7a2e1a", "#f1c27d"], afin: ["#111", "#8d5524"], inv: ["#e6c07b", "#ffdbac"],
  juiz: ["#9a9a9a", "#e0ac69"], aud: ["#3b2a1a", "#c68642"],
};

const zoneHits = [];
let R, scene, cam, ctl, box, overlay, clock, people = [], monTex, monOn = {}, tvTex,
  ledTex, labels = [], bubble, bubAt = 0, bubI = 0, bubWho = null, visible = true, running = false;

function supported() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); }
  catch (_) { return false; }
}

const mat = (c, e = 0, o = 1) => new THREE.MeshStandardMaterial({ color: c, emissive: e ? c : 0x000000, emissiveIntensity: e, transparent: o < 1, opacity: o, roughness: .6, metalness: .1 });
function boxM(w, h, d, m, x, y, z, parent = scene) { const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z); b.castShadow = h > .3 && !m.transparent; b.receiveShadow = true; parent.add(b); return b; }
function line(pts, c, parent = scene) { const g = new THREE.BufferGeometry().setFromPoints(pts); const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: c })); parent.add(l); return l; }

// ---------- texturas animadas ----------
function canvasTex(w, h, draw) { const c = document.createElement("canvas"); c.width = w; c.height = h; const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.userData = { c, draw }; draw(c.getContext("2d"), 0); return t; }
function drawMon(g, t) {
  g.fillStyle = "#06121f"; g.fillRect(0, 0, 256, 160);
  for (let i = 0; i < 22; i++) {
    const v = Math.sin(i * .7 + t * .6) * 30 + Math.sin(i * 1.9 + t) * 14, up = Math.cos(i * 1.3 + t * .8) > 0;
    g.fillStyle = up ? "#4FD1C5" : "#FF6F91"; const y = 80 - v, h = 12 + Math.abs(Math.sin(i + t)) * 22;
    g.fillRect(10 + i * 11, y - h / 2, 6, h); g.fillRect(12 + i * 11, y - h / 2 - 8, 2, h + 16);
  }
  g.fillStyle = "#B794F4"; g.font = "bold 16px monospace"; g.fillText("4H · análise", 8, 18);
}
function drawLeds(g) {
  g.fillStyle = "#0a0f1e"; g.fillRect(0, 0, 64, 160);
  for (let y = 6; y < 156; y += 9) for (let x = 6; x < 60; x += 8) {
    const r = Math.random(); g.fillStyle = r > .8 ? "#7CFFB2" : r > .6 ? "#63B3ED" : r > .55 ? "#F6C453" : "#1b2a44"; g.fillRect(x, y, 4, 3);
  }
}
function drawTV(g) {
  const D = API().D() || {}, btc = (D.universe || []).find(r => r.asset === "BTC") || {}, mf = D.market_filter || {};
  g.fillStyle = "#0b1b2a"; g.fillRect(0, 0, 512, 288); g.strokeStyle = "#68D391"; g.lineWidth = 4; g.strokeRect(6, 6, 500, 276);
  g.fillStyle = "#68D391"; g.font = "bold 30px sans-serif"; g.fillText("Sala de reunião", 24, 46);
  g.fillStyle = "#fff"; g.font = "24px sans-serif";
  const ops = (D.active_signals || []).filter(s => s.status === "TRIGGERED" && s.mode !== "PAPER").map(s => s.asset).join(", ") || "nenhuma";
  const ne = D.next_event ? `${D.next_event.name}` : "sem eventos";
  [`1. BTC ${btc.price ? Math.round(btc.price).toLocaleString("pt-PT") : "–"} (${(btc.chg_24h || 0) >= 0 ? "+" : ""}${(btc.chg_24h || 0).toFixed(1)}%)`,
   `2. Mercado ${mf.btc_above_sma200 ? "acima" : "abaixo"} da média de 200 dias`,
   `3. Operações abertas: ${ops}`, `4. Próximo evento: ${ne}`]
    .forEach((s, i) => g.fillText(s.slice(0, 38), 24, 96 + i * 44));
}

// ---------- cenario ----------
function buildRoom() {
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(42, 28), mat("#1a1150"));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  const grid = new THREE.GridHelper(42, 42, 0x3b2a8f, 0x2a1f6e); grid.position.y = .01; scene.add(grid);
  // corredor com linhas de neon
  [-1.6, 1.6].forEach(x => boxM(.06, .02, 26, mat("#FF6FB5", 1.4), x, .02, 0));
  [-0.5, 0.5].forEach(x => boxM(.03, .02, 26, mat("#B794F4", .9), x, .02, 0));
  // zonas: tapete, paredes de vidro, arestas de neon
  for (const [k, Z] of Object.entries(ZONES)) {
    const w = Z.x[1] - Z.x[0], d = Z.z[1] - Z.z[0], cx = (Z.x[0] + Z.x[1]) / 2, cz = (Z.z[0] + Z.z[1]) / 2;
    if (k !== "srv") { const rug = new THREE.Mesh(new THREE.PlaneGeometry(w - .4, d - .4), mat(k === "cafe" ? "#2a1a5e" : "#2b1d74")); rug.rotation.x = -Math.PI / 2; rug.position.set(cx, .015, cz); scene.add(rug); }
    const col = new THREE.Color(Z.c), h = k === "meet" ? 2.6 : 1.2;
    const glass = mat(Z.c, .15, .07);
    const walls = [[cx, Z.z[0], w, .05], [cx, Z.z[1], w, .05], [Z.x[0], cz, .05, d], [Z.x[1], cz, .05, d]];
    walls.forEach(([x, z, ww, dd], i) => {
      const doorSide = (k === "ops" || k === "lab") ? 3 : 2; if (i === doorSide && k !== "srv") return; // lado do corredor aberto
      if (k === "srv") return;
      boxM(ww, h, dd, glass, x, h / 2, z);
    });
    const c = [V(Z.x[0], Z.z[0]), V(Z.x[1], Z.z[0]), V(Z.x[1], Z.z[1]), V(Z.x[0], Z.z[1]), V(Z.x[0], Z.z[0])];
    line(c.map(p => p.clone().setY(.03)), col); if (k !== "srv") line(c.map(p => p.clone().setY(h)), col);
    [[Z.x[0], Z.z[0]], [Z.x[1], Z.z[0]], [Z.x[1], Z.z[1]], [Z.x[0], Z.z[1]]].forEach(([x, z]) => k !== "srv" && boxM(.07, h, .07, mat(Z.c, .45), x, h / 2, z));
    const zl = label(Z.name, Z.c, true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = `1px solid ${Z.c}66`;
    zl.addEventListener("click", () => API().openZone(k));
    labels.push({ el: zl, p: new THREE.Vector3(cx, (k === "meet" ? 3.3 : 2.1), Z.z[0] + .2) });
    const hit = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshBasicMaterial({ visible: false })); hit.rotation.x = -Math.PI / 2; hit.position.set(cx, .05, cz); hit.userData.zone = k; scene.add(hit); zoneHits.push(hit);
  }
  // sala de reuniao: mesa oval, cadeiras, ecra
  const t = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, .08, 32), mat("#3b3f6e")); t.scale.set(1.9, 1, .9); t.position.set(7.5, .75, -8); scene.add(t);
  boxM(.2, .72, .2, mat("#222"), 7.5, .36, -8);
  tvTex = canvasTex(512, 288, drawTV);
  const tv = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 2.36), new THREE.MeshBasicMaterial({ map: tvTex, toneMapped: false })); tv.position.set(8, 1.75, -11.9); scene.add(tv);
  // cafe: balcao, maquina, mesas, sofa
  boxM(1, 1, 4.6, mat("#3a2b20"), 12.3, .5, .9); boxM(1.05, .06, 4.7, mat("#c08a5a"), 12.3, 1.02, .9);
  boxM(.5, .6, .45, mat("#888"), 12.3, 1.35, -.1); boxM(.12, .12, .05, mat("#ff4d4d", 2), 12.06, 1.45, -.1);
  [[6.7, -1.1]].forEach(([x, z]) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(.7, .7, .06, 24), mat("#c08a5a")); m.position.set(x, .75, z); scene.add(m); boxM(.1, .72, .1, mat("#222"), x, .36, z); });
  boxM(3.8, .45, .9, mat("#5b3d8a"), 6.4, .25, 3.6); boxM(3.8, .7, .25, mat("#6e4ca3"), 6.4, .6, 4);
  const rug = new THREE.Mesh(new THREE.CircleGeometry(2.2, 32), mat("#b8863b")); rug.rotation.x = -Math.PI / 2; rug.position.set(6.6, .02, 1.3); scene.add(rug);
  // plantas
  [[-18, -11.4], [-18, 11.4], [2.9, -3], [2.9, 5], [12.6, 11.4], [12.6, -3]].forEach(([x, z]) => {
    boxM(.5, .5, .5, mat("#7a4b2a"), x, .25, z); const s = new THREE.Mesh(new THREE.SphereGeometry(.55, 12, 10), mat("#38d6b5", .25)); s.position.set(x, 1, z); scene.add(s);
  });
  // servidores com luzes a piscar
  ledTex = canvasTex(64, 160, drawLeds);
  for (let z = -11; z <= 11; z += 1.6) {
    const rack = boxM(1.1, 2.4, 1.2, mat("#0d1224"), 18.6, 1.2, z);
    const f = new THREE.Mesh(new THREE.PlaneGeometry(.9, 2.2), new THREE.MeshBasicMaterial({ map: ledTex, toneMapped: false })); f.position.set(18.03, 1.2, z); f.rotation.y = -Math.PI / 2; scene.add(f);
  }
  boxM(.06, .02, 24, mat("#63B3ED", 1.5), 17.2, .02, 0);
}
function buildDesk(id) {
  const d = DESK[id], g = new THREE.Group(); g.position.copy(d.p); scene.add(g);
  const f = d.f; // agente olha para x*f
  boxM(1.1, .06, 2.0, mat("#a06b42"), 0, .75, 0, g);
  [[-.45, -.85], [.45, -.85], [-.45, .85], [.45, .85]].forEach(([x, z]) => boxM(.06, .72, .06, mat("#222"), x, .36, z, g));
  boxM(.05, .5, 1.2, mat("#111"), f * .45, 1.1, 0, g); // monitor
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(1.1, .44), new THREE.MeshBasicMaterial({ color: 0x0b1424 }));
  scr.position.set(f * .42, 1.1, 0); scr.rotation.y = -f * Math.PI / 2; g.add(scr); monOn[id] = scr;
  boxM(.08, .3, .08, mat("#111"), f * .45, .88, 0, g);
  boxM(.3, .02, .5, mat("#ddd"), -f * .15, .79, .5, g); // papeis
  deskProps(g, f, id);
  if (id === "scan" || id === "mon") deskTex[id] = canvasTex(512, 256, () => {});
  // cadeira
  const ch = new THREE.Group(); ch.position.set(-f * .95, 0, 0); g.add(ch);
  boxM(.55, .08, .55, mat("#2b2b40"), 0, .48, 0, ch); boxM(.08, .6, .55, mat("#2b2b40"), -f * .27, .8, 0, ch);
  boxM(.06, .45, .06, mat("#111"), 0, .24, 0, ch);
}


// ---------- acessorios ----------
let wallTex = null, wallI = 0, wallT = 0, clock3d = null, deskTex = {};
function drawWall(g) {
  const W = 1024, H = 512, feed = (window.chartFeed && window.chartFeed()) || [];
  if (!feed.length) { g.fillStyle = "#07142a"; g.fillRect(0, 0, W, H); return; }
  const it = feed[wallI % feed.length];
  window.drawCandles(g, W, H, it.cs, it.lv, { title: it.title, bg: "#060f22" });
  g.strokeStyle = "#4FD1C5"; g.lineWidth = 6; g.strokeRect(3, 3, W - 6, H - 6);
  g.fillStyle = "#4FD1C5"; g.font = "600 22px system-ui"; g.textAlign = "right"; g.fillText(`${wallI % feed.length + 1}/${feed.length}`, W - 70, 30); g.textAlign = "left";
}
function buildWall() {
  wallTex = canvasTex(1024, 512, drawWall);
  const g = new THREE.Group(); g.position.set(-6.4, 0, -10.4); g.rotation.y = Math.PI / 4; scene.add(g);
  boxM(6.6, 3.5, .18, mat("#0b0b18"), 0, 2.45, 0, g);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(6.3, 3.15), new THREE.MeshBasicMaterial({ map: wallTex, toneMapped: false })); scr.position.set(0, 2.45, .1); g.add(scr);
  boxM(6.7, .06, .06, mat("#4FD1C5", 2.2), 0, .66, .1, g); boxM(6.7, .06, .06, mat("#4FD1C5", 2.2), 0, 4.24, .1, g);
  boxM(.18, .7, .18, mat("#222"), -2.2, .35, 0, g); boxM(.18, .7, .18, mat("#222"), 2.2, .35, 0, g);
  const l = label("Gráficos ao vivo", "#4FD1C5", true); l.style.pointerEvents = "auto"; l.style.cursor = "pointer"; l.addEventListener("click", () => API().openZone("ops"));
  labels.push({ el: l, p: new THREE.Vector3(-6.4, 4.7, -10.4) });
}
function drawClock(g) {
  const n = new Date(); g.clearRect(0, 0, 256, 256); g.fillStyle = "#f4f2ff"; g.beginPath(); g.arc(128, 128, 118, 0, 7); g.fill();
  g.strokeStyle = "#FF6FB5"; g.lineWidth = 10; g.stroke(); g.fillStyle = "#222";
  for (let i = 0; i < 12; i++) { const a = i / 12 * 6.283; g.fillRect(128 + Math.sin(a) * 98 - 3, 128 - Math.cos(a) * 98 - 3, 6, 6); }
  const hand = (a, L, w, c) => { g.strokeStyle = c; g.lineWidth = w; g.lineCap = "round"; g.beginPath(); g.moveTo(128, 128); g.lineTo(128 + Math.sin(a) * L, 128 - Math.cos(a) * L); g.stroke(); };
  hand(((n.getHours() % 12) + n.getMinutes() / 60) / 12 * 6.283, 55, 9, "#222"); hand(n.getMinutes() / 60 * 6.283, 82, 6, "#222"); hand(n.getSeconds() / 60 * 6.283, 88, 2, "#FF6FB5");
  g.fillStyle = "#3b2a8f"; g.font = "bold 22px system-ui"; g.textAlign = "center"; g.fillText("Lisboa", 128, 180); g.textAlign = "left";
}
// ---------- painel de dados da parede ----------
// 5 paineis lado a lado, com dados reais do scan e velas da Bybit:
// BTC 4H com volume e liquidez | livro de ordens e derivados do BTC |
// volume relativo por moeda | operacao aberta com volume | mapa do mercado 24h
let dataTex = null, dataI = 0;
const fmtUsd = v => v == null ? "–" : v >= 1e9 ? (v / 1e9).toFixed(1).replace(".", ",") + " mil M" : v >= 1e6 ? (v / 1e6).toFixed(1).replace(".", ",") + " M" : v >= 1e3 ? Math.round(v / 1e3) + " mil" : Math.round(v) + "";
const pxs = v => v == null ? "–" : v >= 100 ? Math.round(v).toLocaleString("pt-PT") : v >= 1 ? v.toFixed(3).replace(".", ",") : Number(v.toPrecision(4)).toString().replace(".", ",");
function panelFrame(g, x, w, H, title, c) {
  g.fillStyle = "#0a1226"; g.fillRect(x + 6, 6, w - 12, H - 12);
  g.strokeStyle = c; g.lineWidth = 3; g.strokeRect(x + 6, 6, w - 12, H - 12);
  g.fillStyle = c; g.font = "700 26px system-ui,sans-serif"; g.fillText(title, x + 22, 40);
}
function candlesVol(g, x0, y0, w, h, cs, o) {
  o = o || {}; if (!cs || !cs.length) { g.fillStyle = "#8AA0B4"; g.font = "22px system-ui"; g.fillText("a carregar…", x0 + 10, y0 + h / 2); return; }
  const n = Math.min(cs.length, o.n || 60), d = cs.slice(-n), vh = h * .22, ph = h - vh - 6;
  let lo = Math.min(...d.map(c => c.l)), hi = Math.max(...d.map(c => c.h));
  (o.zones || []).forEach(z => { if (z[0] > lo * .9 && z[1] < hi * 1.1) { lo = Math.min(lo, z[0]); hi = Math.max(hi, z[1]); } });
  (o.lines || []).forEach(l => { if (l.v > lo * .92 && l.v < hi * 1.08) { lo = Math.min(lo, l.v); hi = Math.max(hi, l.v); } });
  const sp = (hi - lo) || hi * .01; lo -= sp * .03; hi += sp * .03;
  const X = i => x0 + (i + .5) * w / n, Y = v => y0 + (hi - v) / (hi - lo) * ph, bw = Math.max(2, w / n * .6);
  (o.zones || []).forEach(z => { const a = Math.max(lo, z[0]), b = Math.min(hi, z[1]); if (b <= a) return; g.fillStyle = z[2]; g.fillRect(x0, Y(b), w, Y(a) - Y(b)); });
  const vmax = Math.max(...d.map(c => c.v || 0)) || 1;
  d.forEach((c, i) => { const up = c.c >= c.o; g.fillStyle = up ? "#3ee0c455" : "#ff6f8a55"; const vv = (c.v || 0) / vmax * vh; g.fillRect(X(i) - bw / 2, y0 + h - vv, bw, vv);
    g.strokeStyle = g.fillStyle = up ? "#3ee0c4" : "#ff6f8a"; g.lineWidth = 2; g.beginPath(); g.moveTo(X(i), Y(c.h)); g.lineTo(X(i), Y(c.l)); g.stroke();
    const y1 = Y(Math.max(c.o, c.c)), y2 = Y(Math.min(c.o, c.c)); g.fillRect(X(i) - bw / 2, y1, bw, Math.max(2, y2 - y1)); });
  g.font = "600 18px system-ui";
  (o.lines || []).forEach(l => { if (l.v < lo || l.v > hi) return; const y = Y(l.v); g.strokeStyle = l.c; g.setLineDash([10, 7]); g.lineWidth = 2; g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 + w, y); g.stroke(); g.setLineDash([]);
    g.fillStyle = l.c; const tw = g.measureText(l.t).width + 10; g.fillRect(x0 + w - tw, y - 12, tw, 22); g.fillStyle = "#07142a"; g.fillText(l.t, x0 + w - tw + 5, y + 5); });
  const last = d[d.length - 1].c; g.fillStyle = "#FFA94D"; g.beginPath(); g.arc(X(n - 1), Y(last), 6, 0, 7); g.fill();
  g.fillStyle = "#8AA0B4"; g.font = "16px system-ui"; g.fillText("volume", x0 + 4, y0 + h - vh + 14);
}
function drawDataWall(g) {
  const W = 3072, H = 384, D = API() && API().D ? API().D() || {} : {}, U = D.universe || [], feed = (window.chartFeed && window.chartFeed()) || [];
  g.fillStyle = "#060b1c"; g.fillRect(0, 0, W, H);
  const P = [[0, 760], [760, 560], [1320, 560], [1880, 640], [2520, 552]];
  // 1. BTC 4H com volume e liquidez
  const btc = U.find(r => r.asset === "BTC") || {}, a4 = ((btc.analysis || {})["4h"]) || {}, lq = a4.liquidity || {};
  panelFrame(g, P[0][0], P[0][1], H, `BTC · 4H · ${pxs(btc.price)}  ${(btc.chg_24h || 0) >= 0 ? "+" : ""}${(btc.chg_24h || 0).toFixed(1).replace(".", ",")}%`, "#4FD1C5");
  const bf = feed.find(f => f.asset === "BTC");
  const lines = [].concat((lq.pools_above || []).slice(0, 1).map(v => ({ v, c: "#FF6FB5", t: "liquidez " + pxs(v) })), (lq.pools_below || []).slice(0, 1).map(v => ({ v, c: "#63B3ED", t: "liquidez " + pxs(v) })));
  const zones = [].concat(lq.fvg_above ? [[lq.fvg_above[0], lq.fvg_above[1], "#FF6FB522"]] : [], lq.fvg_below ? [[lq.fvg_below[0], lq.fvg_below[1], "#63B3ED22"]] : []);
  candlesVol(g, P[0][0] + 22, 56, P[0][1] - 44, H - 76, bf && bf.cs, { lines, zones, n: 54 });
  // 2. Liquidez e derivados do BTC
  let x = P[1][0], w = P[1][1]; panelFrame(g, x, w, H, "Liquidez · BTC", "#FF6FB5");
  const bk = btc.book || {}, dv = btc.derivatives || {}, lqd = dv.liquidations || {};
  const buy = bk.imbalance != null ? (1 + bk.imbalance) / 2 : null;
  g.fillStyle = "#8AA0B4"; g.font = "20px system-ui"; g.fillText("Livro de ordens (±1%)", x + 22, 82);
  if (buy != null) { const bwid = w - 44; g.fillStyle = "#3ee0c4"; g.fillRect(x + 22, 92, bwid * buy, 26); g.fillStyle = "#ff6f8a"; g.fillRect(x + 22 + bwid * buy, 92, bwid * (1 - buy), 26);
    g.fillStyle = "#07142a"; g.font = "700 18px system-ui"; g.fillText(`compra ${Math.round(buy * 100)}%`, x + 30, 112); g.textAlign = "right"; g.fillText(`venda ${Math.round((1 - buy) * 100)}%`, x + w - 30, 112); g.textAlign = "left"; }
  const row = (k, v, y, c) => { g.fillStyle = "#8AA0B4"; g.font = "20px system-ui"; g.fillText(k, x + 22, y); g.fillStyle = c || "#E6EDF3"; g.font = "700 22px system-ui"; g.textAlign = "right"; g.fillText(v, x + w - 22, y); g.textAlign = "left"; };
  row("Profundidade a 1%", "$" + fmtUsd(bk.depth_1pct_usd), 150);
  row("Liquidez acima", (lq.pools_above || []).slice(0, 2).map(pxs).join(" · ") || "–", 182, "#FF6FB5");
  row("Liquidez abaixo", (lq.pools_below || []).slice(0, 2).map(pxs).join(" · ") || "–", 214, "#63B3ED");
  row("Open interest 24h", dv.oi_chg_24h_pct != null ? (dv.oi_chg_24h_pct > 0 ? "+" : "") + dv.oi_chg_24h_pct.toFixed(1).replace(".", ",") + "%" : "–", 246);
  row("Funding (anual)", dv.funding_apr != null ? dv.funding_apr.toFixed(1).replace(".", ",") + "%" : "–", 278);
  const L = lqd.long_usd || 0, S = lqd.short_usd || 0, tot = (L + S) || 1;
  g.fillStyle = "#8AA0B4"; g.font = "20px system-ui"; g.fillText("Liquidações 24h", x + 22, 312);
  g.fillStyle = "#ff6f8a"; g.fillRect(x + 22, 322, (w - 44) * L / tot, 22); g.fillStyle = "#3ee0c4"; g.fillRect(x + 22 + (w - 44) * L / tot, 322, (w - 44) * S / tot, 22);
  g.fillStyle = "#E6EDF3"; g.font = "600 17px system-ui"; g.fillText(`longs $${fmtUsd(L)}`, x + 26, 360); g.textAlign = "right"; g.fillText(`shorts $${fmtUsd(S)}`, x + w - 26, 360); g.textAlign = "left";
  // 3. Volume relativo (4H) e fluxo comprador
  x = P[2][0]; w = P[2][1]; panelFrame(g, x, w, H, "Volume relativo · 4H", "#F6C453");
  const vr = U.filter(r => r.analysis && r.analysis["4h"] && r.analysis["4h"].volume && r.analysis["4h"].volume.rvol != null)
    .map(r => ({ a: r.asset, rv: r.analysis["4h"].volume.rvol, bs: r.analysis["4h"].volume.buy_share })).sort((p, q) => q.rv - p.rv).slice(0, 8);
  const rmax = Math.max(2, ...vr.map(r => r.rv));
  vr.forEach((r, i) => { const y = 64 + i * 37, bw2 = (w - 190) * Math.min(1, r.rv / rmax);
    g.fillStyle = "#E6EDF3"; g.font = "700 20px system-ui"; g.fillText(r.a, x + 22, y + 21);
    g.fillStyle = r.rv >= 1.5 ? "#F6C453" : "#F6C45377"; g.fillRect(x + 110, y + 4, bw2, 22);
    g.fillStyle = "#E6EDF3"; g.font = "600 18px system-ui"; g.fillText(r.rv.toFixed(1).replace(".", ",") + "x", x + 116 + bw2, y + 21);
    if (r.bs != null) { g.fillStyle = r.bs >= .5 ? "#3ee0c4" : "#ff6f8a"; g.textAlign = "right"; g.fillText(Math.round(r.bs * 100) + "% compra", x + w - 22, y + 21); g.textAlign = "left"; } });
  g.fillStyle = "#8AA0B4"; g.font = "16px system-ui"; g.fillText("1x = volume normal · % compra = fluxo comprador (CVD)", x + 22, H - 22);
  // 4. Operacao aberta (alterna) com volume
  const ops = feed.filter(f => f.asset !== "BTC"); x = P[3][0]; w = P[3][1];
  if (ops.length) { const it = ops[dataI % ops.length]; panelFrame(g, x, w, H, it.title || it.asset, "#FFA94D");
    candlesVol(g, x + 22, 56, w - 44, H - 76, it.cs, { lines: (it.lv || []).map(l => ({ v: l.v, c: l.c, t: l.label })), n: 50 }); }
  else { panelFrame(g, x, w, H, "Operações", "#FFA94D"); g.fillStyle = "#8AA0B4"; g.font = "24px system-ui"; g.fillText("Sem operações abertas.", x + 22, H / 2); }
  // 5. Mapa do mercado 24h (as 16 moedas com mais volume)
  x = P[4][0]; w = P[4][1]; panelFrame(g, x, w, H, "Mercado · 24h", "#68D391");
  const top = U.filter(r => r.volume_24h).sort((p, q) => q.volume_24h - p.volume_24h).slice(0, 16), cw = (w - 44) / 4, chh = (H - 76) / 4;
  top.forEach((r, i) => { const cx = x + 22 + (i % 4) * cw, cy = 56 + Math.floor(i / 4) * chh, ch = r.chg_24h || 0, k = Math.min(1, Math.abs(ch) / 8);
    g.fillStyle = ch >= 0 ? `rgba(62,224,196,${.15 + k * .7})` : `rgba(255,111,138,${.15 + k * .7})`; g.fillRect(cx + 3, cy + 3, cw - 6, chh - 6);
    g.fillStyle = "#fff"; g.font = "700 20px system-ui"; g.fillText(r.asset, cx + 12, cy + 30); g.font = "600 18px system-ui"; g.fillText((ch >= 0 ? "+" : "") + ch.toFixed(1).replace(".", ",") + "%", cx + 12, cy + 56); });
}
function buildAccessories() {
  // parede do fundo: painel de dados gigante (graficos, volume, liquidez)
  boxM(42, 6, .3, mat("#130e33"), 0, 3, -13.2);
  dataTex = canvasTex(3072, 384, drawDataWall);
  dataTex.anisotropy = 4;
  const dw = new THREE.Mesh(new THREE.PlaneGeometry(35.2, 4.4), new THREE.MeshBasicMaterial({ map: dataTex, toneMapped: false })); dw.position.set(-.6, 3.2, -13.03); scene.add(dw);
  boxM(35.6, .1, .14, mat("#B794F4", 1.2), -.6, 5.45, -13); boxM(35.6, .1, .14, mat("#4FD1C5", 1.2), -.6, .95, -13);
  // relogio de parede, no canto do servidor
  clock3d = canvasTex(256, 256, drawClock);
  const ck = new THREE.Mesh(new THREE.CircleGeometry(.75, 40), new THREE.MeshBasicMaterial({ map: clock3d, transparent: true, toneMapped: false })); ck.position.set(18.4, 4.3, -13.02); scene.add(ck);
  // estante com livros e trofeu na Pesquisa
  const sh = new THREE.Group(); sh.position.set(-18.4, 0, 3.6); sh.rotation.y = Math.PI / 2; scene.add(sh);
  boxM(3.2, 2.6, .5, mat("#3a2b20"), 0, 1.3, 0, sh);
  const bc = ["#e05d5d", "#4FD1C5", "#F6C453", "#B794F4", "#63B3ED", "#68D391"];
  for (let r = 0; r < 4; r++) { boxM(3.0, .05, .45, mat("#5a4030"), 0, .25 + r * .62, .03, sh);
    for (let i = 0; i < 9; i++) { if ((i + r) % 4 === 3) continue; const hgt = .38 + ((i * 7 + r * 3) % 4) * .05; boxM(.22, hgt, .34, mat(bc[(i + r) % 6]), -1.3 + i * .32, .28 + r * .62 + hgt / 2, .05, sh); } }
  // bebedouro, impressora, caixotes, candeeiros de pe
  boxM(.5, 1.0, .5, mat("#ddd"), 12.4, .5, 3.4); const wb = new THREE.Mesh(new THREE.CylinderGeometry(.22, .22, .5, 16), mat("#63B3ED", .4, .7)); wb.position.set(12.4, 1.25, 3.4); scene.add(wb);
  boxM(.9, .55, .7, mat("#e8e8ee"), 12.2, .78, 11.2); boxM(.9, .75, .7, mat("#555"), 12.2, .37, 11.2); boxM(.5, .04, .3, mat("#fff"), 12.2, 1.07, 11.3);
  [[-3.6, -2.6], [-3.6, .6], [3.6, 5.4]].forEach(([x, z]) => { const b = new THREE.Mesh(new THREE.CylinderGeometry(.18, .15, .4, 14), mat("#444")); b.position.set(x, .2, z); scene.add(b); });
  [[-18.4, -11.4, "#4FD1C5"], [12.6, 5.4, "#F6C453"], [-3.7, 11.4, "#B794F4"]].forEach(([x, z, c]) => {
    boxM(.08, 2.2, .08, mat("#222"), x, 1.1, z); const sh_ = new THREE.Mesh(new THREE.ConeGeometry(.35, .4, 20, 1, true), mat(c, 1.6)); sh_.position.set(x, 2.25, z); scene.add(sh_);
    const pl = new THREE.PointLight(c, 4, 6); pl.position.set(x, 2, z); scene.add(pl); });
  // pufes no cafe e mesa baixa com portatil na sala de reuniao
  [[9.4, 3.1, "#FF6FB5"], [10.6, 2.6, "#4FD1C5"]].forEach(([x, z, c]) => { const pf = new THREE.Mesh(new THREE.SphereGeometry(.45, 18, 12), mat(c, .3)); pf.scale.y = .6; pf.position.set(x, .27, z); scene.add(pf); });
  boxM(.6, .03, .42, mat("#999"), 7.0, .8, -8.1); const lid = boxM(.6, .38, .03, mat("#777"), 7.0, .99, -8.32); lid.rotation.x = -.25;
  const lsc = new THREE.Mesh(new THREE.PlaneGeometry(.52, .3), new THREE.MeshBasicMaterial({ color: 0x4FD1C5 })); lsc.position.set(7.0, .99, -8.3); lsc.rotation.x = -.25; scene.add(lsc);
  [[6.4, -8.0], [8.3, -7.8], [8.6, -8.3]].forEach(([x, z]) => { const cup = new THREE.Mesh(new THREE.CylinderGeometry(.06, .05, .12, 12), mat("#fff")); cup.position.set(x, .84, z); scene.add(cup); });
  // bancos da mesa do cafe
  [[6.0, -0.4], [7.4, -0.4]].forEach(([x, z]) => { const st = new THREE.Mesh(new THREE.CylinderGeometry(.24, .2, .07, 18), mat("#c08a5a")); st.position.set(x, .47, z); st.castShadow = true; scene.add(st);
    boxM(.06, .44, .06, mat("#222"), x, .22, z); const ft = new THREE.Mesh(new THREE.CylinderGeometry(.2, .2, .03, 14), mat("#222")); ft.position.set(x, .015, z); scene.add(ft); });
  // cadeiras da reuniao
  [[6.5, -9.3, 0], [8.5, -9.3, 0], [6.5, -6.7, Math.PI], [8.5, -6.7, Math.PI]].forEach(([x, z, r]) => {
    const c = new THREE.Group(); c.position.set(x, 0, z); c.rotation.y = r; scene.add(c); boxM(.55, .08, .55, mat("#2b2b40"), 0, .48, 0, c); boxM(.55, .6, .08, mat("#2b2b40"), 0, .8, -.27, c); boxM(.06, .45, .06, mat("#111"), 0, .24, 0, c); });
}
function deskProps(g, f, id) {
  // teclado, rato, caneca, candeeiro, segundo monitor e auscultadores
  boxM(.18, .02, .55, mat("#1d1d2e"), -f * .1, .79, 0, g); boxM(.1, .02, .07, mat("#1d1d2e"), -f * .1, .79, .42, g);
  const mug = new THREE.Mesh(new THREE.CylinderGeometry(.055, .05, .12, 12), mat(["#FF6FB5", "#4FD1C5", "#F6C453", "#fff"][id.length % 4])); mug.position.set(-f * .2, .84, -.7); g.add(mug);
  boxM(.03, .45, .03, mat("#222"), f * .3, 1.0, .82, g); const lamp = new THREE.Mesh(new THREE.ConeGeometry(.1, .14, 14, 1, true), mat("#F6C453", 1.4)); lamp.position.set(f * .22, 1.2, .82); lamp.rotation.z = f * .6; g.add(lamp);
  if (id === "scan" || id === "mon" || id === "afin") {
    const m2 = boxM(.04, .4, .8, mat("#111"), f * .4, 1.08, -.95, g); m2.rotation.y = -f * .5;
  }
  if (id.length % 2) { const hp = new THREE.Mesh(new THREE.TorusGeometry(.1, .025, 8, 16, Math.PI), mat("#333")); hp.position.set(-f * .3, .84, .75); hp.rotation.x = -Math.PI / 2; g.add(hp); }
}

// ---------- radar holografico (Mesa de operacoes) e quadro (Pesquisa) ----------
let radar = null, board = null;
function buildRadar() {
  const g = new THREE.Group(); g.position.set(-15.5, 0, -4.2); scene.add(g);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(2.3, 2.5, .8, 40), mat("#151033")); base.position.y = .4; g.add(base);
  const top = new THREE.Mesh(new THREE.CircleGeometry(2.2, 48), new THREE.MeshBasicMaterial({ color: 0x0c2a33, transparent: true, opacity: .9 }));
  top.rotation.x = -Math.PI / 2; top.position.y = .82; g.add(top);
  [0.75, 1.4, 2.05].forEach(r => { const t = new THREE.Mesh(new THREE.TorusGeometry(r, .025, 6, 64), mat("#4FD1C5", 1.5)); t.rotation.x = Math.PI / 2; t.position.y = .84; g.add(t); });
  const sweep = new THREE.Mesh(new THREE.CircleGeometry(2.1, 24, 0, .7), new THREE.MeshBasicMaterial({ color: 0x4FD1C5, transparent: true, opacity: .25, side: THREE.DoubleSide }));
  sweep.rotation.x = -Math.PI / 2; sweep.position.y = .86; g.add(sweep);
  const blips = new THREE.Group(); blips.position.y = .9; g.add(blips);
  radar = { g, sweep, blips, t: 0 };
  const l = label("Radar", "#4FD1C5", true); l.style.pointerEvents = "auto"; l.style.cursor = "pointer"; l.addEventListener("click", () => API().openZone("ops"));
  labels.push({ el: l, p: new THREE.Vector3(-15.5, 2.4, -4.2) });
}
function updateRadar() {
  const D = API().D(); if (!radar || !D) return;
  radar.blips.clear();
  const J = (D.journal || {}).rows || [], dec = new Set(J.filter(r => r.executed === false).map(r => r.id));
  const act = (D.active_signals || []).filter(s => s.mode !== "PAPER" && !dec.has(s.id));
  const cur = a => ((D.universe || []).find(r => r.asset === a) || {}).price;
  const add = (r, ang, c, h) => { const m = new THREE.Mesh(new THREE.SphereGeometry(.13, 12, 10), mat(c, 2)); m.position.set(Math.cos(ang) * r, 0, Math.sin(ang) * r); radar.blips.add(m);
    const st = new THREE.Mesh(new THREE.CylinderGeometry(.02, .02, h, 6), mat(c, 1.5)); st.position.set(m.position.x, h / 2, m.position.z); radar.blips.add(st); m.position.y = h; };
  act.forEach((s, i) => { const open = s.status === "TRIGGERED"; add(open ? .35 : 1.0, i * 2.4, open ? "#FFA94D" : "#4FD1C5", open ? .9 : .6); });
  (D.universe || []).forEach(r => [r.decision, r.decision_short].forEach(d => {
    if (!d || d.decision !== "WATCHLIST" || !d.plan || d.active_signal) return; const p = cur(r.asset); if (!p) return;
    const lo = d.plan.entry_zone[0], hi = d.plan.entry_zone[1], dist = p < lo ? (lo / p - 1) * 100 : p > hi ? (p / hi - 1) * 100 : 0;
    add(.75 + Math.min(dist, 10) / 10 * 1.3, (r.asset.charCodeAt(0) * 37 % 360) / 57.3, "#63B3ED", .35);
  }));
}
function drawBoard(g) {
  const F = (API().files && API().files()) || {}, rb = F.rb && F.rb.TODAS, lg = F.lg && F.lg.estrategias && F.lg.estrategias.TODAS;
  g.fillStyle = "#f4f2ff"; g.fillRect(0, 0, 512, 320); g.strokeStyle = "#B794F4"; g.lineWidth = 8; g.strokeRect(4, 4, 504, 312);
  g.fillStyle = "#3b2a8f"; g.font = "bold 34px sans-serif"; g.fillText("Contra o acaso", 24, 52);
  g.font = "26px sans-serif"; g.fillStyle = "#222";
  const lines = rb ? [`Histórico: ${rb.r_real.toFixed(2)}R`, `Ao acaso: ${rb.r_acaso_mediana.toFixed(2)}R`, rb.vantagem ? "→ bate o acaso" : "→ ainda não bate o acaso", lg ? `Ao vivo: ${lg.n} sinais (faltam ${Math.max(0, 30 - lg.n)})` : ""] : ["A carregar…"];
  lines.forEach((t, i) => { g.fillStyle = i === 2 ? (rb && rb.vantagem ? "#1a8a6a" : "#c0392b") : "#222"; g.fillText(t, 24, 104 + i * 48); });
  g.fillStyle = "#3b2a8f"; g.fillRect(380, 250, 110, 8); g.fillRect(380, 230, 70, 8); g.fillRect(380, 210, 95, 8);
}
function buildBoard() {
  const t = canvasTex(512, 320, drawBoard);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 3.25), new THREE.MeshBasicMaterial({ map: t, toneMapped: false }));
  // na diagonal: visivel tanto na vista de frente como na vista de lado (telemovel)
  const bg = new THREE.Group(); bg.position.set(-6.2, 0, 4.3); bg.rotation.y = -Math.PI / 4; scene.add(bg);
  m.position.set(0, 2.1, .07); bg.add(m); boxM(5.5, 3.5, .1, mat("#2b2470"), 0, 2.1, 0, bg);
  boxM(.1, .5, .1, mat("#222"), -1.8, .25, 0, bg); boxM(.1, .5, .1, mat("#222"), 1.8, .25, 0, bg);
  board = t;
}


// ---------- pessoas ----------
function label(text, color, zone) {
  const el = document.createElement("div"); el.textContent = text;
  el.style.cssText = `position:absolute;transform:translate(-50%,-100%);pointer-events:none;white-space:nowrap;font:${zone ? "700 11px" : "700 11px"} system-ui,sans-serif;color:${color};text-shadow:0 0 6px ${color}88,0 1px 2px #000`;
  overlay.appendChild(el); return el;
}
// Pessoas de escritorio: corpo articulado (anca, joelho, ombro, cotovelo),
// rosto, cabelo, roupa e acessorios proprios de cada agente.
const STYLE = {
  scan: { skin: "#f1c27d", hair: "#2b1b12", hs: "short", top: "#e8eef7", jacket: "#2d3b55", legs: "#2a2f45", glasses: 1 },
  mon: { skin: "#e0ac69", hair: "#d9a441", hs: "bun", top: "#FFA94D", legs: "#2b2b3a" },
  vig: { skin: "#c68642", hair: "#3a3a3a", hs: "buzz", top: "#4a5568", legs: "#1f2433", beard: 1 },
  news: { skin: "#f1c27d", hair: "#7a2e1a", hs: "long", top: "#F6C453", jacket: "#5a3d2b", legs: "#33281f" },
  afin: { skin: "#8d5524", hair: "#111", hs: "curly", top: "#B794F4", legs: "#252038", glasses: 1 },
  inv: { skin: "#ffdbac", hair: "#e6c07b", hs: "long", top: "#63B3ED", legs: "#1d2a3d" },
  juiz: { skin: "#e0ac69", hair: "#bdbdbd", hs: "short", top: "#f4f4f4", jacket: "#5b2333", legs: "#2a2028", beard: 1, glasses: 1 },
  aud: { skin: "#c68642", hair: "#2b1d12", hs: "short", top: "#68D391", legs: "#1f2b25" },
};
const sm = (c, r = .7) => new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: 0 });
function cap(r, len, m, parent, y) { const g = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 4, 10), m); g.position.y = y; g.castShadow = true; parent.add(g); return g; }
function joint(parent, x, y, z) { const j = new THREE.Group(); j.position.set(x, y, z); parent.add(j); return j; }
function makePerson(a) {
  const S = STYLE[a.id], g0 = new THREE.Group(), g = new THREE.Group(); g0.add(g);
  const skin = sm(S.skin, .55), hair = sm(S.hair, .8), top = sm(S.top, .75), jk = S.jacket ? sm(S.jacket, .7) : null, legs = sm(S.legs, .8), shoe = sm("#151515", .4);
  const hips = joint(g, 0, .95, 0);
  // pernas: coxa -> joelho -> canela -> pe
  const leg = side => { const th = joint(hips, side * .1, 0, 0); cap(.075, .34, legs, th, -.22);
    const kn = joint(th, 0, -.45, 0); cap(.062, .34, legs, kn, -.21);
    const ft = new THREE.Mesh(new THREE.BoxGeometry(.11, .07, .25), shoe); ft.position.set(0, -.43, .05); ft.castShadow = true; kn.add(ft); return { th, kn }; };
  const L = leg(-1), Rr = leg(1);
  // tronco
  const spine = joint(hips, 0, 0, 0);
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(.16, .32, 4, 12), jk || top); torso.scale.set(1.28, 1, .78); torso.position.y = .3; torso.castShadow = true; spine.add(torso);
  const belt = new THREE.Mesh(new THREE.CylinderGeometry(.17, .17, .05, 16), sm("#222", .5)); belt.scale.set(1.2, 1, .8); belt.position.y = .04; spine.add(belt);
  if (jk) { const shirt = new THREE.Mesh(new THREE.PlaneGeometry(.12, .3), top); shirt.position.set(0, .36, .128); spine.add(shirt);
    const tie = new THREE.Mesh(new THREE.BoxGeometry(.04, .2, .01), sm(a.c, .5)); tie.position.set(0, .34, .133); spine.add(tie); }
  else { const badge = new THREE.Mesh(new THREE.BoxGeometry(.07, .09, .01), sm("#fff", .3)); badge.position.set(.08, .4, .126); spine.add(badge); }
  // bracos: ombro -> cotovelo -> mao
  const arm = side => { const sh = joint(spine, side * .25, .5, 0); cap(.055, .22, jk || top, sh, -.15);
    const el = joint(sh, 0, -.3, 0); cap(.047, .2, jk || top, el, -.13);
    const hd = new THREE.Mesh(new THREE.SphereGeometry(.05, 10, 8), skin); hd.position.y = -.29; el.add(hd); return { sh, el, hd }; };
  const AL = arm(-1), AR = arm(1);
  const cup = new THREE.Mesh(new THREE.CylinderGeometry(.04, .035, .09, 12), sm("#fafafa", .3)); cup.position.set(0, -.3, .05); cup.visible = false; AR.el.add(cup);
  // cabeca
  const neck = cap(.045, .06, skin, spine, .62);
  const head = joint(spine, 0, .78, 0);
  const sk = new THREE.Mesh(new THREE.SphereGeometry(.115, 20, 16), skin); sk.scale.set(.95, 1.1, 1); sk.castShadow = true; head.add(sk);
  [-1, 1].forEach(sd => { const ear = new THREE.Mesh(new THREE.SphereGeometry(.025, 8, 6), skin); ear.position.set(sd * .11, 0, 0); head.add(ear);
    const eye = new THREE.Mesh(new THREE.SphereGeometry(.014, 8, 6), sm("#1a1a1a", .2)); eye.position.set(sd * .042, .02, .105); head.add(eye);
    const br = new THREE.Mesh(new THREE.BoxGeometry(.04, .009, .01), hair); br.position.set(sd * .043, .052, .107); head.add(br); });
  const nose = new THREE.Mesh(new THREE.SphereGeometry(.016, 8, 6), skin); nose.position.set(0, -.008, .118); head.add(nose);
  const mouth = new THREE.Mesh(new THREE.BoxGeometry(.04, .007, .01), sm("#8a4a3a", .5)); mouth.position.set(0, -.052, .106); head.add(mouth);
  // cabelo
  const capH = new THREE.Mesh(new THREE.SphereGeometry(.122, 20, 14, 0, Math.PI * 2, 0, S.hs === "buzz" ? 1.2 : 1.5), hair); capH.scale.set(.98, 1.1, 1.04); capH.position.set(0, .012, -.008); head.add(capH);
  if (S.hs === "long") { const back = new THREE.Mesh(new THREE.CapsuleGeometry(.1, .16, 4, 10), hair); back.scale.set(1.15, 1, .6); back.position.set(0, -.1, -.06); head.add(back); }
  if (S.hs === "bun") { const bun = new THREE.Mesh(new THREE.SphereGeometry(.055, 12, 10), hair); bun.position.set(0, .1, -.1); head.add(bun); }
  if (S.hs === "curly") for (let i = 0; i < 9; i++) { const c = new THREE.Mesh(new THREE.SphereGeometry(.045, 8, 6), hair); const an = i / 9 * Math.PI * 2; c.position.set(Math.cos(an) * .09, .07 + (i % 2) * .02, Math.sin(an) * .08 - .01); head.add(c); }
  if (S.beard) { const bd = new THREE.Mesh(new THREE.SphereGeometry(.09, 14, 10, 0, Math.PI * 2, Math.PI * .55, Math.PI * .45), hair); bd.scale.set(1, 1.1, 1.05); bd.position.set(0, -.012, .012); head.add(bd); }
  if (S.glasses) { const gm = sm("#111", .3); [-1, 1].forEach(sd => { const r = new THREE.Mesh(new THREE.TorusGeometry(.026, .005, 6, 16), gm); r.position.set(sd * .043, .02, .118); head.add(r); });
    const br = new THREE.Mesh(new THREE.BoxGeometry(.03, .005, .005), gm); br.position.set(0, .022, .12); head.add(br); }
  // anel de selecao e halo com a cor do agente
  const ring = new THREE.Mesh(new THREE.RingGeometry(.42, .5, 32), new THREE.MeshBasicMaterial({ color: 0xFFA94D, transparent: true, opacity: 0 }));
  ring.rotation.x = -Math.PI / 2; ring.position.y = .03; g0.add(ring);
  const halo = new THREE.Mesh(new THREE.RingGeometry(.3, .35, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color(a.c), transparent: true, opacity: .5, toneMapped: false }));
  halo.rotation.x = -Math.PI / 2; halo.position.y = .025; g0.add(halo);
  g0.traverse(o => { o.userData.agent = a.id; });
  g0.scale.setScalar(1.18); scene.add(g0);
  const desk = DESK[a.id], seat = desk.p.clone().add(V(-desk.f * .95, 0));
  g0.position.copy(seat);
  return { a, g: g0, body: g, rig: { hips, spine, head, L, R: Rr, AL, AR, cup, torso }, ring, zone: desk.z, path: [], mode: "work", spot: null, wait: 0, sit: true, seat,
    face: desk.f > 0 ? Math.PI / 2 : -Math.PI / 2, name: label(a.nm, a.c), ph: Math.random() * 6 };
}
function route(p, target, tz) {
  const pts = []; const here = p.g.position;
  if (p.zone !== tz) {
    const d1 = ZONES[p.zone].door, d2 = ZONES[tz].door;
    const lane = p.lane || 0; pts.push(d1.clone(), V(lane, d1.z), V(lane, d2.z), d2.clone());
  }
  pts.push(target.clone()); return pts;
}
function stateOf(id) { return (API().states() || {})[id] || "pause"; }
function decide(p) {
  const st = stateOf(p.a.id); p.state = st;
  if (st === "work") { if (p.mode !== "work") { p.mode = "work"; p.spot = null; p.path = route(p, p.seat, DESK[p.a.id].z); p.dest = DESK[p.a.id].z; p.sit = false; } return; }
  if (p.mode === "work" || (!p.path.length && p.wait <= 0)) {
    const used = new Set(people.filter(q => q.spot != null).map(q => q.spot));
    let opts = SPOTS.map((s, k) => k).filter(k => !used.has(k) && (st !== "sleep" || SPOTS[k].k === "sofa" || SPOTS[k].k === "reuniao"));
    if (!opts.length) opts = SPOTS.map((s, k) => k).filter(k => !used.has(k));
    const k = opts[Math.floor(Math.random() * opts.length)]; if (k == null) return;
    p.spot = k; p.mode = st; p.sit = false; p.path = route(p, SPOTS[k].p, SPOTS[k].z); p.dest = SPOTS[k].z;
    p.wait = st === "sleep" ? 1e9 : 14 + Math.random() * 22;
  }
}
function animate(p, dt, t) {
  const pos = p.g.position;
  if (p.path.length) {
    const tg = p.path[0], d = tg.clone().sub(pos); d.y = 0; const L = d.length(), v = 1.8 * dt;
    if (L <= v) { pos.copy(tg); p.path.shift(); if (!p.path.length) { p.zone = p.dest; p.sit = p.mode === "work" || (p.spot != null && !!SPOTS[p.spot].sit); } }
    else { pos.addScaledVector(d.normalize(), v); p.g.rotation.y = Math.atan2(d.x, d.z); }
  } else if (p.mode !== "work" && p.mode !== "sleep") p.wait -= dt;
  const walking = p.path.length > 0;
  if (!walking) p.g.rotation.y = p.mode === "work" ? p.face : (p.spot != null && SPOTS[p.spot].r != null ? SPOTS[p.spot].r : p.g.rotation.y);
  const sit = p.sit && !walking, typing = p.mode === "work" && sit, sleep = p.mode === "sleep" && !walking;
  const cafe = !walking && p.spot != null && SPOTS[p.spot].k === "cafe";
  const k = p.rig, ph = t * 7.5 + p.ph, sw = walking ? Math.sin(ph) : 0;
  p.ring.material.opacity = API().sel() === p.a.id ? .9 : 0;
  // altura da anca: de pe 0, sentado desce ate a cadeira; ligeiro balanco ao andar
  k.hips.position.y = sit ? .5 : .95 + (walking ? Math.abs(Math.cos(ph)) * .025 : 0);
  const leg = (P, s) => {
    if (sit) { P.th.rotation.x = -1.45; P.kn.rotation.x = 1.4; return; }
    P.th.rotation.x = s * .55; P.kn.rotation.x = walking ? Math.max(0, -s) * .9 + .08 : 0;
  };
  leg(k.L, sw); leg(k.R, -sw);
  // bracos
  if (typing) {
    k.AL.sh.rotation.x = -.75; k.AR.sh.rotation.x = -.75; k.AL.sh.rotation.z = .22; k.AR.sh.rotation.z = -.22;
    k.AL.el.rotation.x = -.85 + Math.sin(t * 15 + p.ph) * .07; k.AR.el.rotation.x = -.85 + Math.cos(t * 13 + p.ph) * .07;
  } else if (walking) {
    k.AL.sh.rotation.set(-sw * .45, 0, .06); k.AR.sh.rotation.set(sw * .45, 0, -.06); k.AL.el.rotation.x = -.25; k.AR.el.rotation.x = -.25;
  } else {
    k.AL.sh.rotation.set(sit ? -.3 : 0, 0, .08); k.AR.sh.rotation.set(cafe ? -.45 : (sit ? -.3 : 0), 0, -.08);
    k.AL.el.rotation.x = sit ? -.6 : -.08; k.AR.el.rotation.x = cafe ? -1.35 : (sit ? -.6 : -.08);
  }
  k.cup.visible = cafe;
  // tronco e cabeca: respirar, inclinar ao escrever, dormir encostado
  const br = Math.sin(t * 1.6 + p.ph) * .012;
  k.torso.scale.y = 1 + br; k.spine.rotation.x = sleep ? -.22 : (typing ? .12 : (walking ? .05 : 0));
  k.head.rotation.x = sleep ? .55 : (typing ? .12 : Math.sin(t * .5 + p.ph) * .05);
  k.head.rotation.y = !walking && !typing && !sleep ? Math.sin(t * .35 + p.ph) * .35 : 0;
}

// ---------- ciclo ----------
function project(v) { const p = v.clone().project(cam), r = R.domElement; return { x: (p.x + 1) / 2 * r.clientWidth, y: (1 - p.y) / 2 * r.clientHeight, ok: p.z < 1 }; }
function placeOverlays(dt) {
  labels.forEach(l => { const s = project(l.p); l.el.style.left = s.x + "px"; l.el.style.top = s.y + "px"; l.el.style.display = s.ok ? "" : "none"; });
  people.forEach(p => { const s = project(p.g.position.clone().setY(p.g.position.y + 2.5)); p.name.style.left = s.x + "px"; p.name.style.top = s.y + "px"; p.name.style.display = API().sel() === p.a.id ? "" : "none";
    p.name.textContent = p.a.nm + (p.mode === "sleep" && !p.path.length ? " 💤" : ""); });
  const od = API().data(); if (!od) return;
  bubAt -= dt; const sel = API().sel();
  if (bubAt <= 0 || (sel && bubWho !== sel)) {
    const cand = sel ? people.filter(p => p.a.id === sel) : people.filter(p => od[p.a.id].on || Math.random() < .3);
    const p = cand[(bubI++) % Math.max(1, cand.length)] || people[0]; bubWho = p.a.id; bubAt = 4.5;
    const o = od[p.a.id]; bubble.innerHTML = `<b>${p.a.nm}</b><br>${o.msgs[bubI % o.msgs.length]}`; bubble.style.borderColor = p.a.c;
  }
  const p = people.find(q => q.a.id === bubWho); if (!p) return;
  const s = project(p.g.position.clone().setY(p.g.position.y + 2.7)); const w = bubble.offsetWidth, W = R.domElement.clientWidth;
  bubble.style.left = Math.max(4, Math.min(W - w - 4, s.x - w / 2)) + "px"; const hud = document.getElementById("hud"), top = hud ? hud.offsetHeight + 4 : 4; bubble.style.top = Math.max(top, s.y - bubble.offsetHeight) + "px";
}
let ledT = 0, tvT = 0, composer = null, bloom = null;
function frame() {
  if (!running) return; requestAnimationFrame(frame);
  if (document.body.classList.contains("sheet-open") || !visible || document.hidden) return;
  const dt = Math.min(.1, clock.getDelta()), t = clock.elapsedTime;
  people.forEach(p => { if (!p.path.length || (stateOf(p.a.id) === "work" && p.mode !== "work")) decide(p); animate(p, dt, t); });
  // monitores ligados so para quem esta a trabalhar e sentado
  monTex.userData.draw(monTex.userData.c.getContext("2d"), t); monTex.needsUpdate = true;
  people.forEach(p => { const on = p.mode === "work" && p.sit && !p.path.length, m = monOn[p.a.id].material, tx = deskTex[p.a.id] || monTex;
    if (on && m.map !== tx) { m.map = tx; m.color.set(0xffffff); m.needsUpdate = true; } else if (!on && m.map) { m.map = null; m.color.set(0x0b1424); m.needsUpdate = true; } });
  const nowMs = performance.now();
  if (nowMs - (frame.ledAt || 0) > 350) { frame.ledAt = nowMs; drawLeds(ledTex.userData.c.getContext("2d")); ledTex.needsUpdate = true; }
  // ecras com relogio real (nao depende da taxa de imagens) e redesenho quando
  // chegam velas novas
  const feedN = ((window.chartFeed && window.chartFeed()) || []).filter(f => f.cs).length;
  if (nowMs - (frame.wallAt || 0) > 7000 || feedN !== frame.feedN) { frame.wallAt = nowMs; frame.feedN = feedN; wallI++; if (wallTex) { drawWall(wallTex.userData.c.getContext("2d")); wallTex.needsUpdate = true; }
    const feed = (window.chartFeed && window.chartFeed()) || [];
    for (const [id, tx] of Object.entries(deskTex)) { const list = id === "mon" ? feed.filter(f => f.asset !== "BTC") : feed.filter(f => f.asset === "BTC").concat(feed);
      const it = list.length ? list[(wallI + (id === "mon" ? 1 : 0)) % list.length] : null; const g = tx.userData.c.getContext("2d");
      if (it) window.drawCandles(g, 512, 256, it.cs, it.lv, { title: it.asset, axis: false, n: 40 }); tx.needsUpdate = true; }
    if (clock3d) { drawClock(clock3d.userData.c.getContext("2d")); clock3d.needsUpdate = true; }
    if (dataTex) { dataI++; drawDataWall(dataTex.userData.c.getContext("2d")); dataTex.needsUpdate = true; } }
  if (nowMs - (frame.tvAt || -1e9) > 30000 || tvT <= 0) { frame.tvAt = nowMs; tvT = 30; drawTV(tvTex.userData.c.getContext("2d")); tvTex.needsUpdate = true; updateRadar(); drawBoard(board.userData.c.getContext("2d")); board.needsUpdate = true; }
  if (radar) { radar.sweep.rotation.z -= dt * 1.4; radar.blips.children.forEach((b, i) => { if (b.geometry.type === "SphereGeometry") b.scale.setScalar(1 + Math.sin(t * 4 + i) * .15); }); }
  ctl.update(); if (composer) composer.render(); else R.render(scene, cam); placeOverlays(dt);
}
function resize() {
  const w = box.clientWidth, h = box.clientHeight > 200 ? box.clientHeight : Math.round(w * (w < 600 ? .95 : .62));
  R.setSize(w, h, false); R.domElement.style.width = w + "px"; R.domElement.style.height = h + "px"; cam.aspect = w / h; cam.updateProjectionMatrix();
  if (composer) { composer.setSize(w, h); bloom.resolution.set(w / 2, h / 2); }
  // telemovel na vertical: afastar a camara para caber o escritorio todo
  // na vertical: vista de lado (o escritorio comprido fica na profundidade),
  // com a Mesa de operações e a Pesquisa mais perto
  if (!resize.done) { if (cam.aspect < .8) { cam.position.set(-37, 37, -1.5); ctl.target.set(-5, 0, -1.5); } else if (cam.aspect < 1.1) cam.position.set(11, 21, 24); else cam.position.set(9, 17, 19); resize.done = true; }
}

function init(container) {
  if (!supported()) return false;
  box = container; box.innerHTML = ""; if (getComputedStyle(box).position === "static") box.style.position = "relative";
  R = new THREE.WebGLRenderer({ antialias: true, alpha: false }); R.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  R.setClearColor(0x0a0820); R.domElement.style.borderRadius = "0"; R.domElement.style.display = "block"; R.domElement.style.touchAction = "none";
  box.appendChild(R.domElement);
  overlay = document.createElement("div"); overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden;border-radius:12px"; box.appendChild(overlay);
  bubble = document.createElement("div"); bubble.className = "obub3"; overlay.appendChild(bubble);
  if (!document.getElementById("odetail")) { const det = document.createElement("div"); det.id = "odetail"; box.parentNode.insertBefore(det, box.nextSibling); }
  scene = new THREE.Scene(); scene.fog = new THREE.Fog(0x0a0820, 38, 70);
  cam = new THREE.PerspectiveCamera(42, 1.3, .1, 200); cam.position.set(9, 17, 19);
  ctl = new OrbitControls(cam, R.domElement); ctl.target.set(0, 0, 0); ctl.enableDamping = true; ctl.minDistance = 10; ctl.maxDistance = 70;
  ctl.maxPolarAngle = 1.25; ctl.minPolarAngle = .35; ctl.enablePan = false;
  scene.add(new THREE.HemisphereLight(0xd6ccff, 0x2a1f6e, 1.55));
  const dl = new THREE.DirectionalLight(0xfff4e8, 1.35); dl.position.set(8, 20, 10); scene.add(dl);
  // sombras suaves (desligadas em telemoveis fracos, ver qualidade abaixo)
  const lowEnd = (navigator.hardwareConcurrency || 4) <= 4 && /iPhone|Android/.test(navigator.userAgent) && Math.min(screen.width, screen.height) < 380;
  if (!lowEnd) { R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFSoftShadowMap; dl.castShadow = true; dl.shadow.mapSize.set(1024, 1024);
    Object.assign(dl.shadow.camera, { left: -24, right: 24, top: 16, bottom: -16, near: 1, far: 60 }); dl.shadow.bias = -.0008; }
  const pl1 = new THREE.PointLight(0xff6fb5, 30, 26); pl1.position.set(0, 4, 0); scene.add(pl1);
  const pl2 = new THREE.PointLight(0x4fd1c5, 25, 24); pl2.position.set(-10, 4, -6); scene.add(pl2);
  R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.2; R.outputColorSpace = THREE.SRGBColorSpace;
  try {
    composer = new EffectComposer(R); composer.addPass(new RenderPass(scene, cam));
    bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), .55, .45, .9); composer.addPass(bloom); composer.addPass(new OutputPass());
  } catch (e) { composer = null; }
  monTex = canvasTex(256, 160, drawMon);
  buildRoom(); buildAccessories(); Object.keys(DESK).forEach(buildDesk); buildRadar(); buildBoard(); updateRadar();
  people = API().agents.map(makePerson);
  // ao abrir: quem esta em pausa ja esta num sitio de descanso (sem marcha em
  // grupo pelo corredor), cada um com a sua faixa e o seu ritmo
  const used = new Set();
  people.forEach((p, i) => {
    p.lane = (i - 3.5) * .32; const st = stateOf(p.a.id); p.state = st;
    if (st === "work") return;
    const opts = SPOTS.map((s, k) => k).filter(k => !used.has(k) && (st !== "sleep" || ["sofa", "reuniao"].includes(SPOTS[k].k)));
    const k = opts[Math.floor(Math.random() * opts.length)]; if (k == null) return; used.add(k);
    p.spot = k; p.mode = st; p.zone = SPOTS[k].z; p.dest = SPOTS[k].z; p.g.position.copy(SPOTS[k].p); p.sit = !!SPOTS[k].sit;
    p.wait = st === "sleep" ? 1e9 : 6 + Math.random() * 30;
  });
  // toque num agente (distingue de arrastar a camara)
  let down = null; const ray = new THREE.Raycaster(), m = new THREE.Vector2();
  R.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  R.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 8) return;
    const r = R.domElement.getBoundingClientRect(); m.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    ray.setFromCamera(m, cam); const hit = ray.intersectObjects(people.map(p => p.g), true)[0];
    if (hit) { API().select(hit.object.userData.agent); bubAt = 0; return; }
    const zh = ray.intersectObjects(zoneHits, false)[0]; if (zh) API().openZone(zh.object.userData.zone);
  });
  new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(box);
  addEventListener("resize", resize); resize();
  clock = new THREE.Clock(); running = true; frame();
  return true;
}
window.Office3D = { init, supported, refresh: () => { tvT = 0; } };
