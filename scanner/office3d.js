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
  aud: { z: "ctrl", p: V(10.5, 7.4), f: 1 },
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
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(42, 28), mat("#4f545c"));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  const grid = new THREE.GridHelper(42, 42, 0x5d626a, 0x575b63); grid.position.y = .01; scene.add(grid);
  // corredor com linhas de neon
  [-1.6, 1.6].forEach(x => boxM(.06, .02, 26, mat("#d9d4c7", .15), x, .02, 0));
  [-0.5, 0.5].forEach(x => boxM(.03, .02, 26, mat("#bfb8a8", .1), x, .02, 0));
  // zonas: tapete, paredes de vidro, arestas de neon
  for (const [k, Z] of Object.entries(ZONES)) {
    const w = Z.x[1] - Z.x[0], d = Z.z[1] - Z.z[0], cx = (Z.x[0] + Z.x[1]) / 2, cz = (Z.z[0] + Z.z[1]) / 2;
    if (k !== "srv") { const rug = new THREE.Mesh(new THREE.PlaneGeometry(w - .4, d - .4), mat(k === "cafe" ? "#6b5139" : "#3d4450")); rug.rotation.x = -Math.PI / 2; rug.position.set(cx, .015, cz); scene.add(rug); }
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
    [[Z.x[0], Z.z[0]], [Z.x[1], Z.z[0]], [Z.x[1], Z.z[1]], [Z.x[0], Z.z[1]]].forEach(([x, z]) => k !== "srv" && boxM(.07, h, .07, mat("#c9ccd2", .05), x, h / 2, z));
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
  // mesa redonda: ecra na parede esquerda da sala de reuniao (votos reais dos lutadores)
  mesaTex = canvasTex(512, 384, drawMesa);
  const ms = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 2.55), new THREE.MeshBasicMaterial({ map: mesaTex, toneMapped: false }));
  ms.position.set(3.12, 1.8, -8); ms.rotation.y = Math.PI / 2; scene.add(ms);
  const mh = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 2.55), new THREE.MeshBasicMaterial({ visible: false })); mh.position.copy(ms.position); mh.rotation.y = ms.rotation.y; mh.userData.zone = "mesa"; scene.add(mh); zoneHits.push(mh);
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
let radar = null, board = null, mesaTex = null, mesaI = 0;
// mesa redonda: uma moeda de cada vez, com o voto de cada lutador vivo
function drawMesa(g) {
  const D = (API() && API().D && API().D()) || {}, M = D.mesa || [];
  g.fillStyle = "#101a2e"; g.fillRect(0, 0, 512, 384); g.strokeStyle = "#68D391"; g.lineWidth = 6; g.strokeRect(3, 3, 506, 378);
  g.fillStyle = "#9AE6B4"; g.font = "bold 26px sans-serif"; g.fillText("🗣️ Mesa redonda", 18, 40);
  if (!M.length) { g.fillStyle = "#cbd5e0"; g.font = "20px sans-serif"; g.fillText("à espera do próximo scan", 18, 90); return; }
  const m = M[mesaI % M.length], r = (D.universe || []).find(x => x.asset === m.asset) || {}, v = r.debate || [];
  g.fillStyle = "#fff"; g.font = "bold 30px sans-serif"; g.fillText(m.asset, 18, 82);
  g.fillStyle = m.a_favor ? "#68D391" : "#a0aec0"; g.font = "22px sans-serif"; g.fillText(`${m.a_favor} de ${m.votantes} entravam`, 150, 80);
  g.font = "19px sans-serif";
  v.slice(0, 10).forEach((x, i) => { const col = i % 2, row = Math.floor(i / 2), X = 18 + col * 248, Y = 122 + row * 50;
    g.fillStyle = x.voto === "entra" ? "#1f4d3a" : "#2a2f45"; g.fillRect(X, Y - 26, 236, 40);
    g.fillStyle = x.voto === "entra" ? "#9AE6B4" : "#cbd5e0"; g.fillText(`${x.voto === "entra" ? "✅" : "❌"} ${x.persona}`, X + 8, Y);
  });
  g.fillStyle = "#718096"; g.font = "15px sans-serif"; g.fillText(`${(mesaI % M.length) + 1}/${M.length} · toca para ver as razões`, 18, 372);
}
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
  const J = (D.journal || {}).rows || [], dec = new Set(J.filter(r => r.executed === false || r.user_closed_flag).map(r => r.id));
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



// ---------- arena: as estrategias a lutar (dados reais de D.arena) ----------
// Cada estrategia e um lutador. Quem lidera fica no pedestal com coroa, quem
// esta a competir treina em pares, quem ganha o direito ao dinheiro real tem
// um feixe dourado, e quem morre vai para o cemiterio ao lado do ringue.
const ARENA_C = V(27, 0);
let arenaG = null, arenaTex = null, arenaSig = "", fighters = [], arenaLabels = [];
const SHORT = { BREAKOUT: "Quebra", PULLBACK: "Recuo", LIQUIDITY_SWEEP: "Sweep", RANGE: "Range",
  TREND_DAILY: "Tendência", BOUNCE_G0: "Bounce G0", BOUNCE_V1: "Bounce V1", BOUNCE_V2: "Bounce V2", BOUNCE_V3: "Bounce V3", BOUNCE_1H: "Bounce 1H", BOUNCE_X30: "Bounce RSI30", DIP_TREND: "Recuo forte", CAPITULACAO: "Capitulação", BOUNCE_FLUXO: "Bounce fluxo", BOUNCE_FORTE: "Bounce forte", BOUNCE_SQUEEZE: "Bounce squeeze", BOUNCE_ISOLADA: "Bounce isolada", BOUNCE_DESALAV: "Desalavancagem", BOUNCE_MACRO: "Macro favorável", BOUNCE_MEDO: "Medo macro", BOUNCE_ABSORCAO: "Absorção", BOUNCE_LSR: "Long/short", TURTLE: "Tartarugas", SQUEEZE_BB: "Compressão", MOMENTUM: "Momentum", REJEITADOS: "Rejeitados" };
const FCOL = ["#4FD1C5", "#FF6FB5", "#F6C453", "#B794F4", "#63B3ED", "#68D391", "#FFA94D", "#FC8181", "#90CDF4", "#FBD38D", "#9AE6B4", "#D6BCFA"];
// no 3D mostra-se a amostra maior: o combate de 90 dias (forma recente) quando
// existe, senao os sinais ao vivo
function arenaRows() { const A = (API().D() || {}).arena; return ((A && A.classificacao) || []).map(b => { const f = b.forma;
  return f && f.n > b.n ? Object.assign({}, b, { n: f.n, wins: f.wins, avg_r: f.avg_r, ultimas: f.ultimas || [], live_n: b.n, src: "90 dias" }) : b; }); }
function drawArenaBoard(g) {
  const W = 768, H = 512, rows = arenaRows();
  const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, "#14082e"); bg.addColorStop(1, "#060312"); g.fillStyle = bg; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#FF6FB5"; g.lineWidth = 8; g.strokeRect(4, 4, W - 8, H - 8);
  g.fillStyle = "#FF6FB5"; g.font = "800 46px system-ui"; g.fillText("⚔ ARENA", 28, 62);
  g.fillStyle = "#c9c2ee"; g.font = "500 20px system-ui"; g.fillText("combate de 90 dias · R médio contra o acaso", 270, 58);
  if (!rows.length) { g.fillStyle = "#c9c2ee"; g.font = "28px system-ui"; g.fillText("A carregar a classificação…", 28, 140); return; }
  rows.slice(0, 9).forEach((b, i) => {
    const y = 108 + i * 44, dead = b.estado === "MORTA", up = b.estado === "SOBE";
    g.fillStyle = i % 2 ? "#ffffff08" : "#ffffff12"; g.fillRect(20, y - 30, W - 40, 40);
    g.fillStyle = dead ? "#6b6585" : up ? "#F6C453" : "#ffffff"; g.font = "700 26px system-ui";
    g.fillText(`${i + 1}. ${b.persona ? b.persona + " · " : ""}${SHORT[b.id] || b.id}`, 32, y);
    g.font = "600 24px system-ui"; g.fillStyle = "#c9c2ee"; g.fillText(`${b.n} op.`, 330, y);
    const r = b.avg_r; g.fillStyle = r == null ? "#8a83ad" : r > 0 ? "#68D391" : "#FC8181";
    g.fillText(r == null ? "–" : (r > 0 ? "+" : "") + r.toFixed(2).replace(".", ",") + "R", 440, y);
    g.fillStyle = dead ? "#8a83ad" : up ? "#F6C453" : "#4FD1C5";
    g.fillText(dead ? "💀 morta" : up ? "🏆 sobe" : "⚔ a lutar", 580, y);
  });
}
function robotFighter(col, dead) {
  const g = new THREE.Group(), body = new THREE.Group(); g.add(body);
  const c = new THREE.Color(dead ? "#6b6585" : col);
  const m = new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: dead ? .05 : .35, roughness: .4, metalness: .3, transparent: dead, opacity: dead ? .55 : 1 });
  const dark = new THREE.MeshStandardMaterial({ color: "#1b1730", roughness: .6, transparent: dead, opacity: dead ? .55 : 1 });
  const glove = new THREE.MeshStandardMaterial({ color: dead ? "#555" : "#e53e3e", roughness: .4, transparent: dead, opacity: dead ? .55 : 1 });
  const hips = joint(body, 0, .95, 0);
  const leg = sd => { const th = joint(hips, sd * .12, 0, 0); cap(.085, .36, dark, th, -.24); const kn = joint(th, 0, -.48, 0); cap(.07, .34, dark, kn, -.21); return { th, kn }; };
  const L = leg(-1), Rr = leg(1);
  const spine = joint(hips, 0, 0, 0);
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(.19, .32, 4, 12), m); torso.scale.set(1.25, 1, .8); torso.position.y = .32; torso.castShadow = true; spine.add(torso);
  const arm = sd => { const sh = joint(spine, sd * .3, .52, 0); cap(.065, .22, m, sh, -.15); const el = joint(sh, 0, -.3, 0); cap(.055, .18, m, el, -.12);
    const gl = new THREE.Mesh(new THREE.SphereGeometry(.09, 12, 10), glove); gl.position.y = -.27; el.add(gl); return { sh, el }; };
  const AL = arm(-1), AR = arm(1);
  const head = joint(spine, 0, .82, 0);
  const sk = new THREE.Mesh(new THREE.SphereGeometry(.15, 18, 14), m); head.add(sk);
  const visor = new THREE.Mesh(new THREE.BoxGeometry(.22, .06, .05), new THREE.MeshBasicMaterial({ color: dead ? 0x333333 : 0xffffff, toneMapped: false })); visor.position.set(0, .02, .13); head.add(visor);
  g.scale.setScalar(1.25);
  return { g, body, rig: { hips, spine, head, L, R: Rr, AL, AR } };
}

// lutadores com aspeto de pessoas reais (o mesmo corpo articulado do
// escritorio), com luvas de boxe; o aspeto e estavel para cada analista
const FEM = new Set(["Rita", "Vera", "Violeta", "Raquel", "Leonor", "Matilde", "Carolina", "Beatriz", "Mariana", "Francisca", "Clara", "Joana", "Catarina", "Lara", "Sofia", "Marta", "Inês", "Carla", "Patrícia", "Diana", "Fernanda", "Isabel"]);
const SKINS = ["#ffdbac", "#f1c27d", "#e0ac69", "#c68642", "#8d5524"], HAIRS = ["#1a1a1a", "#3b2a1a", "#6b3b1f", "#b5803a", "#d9b26a", "#7a2e1a"];
function hsh(t) { let h = 7; for (const c of String(t)) h = (h * 31 + c.charCodeAt(0)) % 9973; return h; }
function fighter(col, dead, id, persona) {
  const nm = (persona || "").replace(" Jr.", ""), h = hsh(id || nm), fem = FEM.has(nm);
  const key = "fx_" + (id || nm || h);
  STYLE[key] = { skin: SKINS[h % SKINS.length], hair: HAIRS[(h >> 2) % HAIRS.length], hs: fem ? (h % 2 ? "long" : "bun") : ["short", "buzz", "curly"][h % 3],
    top: col, legs: "#1d1b2e", beard: !fem && h % 4 === 0 ? 1 : 0, glasses: h % 5 === 0 ? 1 : 0 };
  DESK[key] = { z: "srv", p: V(0, 0), f: 1 };
  const p = makePerson({ id: key, nm: nm || "?", c: col });
  scene.remove(p.g); p.name.remove();
  const glove = new THREE.MeshStandardMaterial({ color: dead ? "#555" : "#d62f2f", roughness: .35 });
  [p.rig.AL, p.rig.AR].forEach(a => { const gl = new THREE.Mesh(new THREE.SphereGeometry(.075, 12, 10), glove); gl.position.y = -.29; a.el.add(gl); });
  if (dead) p.g.traverse(o => { if (o.isMesh) o.material = new THREE.MeshStandardMaterial({ color: "#6b6585", transparent: true, opacity: .5, roughness: .8 }); });
  p.g.scale.setScalar(1.05);
  return { g: p.g, rig: p.rig };
}
function buildArena() {
  arenaG = new THREE.Group(); scene.add(arenaG);
  // chao da ala da arena (o escritorio acaba nos servidores)
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(14, 28), mat("#3a3e46")); fl.rotation.x = -Math.PI / 2; fl.position.set(26.5, 0, 0); fl.receiveShadow = true; scene.add(fl);
  const gr = new THREE.GridHelper(14, 14, 0x4c5159, 0x464a52); gr.position.set(26.5, .012, 0); scene.add(gr);
  // ringue: plataforma, cordas de neon e postes
  const plat = new THREE.Mesh(new THREE.CylinderGeometry(5.6, 5.9, .35, 8), mat("#2c2f38")); plat.position.set(ARENA_C.x, .175, ARENA_C.z); plat.receiveShadow = true; plat.castShadow = true; scene.add(plat);
  const top = new THREE.Mesh(new THREE.CircleGeometry(5.4, 8), mat("#34445f")); top.rotation.x = -Math.PI / 2; top.position.set(ARENA_C.x, .36, ARENA_C.z); scene.add(top);
  const logo = new THREE.Mesh(new THREE.RingGeometry(1.6, 1.75, 48), new THREE.MeshBasicMaterial({ color: 0xFF6FB5, toneMapped: false })); logo.rotation.x = -Math.PI / 2; logo.position.set(ARENA_C.x, .37, ARENA_C.z); scene.add(logo);
  const posts = [];
  for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2 + Math.PI / 8; const x = ARENA_C.x + Math.cos(a) * 5.3, z = ARENA_C.z + Math.sin(a) * 5.3;
    boxM(.14, 1.6, .14, mat("#FF6FB5", .9), x, 1.15, z); posts.push(new THREE.Vector3(x, 0, z)); }
  [0.95, 1.4].forEach((h, k) => line(posts.concat([posts[0]]).map(p => p.clone().setY(h)), k ? 0xFF6FB5 : 0x4FD1C5));
  // placar
  arenaTex = canvasTex(768, 512, drawArenaBoard);
  // placar virado para a vista do telemovel
  const sbg = new THREE.Group(); sbg.position.set(33.3, 0, -1); sbg.rotation.y = -Math.PI / 2; scene.add(sbg);
  const sb = new THREE.Mesh(new THREE.PlaneGeometry(8.4, 5.6), new THREE.MeshBasicMaterial({ map: arenaTex, toneMapped: false }));
  sb.position.set(0, 3.1, .12); sbg.add(sb); boxM(8.8, 6, .2, mat("#120a30"), 0, 3.1, 0, sbg);
  boxM(.2, 1, .2, mat("#222"), -3.5, .5, 0, sbg); boxM(.2, 1, .2, mat("#222"), 3.5, .5, 0, sbg);
  // holofotes
  const sp = new THREE.PointLight(0xff6fb5, 40, 16); sp.position.set(ARENA_C.x, 6, ARENA_C.z); scene.add(sp);
  const sp2 = new THREE.PointLight(0x4fd1c5, 25, 14); sp2.position.set(ARENA_C.x - 3, 5, ARENA_C.z + 4); scene.add(sp2);
  const zl = label("Arena", "#FF6FB5", true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = "1px solid #FF6FB566";
  zl.addEventListener("click", () => API().openZone("arena")); labels.push({ el: zl, p: new THREE.Vector3(ARENA_C.x, 2.6, ARENA_C.z - 5.8) });
  const hit = new THREE.Mesh(new THREE.PlaneGeometry(14, 22), new THREE.MeshBasicMaterial({ visible: false })); hit.rotation.x = -Math.PI / 2; hit.position.set(26.5, .4, 0); hit.userData.zone = "arena"; scene.add(hit); zoneHits.push(hit);
  updateArena();
}
function updateArena() {
  if (!arenaG) return;
  const rows = arenaRows(), sig = JSON.stringify(rows.map(b => [b.id, b.estado, b.n, b.avg_r, b.wins]));
  drawArenaBoard(arenaTex.userData.c.getContext("2d")); arenaTex.needsUpdate = true;
  if (sig === arenaSig) return; arenaSig = sig;
  fighters.forEach(f => arenaG.remove(f.g)); fighters = [];
  arenaLabels.forEach(l => { l.el.remove(); const i = labels.indexOf(l); if (i >= 0) labels.splice(i, 1); }); arenaLabels = [];
  const alive = rows.filter(b => b.estado !== "MORTA"), dead = rows.filter(b => b.estado === "MORTA");
  const hasLeader = alive.length && alive[0].n > 0 && alive[0].avg_r > 0;   // coroa so com resultado positivo
  alive.forEach((b, i) => {
    const f = fighter(FCOL[rows.indexOf(b) % FCOL.length], false, b.id, b.persona); f.b = b; f.rank = i; f.ph = i * 1.7;
    if (i === 0 && hasLeader) {           // lider: pedestal no centro com coroa
      const ped = new THREE.Mesh(new THREE.CylinderGeometry(.8, .95, .9, 24), mat("#F6C453", .5)); ped.position.set(ARENA_C.x, .8, ARENA_C.z); arenaG.add(ped);
      f.home = new THREE.Vector3(ARENA_C.x, 1.25, ARENA_C.z); f.leader = true;
      const crown = new THREE.Group(); const ring = new THREE.Mesh(new THREE.CylinderGeometry(.16, .18, .1, 16, 1, true), mat("#F6C453", 1.2)); crown.add(ring);
      for (let k = 0; k < 5; k++) { const sp = new THREE.Mesh(new THREE.ConeGeometry(.04, .12, 6), mat("#F6C453", 1.2)); const a = k / 5 * Math.PI * 2; sp.position.set(Math.cos(a) * .15, .1, Math.sin(a) * .15); crown.add(sp); }
      crown.position.y = .2; f.rig.head.add(crown);
    } else {                               // os outros treinam em pares a volta
      const k = i - (hasLeader ? 1 : 0), pair = Math.floor(k / 2), side = k % 2 ? 1 : -1, n = Math.ceil((alive.length - (hasLeader ? 1 : 0)) / 2);
      // a arena cresce com os concorrentes: com mais de 5 pares abre um 2.º anel
      const a = pair / Math.max(1, n) * Math.PI * 2 + .4, rad = n > 5 ? (pair % 2 ? 4.3 : 2.6) : 3.3;
      const cx = ARENA_C.x + Math.cos(a) * rad, cz = ARENA_C.z + Math.sin(a) * rad, tx = -Math.sin(a), tz = Math.cos(a);
      f.home = new THREE.Vector3(cx + tx * side * .65, .36, cz + tz * side * .65);
      f.lab = new THREE.Vector3(cx + tx * side * 1.5, .36, cz + tz * side * 1.5);   // etiqueta afastada do par
      f.faceTo = Math.atan2(-tx * side, -tz * side);
    }
    const wins = Math.min(5, b.wins || 0);        // medalhas por operacoes ganhas
    for (let m = 0; m < wins; m++) { const md = new THREE.Mesh(new THREE.CylinderGeometry(.07, .07, .02, 16), mat("#F6C453", 1.1)); md.rotation.x = Math.PI / 2;
      md.position.set(-.16 + m * .08, 1.45, .2); f.g.add(md); }
    if (b.estado === "SOBE") { const beam = new THREE.Mesh(new THREE.CylinderGeometry(.55, .55, 9, 24, 1, true), new THREE.MeshBasicMaterial({ color: 0xF6C453, transparent: true, opacity: .18, side: THREE.DoubleSide, toneMapped: false })); beam.position.y = 4.5; f.g.add(beam); }
    f.g.position.copy(f.home); arenaG.add(f.g); fighters.push(f);
  });
  updateMemorial(dead);                    // quem morre vai para o memorial (sala propria)
  // etiquetas curtas (nome e resultado), em duas alturas para os pares nao
  // se taparem, e so quando a camara esta perto da arena
  fighters.forEach((f, i) => { const r = f.b.avg_r, nm = (f.b.persona || SHORT[f.b.id] || f.b.id) + (f.b.n ? ` ${r > 0 ? "+" : ""}${(r || 0).toFixed(2).replace(".", ",")}R` : "");
    const el = label((f.leader ? "👑 " : f.b.estado === "SOBE" ? "🏆 " : "") + nm, f.b.estado === "SOBE" ? "#F6C453" : r > 0 ? "#9AE6B4" : "#ffffff", true);
    el.style.padding = "1px 6px"; el.style.borderRadius = "6px"; el.style.background = "#0c0a24cc"; el.style.fontSize = "10.5px";
    const l = { el, p: (f.lab || f.home).clone().setY(f.home.y + (f.leader ? 3.1 : i % 2 ? 2.2 : 2.9)), near: ARENA_C.clone(), maxD: 38 }; labels.push(l); arenaLabels.push(l); });
}
function animateArena(dt, t) {
  fighters.forEach(f => {
    if (f.dead) return; const k = f.rig, ph = t * 6 + f.ph;
    if (f.leader) {                        // vitoria: bracos no ar e roda devagar
      f.g.rotation.y += dt * .5; k.AL.sh.rotation.set(Math.PI * .85, 0, .3); k.AR.sh.rotation.set(Math.PI * .85, 0, -.3);
      k.AL.el.rotation.x = .2; k.AR.el.rotation.x = .2; f.g.position.y = f.home.y + Math.abs(Math.sin(t * 2)) * .12; return;
    }
    // guarda alta, saltitar e socos alternados
    f.g.rotation.y = f.faceTo + Math.sin(t * .8 + f.ph) * .15;
    f.g.position.y = f.home.y + Math.abs(Math.sin(ph)) * .06;
    k.L.th.rotation.x = .25; k.R.th.rotation.x = -.25; k.L.kn.rotation.x = .3; k.R.kn.rotation.x = .3;
    const pL = Math.max(0, Math.sin(t * 3.1 + f.ph)), pR = Math.max(0, Math.sin(t * 3.1 + f.ph + Math.PI));
    k.AL.sh.rotation.set(-1.1 - pL * .5, 0, .25); k.AL.el.rotation.x = -1.6 + pL * 1.5;
    k.AR.sh.rotation.set(-1.1 - pR * .5, 0, -.25); k.AR.el.rotation.x = -1.6 + pR * 1.5;
    k.spine.rotation.y = (pL - pR) * .25; k.head.rotation.x = .08;
  });
}


// ---------- recompensas: conquistas reais desbloqueiam espacos (D.rewards) ----------
let rewG = null, rewSig = "", rewLabels = [], rewSeen = null, confetti = [];
const REW_SHORT = { WIN1: "1.ª operação ganha", WIN3: "3 operações ganhas", PEAK: "capital acima do início", WEEK: "semana positiva", ARENA: "analista sobe na arena" };
// sala de trofeus: espaco proprio a sul da sala de estrategia (espelho do memorial)
const TRO_X0 = 36.6, TRO_LEN = 9.4, TRO_ZC = -10.1;
const REW_POS = { WIN1: V(39.0, -12.2), PEAK: V(39.0, -10.0), WEEK: V(39.0, -7.9), WIN3: V(43.4, -11.7), ARENA: V(43.4, -8.3) };
function rewardRows() { return (API().D() || {}).rewards || []; }
function rewardObj(id) {
  const g = new THREE.Group();
  if (id === "WIN1") {                 // mesa de bilhar
    boxM(2.2, .18, 1.2, mat("#1f7a4a"), 0, .82, 0, g); boxM(2.4, .14, 1.4, mat("#6b3b1f"), 0, .78, 0, g);
    [[-1, -.55], [1, -.55], [-1, .55], [1, .55]].forEach(([x, z]) => boxM(.14, .75, .14, mat("#4a2a14"), x, .37, z, g));
    ["#ffffff", "#F6C453", "#FC8181", "#63B3ED", "#111111"].forEach((c, i) => { const b = new THREE.Mesh(new THREE.SphereGeometry(.05, 10, 8), mat(c)); b.position.set(-.5 + i * .25, .96, (i % 2) * .2 - .1); g.add(b); });
    const cue = boxM(1.4, .03, .03, mat("#c08a5a"), .3, .96, .35, g); cue.rotation.y = .3;
  } else if (id === "WIN3") {          // bar no terraco
    boxM(2.6, 1, .6, mat("#3a2b20"), 0, .5, 0, g); boxM(2.7, .06, .7, mat("#c08a5a"), 0, 1.02, 0, g);
    boxM(2.6, 1.6, .1, mat("#1b1430"), 0, 1.9, -.6, g);
    ["#4FD1C5", "#FF6FB5", "#F6C453", "#B794F4"].forEach((c, i) => { const b = new THREE.Mesh(new THREE.CylinderGeometry(.06, .06, .3, 10), mat(c, .8)); b.position.set(-.9 + i * .6, 1.55, -.5); g.add(b); });
    [-.8, 0, .8].forEach(x => { const st = new THREE.Mesh(new THREE.CylinderGeometry(.2, .2, .06, 14), mat("#FF6FB5", .4)); st.position.set(x, .75, .7); g.add(st); boxM(.06, .72, .06, mat("#222"), x, .36, .7, g); });
    const sign = boxM(1.2, .3, .05, mat("#FF6FB5", 1.6), 0, 2.85, -.55, g);
  } else if (id === "PEAK") {          // trofeu dourado
    boxM(.8, .9, .8, mat("#2b1d74"), 0, .45, 0, g);
    const pts = [[0, 0], [.22, 0], [.08, .1], [.06, .35], [.3, .55], [.32, .85], [0, .85]].map(([x, y]) => new THREE.Vector2(x, y));
    const cup = new THREE.Mesh(new THREE.LatheGeometry(pts, 24), mat("#F6C453", .9)); cup.position.y = .9; g.add(cup);
    [-1, 1].forEach(sd => { const h = new THREE.Mesh(new THREE.TorusGeometry(.12, .025, 8, 16, Math.PI), mat("#F6C453", .9)); h.position.set(sd * .33, 1.6, 0); h.rotation.z = sd * Math.PI / 2; g.add(h); });
    g.userData.spin = cup;
  } else if (id === "WEEK") {          // maquina de arcade
    boxM(.8, 1.8, .7, mat("#2a1f6e"), 0, .9, 0, g);
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(.6, .45), new THREE.MeshBasicMaterial({ color: 0x4FD1C5, toneMapped: false })); scr.position.set(0, 1.35, .36); g.add(scr); g.userData.blink = scr;
    boxM(.7, .12, .3, mat("#111"), 0, .98, .42, g);
    [["#FC8181", -.15], ["#F6C453", .05], ["#68D391", .2]].forEach(([c, x]) => { const b = new THREE.Mesh(new THREE.SphereGeometry(.035, 8, 6), mat(c, 1)); b.position.set(x, 1.06, .48); g.add(b); });
    boxM(.82, .2, .72, mat("#FF6FB5", 1.2), 0, 1.92, 0, g);
  } else {                             // hall da fama: estatua dourada
    boxM(1, .6, 1, mat("#2b1d74"), 0, .3, 0, g);
    const f = robotFighter("#F6C453", false); f.g.scale.setScalar(1.1); f.g.position.y = .6;
    f.rig.AL.sh.rotation.set(Math.PI * .85, 0, .3); f.rig.AR.sh.rotation.set(Math.PI * .85, 0, -.3);
    f.g.traverse(o => { if (o.material) o.material = mat("#F6C453", .7); }); g.add(f.g);
  }
  return g;
}
function ghostify(g) {                 // por desbloquear: holograma em arame
  const gm = new THREE.MeshBasicMaterial({ color: 0x8a83ad, wireframe: true, transparent: true, opacity: .22 });
  g.traverse(o => { if (o.isMesh) { o.material = gm; o.castShadow = false; } });
}
function drawPlaque(g, r) {
  const W = 320, H = 120;
  g.fillStyle = r.unlocked ? "#2b2205" : "#1a1830"; g.fillRect(0, 0, W, H);
  g.strokeStyle = r.unlocked ? "#F6C453" : "#5d5885"; g.lineWidth = 6; g.strokeRect(4, 4, W - 8, H - 8);
  g.textAlign = "center"; g.fillStyle = r.unlocked ? "#F6C453" : "#c9c2ee"; g.font = "800 28px system-ui";
  g.fillText((r.unlocked ? "🏆 " : "🔒 ") + r.name, W / 2, 48);
  g.font = "500 18px system-ui"; g.fillStyle = r.unlocked ? "#f3e6b8" : "#9a94b8";
  const d = r.at ? new Date(r.at * 1000).toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit" }) : "";
  let t = r.unlocked ? `conquistado a ${d}` : (REW_SHORT[r.id] || r.cond);
  while (g.measureText(t).width > W - 30 && t.length > 4) t = t.slice(0, -2);
  g.fillText(t, W / 2, 86); g.textAlign = "left";
}
function buildRewards() {
  rewG = new THREE.Group(); scene.add(rewG);
  const cx = TRO_X0 + TRO_LEN / 2;
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(TRO_LEN, 7.4), mat("#3b3328")); fl.rotation.x = -Math.PI / 2; fl.position.set(cx, .006, TRO_ZC); fl.receiveShadow = true; scene.add(fl);
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(TRO_LEN - .8, 6.6), mat("#6a2f2f")); rug.rotation.x = -Math.PI / 2; rug.position.set(cx, .012, TRO_ZC); scene.add(rug);
  const wall = mat("#5c5040"); boxM(TRO_LEN, .9, .18, wall, cx, .45, TRO_ZC - 3.7); boxM(TRO_LEN, .9, .18, wall, cx, .45, TRO_ZC + 3.7); boxM(.18, .9, 7.4, wall, TRO_X0 + TRO_LEN, .45, TRO_ZC);
  boxM(TRO_LEN, .05, .05, mat("#F6C453", 1.4), cx, .92, TRO_ZC - 3.6); boxM(TRO_LEN, .05, .05, mat("#F6C453", 1.4), cx, .92, TRO_ZC + 3.6);
  const lt = new THREE.PointLight(0xffd88a, 10, 12); lt.position.set(cx, 4, TRO_ZC); scene.add(lt);
  const zl = label("Sala de troféus", "#F6C453", true); zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = "1px solid #F6C45366";
  labels.push({ el: zl, p: new THREE.Vector3(TRO_X0 - .8, .2, TRO_ZC) });
  updateRewards();
}
function updateRewards() {
  if (!rewG) return;
  const rows = rewardRows(), sig = JSON.stringify(rows.map(r => [r.id, r.unlocked]));
  if (sig === rewSig) return; rewSig = sig;
  const newly = rewSeen ? rows.filter(r => r.unlocked && !rewSeen.has(r.id)) : [];
  rewSeen = new Set(rows.filter(r => r.unlocked).map(r => r.id));
  rewG.clear(); rewLabels.forEach(l => { l.el.remove(); const i = labels.indexOf(l); if (i >= 0) labels.splice(i, 1); }); rewLabels = [];
  rows.forEach(r => {
    const pos = REW_POS[r.id]; if (!pos) return;
    const g = rewardObj(r.id); g.position.copy(pos); g.rotation.y = -Math.PI / 2; if (!r.unlocked) ghostify(g); rewG.add(g);
    // placa legivel a frente de cada premio (sem etiquetas a flutuar)
    const tx = canvasTex(320, 120, gg => drawPlaque(gg, r));
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(1.6, .6), new THREE.MeshBasicMaterial({ map: tx, toneMapped: false }));
    pl.position.set(pos.x - 1.45, .55, pos.z); pl.rotation.y = -Math.PI / 2; pl.rotation.x = 0; rewG.add(pl);
    boxM(.06, .5, .06, mat("#3a3020"), pos.x - 1.4, .25, pos.z, rewG);
  });
  newly.forEach(r => burst(REW_POS[r.id]));
}
function burst(p) {                    // confetes quando se desbloqueia
  if (!p) return; const n = 120, geo = new THREE.BufferGeometry(), pos = new Float32Array(n * 3), col = new Float32Array(n * 3), vel = [];
  const cs = ["#F6C453", "#FF6FB5", "#4FD1C5", "#B794F4", "#68D391"].map(c => new THREE.Color(c));
  for (let i = 0; i < n; i++) { pos.set([p.x, 1.5, p.z], i * 3); const c = cs[i % cs.length]; col.set([c.r, c.g, c.b], i * 3);
    vel.push(new THREE.Vector3((Math.random() - .5) * 4, 3 + Math.random() * 4, (Math.random() - .5) * 4)); }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3)); geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({ size: .14, vertexColors: true, toneMapped: false })); scene.add(pts);
  confetti.push({ pts, vel, life: 4 });
}
function animateRewards(dt, t) {
  if (rewG) rewG.children.forEach(g => { if (g.userData.spin) g.userData.spin.rotation.y += dt * .8;
    if (g.userData.blink) g.userData.blink.material.color.setHSL((t * .15) % 1, .7, .55); });
  confetti = confetti.filter(c => { c.life -= dt; const a = c.pts.geometry.attributes.position;
    for (let i = 0; i < c.vel.length; i++) { c.vel[i].y -= 6 * dt; a.setXYZ(i, a.getX(i) + c.vel[i].x * dt, Math.max(.05, a.getY(i) + c.vel[i].y * dt), a.getZ(i) + c.vel[i].z * dt); }
    a.needsUpdate = true; if (c.life <= 0) { scene.remove(c.pts); return false; } return true; });
}


// ---------- sala dos setores: cada analista acompanha um grupo de moedas ----------
// A analise de todas as moedas e a mesma (scan de 5 em 5 min); aqui a equipa
// mostra, por setor, o estado real de cada moeda no ecra por cima da mesa.
const SEC_POS = { sec_maj: V(21.8, 8.9), sec_l1: V(21.8, 11.0), sec_defi: V(21.8, 13.1), sec_ai: V(25.9, 8.9), sec_meme: V(25.9, 11.0) };
let secPeople = [], secTex = {};
function secRows(S) {
  const D = API().D() || {}, U = D.universe || [];
  return U.filter(r => window.sectorOf(r.asset) === S.id).map(r => ({ r, st: window.coinStatus(D, r) }))
    .sort((a, b) => a.st.k - b.st.k || Math.abs(b.r.chg_24h || 0) - Math.abs(a.r.chg_24h || 0));
}
function drawSector(g, S) {
  const W = 512, H = 384, rows = secRows(S);
  g.fillStyle = "#070b1c"; g.fillRect(0, 0, W, H); g.strokeStyle = S.c; g.lineWidth = 6; g.strokeRect(3, 3, W - 6, H - 6);
  g.fillStyle = S.c; g.font = "800 30px system-ui"; g.fillText(`${S.nm} · ${S.t}`, 18, 42);
  g.font = "500 18px system-ui"; g.fillStyle = "#9fb0d0"; g.fillText(`${rows.length} moedas · scan de 5 em 5 min`, 18, 68);
  rows.slice(0, 9).forEach(({ r, st }, i) => {
    const y = 104 + i * 31; g.fillStyle = i % 2 ? "#ffffff06" : "#ffffff10"; g.fillRect(12, y - 22, W - 24, 29);
    g.font = "700 21px system-ui"; g.fillStyle = "#fff"; g.fillText(r.asset, 22, y);
    const c = r.chg_24h || 0; g.fillStyle = c >= 0 ? "#68D391" : "#FC8181"; g.fillText((c > 0 ? "+" : "") + c.toFixed(1).replace(".", ",") + "%", 120, y);
    g.font = "500 18px system-ui"; g.fillStyle = st.k === 0 ? "#63B3ED" : st.k === 1 ? "#68D391" : st.k === 2 ? "#F6C453" : "#7d86a8";
    g.fillText(`${st.ic} ${st.tx}`.slice(0, 34), 220, y);
  });
  if (rows.length > 9) { g.fillStyle = "#7d86a8"; g.font = "16px system-ui"; g.fillText(`+${rows.length - 9} moedas (toca para ver todas)`, 22, H - 10); }
}
function buildSectors() {
  const S0 = window.SECTORS || []; if (!S0.length) return;
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(9, 6.2), mat("#36404e")); rug.rotation.x = -Math.PI / 2; rug.position.set(24.2, .02, 10.9); scene.add(rug);
  line([V(19.8, 7.7), V(28.7, 7.7), V(28.7, 13.95), V(19.8, 13.95), V(19.8, 7.7)].map(p => p.setY(.04)), 0x63B3ED);
  const zl = label("Setores", "#63B3ED", true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = "1px solid #63B3ED66";
  zl.addEventListener("click", () => API().openZone("sectors")); labels.push({ el: zl, p: new THREE.Vector3(19.9, 1.0, 7.9) });
  S0.forEach(S => {
    const pos = SEC_POS[S.id]; if (!pos) return;
    DESK[S.id] = { z: "srv", p: pos, f: 1 }; buildDesk(S.id);
    const tx = canvasTex(512, 384, g => drawSector(g, S)); secTex[S.id] = tx;
    const m = monOn[S.id].material; m.map = tx; m.color.set(0xffffff); m.needsUpdate = true;
    const pan = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 1.42), new THREE.MeshBasicMaterial({ map: tx, toneMapped: false }));
    pan.position.set(pos.x + .62, 2.45, pos.z); pan.rotation.y = -Math.PI / 2; scene.add(pan);
    boxM(.05, 1.5, 2.0, mat("#0d1224"), pos.x + .66, 2.45, pos.z); boxM(.06, .9, .06, mat("#222"), pos.x + .66, 1.25, pos.z);
    const p = makePerson({ id: S.id, nm: `${S.nm} · ${S.t}`, c: S.c });
    p.mode = "work"; p.sit = true; p.path = []; p.name.style.display = "none"; secPeople.push(p);
  });
}
function updateSectors() { (window.SECTORS || []).forEach(S => { const t = secTex[S.id]; if (t) { drawSector(t.userData.c.getContext("2d"), S); t.needsUpdate = true; } }); }


// ---------- sala de estrategia: cada analista da arena tambem trabalha a
// secretaria, com o seu desempenho real no ecra. A sala cresce sozinha:
// uma secretaria por analista vivo (os mortos saem, nao ficam mesas vazias)
const ST_X0 = 38.6, ST_DX = 3.4, ST_ZS = [-2.4, 2.4], ST_WALL = 36.6;
let stLen = 8;                         // comprimento atual da sala (cresce)
let stG = null, stSig = "", stPeople = [], stTex = {}, stFloor = null;
function drawStrat(g, b) {
  const W = 512, H = 320, r = b.avg_r;
  g.fillStyle = "#0b1220"; g.fillRect(0, 0, W, H);
  if (b.champ || b.prov) { g.fillStyle = "#F6C453"; g.fillRect(0, 0, W, 6); g.font = "800 16px system-ui"; g.textAlign = "right"; g.fillText(b.champ ? "🏆 CAMPEÃO · SINAIS REAIS" : "✓ PROVOU · PAPEL AO VIVO", W - 14, 28); g.textAlign = "left"; }
  g.fillStyle = "#e9eef7"; g.font = "800 30px system-ui"; g.fillText(`${b.persona || ""} · ${SHORT[b.id] || b.id}`, 18, 44);
  g.font = "500 18px system-ui"; g.fillStyle = "#93a4c3"; g.fillText(b.name || "", 18, 70);
  g.font = "700 46px system-ui"; g.fillStyle = r == null ? "#93a4c3" : r > 0 ? "#68D391" : "#FC8181";
  g.fillText(r == null ? "sem operações" : (r > 0 ? "+" : "") + r.toFixed(2).replace(".", ",") + "R", 18, 130);
  g.font = "600 20px system-ui"; g.fillStyle = "#c9d3e6"; g.fillText(`${b.n} op.${b.src ? " (90 dias)" : ""} · ${b.wins || 0} ganhas · ${b.estado === "SOBE" ? "🏆 sobe" : "⚔ a lutar"}`, 18, 168);
  const u = b.ultimas || []; g.fillStyle = "#93a4c3"; g.font = "16px system-ui"; g.fillText("últimas operações", 18, 206);
  u.forEach((x, i) => { g.fillStyle = x > 0 ? "#68D391" : "#FC8181"; const h = Math.min(70, Math.abs(x) * 35 + 6); g.fillRect(18 + i * 46, x > 0 ? 290 - h : 290, 34, h > 0 ? (x > 0 ? h : Math.min(h, 28)) : 4); });
  if (!u.length) { g.fillStyle = "#5d6b85"; g.fillText("à espera do primeiro sinal", 18, 260); }
  g.strokeStyle = "#2b3a55"; g.beginPath(); g.moveTo(14, 290); g.lineTo(W - 14, 290); g.stroke();
}
function buildStrategyRoom() {
  stG = new THREE.Group(); scene.add(stG);
  const zl = label("Sala de estratégia", "#9fd3ff", true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c1220b3"; zl.style.border = "1px solid #9fd3ff66";
  zl.addEventListener("click", () => API().openZone("arena")); labels.push({ el: zl, p: new THREE.Vector3(37.4, 2.6, 0) });
  updateStrategyRoom();
}
function updateStrategyRoom() {
  if (!stG) return;
  const P = (API().D() || {}).promo || {}, Q = new Set((P.qualificados || []).map(q => q.id)), CH = new Set(P.campeoes || (P.campeao ? [P.campeao] : []));
  // o campeao fica na primeira secretaria; os qualificados a seguir
  // so quem PROVOU no combate tem secretaria aqui; os outros estao na academia
  const rows = arenaRows().filter(b => b.estado !== "MORTA" && Q.has(b.id)).map(b => Object.assign({}, b, { champ: CH.has(b.id), prov: true }))
    .sort((a, b) => (b.champ - a.champ) || ((b.avg_r || 0) - (a.avg_r || 0)));
  const sig = JSON.stringify(rows.map(b => [b.id, b.n, b.avg_r, b.wins, b.estado, b.champ, b.prov]));
  rows.forEach(b => { const t = stTex[b.id]; if (t) { drawStrat(t.userData.c.getContext("2d"), b); t.needsUpdate = true; } });
  if (sig === stSig) return;
  const ids = rows.map(b => b.id + (b.champ ? "*" : "") + (b.prov ? "+" : "")).join(","), same = stSig && JSON.parse(stSig).map(x => x[0] + (x[5] ? "*" : "") + (x[6] ? "+" : "")).join(",") === ids; stSig = sig;
  if (same) return;                    // so os ecras mudaram
  stG.clear(); stPeople.forEach(p => { scene.remove(p.g); p.name.remove(); }); stPeople = []; stTex = {};
  moneyLabels.filter(m => m.room === "st").forEach(m => { m.el.remove(); const i = labels.indexOf(m); if (i >= 0) labels.splice(i, 1); });
  moneyLabels = moneyLabels.filter(m => m.room !== "st");
  const nRows = Math.max(1, Math.ceil(rows.length / ST_ZS.length)), len = 2 + nRows * ST_DX; stLen = len;
  // chao e paredes de vidro: a sala cresce com o numero de analistas
  const cx = ST_WALL + len / 2;
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(len, 10), mat("#454a53")); fl.rotation.x = -Math.PI / 2; fl.position.set(cx, .005, 0); fl.receiveShadow = true; stG.add(fl);
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(len - .8, 8.6), mat("#3d4656")); rug.rotation.x = -Math.PI / 2; rug.position.set(cx, .015, 0); stG.add(rug);
  const glass = mat("#9fd3ff", .05, .08); boxM(len, 1.2, .05, glass, cx, .6, -5, stG); boxM(len, 1.2, .05, glass, cx, .6, 5, stG);
  boxM(.05, 1.2, 10, glass, ST_WALL + len, .6, 0, stG);
  rows.forEach((b, i) => {
    const x = ST_X0 + Math.floor(i / ST_ZS.length) * ST_DX, z = ST_ZS[i % ST_ZS.length];
    const col = FCOL[arenaRows().indexOf(b) % FCOL.length];
    // secretaria virada para a vista do telemovel (ecra para -x)
    const g = new THREE.Group(); g.position.set(x, 0, z); stG.add(g);
    boxM(1.1, .06, 2.2, mat("#8b6a4c"), 0, .75, 0, g); [[-.45, -.95], [.45, -.95], [-.45, .95], [.45, .95]].forEach(([a, c]) => boxM(.06, .72, .06, mat("#2a2a2a"), a, .36, c, g));
    const tx = canvasTex(512, 320, gg => drawStrat(gg, b)); stTex[b.id] = tx;
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(1.7, 1.06), new THREE.MeshBasicMaterial({ map: tx, toneMapped: false })); scr.position.set(.42, 1.42, 0); scr.rotation.y = -Math.PI / 2; g.add(scr);
    boxM(.05, 1.12, 1.76, mat("#111"), .45, 1.42, 0, g); boxM(.08, .4, .08, mat("#111"), .45, .95, 0, g);
    boxM(.18, .02, .55, mat("#1d1d2e"), -.1, .79, 0, g);
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(.055, .05, .12, 12), mat(col)); mug.position.set(-.2, .84, -.75); g.add(mug);
    const ch = new THREE.Group(); ch.position.set(-.95, 0, 0); g.add(ch); boxM(.55, .08, .55, mat("#2b2b40"), 0, .48, 0, ch); boxM(.08, .6, .55, mat("#2b2b40"), -.27, .8, 0, ch);
    // o analista, com o mesmo aspeto que tem na arena
    const key = "st_" + b.id, nm = (b.persona || "").replace(" Jr.", ""), h = hsh(b.id || nm), fem = FEM.has(nm);
    STYLE[key] = { skin: SKINS[h % SKINS.length], hair: HAIRS[(h >> 2) % HAIRS.length], hs: fem ? (h % 2 ? "long" : "bun") : ["short", "buzz", "curly"][h % 3], top: col, legs: "#1d1b2e", beard: !fem && h % 4 === 0 ? 1 : 0, glasses: h % 5 === 0 ? 1 : 0 };
    DESK[key] = { z: "srv", p: V(x, z), f: 1 };
    const p = makePerson({ id: key, nm, c: col }); p.mode = "work"; p.sit = true; p.path = []; p.name.style.display = "none"; stPeople.push(p);
    if (b.champ) {                          // quem opera dinheiro real: $ ganhos/perdidos por cima
      const el = label("", "#fff", true); styleMoney(el);
      const m = { el, p: new THREE.Vector3(x - 1.1, 2.45, z), near: new THREE.Vector3(x, 0, z), maxD: 34, room: "st", strat: b.id };
      labels.push(m); moneyLabels.push(m);
    }
    if (b.champ || b.prov) {               // lugar conquistado: placa dourada (campeao: trofeu grande)
      boxM(.04, .14, 1.0, mat("#F6C453", .9), -.56, .9, 0, g);
      if (b.champ) { const cup = new THREE.Mesh(new THREE.CylinderGeometry(.14, .07, .3, 16), mat("#F6C453", 1.2)); cup.position.set(-.1, .96, .75); g.add(cup);
        const lt = new THREE.PointLight(0xF6C453, 6, 4); lt.position.set(0, 2.4, 0); g.add(lt); }
    }
    if ((b.wins || 0) > 0) { const tr = new THREE.Mesh(new THREE.CylinderGeometry(.06, .04, .16, 12), mat("#F6C453", .9)); tr.position.set(-.25, .86, .75); g.add(tr); }   // premio na mesa
  });
}

// ---------- memorial: quem morre na arena sai do ringue e fica aqui, numa sala
// propria ao lado da sala de estrategia. Cada lapide tem a placa com o nome,
// a estrategia, os numeros com que morreu, a data e o motivo (texto desenhado
// na pedra, sem etiquetas a flutuar umas por cima das outras)
const MEM_X0 = 37.6, MEM_Z = [8.0, 10.1, 12.2], MEM_DX = 2.7;
let memG = null, memSig = "";
function drawTomb(g, b) {
  const W = 320, H = 240, m = b.morte || {}, r = m.avg_r != null ? m.avg_r : b.avg_r;
  const gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, "#6f6a80"); gr.addColorStop(1, "#4d4860"); g.fillStyle = gr; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#8f89a6"; g.lineWidth = 6; g.strokeRect(8, 8, W - 16, H - 16);
  g.textAlign = "center"; g.fillStyle = "#f2eff8"; g.font = "800 34px system-ui"; g.fillText(b.persona || "", W / 2, 58);
  g.font = "600 20px system-ui"; g.fillStyle = "#dcd8e8"; g.fillText((b.name || b.id).replace(" (ao vivo)", "").replace(" (papel)", "").slice(0, 26), W / 2, 90);
  g.font = "700 30px system-ui"; g.fillStyle = r > 0 ? "#9AE6B4" : "#FEB2B2"; g.fillText(r == null ? "–" : (r > 0 ? "+" : "") + r.toFixed(2).replace(".", ",") + "R", W / 2, 138);
  g.font = "500 18px system-ui"; g.fillStyle = "#e6e2f0"; g.fillText(`${m.n != null ? m.n : b.n} operações`, W / 2, 166);
  const d = m.t ? new Date(m.t * 1000).toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit" }) : "";
  g.font = "500 16px system-ui"; g.fillStyle = "#cfcade"; g.fillText(`† ${d}${b.motivo || m.motivo ? " · " + (b.motivo || m.motivo).replace("forma recente", "combate") : ""}`, W / 2, 200);
  g.textAlign = "left";
}
function buildMemorial() {
  memG = new THREE.Group(); scene.add(memG);
  const zl = label("Memorial", "#c9c2ee", true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = "1px solid #c9c2ee66";
  zl.addEventListener("click", () => API().openZone("arena")); labels.push({ el: zl, p: new THREE.Vector3(MEM_X0 - 1.6, .2, 10.1) });
}
function updateMemorial(dead) {
  if (!memG) return;
  const sig = JSON.stringify(dead.map(b => [b.id, b.motivo, (b.morte || {}).t]));
  if (sig === memSig) return; memSig = sig;
  memG.clear();
  const rows = Math.max(1, Math.ceil(dead.length / MEM_Z.length)), len = 1.6 + rows * MEM_DX, cx = MEM_X0 - 1 + len / 2;
  // sala: chao escuro, relva baixa, muro e luz fria
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(len, 7.4), mat("#2a2d33")); fl.rotation.x = -Math.PI / 2; fl.position.set(cx, .006, 10.1); fl.receiveShadow = true; memG.add(fl);
  const gr = new THREE.Mesh(new THREE.PlaneGeometry(len - .6, 6.8), mat("#2f4a37")); gr.rotation.x = -Math.PI / 2; gr.position.set(cx, .012, 10.1); memG.add(gr);
  const wall = mat("#5b5f69"); boxM(len, .7, .18, wall, cx, .35, 6.4, memG); boxM(len, .7, .18, wall, cx, .35, 13.8, memG); boxM(.18, .7, 7.4, wall, MEM_X0 - 1 + len, .35, 10.1, memG);
  const lt = new THREE.PointLight(0xb9c6ff, 8, 12); lt.position.set(cx, 4, 10.1); memG.add(lt);
  if (!dead.length) {                      // ninguem morreu ainda: placa vazia
    const tx = canvasTex(320, 240, g => { g.fillStyle = "#4d4860"; g.fillRect(0, 0, 320, 240); g.fillStyle = "#e6e2f0"; g.font = "600 22px system-ui"; g.textAlign = "center"; g.fillText("Ainda ninguém morreu", 160, 128); });
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 1.05), new THREE.MeshBasicMaterial({ map: tx })); pl.position.set(MEM_X0 + .3, .9, 10.1); pl.rotation.y = -Math.PI / 2; memG.add(pl); return;
  }
  dead.forEach((b, i) => {
    const x = MEM_X0 + Math.floor(i / MEM_Z.length) * MEM_DX, z = MEM_Z[i % MEM_Z.length];
    const g = new THREE.Group(); g.position.set(x, 0, z); memG.add(g);
    boxM(.5, .12, 1.7, mat("#3d3a48"), .05, .06, 0, g);                         // base
    boxM(.22, 1.25, 1.5, mat("#5d5870"), .12, .74, 0, g);                       // pedra
    boxM(.24, .1, 1.62, mat("#6b6680"), .12, 1.41, 0, g);                      // remate
    const tx = canvasTex(320, 240, gg => drawTomb(gg, b));
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(1.36, 1.02), new THREE.MeshBasicMaterial({ map: tx })); pl.position.set(0, .8, 0); pl.rotation.y = -Math.PI / 2; g.add(pl);
    // vela e flores a frente da lapide
    const cd = new THREE.Mesh(new THREE.CylinderGeometry(.05, .05, .2, 10), mat("#f4f1e8")); cd.position.set(-.45, .1, -.45); g.add(cd);
    const fm = new THREE.Mesh(new THREE.SphereGeometry(.04, 8, 6), mat("#F6C453", 2)); fm.position.set(-.45, .24, -.45); g.add(fm);
    [-.1, .05, .2].forEach((dz, k) => { const fw = new THREE.Mesh(new THREE.SphereGeometry(.07, 8, 6), mat(["#FC8181", "#F6C453", "#B794F4"][k])); fw.position.set(-.42, .08, .35 + dz); g.add(fw); });
  });
}
function goMemorial() { const n = Math.max(1, Math.ceil(arenaRows().filter(b => b.estado === "MORTA").length / MEM_Z.length)), len = 1.6 + n * MEM_DX;
  const T = V(MEM_X0 - 1 + len / 2, 10.45), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target); cam.position.copy(ctl.target.clone().add(d.setLength(14 + len * .5))); ctl.update(); }

// ---------- dinheiro: ganhos e perdas reais (operacoes que marcaste como
// executadas; fechadas pelo teu resultado, abertas ao preco atual)
let moneyLabels = [];
function styleMoney(el) { el.style.padding = "1px 6px"; el.style.borderRadius = "7px"; el.style.background = "#08121ee6"; el.style.fontSize = "11px"; el.style.fontWeight = "800"; el.style.border = "1px solid #ffffff22"; }
function moneyOf(filter) {
  const D = API().D() || {}, J = (D.journal || {}).rows || [], U = {}; (D.universe || []).forEach(r => { U[r.asset] = r.price; });
  let done = 0, open = 0;
  J.filter(r => r.executed === true && filter(r)).forEach(r => {
    const R = r.user_result_r != null ? r.user_result_r : r.result_r;
    if (r.status === "CLOSED" || r.user_result_r != null) { if (R != null && r.risk_usdc) done += R * r.risk_usdc; }
    else if (r.status === "OPEN") { const e = r.exec_price || r.entry, c = U[r.asset]; if (e && c && r.position_usdc) open += (c / e - 1) * r.position_usdc; }
  });
  return { done, open };
}
const fmtPnl = v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2).replace(".", ",") + " $";
function updateMoney() {
  moneyLabels.forEach(m => {
    let txt, v;
    if (m.strat) { const r = moneyOf(x => x.strategy === m.strat); v = r.done + r.open; txt = `💵 ${fmtPnl(v)}` + (Math.abs(r.open) > .005 ? " · aberto" : ""); }
    else if (m.kind === "done") { v = moneyOf(() => true).done; txt = `💵 ${fmtPnl(v)}`; m.el.title = "Resultado das tuas operações fechadas"; }
    else { v = moneyOf(() => true).open; txt = `📈 ${fmtPnl(v)} aberto`; m.el.title = "Resultado das operações abertas ao preço atual"; }
    m.el.textContent = txt; m.el.style.color = v > .005 ? "#68D391" : v < -.005 ? "#FC8181" : "#e9eef7";
  });
}
function buildOpsMoney() {                 // por cima do Tiago e da Marta, na mesa de operacoes
  [["scan", "done"], ["mon", "open"]].forEach(([id, kind]) => {
    const d = DESK[id]; if (!d) return; const el = label("", "#fff", true); styleMoney(el);
    const m = { el, p: d.p.clone().add(V(-d.f * .95, 0)).setY(2.6), kind, room: "ops" }; labels.push(m); moneyLabels.push(m);
  });
}

// ---------- academia de trading: quem ainda nao provou no combate aprende
// aqui (lutadores vivos sem qualificacao). O quadro mostra o que falta a cada
// um para ganhar lugar na sala de estrategia; o mentor da a aula.
const AC_X0 = 48.6, AC_ZC = -10.1, AC_ZS = [-11.4, -8.8], AC_DX = 2.4;
let acG = null, acSig = "", acPeople = [], acBoard = null, acEnd = 56, acLabel = null;
function drawAcademy(g, rows) {
  const W = 1024, H = 576; g.fillStyle = "#f6f4ec"; g.fillRect(0, 0, W, H); g.strokeStyle = "#7a5c3a"; g.lineWidth = 14; g.strokeRect(7, 7, W - 14, H - 14);
  g.fillStyle = "#1f3b2d"; g.font = "800 52px system-ui"; g.fillText("🎓 Academia de Trading", 36, 74);
  g.font = "600 25px system-ui"; g.fillStyle = "#4a5a52"; g.fillText("Para subir: 20 operações no combate, resultado positivo e acima do acaso", 36, 116);
  if (!rows.length) { g.font = "600 34px system-ui"; g.fillStyle = "#4a5a52"; g.fillText("Sem alunos: todos os vivos já provaram.", 36, 220); return; }
  const step = Math.min(104, (H - 150) / Math.min(rows.length, 4));
  rows.slice(0, 4).forEach((b, i) => {
    const f = b.forma || {}, n = f.n || 0, r = f.avg_r, p95 = f.acaso_p95, y = 150 + i * step + 40;
    g.fillStyle = i % 2 ? "#ece8da" : "#f2efe4"; g.fillRect(24, y - 40, W - 48, step - 8);
    g.fillStyle = "#1d2a24"; g.font = "800 34px system-ui"; g.fillText(b.persona || b.id, 40, y);
    g.font = "500 22px system-ui"; g.fillStyle = "#4a5a52"; g.fillText((b.name || b.id).replace(" (papel)", "").replace(" (combate)", "").slice(0, 34), 40, y + 30);
    const bw = 260, bx = 520; g.fillStyle = "#d8d2bd"; g.fillRect(bx, y - 22, bw, 20); g.fillStyle = "#2f855a"; g.fillRect(bx, y - 22, bw * Math.min(1, n / 20), 20);
    g.fillStyle = "#3d4a44"; g.font = "700 22px system-ui"; g.fillText(`${n}/20`, bx + bw + 12, y - 4);
    const ok = r != null && r > 0 && p95 != null && r > p95;
    const falta = n < 20 ? `faltam ${20 - n} operações` : r == null || r <= 0 ? "precisa de resultado positivo" : !ok ? "ainda não bate o acaso" : "pronto a subir";
    g.fillStyle = r > 0 ? "#2f855a" : "#c53030"; g.font = "800 30px system-ui"; g.textAlign = "right"; g.fillText(r == null ? "–" : (r > 0 ? "+" : "") + r.toFixed(2).replace(".", ",") + "R", W - 40, y); g.textAlign = "left";
    g.fillStyle = "#7a5a2a"; g.font = "600 21px system-ui"; g.fillText(falta, bx, y + 28);
  });
}
function buildAcademy() {
  acG = new THREE.Group(); scene.add(acG);
  const zl = label("Academia de Trading", "#9AE6B4", true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = "1px solid #9AE6B466";
  zl.addEventListener("click", () => API().openZone("arena")); acLabel = { el: zl, p: new THREE.Vector3(AC_X0 - 1.4, .2, AC_ZC) }; labels.push(acLabel);
  updateAcademy();
}
function academyRows() {
  const Q = new Set((((API().D() || {}).promo || {}).qualificados || []).map(q => q.id));
  return ((((API().D() || {}).arena || {}).classificacao) || []).filter(b => b.estado !== "MORTA" && !Q.has(b.id) && b.id !== "REJEITADOS");
}
function updateAcademy() {
  if (!acG) return;
  const rows = academyRows(), sig = JSON.stringify(rows.map(b => [b.id, (b.forma || {}).n, (b.forma || {}).avg_r]));
  if (acBoard) { drawAcademy(acBoard.userData.c.getContext("2d"), rows); acBoard.needsUpdate = true; }
  const ids = rows.map(b => b.id).join(",");
  if (acSig === ids) return; acSig = ids;
  acG.clear(); acPeople.forEach(p => { scene.remove(p.g); p.name.remove(); }); acPeople = [];
  const nRows = Math.max(2, Math.ceil(rows.length / AC_ZS.length)), len = 4.2 + nRows * AC_DX, cx = AC_X0 - 1 + len / 2; acEnd = AC_X0 - 1 + len;
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(len, 7.4), mat("#4a4136")); fl.rotation.x = -Math.PI / 2; fl.position.set(cx, .006, AC_ZC); fl.receiveShadow = true; acG.add(fl);
  const wd = new THREE.Mesh(new THREE.PlaneGeometry(len - .6, 6.8), mat("#8a6a48")); wd.rotation.x = -Math.PI / 2; wd.position.set(cx, .012, AC_ZC); acG.add(wd);
  const wall = mat("#6b6f78"); boxM(len, .9, .18, wall, cx, .45, AC_ZC - 3.7, acG); boxM(len, .9, .18, wall, cx, .45, AC_ZC + 3.7, acG); boxM(.18, 3.4, 7.4, wall, acEnd, 1.7, AC_ZC, acG);
  const lt = new THREE.PointLight(0xfff3d6, 10, 14); lt.position.set(cx, 4, AC_ZC); acG.add(lt);
  // quadro na parede do fundo, virado para os alunos e para a camara
  acBoard = canvasTex(1024, 576, g => drawAcademy(g, rows));
  const bd = new THREE.Mesh(new THREE.PlaneGeometry(5.4, 3.04), new THREE.MeshBasicMaterial({ map: acBoard, toneMapped: false })); bd.position.set(acEnd - .14, 2.0, AC_ZC); bd.rotation.y = -Math.PI / 2; acG.add(bd);
  boxM(.1, 3.2, 5.6, mat("#5a4030"), acEnd - .08, 2.0, AC_ZC, acG);
  // mentor ao lado do quadro
  STYLE.ac_mentor = { skin: "#e0ac69", hair: "#cfcfcf", hs: "short", top: "#f2f2f2", jacket: "#2d3b55", legs: "#22263a", glasses: 1, beard: 1 };
  DESK.ac_mentor = { z: "srv", p: V(acEnd - 1.0 - .95, AC_ZC + 2.4), f: -1 };
  const mp = makePerson({ id: "ac_mentor", nm: "Artur · Mentor", c: "#9AE6B4" }); mp.mode = "teach"; mp.sit = false; mp.path = []; mp.name.style.display = "none"; acPeople.push(mp);
  rows.forEach((b, i) => {
    const x = AC_X0 + .4 + Math.floor(i / AC_ZS.length) * AC_DX, z = AC_ZS[i % AC_ZS.length], col = FCOL[i % FCOL.length];
    const g = new THREE.Group(); g.position.set(x, 0, z); acG.add(g);
    boxM(.7, .05, 1.2, mat("#c9a26b"), 0, .72, 0, g); [[-.3, -.5], [.3, -.5], [-.3, .5], [.3, .5]].forEach(([a, c]) => boxM(.05, .7, .05, mat("#333"), a, .35, c, g));
    boxM(.04, .3, .5, mat("#222"), .25, .9, 0, g); const sc = new THREE.Mesh(new THREE.PlaneGeometry(.46, .26), new THREE.MeshBasicMaterial({ color: 0x4FD1C5, toneMapped: false })); sc.position.set(.225, .9, 0); sc.rotation.y = -Math.PI / 2; g.add(sc);
    boxM(.3, .02, .4, mat("#f4f1e8"), -.12, .76, .25, g);           // caderno
    const ch = new THREE.Group(); ch.position.set(-.85, 0, 0); g.add(ch); boxM(.45, .06, .45, mat("#2b2b40"), 0, .46, 0, ch); boxM(.06, .5, .45, mat("#2b2b40"), -.22, .74, 0, ch);
    const key = "ac_" + b.id, nm = b.persona || b.id, h = hsh(b.id), fem = FEM.has(nm);
    STYLE[key] = { skin: SKINS[h % SKINS.length], hair: HAIRS[(h >> 2) % HAIRS.length], hs: fem ? (h % 2 ? "long" : "bun") : ["short", "buzz", "curly"][h % 3], top: col, legs: "#1d1b2e", glasses: h % 3 === 0 ? 1 : 0 };
    DESK[key] = { z: "srv", p: V(x + .1, z), f: 1 };
    const p = makePerson({ id: key, nm, c: col }); p.mode = "work"; p.sit = true; p.path = []; p.name.style.display = "none"; acPeople.push(p);
  });
}
function goAcademy() { const len = acEnd - (AC_X0 - 1), T = V(AC_X0 - 1 + len / 2 + 1.2, AC_ZC + .35), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target); cam.position.copy(ctl.target.clone().add(d.setLength(15 + len * .5))); ctl.update(); }

// ---------- equipa permanente: trabalho que corre em CADA scan de 5 min ----------
// Os agentes agendados (Jorge, Ines, Andre, Nuno, Sofia, Henrique) so trabalham
// quando a corrida deles acontece; estas pessoas fazem o trabalho continuo que
// o scanner faz de facto a cada 5 minutos, por isso nunca ha salas vazias.
// Cada ecra mostra os numeros reais do ultimo scan.
const STAFF = [
  { id: "acaso", nm: "Clara · Acaso", z: "lab", p: V(-15.2, 2.5), c: "#B794F4", st: { skin: "#f1c27d", hair: "#1c1c1c", hs: "bun", top: "#B794F4", jacket: "#3b2f5a", legs: "#232033", glasses: 1 } },
  { id: "regime", nm: "Hugo · Regime", z: "lab", p: V(-15.2, 6.2), c: "#4FD1C5", st: { skin: "#e0ac69", hair: "#4a3020", hs: "short", top: "#e8eef7", jacket: "#22404a", legs: "#1f2a33", beard: 1 } },
  { id: "dados", nm: "Lúcia · Dados", z: "lab", p: V(-15.2, 9.9), c: "#63B3ED", st: { skin: "#8d5524", hair: "#111", hs: "long", top: "#63B3ED", legs: "#1d2433" } },
  { id: "risco", nm: "Paulo · Risco", z: "ctrl", p: V(10.5, 10.4), c: "#FC8181", st: { skin: "#ffdbac", hair: "#8a8a8a", hs: "short", top: "#f2f2f2", jacket: "#3a2a2a", legs: "#262626", glasses: 1 } },
];
let staffPeople = [], staffTex = {};
const pc = (x, d = 1) => (x == null || isNaN(x)) ? "–" : (x > 0 ? "+" : "") + Number(x).toFixed(d).replace(".", ",");
function staffLines(id) {
  const D = (API().D && API().D()) || {}, F = (API().files && API().files()) || {}, C = D.config || {};
  const ageMin = D.generated_at ? Math.round((Date.now() / 1000 - D.generated_at) / 60) : null;
  if (id === "acaso") {
    const rb = F.rb && F.rb.TODAS, lg = F.lg && F.lg.estrategias && F.lg.estrategias.TODAS;
    const pb = D.paper_bounce || {}, sh = D.paper_shadow || {};
    const pn = Object.values(pb).reduce((a, g) => a + (g.n || 0), 0) + (sh.n || 0);
    const po = Object.values(pb).reduce((a, g) => a + ((g.open || []).length), 0) + ((sh.open || []).length);
    return ["Mede tudo contra entradas ao acaso",
      rb ? [`Histórico ${pc(rb.r_real, 2)}R · acaso ${pc(rb.r_acaso_mediana, 2)}R`, rb.vantagem ? "#68D391" : "#FC8181"] : ["Histórico: a carregar…", "#93a4c3"],
      lg ? `Ao vivo: ${lg.n} sinais (faltam ${Math.max(0, 30 - lg.n)} p/ veredicto)` : "Ao vivo: à espera de sinais",
      `Papel: ${pn} fechadas · ${po} abertas agora`];
  }
  if (id === "regime") {
    const mf = D.market_filter || {}, ev = D.next_event, dv = D.derivatives_source || {};
    const h = ev && ev.t ? Math.round((ev.t - Date.now() / 1000) / 3600) : null;
    return ["Regime de mercado, a cada 5 min",
      mf.close ? [`BTC ${mf.btc_above_sma200 ? "acima" : "ABAIXO"} da média 200d (${pc(mf.distance_pct)}%)`, mf.btc_above_sma200 ? "#68D391" : "#FC8181"] : "BTC: a carregar…",
      `Derivados: ${dv.with_perp != null ? dv.with_perp + " moedas com funding" : "–"}`,
      ev ? [`${D.event_block ? "⛔ " : ""}${ev.name}${h != null ? (h >= 0 ? ` daqui a ${h} h` : "") : ""}`, D.event_block ? "#FC8181" : "#F6C453"] : "Sem eventos marcados"];
  }
  if (id === "dados") {
    const src = D.sources || {}, n = D.counts || {};
    const ok = Object.entries(src).map(([k, v]) => `${k} ${v.ok ? "✓" : "✗"}`).join(" · ");
    return ["Qualidade dos dados de cada scan",
      ok || "Fontes: a carregar…",
      `${n.pairs_seen || 0} pares → ${n.eligible || 0} elegíveis → ${n.data_valid || 0} válidos`,
      ageMin == null ? "–" : [`Último scan: há ${ageMin} min`, ageMin > 30 ? "#FC8181" : "#68D391"]];
  }
  const J = (D.journal || {}).rows || [], dec = new Set(J.filter(r => r.executed === false || r.user_closed_flag).map(r => r.id));
  const open = (D.active_signals || []).filter(s => s.mode !== "PAPER" && !dec.has(s.id) && s.status === "TRIGGERED").length;
  return ["Controla o risco antes de cada sinal",
    [`Abertas ${open}/${C.max_open_positions || "–"}`, open >= (C.max_open_positions || 99) ? "#F6C453" : "#68D391"],
    `Risco ${C.risk_pct_of_capital || "–"}% de ${C.capital_usdc != null ? Number(C.capital_usdc).toFixed(2).replace(".", ",") : "–"} USDC`,
    D.halt ? ["⛔ Programa travado", "#FC8181"] : [`Perda máx.: ${C.max_daily_loss_r || "–"}R/dia · ${C.max_weekly_loss_r || "–"}R/semana`, "#c9d3e6"]];
}
function drawStaff(g, S) {
  const W = 512, H = 384, L = staffLines(S.id);
  g.fillStyle = "#0b1220"; g.fillRect(0, 0, W, H); g.fillStyle = S.c; g.fillRect(0, 0, W, 8);
  g.fillStyle = "#e9eef7"; g.font = "800 34px system-ui"; g.fillText(S.nm, 20, 56);
  g.fillStyle = "#93a4c3"; g.font = "500 20px system-ui"; g.fillText(L[0], 20, 88);
  L.slice(1).forEach((x, i) => { const [t, c] = Array.isArray(x) ? x : [x, "#c9d3e6"]; g.fillStyle = c; g.font = (i === 0 ? "700 26px" : "600 22px") + " system-ui";
    let tt = t; while (g.measureText(tt).width > W - 40 && tt.length > 4) tt = tt.slice(0, -2); if (tt !== t) tt += "…"; g.fillText(tt, 20, 146 + i * 62); });
  g.fillStyle = "#4b5a75"; g.font = "16px system-ui"; g.fillText("dados do último scan · atualiza a cada 5 min", 20, H - 18);
}
function buildStaff() {
  STAFF.forEach(S => {
    DESK[S.id] = { z: S.z, p: S.p, f: 1 }; buildDesk(S.id); STYLE[S.id] = S.st;
    const tx = canvasTex(512, 384, g => drawStaff(g, S)); staffTex[S.id] = tx;
    const m = monOn[S.id].material; m.map = tx; m.color.set(0xffffff); m.needsUpdate = true;
    const pan = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 1.42), new THREE.MeshBasicMaterial({ map: tx, toneMapped: false }));
    pan.position.set(S.p.x + .62, 2.45, S.p.z); pan.rotation.y = -Math.PI / 2; scene.add(pan);
    boxM(.05, 1.5, 2.0, mat("#0d1224"), S.p.x + .66, 2.45, S.p.z); boxM(.06, .9, .06, mat("#222"), S.p.x + .66, 1.25, S.p.z);
    const p = makePerson({ id: S.id, nm: S.nm, c: S.c }); p.mode = "work"; p.sit = true; p.path = []; p.staffZone = S.z; p.name.style.display = "none"; staffPeople.push(p);
  });
}
function updateStaff() { STAFF.forEach(S => { const t = staffTex[S.id]; if (t) { drawStaff(t.userData.c.getContext("2d"), S); t.needsUpdate = true; } }); }

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
  sec_maj: { skin: "#ffdbac", hair: "#6b3b1f", hs: "bun", top: "#F6C453", jacket: "#2d2a55", legs: "#22223a" },
  sec_l1: { skin: "#e0ac69", hair: "#1a1a1a", hs: "short", top: "#63B3ED", legs: "#1d2a3d", glasses: 1 },
  sec_defi: { skin: "#8d5524", hair: "#111", hs: "long", top: "#68D391", legs: "#1f2b25" },
  sec_ai: { skin: "#f1c27d", hair: "#c9a26b", hs: "curly", top: "#B794F4", legs: "#252038" },
  sec_meme: { skin: "#c68642", hair: "#3b1a2a", hs: "long", top: "#FF6FB5", jacket: "#3a1f3f", legs: "#2a2028" },
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
    // 24/7 (decisao do Rui): entre corridas cada agente fica sobretudo na sua
    // secretaria, a acompanhar os dados ao vivo; pausas curtas no cafe
    if (true) {                            // 24/7: sempre a secretaria
      p.mode = "desk"; p.spot = null; p.sit = false; p.path = route(p, p.seat, DESK[p.a.id].z); p.dest = DESK[p.a.id].z;
      p.wait = 60 + Math.random() * 90; return;
    }
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
    if (L <= v) { pos.copy(tg); p.path.shift(); if (!p.path.length) { p.zone = p.dest; p.sit = p.mode === "work" || p.mode === "desk" || (p.spot != null && !!SPOTS[p.spot].sit); } }
    else { pos.addScaledVector(d.normalize(), v); p.g.rotation.y = Math.atan2(d.x, d.z); }
  } else if (p.mode !== "work" && p.mode !== "sleep") p.wait -= dt;
  const walking = p.path.length > 0;
  if (!walking) p.g.rotation.y = p.mode === "work" || p.mode === "desk" ? p.face : (p.spot != null && SPOTS[p.spot].r != null ? SPOTS[p.spot].r : p.g.rotation.y);
  const sit = p.sit && !walking, typing = (p.mode === "work" || p.mode === "desk") && sit, sleep = p.mode === "sleep" && !walking;
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
  labels.forEach(l => { const s = project(l.p); l.el.style.left = s.x + "px"; l.el.style.top = s.y + "px";
    l.el.style.display = s.ok && !(l.maxD && cam.position.distanceTo(l.near) > l.maxD) ? "" : "none"; });
  people.forEach(p => { const s = project(p.g.position.clone().setY(p.g.position.y + 2.5)); p.name.style.left = s.x + "px"; p.name.style.top = s.y + "px"; p.name.style.display = API().sel() === p.a.id ? "" : "none";
    p.name.textContent = p.a.nm + (p.mode === "sleep" && !p.path.length ? " 💤" : ""); });
  const od = API().data(); if (!od) return;
  bubble.style.display = ctl.target.x > 21 ? "none" : "";
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
  people.forEach(p => { const on = (p.mode === "work" || p.mode === "desk") && p.sit && !p.path.length, m = monOn[p.a.id].material, tx = deskTex[p.a.id] || monTex;
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
  if (nowMs - (frame.tvAt || -1e9) > 30000 || tvT <= 0) { frame.tvAt = nowMs; tvT = 30; drawTV(tvTex.userData.c.getContext("2d")); tvTex.needsUpdate = true; if (mesaTex) { mesaI++; drawMesa(mesaTex.userData.c.getContext("2d")); mesaTex.needsUpdate = true; } updateRadar(); updateArena(); updateRewards(); updateSectors(); updateStrategyRoom(); updateStaff(); updateAcademy(); updateMoney(); drawBoard(board.userData.c.getContext("2d")); board.needsUpdate = true; }
  if (radar) { radar.sweep.rotation.z -= dt * 1.4; radar.blips.children.forEach((b, i) => { if (b.geometry.type === "SphereGeometry") b.scale.setScalar(1 + Math.sin(t * 4 + i) * .15); }); }
  animateArena(dt, t); animateRewards(dt, t); secPeople.forEach(p => animate(p, dt, t)); stPeople.forEach(p => animate(p, dt, t)); staffPeople.forEach(p => animate(p, dt, t)); acPeople.forEach(p => animate(p, dt, t));
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
  R.setClearColor(0x1b1f27); R.domElement.style.borderRadius = "0"; R.domElement.style.display = "block"; R.domElement.style.touchAction = "none";
  box.appendChild(R.domElement);
  overlay = document.createElement("div"); overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden;border-radius:12px"; box.appendChild(overlay);
  bubble = document.createElement("div"); bubble.className = "obub3"; overlay.appendChild(bubble);
  if (!document.getElementById("odetail")) { const det = document.createElement("div"); det.id = "odetail"; box.parentNode.insertBefore(det, box.nextSibling); }
  scene = new THREE.Scene(); scene.fog = new THREE.Fog(0x1b1f27, 50, 95);
  cam = new THREE.PerspectiveCamera(42, 1.3, .1, 200); cam.position.set(9, 17, 19);
  ctl = new OrbitControls(cam, R.domElement); ctl.target.set(0, 0, 0); ctl.enableDamping = true; ctl.minDistance = 10; ctl.maxDistance = 70;
  ctl.maxPolarAngle = 1.25; ctl.minPolarAngle = .35;
  // andar pelo escritorio: um dedo arrasta e desloca sobre o chao (para cima =
  // para a frente); dois dedos rodam e aproximam. No rato: esquerdo roda,
  // direito anda, roda do rato aproxima.
  ctl.enablePan = true; ctl.screenSpacePanning = false; ctl.panSpeed = 1.6; ctl.minDistance = 4;
  ctl.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
  ctl.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
  // nao sair do escritorio: o ponto para onde se olha fica dentro das paredes
  ctl.addEventListener("change", () => { const t = ctl.target, cx = Math.max(-18.5, Math.min(Math.max(48, ST_WALL + stLen + 2, acEnd + 1), t.x)), cz = Math.max(t.x > 19 ? -14 : -8.5, Math.min(t.x > 19 ? 14 : 11.5, t.z));
    if (cx !== t.x || cz !== t.z || t.y !== 0) { const dx = cx - t.x, dz = cz - t.z, dy = -t.y; t.set(cx, 0, cz); cam.position.x += dx; cam.position.z += dz; cam.position.y += dy; } });
  scene.add(new THREE.HemisphereLight(0xffffff, 0x6b6f78, 1.75));
  const dl = new THREE.DirectionalLight(0xfff4e8, 1.35); dl.position.set(8, 20, 10); scene.add(dl);
  // sombras suaves (desligadas em telemoveis fracos, ver qualidade abaixo)
  const lowEnd = (navigator.hardwareConcurrency || 4) <= 4 && /iPhone|Android/.test(navigator.userAgent) && Math.min(screen.width, screen.height) < 380;
  if (!lowEnd) { R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFSoftShadowMap; dl.castShadow = true; dl.shadow.mapSize.set(1024, 1024);
    Object.assign(dl.shadow.camera, { left: -24, right: 24, top: 16, bottom: -16, near: 1, far: 60 }); dl.shadow.bias = -.0008; }
  const pl1 = new THREE.PointLight(0xff6fb5, 30, 26); pl1.position.set(0, 4, 0); scene.add(pl1);
  const pl2 = new THREE.PointLight(0x4fd1c5, 25, 24); pl2.position.set(-10, 4, -6); scene.add(pl2);
  R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.15; R.outputColorSpace = THREE.SRGBColorSpace;
  try {
    composer = new EffectComposer(R); composer.addPass(new RenderPass(scene, cam));
    bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), .28, .4, .92); composer.addPass(bloom); composer.addPass(new OutputPass());
  } catch (e) { composer = null; }
  monTex = canvasTex(256, 160, drawMon);
  buildRoom(); buildAccessories(); Object.keys(DESK).forEach(buildDesk); buildRadar(); buildBoard(); updateRadar(); buildArena(); buildRewards(); buildSectors(); buildStrategyRoom(); buildStaff(); buildMemorial(); buildAcademy(); buildOpsMoney(); updateMoney(); arenaSig = ""; updateArena();
  people = API().agents.map(makePerson);
  // ao abrir: quem esta em pausa ja esta num sitio de descanso (sem marcha em
  // grupo pelo corredor), cada um com a sua faixa e o seu ritmo
  const used = new Set();
  people.forEach((p, i) => {
    p.lane = (i - 3.5) * .32; const st = stateOf(p.a.id); p.state = st;
    if (st === "work") return;
    { p.mode = "desk"; p.wait = 30 + Math.random() * 90; return; }   // ja sentado, a trabalhar
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
    const sh = ray.intersectObjects(secPeople.map(p => p.g), true)[0]; if (sh) { API().openZone("sectors"); return; }
    // lutadores (arena, sala de estrategia, academia): cartao com o combate e o que fazem agora
    const fid = h => { let o = h && h.object; while (o && !o.userData.agent) o = o.parent; const k = o && o.userData.agent || ""; return /^(fx|st|ac)_/.test(k) && k !== "ac_mentor" ? k.slice(3) : null; };
    const fh = ray.intersectObjects(fighters.map(f => f.g), true)[0] || ray.intersectObjects(stPeople.map(p => p.g), true)[0] || ray.intersectObjects(acPeople.map(p => p.g), true)[0];
    if (fh) { const id = fid(fh); if (id && API().fighter) API().fighter(id); else API().openZone("arena"); return; }
    const sf = ray.intersectObjects(staffPeople.map(p => p.g), true)[0]; if (sf) { let o = sf.object; while (o && !o.userData.agent) o = o.parent; const q = staffPeople.find(p => p.a.id === (o && o.userData.agent)); API().openZone(q ? q.staffZone : "lab"); return; }
    const zh = ray.intersectObjects(zoneHits, false)[0]; if (zh) API().openZone(zh.object.userData.zone);
  });
  new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(box);
  addEventListener("resize", resize); resize();
  clock = new THREE.Clock(); running = true; frame();
  return true;
}
// voltar a vista inicial (botao no ecra)
function resetView() { resize.done = false; ctl.target.set(0, 0, 0); resize(); ctl.update(); }
function goArena() { const tx = ARENA_C.x + 2, dx = tx - ctl.target.x, dz = ARENA_C.z - ctl.target.z; ctl.target.set(tx, 0, ARENA_C.z); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target), want = 30; if (d.length() > want) cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
function goRewards() { const T = V(TRO_X0 + TRO_LEN / 2, TRO_ZC + .35), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target); cam.position.copy(ctl.target.clone().add(d.setLength(14 + TRO_LEN * .5))); ctl.update(); }
function goSectors() { const T = V(23.8, 10.9), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target), want = 18; if (d.length() > want) cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
function goStrategy() { const T = V(ST_WALL + stLen / 2 + .6, 0), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target), want = 17 + stLen * .35; cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
function goTo(x, z, want = 14) { const T = V(x, z), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target); cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
window.Office3D = { init, supported, refresh: () => { tvT = 0; }, resetView, goArena, goRewards, goSectors, goStrategy, goMemorial, goAcademy, goTo };
