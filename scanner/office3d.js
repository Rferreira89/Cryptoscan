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
    .forEach((s, i) => g.fillText(s.slice(0, 38), 24, 92 + i * 40));
  const M = D.meta; if (M) { g.fillStyle = "#F6C453"; g.font = "bold 22px sans-serif";
    g.fillText(`🎯 Objetivo: ${Math.round(M.marco)} USDC (faltam ${M.falta_marco.toFixed(2).replace(".", ",")})`.slice(0, 40), 24, 266); }
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
  g.fillStyle = m.a_favor ? "#68D391" : "#a0aec0"; g.font = "22px sans-serif"; g.fillText(`${m.a_favor} de ${m.votantes} operavam`, 150, 80);
  g.font = "19px sans-serif";
  v.slice(0, 10).forEach((x, i) => { const col = i % 2, row = Math.floor(i / 2), X = 18 + col * 248, Y = 122 + row * 50;
    const on = x.voto !== "não";
    g.fillStyle = on ? (x.voto === "vende" ? "#4d1f2a" : "#1f4d3a") : "#2a2f45"; g.fillRect(X, Y - 26, 236, 40);
    g.fillStyle = on ? (x.voto === "vende" ? "#FEB2B2" : "#9AE6B4") : "#cbd5e0"; g.fillText(`${x.voto === "entra" ? "✅" : x.voto === "vende" ? "🔻" : "❌"} ${x.persona}`, X + 8, Y);
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
  TREND_DAILY: "Tendência", BOUNCE_G0: "Bounce G0", BOUNCE_V1: "Bounce V1", BOUNCE_V2: "Bounce V2", BOUNCE_V3: "Bounce V3", BOUNCE_1H: "Bounce 1H", BOUNCE_X30: "Bounce RSI30", DIP_TREND: "Recuo forte", CAPITULACAO: "Capitulação", BOUNCE_FLUXO: "Bounce fluxo", BOUNCE_FORTE: "Bounce forte", BOUNCE_SQUEEZE: "Bounce squeeze", BOUNCE_ISOLADA: "Bounce isolada", BOUNCE_DESALAV: "Desalavancagem", BOUNCE_MACRO: "Macro favorável", BOUNCE_MEDO: "Medo macro", BOUNCE_ABSORCAO: "Absorção", BOUNCE_LSR: "Long/short", BRK_ESPACO: "Rompimento c/ espaço", RETESTE: "Reteste", TURTLE: "Tartarugas", SQUEEZE_BB: "Compressão", MOMENTUM: "Momentum", SHORT_X30: "Short RSI70", SHORT_FLUXO: "Short fluxo", SHORT_TURTLE: "Short 20d", SHORT_SQUEEZE: "Short funding", SHORT_ISOLADA: "Short isolada", REJEITADOS: "Rejeitados" };
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
const FEM = new Set(["Paulina", "Rita", "Vera", "Violeta", "Raquel", "Leonor", "Matilde", "Carolina", "Beatriz", "Mariana", "Francisca", "Clara", "Joana", "Catarina", "Lara", "Sofia", "Marta", "Inês", "Carla", "Patrícia", "Diana", "Fernanda", "Isabel", "Dália", "Mónica", "Xénia", "Filipa", "Sara", "Irene"]);
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
function goMemorial() { p2Leave(); const n = Math.max(1, Math.ceil(arenaRows().filter(b => b.estado === "MORTA").length / MEM_Z.length)), len = 1.6 + n * MEM_DX;
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
function goAcademy() { p2Leave(); const len = acEnd - (AC_X0 - 1), T = V(AC_X0 - 1 + len / 2 + 1.2, AC_ZC + .35), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
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

// ---------- gabinete do Diretor de Trading (a oeste da mesa de operacoes) ----------
// Coordena as analises, verifica conflitos e autoriza ou rejeita cada entrada
// real. O ecra grande mostra a ultima decisao (carimbo verde ou vermelho), o
// da parede lateral as cinco regras e se a ultima entrada passou em cada uma.
const DIR = { x: [-32.5, -21.4], z: [-6.5, 6.5], c: "#F6C453" }, DIR_C = V(-27, 0);
let dirTex = null, dirRulesTex = null, dirLamp = null, dirLampL = null, dirPeople = [], dirSig = "";
const DIR_RULES = [["R1", "Dados válidos e frescos", m => /dados|velas|fontes|preço da Bybit/.test(m)],
  ["R2", "Plano coerente e R:R ≥ 1,2", m => /plano|R:R/.test(m)],
  ["R3", "Menos de 3 departamentos contra", m => /departamentos contra/.test(m)],
  ["R4", "Macroeconomia sem medo", m => /macroeconomia/.test(m)],
  ["R5", "Derivados não contra + outro", m => /derivados contra/.test(m)],
  ["R6", "Histórico a favor nesta fase", m => /histórico contra/.test(m)]];
function dirData() { return (API().D && API().D() || {}).diretor || {}; }
function wrap(g, t, x, y, w, lh, max) { const ws = String(t).split(" "); let l = "", n = 0;
  for (const w_ of ws) { const tt = l ? l + " " + w_ : w_; if (g.measureText(tt).width > w && l) { g.fillText(l, x, y + n * lh); l = w_; if (++n >= max) return n; } else l = tt; }
  if (l && n < max) { g.fillText(l, x, y + n * lh); n++; } return n; }
function drawDirector(g) {
  const W = 1024, H = 576, R = dirData(), L = R.decisoes || [], x = L[0], A = R.avaliacao || {};
  g.fillStyle = "#0b1020"; g.fillRect(0, 0, W, H); g.fillStyle = DIR.c; g.fillRect(0, 0, W, 10);
  g.fillStyle = "#F6E7B0"; g.font = "800 44px system-ui"; g.fillText("🧭 Diretor de Trading", 32, 66);
  g.fillStyle = "#93a4c3"; g.font = "600 22px system-ui"; g.fillText(`24h: ${R.autorizados_24h || 0} autorizadas · ${R.rejeitados_24h || 0} rejeitadas`, 32, 102);
  if (!x) { g.fillStyle = "#cbd5e0"; g.font = "600 32px system-ui"; g.fillText("Sem entradas para rever.", 32, 200);
    g.font = "500 24px system-ui"; g.fillStyle = "#93a4c3"; wrap(g, "Nenhuma entrada real chega ao Telegram sem passar por aqui. Cada agente entrega um relatório estruturado e o diretor decide com regras definidas antes.", 32, 250, W - 64, 34, 4); }
  else {
    const ok = x.decisao === "AUTORIZADO", col = ok ? "#68D391" : "#FC8181";
    g.save(); g.translate(W - 230, 190); g.rotate(-.12); g.strokeStyle = col; g.lineWidth = 8; g.strokeRect(-170, -48, 340, 96);
    g.fillStyle = col; g.font = "900 46px system-ui"; g.textAlign = "center"; g.fillText(ok ? "AUTORIZADO" : "REJEITADO", 0, 16); g.restore(); g.textAlign = "left";
    g.fillStyle = "#fff"; g.font = "800 56px system-ui"; g.fillText(x.ativo, 32, 178);
    g.fillStyle = "#c9d3e6"; g.font = "600 24px system-ui"; g.fillText(`${x.estrategia} · ${x.lado === "SHORT" ? "venda" : "compra"} · dados ${({ valido: "válidos", atrasado: "atrasados", indisponivel: "indisponíveis" })[x.estado_dados] || x.estado_dados}`, 32, 214);
    g.fillStyle = "#718096"; g.font = "500 20px system-ui"; g.fillText(new Date(x.t * 1000).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }), 32, 244);
    let y = 296; g.font = "600 23px system-ui";
    const lines = [...(x.motivos || []).map(m => ["✖ " + m, "#FEB2B2"]), ...(x.a_favor || []).slice(0, 3).map(m => ["✔ " + m, "#9AE6B4"]),
      ...(x.contra || []).slice(0, 2).map(m => ["✖ " + m, "#FEB2B2"]), ...((x.invalidacao || []).slice(0, 1).map(m => ["Invalida se: " + m, "#F6C453"]))];
    for (const [t, c] of lines) { if (y > H - 70) break; g.fillStyle = c; y += 32 * wrap(g, t, 32, y, W - 64, 30, 2) + 6; }
  }
  g.fillStyle = "#4b5a75"; g.font = "18px system-ui";
  g.fillText(`Rejeições seguidas em papel: ${A.evitou_perda || 0} evitaram perda · ${A.custou_ganho || 0} custaram ganho · ${A.em_curso || 0} em curso`, 32, H - 22);
}
function drawDirRules(g) {
  const W = 512, H = 576, x = (dirData().decisoes || [])[0], ms = (x && x.motivos) || [];
  g.fillStyle = "#0b1020"; g.fillRect(0, 0, W, H); g.fillStyle = DIR.c; g.fillRect(0, 0, W, 8);
  g.fillStyle = "#F6E7B0"; g.font = "800 32px system-ui"; g.fillText("Regras do diretor", 24, 56);
  const M = (API().D && API().D() || {}).meta;
  g.fillStyle = "#93a4c3"; g.font = "500 18px system-ui"; g.fillText((x ? `última revisão: ${x.ativo}` : "definidas antes de cada entrada")
    + (M ? ` · objetivo ${Math.round(M.marco)} USDC` : ""), 24, 86);
  DIR_RULES.forEach(([k, t, f], i) => { const y = 132 + i * 70, bad = x && ms.some(f), col = !x ? "#4b5a75" : bad ? "#FC8181" : "#68D391";
    g.fillStyle = "#141c33"; g.fillRect(16, y - 38, W - 32, 60); g.fillStyle = col; g.fillRect(16, y - 38, 8, 60);
    g.font = "800 26px system-ui"; g.fillText(!x ? "•" : bad ? "✖" : "✔", 38, y + 2);
    g.fillStyle = "#e9eef7"; g.font = "800 24px system-ui"; g.fillText(k, 76, y + 2); g.font = "600 21px system-ui"; g.fillStyle = "#c9d3e6"; g.fillText(t, 130, y + 2); });
  g.fillStyle = "#4b5a75"; g.font = "16px system-ui"; g.fillText("toca para ver os relatórios dos agentes", 24, H - 20);
}
function buildDirector() {
  const w = DIR.x[1] - DIR.x[0], d = DIR.z[1] - DIR.z[0], cx = (DIR.x[0] + DIR.x[1]) / 2, cz = (DIR.z[0] + DIR.z[1]) / 2;
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat("#3a2f26")); fl.rotation.x = -Math.PI / 2; fl.position.set(cx, .012, cz); fl.receiveShadow = true; scene.add(fl);
  const rug = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 4.2), mat("#5a2333")); rug.rotation.x = -Math.PI / 2; rug.position.set(DIR_C.x, .02, DIR_C.z); scene.add(rug);
  const glass = mat(DIR.c, .15, .07), h = 2.8, col = new THREE.Color(DIR.c);
  // paredes: fundo (z min), frente (z max, baixa para se ver) e lado oeste; lado este aberto para o escritorio
  boxM(w, h, .05, glass, cx, h / 2, DIR.z[0]); boxM(.05, h, d, glass, DIR.x[0], h / 2, cz); boxM(w, .9, .05, glass, cx, .45, DIR.z[1]);
  const c = [V(DIR.x[0], DIR.z[0]), V(DIR.x[1], DIR.z[0]), V(DIR.x[1], DIR.z[1]), V(DIR.x[0], DIR.z[1]), V(DIR.x[0], DIR.z[0])];
  line(c.map(p => p.clone().setY(.03)), col); line([c[0], c[1]].map(p => p.clone().setY(h)), col); line([c[0], c[3]].map(p => p.clone().setY(h)), col);
  // ecra grande na parede do fundo (a ultima decisao) e ecra das regras na parede oeste
  dirTex = canvasTex(1024, 576, drawDirector);
  const big = new THREE.Mesh(new THREE.PlaneGeometry(6.4, 3.6), new THREE.MeshBasicMaterial({ map: dirTex, toneMapped: false })); big.position.set(cx + .4, 1.95, DIR.z[0] + .1); scene.add(big);
  boxM(6.6, 3.8, .06, mat("#0d1224"), cx + .4, 1.95, DIR.z[0] + .03);
  dirRulesTex = canvasTex(512, 576, drawDirRules);
  const rs = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 3.375), new THREE.MeshBasicMaterial({ map: dirRulesTex, toneMapped: false })); rs.position.set(DIR.x[0] + .06, 1.85, 1.6); rs.rotation.y = Math.PI / 2; scene.add(rs);
  [big, rs].forEach(m => { const hh = m.clone(); hh.material = new THREE.MeshBasicMaterial({ visible: false }); hh.userData.zone = "diretor"; scene.add(hh); zoneHits.push(hh); });
  // secretaria executiva com o diretor, duas cadeiras para quem vem reportar
  DESK.diretor = { z: "ops", p: DIR_C.clone(), f: 1 }; buildDesk("diretor");
  boxM(1.5, .06, 2.6, mat("#5b3a22"), DIR_C.x, .78, DIR_C.z);                    // tampo maior, em madeira escura
  [[1.0, -.6], [1.0, .6]].forEach(([dx, dz]) => { const ch = new THREE.Group(); ch.position.set(DIR_C.x + dx + .3, 0, DIR_C.z + dz); ch.rotation.y = -Math.PI / 2; scene.add(ch);
    boxM(.55, .08, .55, mat("#4a2a35"), 0, .48, 0, ch); boxM(.55, .6, .08, mat("#4a2a35"), 0, .8, -.27, ch); boxM(.06, .45, .06, mat("#111"), 0, .24, 0, ch); });
  // estante, planta e luz de estado (verde: autorizou; vermelho: rejeitou)
  boxM(.5, 2.0, 2.4, mat("#3b2a1a"), DIR.x[0] + .4, 1.0, -4.2); [.5, 1.1, 1.7].forEach(y => boxM(.45, .03, 2.3, mat("#c08a5a"), DIR.x[0] + .4, y, -4.2));
  [[-4.6, "#B794F4"], [-4.0, "#63B3ED"], [-3.5, "#F6C453"]].forEach(([z, cc]) => boxM(.3, .4, .25, mat(cc, .3), DIR.x[0] + .4, .72, z));
  boxM(.5, .5, .5, mat("#7a4b2a"), DIR.x[1] - .6, .25, DIR.z[0] + .6); const pl = new THREE.Mesh(new THREE.SphereGeometry(.55, 12, 10), mat("#38d6b5", .25)); pl.position.set(DIR.x[1] - .6, 1, DIR.z[0] + .6); scene.add(pl);
  dirLamp = new THREE.Mesh(new THREE.SphereGeometry(.16, 16, 12), mat("#F6C453", 2)); dirLamp.position.set(DIR_C.x - .2, 1.35, DIR_C.z - 1.05); scene.add(dirLamp);
  boxM(.05, .5, .05, mat("#222"), DIR_C.x - .2, 1.05, DIR_C.z - 1.05);
  dirLampL = new THREE.PointLight(0xF6C453, 6, 7); dirLampL.position.set(DIR_C.x, 2.4, DIR_C.z); scene.add(dirLampL);
  // a pessoa
  STYLE.diretor = { skin: "#e0ac69", hair: "#3a2a1a", hs: "short", top: "#f4f4f4", jacket: "#1c2440", legs: "#1a1f30", glasses: 1, beard: 1 };
  const tx = canvasTex(512, 384, () => {}); const m = monOn.diretor.material; m.map = dirTex; m.color.set(0xffffff); m.needsUpdate = true;
  const p = makePerson({ id: "diretor", nm: "Diretor de Trading", c: DIR.c }); p.mode = "work"; p.sit = true; p.path = []; p.name.style.display = "none"; dirPeople.push(p);
  const zl = label("🧭 Gabinete do Diretor de Trading", DIR.c, true); zl.style.pointerEvents = "auto"; zl.style.cursor = "pointer"; zl.style.padding = "3px 8px"; zl.style.borderRadius = "99px"; zl.style.background = "#0c0a24b3"; zl.style.border = `1px solid ${DIR.c}66`;
  zl.addEventListener("click", () => API().openZone("diretor")); labels.push({ el: zl, p: new THREE.Vector3(cx, 4.4, DIR.z[0] + .2) });
  updateDirector(true);
}
function updateDirector(force) {
  if (!dirTex) return; const x = (dirData().decisoes || [])[0], sig = x ? x.t + x.ativo + x.decisao : "-";
  drawDirector(dirTex.userData.c.getContext("2d")); dirTex.needsUpdate = true; drawDirRules(dirRulesTex.userData.c.getContext("2d")); dirRulesTex.needsUpdate = true;
  const c = !x ? 0xF6C453 : x.decisao === "AUTORIZADO" ? 0x68D391 : 0xFC8181; dirLamp.material.color.setHex(c); dirLamp.material.emissive && dirLamp.material.emissive.setHex(c); dirLampL.color.setHex(c);
  if (!force && sig !== dirSig && x) { const pp = dirLamp.position.clone(); pp.y += .4; if (x.decisao === "AUTORIZADO") burst(pp); }   // nova autorizacao: confetes
  dirSig = sig;
}
// reuniao no gabinete: as falas da ultima revisao do diretor (ou, sem
// revisao recente, a mesa redonda da moeda mais quente), em balao, uma a uma
let dirBub = null, dirDlgI = 0, dirDlgAt = 0;
function dirDialogue() {
  const D = (API().D && API().D()) || {}, x = ((D.diretor || {}).decisoes || [])[0];
  if (x && x.dialogo && x.dialogo.length && Date.now() / 1000 - x.t < 6 * 3600) return x.dialogo;
  const m = (D.mesa || [])[0], r = m && (D.universe || []).find(u => u.asset === m.asset);
  const CC = D.codigo || [], pc = CC.length ? CC[Math.floor(Date.now() / 60000) % CC.length] : null;
  const lembra = pc ? [{ de: "Diretor", tom: "pergunta", texto: `Lembrem-se: ${pc.titulo}. ${pc.texto}` }] : [];
  if (!r || !(r.debate || []).length) return [{ de: "Diretor", tom: "pergunta", texto: "Sem propostas agora. Departamentos, avisem quando uma moeda virar." }].concat(lembra);
  const v = r.debate.filter(x => x.voto !== "não").concat(r.debate.filter(x => x.voto === "não")).slice(0, 4);
  return [{ de: "Diretor", tom: "pergunta", texto: `Mesa, alguém entra em ${m.asset}?` }]
    .concat(v.map(x => ({ de: x.persona, tom: x.voto === "entra" ? "favor" : "contra", texto: (x.voto === "entra" ? "Eu entrava: " : "Ainda não: ") + (x.razao || "") })))
    .concat([{ de: "Diretor", tom: "pergunta", texto: m.a_favor ? `${m.a_favor} de ${m.votantes} entravam. Só passa a sinal com o gatilho de um campeão e a minha revisão.` : "Ninguém entra. Esperamos pela viragem." }]).concat(lembra);
}
function placeDirBubble(dt) {
  if (!dirBub) { dirBub = document.createElement("div"); dirBub.className = "obub3"; dirBub.style.maxWidth = "calc(100% - 80px)"; overlay.appendChild(dirBub); }
  if (ctl.target.x > -16) { dirBub.style.display = "none"; return; }
  dirDlgAt -= dt; const L = dirDialogue();
  if (dirDlgAt <= 0) { dirDlgAt = 4.2; const m = L[(dirDlgI++) % L.length], dr = m.de === "Diretor";
    const col = dr ? DIR.c : m.tom === "proposta" ? "#4FD1C5" : m.tom === "favor" || m.tom === "autoriza" ? "#68D391" : m.tom === "esperado" ? "#93a4c3" : "#FC8181";
    dirBub.innerHTML = `<b>${m.de}</b><br>${m.texto}`; dirBub.style.borderColor = col; dirBub.dataset.dr = dr ? "1" : ""; }
  const at = dirBub.dataset.dr ? V(DIR_C.x - .9, DIR_C.z).setY(2.4) : V(DIR_C.x + 1.4, DIR_C.z).setY(1.9);
  const s = project(at); if (!s.ok) { dirBub.style.display = "none"; return; }
  dirBub.style.display = ""; const w = dirBub.offsetWidth, W = R.domElement.clientWidth;
  const hud = document.getElementById("hud"), top = hud ? hud.offsetHeight + 4 : 4;
  dirBub.style.left = Math.max(4, Math.min(W - w - 66, s.x - w / 2)) + "px"; dirBub.style.top = Math.max(top, s.y - dirBub.offsetHeight) + "px";
}
function goDirector() { p2Leave();                 // de frente para o ecra grande da parede do fundo
  const T = V(DIR_C.x + .4, DIR_C.z - 2.4); ctl.target.copy(T); const tall = innerHeight > innerWidth;
  cam.position.set(T.x + 1.6, tall ? 10.5 : 8, T.z + (tall ? 12.5 : 10)); ctl.update(); }

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
    // (20/10) pausas: de vez em quando vao ao cafe, ao sofa ou a sala de
    // reuniao; a maior parte do tempo continuam a secretaria
    if (p.mode !== "desk" || Math.random() < .72) {
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

// ---------- painel da missao (holograma no centro do corredor): capital, marco, nucleo,
// resultado real, risco e modo automatico, com os dados do ultimo scan ----------
let misTex = null, misScr = null;
function drawMission(g) {
  const D = API().D() || {}, M = D.meta, EV = D.evolucao, W = 768, H = 600;
  g.fillStyle = "#0b0a24"; g.fillRect(0, 0, W, H); g.strokeStyle = "#B794F4"; g.lineWidth = 5; g.strokeRect(3, 3, W - 6, H - 6);
  if (!M) { g.fillStyle = "#fff"; g.font = "700 30px system-ui"; g.fillText("Missão 1M · a carregar…", 30, 60); return; }
  const mk = M.marcos || [], i = mk.findIndex(x => !x.feito), prev = i > 0 ? mk[i - 1].valor : 0, nxt = i >= 0 ? mk[i].valor : 1e6;
  const pr = Math.max(.02, Math.min(1, (M.capital - prev) / (nxt - prev))), N = D.nucleo || {}, RE = D.reais || {}, RK = D.risco || {}, AU = D.auto || {};
  const f2 = v => Number(v).toFixed(2).replace(".", ","), sg = v => (v >= 0 ? "+" : "−") + f2(Math.abs(v)), UP = "#68D391", DN = "#FF8A80", cl = v => v >= 0 ? UP : DN;
  // cabecalho: capital e percentagem ganha (sem contar depositos)
  g.fillStyle = "#cfc8ff"; g.font = "700 24px system-ui"; g.fillText("🏁 MISSÃO 1M", 28, 46);
  g.fillStyle = "#9fb3c8"; g.font = "600 19px system-ui"; g.fillText(`${M.pct.toFixed(3).replace(".", ",")}% do milhão · marco ${nxt.toLocaleString("pt-PT")} USDC (${Math.round(pr * 100)}%)`, 28, 74);
  g.textAlign = "right"; g.fillStyle = "#fff"; g.font = "800 56px system-ui"; g.fillText(f2(M.capital), W - 96, 72); g.font = "700 20px system-ui"; g.fillStyle = "#9fb3c8"; g.fillText("USDC", W - 28, 72); g.textAlign = "left";
  g.fillStyle = "#221c5a"; g.fillRect(28, 88, W - 56, 10); const gr = g.createLinearGradient(28, 0, W - 28, 0); gr.addColorStop(0, "#4FD1C5"); gr.addColorStop(1, "#B794F4"); g.fillStyle = gr; g.fillRect(28, 88, (W - 56) * pr, 10);
  // percentagens por periodo
  const P = (EV && EV.periodos) || {}, chips = [["24 h", P.dia], ["7 dias", P.semana], ["30 dias", P.mes], ["Total", EV ? EV.pct : null]];
  chips.forEach(([t, v], k) => { const x = 28 + k * 180; g.fillStyle = "#14123a"; g.fillRect(x, 112, 168, 74);
    g.fillStyle = "#9fb3c8"; g.font = "600 18px system-ui"; g.fillText(t, x + 12, 138);
    g.fillStyle = v == null ? "#6b7a90" : cl(v); g.font = "800 30px system-ui"; g.fillText(v == null ? "a gravar" : (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2).replace(".", ",") + "%", x + 12, 174); });
  // grafico real: ganho acumulado em USDC (operacoes fechadas + valor horario da conta, sem depositos)
  const S = (EV && EV.serie) || [], X0 = 70, X1 = W - 28, Y0 = 210, Y1 = 420;
  g.fillStyle = "#0f0d2e"; g.fillRect(28, Y0 - 8, W - 56, Y1 - Y0 + 40);
  if (S.length >= 2) {
    const ts = S.map(p => p[0]), vs = S.map(p => p[1]), t0 = ts[0], t1 = Math.max(ts[ts.length - 1], t0 + 1);
    let lo = Math.min(0, ...vs), hi = Math.max(0, ...vs); if (hi - lo < 1) { hi += .5; lo -= .5; } const pad = (hi - lo) * .1; lo -= pad; hi += pad;
    const xp = t => X0 + (t - t0) / (t1 - t0) * (X1 - X0), yp = v => Y1 - (v - lo) / (hi - lo) * (Y1 - Y0);
    g.strokeStyle = "#2b2470"; g.lineWidth = 1; g.font = "600 15px system-ui"; g.fillStyle = "#8aa0b4"; g.textAlign = "right";
    [hi - pad, (hi + lo) / 2, lo + pad].forEach(v => { g.beginPath(); g.moveTo(X0, yp(v)); g.lineTo(X1, yp(v)); g.stroke(); g.fillText(sg(v), X0 - 6, yp(v) + 5); });
    g.textAlign = "left"; g.strokeStyle = "#cfc8ff66"; g.setLineDash([6, 6]); g.beginPath(); g.moveTo(X0, yp(0)); g.lineTo(X1, yp(0)); g.stroke(); g.setLineDash([]);
    // depositos marcados no grafico (nao contam como ganho)
    (EV.fluxos || []).filter(fx => fx[0] >= t0 && fx[0] <= t1).forEach(fx => { const x = xp(fx[0]);
      g.strokeStyle = "#63B3EDaa"; g.setLineDash([4, 5]); g.beginPath(); g.moveTo(x, Y0); g.lineTo(x, Y1); g.stroke(); g.setLineDash([]);
      g.fillStyle = "#63B3ED"; g.font = "700 15px system-ui"; g.textAlign = x > X1 - 90 ? "right" : "left"; g.fillText(`${fx[1] >= 0 ? "+" : "−"}${Math.round(Math.abs(fx[1]))} depósito`, x + (x > X1 - 90 ? -5 : 5), Y1 - 8); g.textAlign = "left"; });
    const last = vs[vs.length - 1], c = cl(last);
    g.beginPath(); g.moveTo(xp(ts[0]), yp(0)); S.forEach(([t, v]) => g.lineTo(xp(t), yp(v))); g.lineTo(xp(ts[ts.length - 1]), yp(0)); g.closePath(); g.fillStyle = c + "33"; g.fill();
    g.beginPath(); S.forEach(([t, v], k) => k ? g.lineTo(xp(t), yp(v)) : g.moveTo(xp(t), yp(v))); g.strokeStyle = c; g.lineWidth = 3.5; g.stroke();
    g.fillStyle = c; g.beginPath(); g.arc(xp(ts[ts.length - 1]), yp(last), 6, 0, 7); g.fill();
    const dt = t => new Date(t * 1000).toLocaleDateString("pt-PT", { day: "2-digit", month: "2-digit" });
    g.fillStyle = "#8aa0b4"; g.font = "600 15px system-ui"; g.fillText(dt(t0), X0, Y1 + 24); g.textAlign = "right"; g.fillText("agora", X1, Y1 + 24); g.textAlign = "left";
    g.fillStyle = c; g.font = "800 22px system-ui"; g.fillText(`Ganho real: ${sg(EV.g_usdc)} USDC`, X0 + 8, Y0 + 20);
    g.fillStyle = "#9fb3c8"; g.font = "600 17px system-ui"; g.textAlign = "right"; g.fillText(`puseste ${f2(EV.investido)} · vale ${f2(M.capital)}`, X1 - 6, Y0 + 20); g.textAlign = "left";
  } else { g.fillStyle = "#9fb3c8"; g.font = "600 20px system-ui"; g.fillText("O gráfico real começa com a primeira amostra da conta.", 48, 320); }
  // caixas
  let nv = 0, nr = 0; Object.entries(N.plano || {}).forEach(([k, p]) => { if (N.pos && N.pos[k]) { nv += p.valor_usdc || 0; nr += p.resultado_usdc || 0; } });
  const box = (x, t, v, c) => { g.fillStyle = "#14123a"; g.fillRect(x, 462, 230, 84); g.fillStyle = "#9fb3c8"; g.font = "600 18px system-ui"; g.fillText(t, x + 12, 490); g.fillStyle = c || "#fff"; g.font = "800 26px system-ui"; g.fillText(v, x + 12, 530); };
  box(28, "🧱 Núcleo", nv ? `${Math.round(nv)} · ${sg(nr)}` : (N.ligado ? "à espera" : "desligado"), cl(nr));
  box(269, "🧾 Ativas (real)", RE.n ? `${sg(RE.pnl_usdc)} · ${RE.n} op.` : "sem fechos", cl(RE.pnl_usdc || 0));
  box(510, AU.ligado ? "🤖 Auto ligado" : "🤖 Auto desligado", "Risco " + (RK.reduzido ? "½" : "normal"), RK.reduzido ? "#F6C453" : UP);
  g.fillStyle = "#8aa0b4"; g.font = "600 15px system-ui";
  g.fillText(`Ganho sem contar depósitos (linhas azuis) · campeão: ${((D.promo || {}).campeoes || []).join(", ") || "nenhum"} · toca para ampliar`.slice(0, 96), 28, 576);
}
function buildMission() {
  misTex = canvasTex(768, 600, drawMission);
  misScr = new THREE.Mesh(new THREE.PlaneGeometry(5.6, 4.375), new THREE.MeshBasicMaterial({ map: misTex, toneMapped: false, side: THREE.DoubleSide }));
  misScr.position.set(0, 4.0, 0); scene.add(misScr);
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.1, 1.3, 40), new THREE.MeshBasicMaterial({ color: 0xB794F4, transparent: true, opacity: .55, toneMapped: false })); ring.rotation.x = -Math.PI / 2; ring.position.set(0, .03, 0); scene.add(ring);
  boxM(.06, 2, .06, mat("#B794F4", .8, .5), 0, 1, 0);
}
// toque no painel: abre-o em grande, por cima do escritorio
function showMission() {
  updateMission(); updateCofre(); let el = document.getElementById("misbig");
  if (!el) { el = document.createElement("div"); el.id = "misbig"; el.style.cssText = "position:fixed;inset:0;z-index:70;background:#05041acc;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:16px";
    el.innerHTML = '<img alt="Painel da missão" style="width:min(100%,760px);border-radius:14px;box-shadow:0 0 40px #B794F466"><div style="display:flex;gap:8px"><button data-k="g" style="font:700 14px system-ui;padding:10px 16px;border-radius:99px;border:1px solid #B794F4;background:#2a1d5e;color:#fff">Abrir o gestor</button><button data-k="x" style="font:700 14px system-ui;padding:10px 16px;border-radius:99px;border:1px solid #555;background:#111;color:#fff">Fechar</button></div>';
    el.addEventListener("click", e => { const k = e.target.dataset && e.target.dataset.k; el.style.display = "none"; if (k === "g") API().openZone("ops"); });
    document.body.appendChild(el); }
  el.querySelector("img").src = misTex.userData.c.toDataURL(); el.style.display = "flex";
}
function updateMission() { if (misTex) { drawMission(misTex.userData.c.getContext("2d")); misTex.needsUpdate = true; } }

// ---------- cofre do nucleo (fundo sul do corredor): o valor de cada moeda e
// quanto falta para o ponto de saida (fecho diario abaixo da media de 200 dias) ----------
let cofreTex = null, cofreScr = null;
function drawCofre(g) {
  const N = (API().D() || {}).nucleo || {}, W = 768, H = 470, cor = { BTC: "#F7931A", ETH: "#8C8CF7", SOL: "#14F195" };
  g.fillStyle = "#0d0b06"; g.fillRect(0, 0, W, H); g.strokeStyle = "#F6C453"; g.lineWidth = 5; g.strokeRect(3, 3, W - 6, H - 6);
  const f2 = v => Number(v).toFixed(2).replace(".", ","), sg = v => (v >= 0 ? "+" : "−") + f2(Math.abs(v)), px = v => v >= 100 ? Math.round(v).toLocaleString("pt-PT") : Number(v).toFixed(2).replace(".", ",");
  let tv = 0, tr = 0; const P = N.plano || {};
  Object.entries(P).forEach(([a, p]) => { if (N.pos && N.pos[a]) { tv += p.valor_usdc || 0; tr += p.resultado_usdc || 0; } });
  g.fillStyle = "#F6C453"; g.font = "800 28px system-ui"; g.fillText("🧱 COFRE DO NÚCLEO", 26, 48);
  g.textAlign = "right"; g.fillStyle = "#fff"; g.font = "800 34px system-ui"; g.fillText(f2(tv) + " USDC", W - 26, 48);
  g.fillStyle = tr >= 0 ? "#68D391" : "#FF8A80"; g.font = "700 22px system-ui"; g.fillText(sg(tr) + " USDC", W - 26, 78); g.textAlign = "left";
  g.fillStyle = "#b8a77a"; g.font = "600 17px system-ui"; g.fillText("Spot, sem alavancagem · sai para USDC se o fecho diário ficar abaixo da média de 200 dias", 26, 78 + 22);
  ["BTC", "ETH", "SOL"].forEach((a, i) => { const p = P[a] || {}, pos = (N.pos || {})[a], y = 126 + i * 108, c = cor[a];
    g.fillStyle = "#1a160c"; g.fillRect(26, y, W - 52, 96); g.fillStyle = c; g.fillRect(26, y, 8, 96);
    g.fillStyle = c; g.font = "800 30px system-ui"; g.fillText(a, 48, y + 40);
    g.fillStyle = "#fff"; g.font = "700 24px system-ui"; g.fillText(pos ? f2(p.valor_usdc || 0) + " USDC" : (p.acima ? "à espera de compra" : "em USDC"), 140, y + 40);
    if (pos) { g.fillStyle = (p.resultado_usdc || 0) >= 0 ? "#68D391" : "#FF8A80"; g.fillText(sg(p.resultado_usdc || 0), 380, y + 40); }
    const dist = p.preco && p.media ? (p.media / p.preco - 1) * 100 : null;
    g.fillStyle = "#b8a77a"; g.font = "600 18px system-ui";
    g.fillText(p.preco ? `preço ${px(p.preco)} · média 200d ${p.media ? px(p.media) : "–"}${pos ? " · entrada " + px(pos.entrada) : ""}` : "sem preço", 48, y + 74);
    if (dist != null) { const ok = dist < 0; g.textAlign = "right"; g.fillStyle = ok ? "#68D391" : "#FF8A80"; g.font = "800 24px system-ui";
      g.fillText(ok ? `saída a ${Math.abs(dist).toFixed(1).replace(".", ",")}%` : "abaixo da média", W - 46, y + 40);
      g.font = "600 16px system-ui"; g.fillStyle = "#b8a77a"; g.fillText(ok ? "do preço atual" : "vende no fecho diário", W - 46, y + 66); g.textAlign = "left";
      // barra: quanto espaco ha ate a media (0 a 40%)
      const w = Math.max(0, Math.min(1, Math.abs(dist) / 40)); g.fillStyle = "#2a2412"; g.fillRect(48, y + 84, W - 120, 6); g.fillStyle = ok ? "#68D391" : "#FF8A80"; g.fillRect(48, y + 84, (W - 120) * w, 6); } });
}
function buildCofre() {
  cofreTex = canvasTex(768, 470, drawCofre);
  cofreScr = new THREE.Mesh(new THREE.PlaneGeometry(4.6, 2.82), new THREE.MeshBasicMaterial({ map: cofreTex, toneMapped: false, side: THREE.DoubleSide }));
  cofreScr.position.set(0, 3.3, 10.4); scene.add(cofreScr);
  const gold = mat("#F6C453", .35);
  [["BTC", "#F7931A", -1.3], ["ETH", "#8C8CF7", 0], ["SOL", "#14F195", 1.3]].forEach(([a, c, x]) => {
    const b = boxM(.8, .8, .7, mat("#3a3220"), x, .4, 11.1); boxM(.82, .06, .72, gold, x, .82, 11.1);
    const dial = new THREE.Mesh(new THREE.CylinderGeometry(.16, .16, .05, 20), mat(c, .8)); dial.rotation.x = Math.PI / 2; dial.position.set(x, .45, 10.73); scene.add(dial); });
  const lt = new THREE.PointLight(0xF6C453, 7, 7); lt.position.set(0, 2.6, 9.6); scene.add(lt);
}
function updateCofre() { if (cofreTex) { drawCofre(cofreTex.userData.c.getContext("2d")); cofreTex.needsUpdate = true; } }
function showCofre() {
  updateCofre(); let el = document.getElementById("cofrebig");
  if (!el) { el = document.createElement("div"); el.id = "cofrebig"; el.style.cssText = "position:fixed;inset:0;z-index:70;background:#05041acc;display:flex;align-items:center;justify-content:center;padding:16px";
    el.innerHTML = '<img alt="Cofre do núcleo" style="width:min(100%,760px);border-radius:14px;box-shadow:0 0 40px #F6C45366">'; el.addEventListener("click", () => el.style.display = "none"); document.body.appendChild(el); }
  el.querySelector("img").src = cofreTex.userData.c.toDataURL(); el.style.display = "flex";
}

// ---------- 2.o piso: Laboratorio de Estrategias ----------
// Um piso inteiro so de pesquisa. Seis departamentos em fila, pela ordem em
// que uma estrategia tem de passar para chegar ao dinheiro real: ideias ->
// backtest de 1 ano -> teste do acaso -> custos reais -> comite da prova dupla
// -> prova real na Bybit. Cada investigador leva o dossier de um lutador real
// (dados do ringue de um ano, D.arena_longo) de sala em sala; onde o lutador
// chumba, o dossier fica vermelho e volta as ideias; os campeoes chegam a
// prova real com o dossier dourado. No corredor cruzam-se e trocam o que
// descobriram (os numeros sao os do ultimo scan, nada inventado).
const P2H = 6.4;
const P2 = { on: false, g: null, people: [], heads: [], labels: [], tex: {}, scr: [], talk: [], tags: [], focus: null, focusAt: 0, queue: [] };
const P2R = {
  ideias: { n: "Ideias e hipóteses", c: "#B794F4", x: [-19, -7], z: [-12, -3] },
  backtest: { n: "Backtest de 1 ano", c: "#63B3ED", x: [-6, 6], z: [-12, -3] },
  acaso: { n: "Teste do acaso", c: "#F6C453", x: [7, 19], z: [-12, -3] },
  custos: { n: "Custos reais", c: "#FFA94D", x: [7, 19], z: [3, 12] },
  comite: { n: "Comité da prova dupla", c: "#68D391", x: [-6, 6], z: [3, 12] },
  real: { n: "Prova real (Bybit)", c: "#4FD1C5", x: [-19, -7], z: [3, 12] },
  dados: { n: "Recolha de dados (H4)", c: "#9AE6B4", x: [19.5, 24.5], z: [-12, -3] },
  lounge: { n: "Lounge e café", c: "#FF6FB5", x: [19.5, 24.5], z: [3, 12] },
};
// lounge: lugares no sofa (de frente para a TV com a missao), no balcao do cafe e a mesa alta
const P2LOUNGE = [{ p: V(20.8, 9.2), sit: 1, r: 0 }, { p: V(21.9, 9.2), sit: 1, r: 0 }, { p: V(23.0, 9.2), sit: 1, r: 0 },
  { p: V(23.5, 5.2), r: Math.PI / 2 }, { p: V(23.5, 6.4), r: Math.PI / 2 }, { p: V(20.4, 5.6), r: Math.PI / 2 }, { p: V(21.6, 5.6), r: -Math.PI / 2 }];
const P2ORD = ["ideias", "backtest", "acaso", "custos", "comite", "real"];
const P2MIN_N = 20, P2MIN_R = 0.15;
// estudos feitos fora do programa, com historico desde 2021 (resultados reais)
const PESQUISA = [
  ["✅", "Núcleo BTC/ETH/SOL acima da média de 200 dias", "passa nos dois períodos"],
  ["✅", "Shorts na fase de descida (SHORT_X30, ISOLADA)", "provam na queda"],
  ["❌", "Sobrevenda 4H em 2021-24", "falha fora da amostra"],
  ["❌", "Tendência diária contra entradas ao acaso", "não bate o acaso"],
  ["❌", "Estratégias diárias D1 a D4", "chumbaram"],
  ["❌", "Alavancagem no núcleo", "pior na maioria"],
  ["❌", "Vol-target, top 10, ETH/BTC, momentum duplo", "não melhoram"],
  ["❌", "H3: comprar o núcleo no recuo", "pior em 5 de 6"],
  ["➖", "Funding carry", "~5% ao ano: pouco"],
  ["🔬", "H4: liquidações em massa", "em estudo"],
];
const p2n = (x, d = 2) => x == null || isNaN(x) ? "–" : (x > 0 ? "+" : "") + Number(x).toFixed(d).replace(".", ",");
const P2FASE = { subida: "subida", lateral: "lateral", queda: "descida" };
function p2Data() { return API().D() || {}; }
function p2Fase() { return (p2Data().mercado || {}).regime || "lateral"; }
function p2Dead() { return new Set(((p2Data().arena || {}).classificacao || []).filter(b => b.estado === "MORTA").map(b => b.id)); }
function p2Persona(k) { const b = ((p2Data().arena || {}).classificacao || []).find(x => x.id === k); return ((b && b.persona) || k).replace(" Jr.", ""); }
function p2Champs() { return new Set((p2Data().promo || {}).campeoes || []); }
// ate onde chega o lutador k na fase f: indice da sala onde chumba (ou 5 = campeao)
function p2Eval(k, f) {
  const L = ((p2Data().arena_longo || {}).lutadores || {})[k] || {}, x = (L.por_regime || {})[f] || {};
  const n = x.n || 0, r = x.avg_r, p95 = x.acaso_p95, met = x.metades, F = P2FASE[f] || f;
  const o = { k, persona: p2Persona(k), n, r, p95, met, fase: F };
  if (n < P2MIN_N) return Object.assign(o, { stop: 1, why: `só ${n} operações na fase ${F} (precisa de ${P2MIN_N})` });
  if (r == null || r <= 0) return Object.assign(o, { stop: 1, why: `perde na fase ${F}: ${p2n(r)}R por operação` });
  if (p95 == null || r <= p95) return Object.assign(o, { stop: 2, why: `não bate o acaso: ${p2n(r)}R contra ${p2n(p95)}R de entradas ao calhas` });
  if (!met || Math.min(...met) <= 0) return Object.assign(o, { stop: 2, why: `uma metade do ano perde (${met ? met.map(v => p2n(v)).join(" / ") : "–"})` });
  if (r < P2MIN_R) return Object.assign(o, { stop: 3, why: `${p2n(r)}R não paga spread e comissões reais (mínimo +0,15R)` });
  if (!p2Champs().has(k)) return Object.assign(o, { stop: 4, why: `passa nos números (${p2n(r)}R) mas está fora do dinheiro real (suspenso ou sem código revisto)` });
  return Object.assign(o, { stop: 5, why: `campeão na fase ${F}: ${p2n(r)}R em ${n} operações, as duas metades a ganhar` });
}
// todos os lutadores do ringue de um ano, como o motor (promo.regime_qualified):
// um short eliminado no combate de 90 dias (mes de subida) volta se provar na fase
function p2All(f) { return Object.keys((p2Data().arena_longo || {}).lutadores || {}).map(k => p2Eval(k, f)); }
function p2Fact(e, room) {
  if (room === "ideias") return `abro o dossier de ${e.persona} (${e.k})`;
  if (room === "backtest") return `${e.n} operações na fase ${e.fase}, ${p2n(e.r)}R de média`;
  if (room === "acaso") return `acaso ${p2n(e.p95)}R · metades ${e.met ? e.met.map(v => p2n(v)).join(" / ") : "–"}`;
  if (room === "custos") return `${p2n(e.r)}R chega para pagar os custos reais`;
  if (room === "comite") return `as três provas estão cumpridas`;
  return e.why;
}

// ---------- texturas dos ecras ----------
function p2Frame(g, title, c) {
  g.fillStyle = "#0b1020"; g.fillRect(0, 0, 512, 320); g.strokeStyle = c; g.lineWidth = 4; g.strokeRect(2, 2, 508, 316);
  g.fillStyle = c; g.fillRect(0, 0, 512, 44); g.fillStyle = "#0b1020"; g.font = "800 22px system-ui"; g.fillText(title, 14, 30);
}
function p2Rows(g, rows, y0 = 72, lh = 25) {
  rows.slice(0, 10).forEach(([a, b, col], i) => { const y = y0 + i * lh; g.font = "600 17px system-ui"; g.fillStyle = "#dfe6f0"; g.fillText(String(a).slice(0, 34), 14, y);
    g.textAlign = "right"; g.fillStyle = col || "#9fb3c8"; g.fillText(String(b), 498, y); g.textAlign = "left"; });
}
function p2Draw(room, g) {
  const R = P2R[room], f = p2Fase(), F = P2FASE[f] || f, all = p2All(f);
  if (room === "ideias") { p2Frame(g, "💡 Hipóteses testadas", R.c); p2Rows(g, PESQUISA.map(([s, t, v]) => [s + " " + t, v, s === "✅" ? "#68D391" : s === "❌" ? "#FF8A80" : "#F6C453"]), 70, 24.5); return; }
  if (room === "backtest") { p2Frame(g, `📈 Último ano · fase ${F}`, R.c);
    const rs = all.filter(e => e.n).sort((a, b) => (b.r || -9) - (a.r || -9));
    p2Rows(g, [[`${rs.filter(e => e.stop > 1).length} de ${all.length} ganham nesta fase`, "", "#fff"]].concat(rs.map(e => [e.persona + " · " + e.n + " op.", p2n(e.r) + "R", e.r > 0 ? "#68D391" : "#FF8A80"]))); return; }
  if (room === "acaso") { p2Frame(g, "🎲 Bate as entradas ao acaso?", R.c);
    const rs = all.filter(e => e.stop >= 2).sort((a, b) => b.r - a.r);
    p2Rows(g, [[`${all.filter(e => e.stop >= 3).length} de ${rs.length} batem o acaso nas 2 metades`, "", "#fff"]].concat(rs.map(e => [e.persona, e.stop >= 3 ? "✅ " + p2n(e.r) + " > " + p2n(e.p95) : "❌", e.stop >= 3 ? "#68D391" : "#FF8A80"]))); return; }
  if (room === "custos") { p2Frame(g, "💸 Paga as contas? (mín. +0,15R)", R.c);
    const rs = all.filter(e => e.stop >= 3).sort((a, b) => b.r - a.r);
    p2Rows(g, [["spread, comissões e deslize da Bybit UE", "", "#fff"]].concat(rs.map(e => [e.persona, p2n(e.r) + "R " + (e.stop >= 4 ? "✅" : "❌"), e.stop >= 4 ? "#68D391" : "#FF8A80"]))); return; }
  if (room === "comite") { p2Frame(g, "⚖️ Aprovados por fase do mercado", R.c);
    const rows = [];
    ["lateral", "subida", "queda"].forEach(fz => { const ok = p2All(fz).filter(e => e.stop >= 4);
      rows.push([(fz === f ? "▶ " : "") + "Fase " + (P2FASE[fz] || fz), ok.length ? ok.length + " aprovado" + (ok.length > 1 ? "s" : "") : "ninguém — trabalha o núcleo", fz === f ? "#fff" : "#9fb3c8"]);
      ok.slice(0, 2).forEach(e => rows.push(["   " + e.persona + " (" + e.k + ")", p2n(e.r) + "R", "#68D391"])); });
    p2Rows(g, rows); return; }
  if (room === "dados") { p2Frame(g, "🔬 Dados de derivados para o H4", R.c); const DH = p2Data().derivados_hist || {}, dias = DH.desde ? (Date.now() / 1000 - DH.desde) / 86400 : 0, alvo = 60;
    p2Rows(g, [["Moedas a gravar (mais dinheiro aberto)", DH.moedas || 0, "#fff"], ["Amostras horárias", DH.amostras || 0], ["A gravar desde", DH.desde ? new Date(DH.desde * 1000).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–"],
      ["Dias de dados", dias.toFixed(1).replace(".", ",") + " de " + alvo, dias >= alvo ? "#68D391" : "#F6C453"], ["À espera destes dados:", "", "#fff"], ["  H4 liquidações em massa", "a gravar"], ["  Funding extremo + dinheiro aberto", "a gravar"], ["  Rácio long/short no extremo", "a gravar"]], 72, 26);
    g.fillStyle = "#1d2a24"; g.fillRect(14, 290, 484, 14); g.fillStyle = R.c; g.fillRect(14, 290, 484 * Math.min(1, dias / alvo), 14); return; }
  if (room === "real") { p2Frame(g, "🧾 Dinheiro real na Bybit", R.c); const RE = p2Data().reais || {}, N = p2Data().nucleo || {};
    const nv = Object.entries(N.plano || {}).reduce((a, [k, p]) => a + (N.pos && N.pos[k] ? p.valor_usdc || 0 : 0), 0), nr = Object.entries(N.plano || {}).reduce((a, [k, p]) => a + (N.pos && N.pos[k] ? p.resultado_usdc || 0 : 0), 0);
    p2Rows(g, [["Campeões agora", [...p2Champs()].map(p2Persona).join(", ") || "nenhum", "#fff"], ["Operações medidas", RE.n || 0], ["Resultado real", p2n(RE.pnl_usdc) + " USDC", (RE.pnl_usdc || 0) >= 0 ? "#68D391" : "#FF8A80"],
      ["R real vs sinal", p2n(RE.real_r) + " / " + p2n(RE.sinal_r)], ["Comissões", p2n(RE.comissoes_usdc) + " USDC"], ["Núcleo em carteira", nv ? nv.toFixed(0) + " USDC (" + p2n(nr) + ")" : "–", nr >= 0 ? "#68D391" : "#FF8A80"]]
      .concat((RE.ultimas || []).slice(-3).reverse().map(u => ["  " + u.ativo + " · " + (u.id || "").split("-")[1], p2n(u.real_r) + "R", u.real_r >= 0 ? "#68D391" : "#FF8A80"]))); return; }
}
function p2DrawFunnel(g) {
  const f = p2Fase(), all = p2All(f), st = [all.length, all.filter(e => e.stop >= 2).length, all.filter(e => e.stop >= 3).length, all.filter(e => e.stop >= 4).length, all.filter(e => e.stop >= 5).length];
  g.fillStyle = "#0b1020"; g.fillRect(0, 0, 512, 420); g.strokeStyle = "#B794F4"; g.lineWidth = 4; g.strokeRect(2, 2, 508, 416);
  g.fillStyle = "#fff"; g.font = "800 24px system-ui"; g.fillText("🔬 Funil da pesquisa", 16, 36); g.font = "600 16px system-ui"; g.fillStyle = "#9fb3c8"; g.fillText(`fase do mercado: ${P2FASE[f] || f} · ringue de 1 ano`, 16, 60);
  const lab = ["Estratégias vivas", "Ganham no backtest", "Batem o acaso (2 metades)", "Pagam os custos reais", "Dinheiro real"], col = ["#B794F4", "#63B3ED", "#F6C453", "#FFA94D", "#4FD1C5"];
  st.forEach((v, i) => { const y = 84 + i * 64, w = Math.max(40, 470 * v / Math.max(1, st[0])); g.fillStyle = col[i] + "33"; g.fillRect(16, y, 480, 50); g.fillStyle = col[i]; g.fillRect(16, y, w, 50);
    g.fillStyle = "#0b1020"; g.font = "800 26px system-ui"; g.fillText(v, 26, y + 35); g.fillStyle = "#fff"; g.font = "700 18px system-ui"; g.fillText(lab[i], Math.max(80, Math.min(w + 26, 300)), y + 32); });
  g.fillStyle = "#9fb3c8"; g.font = "600 15px system-ui"; g.fillText("Só passa quem prova. Os outros voltam às ideias.", 16, 408);
}

// ---------- construcao ----------
function p2Seats(room) {
  const R = P2R[room], cx = (R.x[0] + R.x[1]) / 2, north = R.z[0] < 0, zb = north ? -8.4 : 8.4;
  return (R.x[1] - R.x[0] < 8 ? [0] : [-3.6, 0, 3.6]).map(dx => ({ desk: V(cx + dx, zb), seat: V(cx + dx, zb + (north ? .95 : -.95)), face: north ? Math.PI : 0 }));
}
function p2Door(room, inside) { const R = P2R[room], cx = (R.x[0] + R.x[1]) / 2, north = R.z[0] < 0; return V(cx, (north ? -1 : 1) * (inside ? 4.2 : 1.9)); }
function p2Stand(room, i) { const R = P2R[room], w = R.x[1] - R.x[0], north = R.z[0] < 0; return V(R.x[0] + 1 + (i % 4) * (w - 2) / 3, north ? -5.4 : 5.4); }
function p2Label(text, c, p, cls) {
  const el = document.createElement("div"); el.textContent = text;
  el.style.cssText = `position:absolute;transform:translate(-50%,-100%);pointer-events:none;white-space:nowrap;font:700 11px system-ui,sans-serif;color:${c};padding:2px 8px;border-radius:99px;background:#0c0a24c8;border:1px solid ${c}66;display:none`;
  overlay.appendChild(el); const l = { el, p, cls }; P2.labels.push(l); return l;
}
function p2Person(key, nm, st, col) {
  STYLE[key] = st; DESK[key] = { z: "srv", p: V(0, 0), f: 1 };
  const p = makePerson({ id: key, nm, c: col }); scene.remove(p.g); p.name.remove(); P2.g.add(p.g);
  p.g.traverse(o => { if (o.isMesh) o.castShadow = false; }); p.path = []; p.nm = nm; return p;
}
function buildFloor2() {
  P2.g = new THREE.Group(); P2.g.position.y = P2H; P2.g.visible = false; scene.add(P2.g); const G = P2.g;
  // laje, chao, corredor com neon e varandim de vidro
  boxM(46, .3, 27, mat("#2b2f38"), 2, -.16, 0, G);
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(46, 27), mat("#4a4f5a")); fl.rotation.x = -Math.PI / 2; fl.position.set(2, .005, 0); fl.receiveShadow = true; G.add(fl);
  const cor = new THREE.Mesh(new THREE.PlaneGeometry(44, 5.4), mat("#3a3550")); cor.rotation.x = -Math.PI / 2; cor.position.set(2, .012, 0); G.add(cor);
  [-2.7, 2.7].forEach(z => boxM(44, .02, .06, mat("#B794F4", 1.2), 2, .02, z, G));
  const rail = mat("#9fd3ff", .05, .1); boxM(46, 1, .04, rail, 2, .5, -13.5, G); boxM(46, 1, .04, rail, 2, .5, 13.5, G); boxM(.04, 1, 27, rail, -21, .5, 0, G); boxM(.04, 1, 27, rail, 25, .5, 0, G);
  // escadas a descer para o 1.o piso (lado oeste)
  for (let i = 0; i < 9; i++) boxM(1.8, .12, .5, mat("#6b6f7a"), -20, -i * .7, -1.5 + i * .5, G);
  // salas
  P2ORD.forEach((room, ri) => {
    const R = P2R[room], w = R.x[1] - R.x[0], d = R.z[1] - R.z[0], cx = (R.x[0] + R.x[1]) / 2, cz = (R.z[0] + R.z[1]) / 2, north = R.z[0] < 0, zc = north ? R.z[1] : R.z[0], zf = north ? R.z[0] : R.z[1];
    const rug = new THREE.Mesh(new THREE.PlaneGeometry(w - .4, d - .4), mat(new THREE.Color(R.c).multiplyScalar(.28).getStyle())); rug.rotation.x = -Math.PI / 2; rug.position.set(cx, .015, cz); G.add(rug);
    const glass = mat(R.c, .15, .08), h = 1.25;
    boxM(w, h, .05, glass, cx, h / 2, zf, G); boxM(.05, h, d, glass, R.x[0], h / 2, cz, G); boxM(.05, h, d, glass, R.x[1], h / 2, cz, G);
    boxM(w / 2 - 1.1, h, .05, glass, R.x[0] + (w / 2 - 1.1) / 2, h / 2, zc, G); boxM(w / 2 - 1.1, h, .05, glass, R.x[1] - (w / 2 - 1.1) / 2, h / 2, zc, G);   // porta no meio
    const c4 = [V(R.x[0], R.z[0]), V(R.x[1], R.z[0]), V(R.x[1], R.z[1]), V(R.x[0], R.z[1]), V(R.x[0], R.z[0])];
    line(c4.map(p => p.clone().setY(h)), new THREE.Color(R.c), G); line(c4.map(p => p.clone().setY(.03)), new THREE.Color(R.c), G);
    // secretarias com monitor
    p2Seats(room).forEach((s, i) => { const g = new THREE.Group(); g.position.copy(s.desk); g.rotation.y = s.face + Math.PI; G.add(g);
      boxM(1.7, .06, .85, mat("#8b6a4c"), 0, .75, 0, g); [[-.75, -.35], [.75, -.35], [-.75, .35], [.75, .35]].forEach(([a, b]) => boxM(.06, .72, .06, mat("#2a2a2a"), a, .36, b, g));
      boxM(.9, .55, .05, mat("#111"), 0, 1.15, -.2, g); const m = new THREE.Mesh(new THREE.PlaneGeometry(.82, .47), new THREE.MeshBasicMaterial({ color: R.c, toneMapped: false })); m.position.set(0, 1.15, -.17); g.add(m);
      const ch = new THREE.Group(); ch.position.set(0, 0, .95); g.add(ch); boxM(.55, .08, .55, mat("#2b2b40"), 0, .48, 0, ch); boxM(.55, .6, .08, mat("#2b2b40"), 0, .8, .27, ch); });
    // ecra grande do departamento (vira-se sempre para quem esta a ver)
    const tx = canvasTex(512, 320, gg => p2Draw(room, gg)); P2.tex[room] = tx;
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(4.6, 2.88), new THREE.MeshBasicMaterial({ map: tx, toneMapped: false, side: THREE.DoubleSide }));
    scr.position.set(cx, 3.3, north ? R.z[0] + 1.6 : R.z[1] - 1.6); G.add(scr); P2.scr.push(scr);
    const lt = new THREE.PointLight(new THREE.Color(R.c), 10, 10); lt.position.set(cx, 3, cz); G.add(lt);
    p2Label(`${ri + 1}. ${R.n}`, R.c, new THREE.Vector3(cx, P2H + 1.6, zc), "room");
    // chefe do departamento, sempre a trabalhar
    const HEADS = { ideias: ["Íris", 1], backtest: ["Tomás", 0], acaso: ["Sara", 1], custos: ["Rodrigo", 0], comite: ["Beatriz", 1], real: ["Hugo", 0] };
    const [nm, fem] = HEADS[room], hh = hsh(nm), s0 = p2Seats(room)[0];
    const p = p2Person("p2h_" + room, nm, { skin: SKINS[hh % 5], hair: HAIRS[(hh >> 2) % 6], hs: fem ? (hh % 2 ? "long" : "bun") : ["short", "buzz", "curly"][hh % 3], top: R.c, jacket: room === "comite" ? "#2d3b55" : null, legs: "#22223a", glasses: hh % 3 === 0 ? 1 : 0, beard: !fem && hh % 2 ? 1 : 0 }, R.c);
    p.g.position.copy(s0.seat); p.mode = "desk"; p.sit = true; p.face = s0.face; p.room = room; P2.heads.push(p);
  });
  ["dados", "lounge"].forEach(room => {
    const R = P2R[room], w = R.x[1] - R.x[0], d = R.z[1] - R.z[0], cx = (R.x[0] + R.x[1]) / 2, cz = (R.z[0] + R.z[1]) / 2, north = R.z[0] < 0, zc = north ? R.z[1] : R.z[0], zf = north ? R.z[0] : R.z[1];
    const rug = new THREE.Mesh(new THREE.PlaneGeometry(w - .4, d - .4), mat(new THREE.Color(R.c).multiplyScalar(.28).getStyle())); rug.rotation.x = -Math.PI / 2; rug.position.set(cx, .015, cz); G.add(rug);
    const glass = mat(R.c, .15, .08), h = 1.25, sw = (w - 2.2) / 2;
    boxM(w, h, .05, glass, cx, h / 2, zf, G); boxM(.05, h, d, glass, R.x[0], h / 2, cz, G); boxM(.05, h, d, glass, R.x[1], h / 2, cz, G);
    boxM(sw, h, .05, glass, R.x[0] + sw / 2, h / 2, zc, G); boxM(sw, h, .05, glass, R.x[1] - sw / 2, h / 2, zc, G);
    const c4 = [V(R.x[0], R.z[0]), V(R.x[1], R.z[0]), V(R.x[1], R.z[1]), V(R.x[0], R.z[1]), V(R.x[0], R.z[0])];
    line(c4.map(p => p.clone().setY(h)), new THREE.Color(R.c), G); line(c4.map(p => p.clone().setY(.03)), new THREE.Color(R.c), G);
    const lt = new THREE.PointLight(new THREE.Color(R.c), 9, 9); lt.position.set(cx, 3, cz); G.add(lt);
    p2Label(R.n, R.c, new THREE.Vector3(cx, P2H + 1.6, zc), "room");
    if (room === "dados") {
      const s0 = p2Seats(room)[0], g = new THREE.Group(); g.position.copy(s0.desk); g.rotation.y = s0.face + Math.PI; G.add(g);
      boxM(1.7, .06, .85, mat("#8b6a4c"), 0, .75, 0, g); boxM(.9, .55, .05, mat("#111"), 0, 1.15, -.2, g);
      const m = new THREE.Mesh(new THREE.PlaneGeometry(.82, .47), new THREE.MeshBasicMaterial({ color: R.c, toneMapped: false })); m.position.set(0, 1.15, -.17); g.add(m);
      for (let k = 0; k < 4; k++) { boxM(.7, 2.1, .8, mat("#0d1224"), 20.2 + k * 1.1, 1.05, -11.3, G); boxM(.5, 1.8, .02, mat("#9AE6B4", .9), 20.2 + k * 1.1, 1.05, -10.89, G); }   // servidores a gravar
      const tx = canvasTex(512, 320, gg => p2Draw("dados", gg)); P2.tex.dados = tx;
      const scr = new THREE.Mesh(new THREE.PlaneGeometry(4, 2.5), new THREE.MeshBasicMaterial({ map: tx, toneMapped: false, side: THREE.DoubleSide })); scr.position.set(cx, 3.6, -8.6); G.add(scr); P2.scr.push(scr);
      const hh = hsh("Leonor"), p = p2Person("p2h_dados", "Leonor", { skin: SKINS[hh % 5], hair: HAIRS[(hh >> 2) % 6], hs: "long", top: R.c, legs: "#22223a", glasses: 1 }, R.c);
      p.g.position.copy(s0.seat); p.mode = "desk"; p.sit = true; p.face = s0.face; p.room = room; P2.heads.push(p);
    } else {
      boxM(3.6, .45, .9, mat("#6e3b6a"), 21.9, .25, 8.7, G); boxM(3.6, .7, .25, mat("#80447b"), 21.9, .6, 8.25, G);           // sofa
      boxM(.9, 1, 3, mat("#3a2b20"), 24, .5, 5.8, G); boxM(.95, .06, 3.1, mat("#c08a5a"), 24, 1.02, 5.8, G);                  // balcao
      boxM(.45, .55, .4, mat("#888"), 24, 1.33, 4.9, G); boxM(.1, .1, .05, mat("#ff4d4d", 2), 23.76, 1.42, 4.9, G);             // maquina de cafe
      const mt = new THREE.Mesh(new THREE.CylinderGeometry(.5, .5, .06, 20), mat("#c08a5a")); mt.position.set(21, 1.05, 5.6); G.add(mt); boxM(.08, 1, .08, mat("#222"), 21, .5, 5.6, G);
      [[19.9, 11.5], [24.1, 11.5], [19.9, 3.5]].forEach(([x, z]) => { boxM(.45, .45, .45, mat("#7a4b2a"), x, .22, z, G); const sp = new THREE.Mesh(new THREE.SphereGeometry(.45, 12, 10), mat("#38d6b5", .25)); sp.position.set(x, .9, z); G.add(sp); });
      if (misTex) { const tv = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 2.5), new THREE.MeshBasicMaterial({ map: misTex, toneMapped: false, side: THREE.DoubleSide })); tv.position.set(21.9, 2.6, 11.4); G.add(tv); P2.scr.push(tv); }
    }
  });
  // funil da pesquisa (topo leste do corredor)
  const ft = canvasTex(512, 420, p2DrawFunnel); P2.tex.funil = ft;
  const fs = new THREE.Mesh(new THREE.PlaneGeometry(4.4, 3.6), new THREE.MeshBasicMaterial({ map: ft, toneMapped: false, side: THREE.DoubleSide })); fs.position.set(22.6, 2.6, 0); G.add(fs); P2.scr.push(fs);
  boxM(.2, 2.2, .2, mat("#222"), 22.6, 1.1, 0, G);
  p2Label("🔬 Laboratório de Estratégias · 2.º piso", "#B794F4", new THREE.Vector3(22.6, P2H + 4.8, 0), "room");
  // investigadores
  const TEAM = [["Ana", 1], ["Bruno", 0], ["Carla", 1], ["Duarte", 0], ["Eva", 1], ["Filipe", 0], ["Gil", 0], ["Helena", 1]];
  TEAM.forEach(([nm, fem], i) => { const hh = hsh(nm + "lab"), col = FCOL[(i * 3) % FCOL.length];
    const p = p2Person("p2r_" + nm, nm, { skin: SKINS[hh % 5], hair: HAIRS[(hh >> 1) % 6], hs: fem ? (hh % 2 ? "long" : "bun") : ["short", "buzz", "curly"][hh % 3], top: col, legs: "#1d1b2e", glasses: i % 3 === 1 ? 1 : 0, beard: !fem && i % 2 ? 1 : 0 }, col);
    const folder = new THREE.Mesh(new THREE.BoxGeometry(.22, .3, .04), new THREE.MeshStandardMaterial({ color: "#e8eef7", emissive: "#e8eef7", emissiveIntensity: .25 })); folder.position.set(0, -.32, .08); p.rig.AR.el.add(folder); p.folder = folder;
    p.room = P2ORD[i % 6]; p.g.position.copy(p2Stand(p.room, i)); p.mode = "stand"; p.wait = 1 + i * 1.3; p.cool = 4 + i;
    p.tag = p2Label("", col, new THREE.Vector3(), "tag"); p.lane = (i - 3.5) * .35; P2.people.push(p); });
}
function p2Pick() {
  const f = p2Fase(), all = p2All(f); if (!all.length) return null;
  const ch = all.filter(e => e.stop === 5);
  if (ch.length && Math.random() < .3) return ch[Math.floor(Math.random() * ch.length)];
  if (!P2.queue.length) P2.queue = all.map(e => e.k).sort(() => Math.random() - .5);
  const k = P2.queue.shift(); return all.find(e => e.k === k) || all[0];
}
function p2Route(p, room, target) {
  const pts = [], cur = p.room;
  if (cur !== room) { const a = p2Door(cur, true), b = p2Door(cur, false), c = p2Door(room, false), d = p2Door(room, true);
    pts.push(a, b.clone().setZ(b.z > 0 ? .3 + p.lane * .3 : -.3 + p.lane * .3), c.clone().setZ(c.z > 0 ? .3 + p.lane * .3 : -.3 + p.lane * .3), c, d); }
  pts.push(target); return pts;
}
function p2Seat(room, p) {
  const used = new Set(P2.people.filter(q => q !== p && q.seatKey).map(q => q.seatKey)), seats = p2Seats(room);
  for (let i = 1; i < seats.length; i++) { const key = room + i; if (!used.has(key)) return { key, s: seats[i] }; }
  return null;
}
function p2Say(p, html, secs = 5) { P2.talk = P2.talk.filter(t => !t.who.includes(p)); P2.talk.push({ who: [p], html, t: secs, el: null }); }
function p2LoungeSpot(p) { const used = new Set(P2.people.filter(q => q !== p && q.lspot).map(q => q.lspot)); const free = P2LOUNGE.filter(x => !used.has(x)); return free[Math.floor(Math.random() * free.length)] || null; }
function p2Go(p) {
  p.coffee = false; p.lspot = null;
  if (!p.plan || p.step >= p.plan.length) {
    if (p.doss) {                         // dossier terminado: pausa no lounge, ver os dados ou outro dossier
      p.doss = null; const r = Math.random();
      p.plan = r < .38 ? ["lounge", "ideias"] : r < .5 ? ["dados", "ideias"] : ["ideias"]; p.step = 0;
    } else { const e = p2Pick(); if (!e) { p.wait = 5; return; } p.doss = e; p.plan = P2ORD.slice(0, Math.min(6, e.stop + 1)); p.step = 0; p.folder.material.color.set("#e8eef7"); p.folder.material.emissive.set("#e8eef7"); }
  }
  const room = p.plan[p.step];
  p.folder.visible = !!p.doss;
  if (room === "lounge") { const sp = p2LoungeSpot(p); if (!sp) { p.step++; p.wait = .5; return; } p.lspot = sp; p.seatKey = null;
    p.path = p2Route(p, room, sp.p.clone()); p.dest = room; p.mode = "stand"; p.sit = false; p.arrive = true; return; }
  const st = p2Seat(room, p); p.seatKey = st ? st.key : null;
  const target = st ? st.s.seat : p2Stand(room, P2.people.indexOf(p));
  p.path = p2Route(p, room, target); p.dest = room; p.mode = st ? "desk" : "stand"; p.face = st ? st.s.face : 0; p.sit = false; p.arrive = true;
}
function p2SmallTalk(a, b) {
  const D = p2Data(), M = D.meta || {}, N = D.nucleo || {}, EV = D.evolucao || {}, all = p2All(p2Fase());
  const nr = Object.entries(N.plano || {}).reduce((s, [k, x]) => s + (N.pos && N.pos[k] ? x.resultado_usdc || 0 : 0), 0);
  const mk = (M.marcos || []).find(x => !x.feito), DH = D.derivados_hist || {};
  const L = [[`Viste o núcleo? Vai ${p2n(nr)} USDC.`, `E a conta está em ${(M.capital || 0).toFixed(2).replace(".", ",")} USDC${mk ? `, faltam ${(mk.valor - M.capital).toFixed(2).replace(".", ",")} para o marco de ${mk.valor}` : ""}.`],
    [`Do funil, só ${all.filter(e => e.stop >= 5).length} de ${all.length} chegam ao dinheiro real.`, `É assim que tem de ser: quem não prova, não mexe no dinheiro do Rui.`],
    [`Já temos ${DH.amostras || 0} amostras de derivados para o H4.`, `Com 60 dias de dados já dá para testar as liquidações a sério.`],
    [`Últimas 24 h: ${EV.periodos && EV.periodos.dia != null ? p2n(EV.periodos.dia) + "%" : "ainda a gravar"}.`, `Sem contar depósitos. Só conta o que o mercado nos dá.`]];
  const [x, y] = L[Math.floor(Math.random() * L.length)];
  P2.talk = P2.talk.filter(t => !t.who.includes(a) && !t.who.includes(b));
  P2.talk.push({ who: [a, b], html: `☕ <b>${a.nm}</b>: ${esc3(x)}<br><b>${b.nm}</b>: ${esc3(y)}`, t: 7, el: null });
}
function p2Arrive(p) {
  p.room = p.dest; p.arrive = false; const room = p.room, e = p.doss; p.wait = 3.5 + Math.random() * 3;
  if (!e) {
    if (room === "lounge" && p.lspot) { p.wait = 12 + Math.random() * 10; p.sit = !!p.lspot.sit; p.coffee = !p.lspot.sit;
      const q = P2.people.find(o => o !== p && o.room === "lounge" && o.lspot && !o.path.length); if (q && Math.random() < .8) p2SmallTalk(p, q); }
    else if (room === "dados") { p.wait = 6; if (Math.random() < .6) { const DH = p2Data().derivados_hist || {}; p2Say(p, `<b>${p.nm}</b> · Recolha de dados<br>Já há ${DH.amostras || 0} amostras de ${DH.moedas || 0} moedas para testar o H4.`, 4); } }
    else p.wait = 1.2;
    p.step++; return;
  }
  const last = p.step === p.plan.length - 1;
  if (last && room !== "ideias") {
    const ok = e.stop === 5, col = ok ? "#F6C453" : "#FF8A80"; p.folder.material.color.set(col); p.folder.material.emissive.set(col);
    p2Say(p, `<b>${p.nm}</b> · ${esc3(P2R[room].n)}<br>${ok ? "✅" : "❌"} <b>${esc3(e.persona)}</b>: ${esc3(e.why)}`, 6); p.wait = 6;
  } else if (Math.random() < .45) p2Say(p, `<b>${p.nm}</b> · ${esc3(P2R[room].n)}<br>${esc3(e.persona)}: ${esc3(p2Fact(e, room))}`, 4);
  p.step++;
}
const esc3 = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function p2Tick(dt, t) {
  if (!P2.g) return;
  P2.heads.forEach(p => animate(p, dt, t));
  P2.people.forEach(p => {
    if (p.talking) { p.talking -= dt; if (p.talking <= 0) { p.talking = 0; p.path = p.saved || []; p.saved = null; p.mode = p.savedMode; } }
    if (!p.talking && !p.path.length) { if (p.arrive) p2Arrive(p); else { p.wait -= dt; if (p.wait <= 0) p2Go(p); } }
    animate(p, dt, t); if (p.cool > 0) p.cool -= dt;
    if (p.talking) { const o = p.partner.g.position; p.g.rotation.y = Math.atan2(o.x - p.g.position.x, o.z - p.g.position.z); }
    else if (!p.path.length && p.lspot) { p.g.rotation.y = p.lspot.r; if (p.coffee) { p.rig.cup.visible = true; p.rig.AR.sh.rotation.x = -.45; p.rig.AR.el.rotation.x = -1.35; } }
    else if (!p.path.length && p.mode === "stand") p.g.rotation.y = P2R[p.room] && P2R[p.room].z[0] < 0 ? Math.PI : 0;
  });
  // encontros no corredor: param, viram-se um para o outro e trocam o que sabem
  const walkers = P2.people.filter(p => p.path.length && !p.talking && p.cool <= 0 && Math.abs(p.g.position.z) < 2.6 && p.doss);
  for (let i = 0; i < walkers.length; i++) for (let j = i + 1; j < walkers.length; j++) {
    const a = walkers[i], b = walkers[j]; if (a.talking || b.talking || a.g.position.distanceTo(b.g.position) > 1.5) continue;
    [a, b].forEach((p, k) => { p.saved = p.path; p.savedMode = p.mode; p.path = []; p.mode = "stand"; p.talking = 5; p.cool = 16; p.partner = k ? a : b; });
    const ea = a.doss, eb = b.doss, nxt = x => P2R[x.plan[Math.min(x.step, x.plan.length - 1)]].n.toLowerCase();
    const reply = eb.stop < ea.stop ? `O meu ${esc3(eb.persona)} vai chumbar: ${esc3(eb.why)}` : eb.stop === 5 ? `Eu levo o ${esc3(eb.persona)}: ${esc3(eb.why)} 🏆` : `Eu levo o ${esc3(eb.persona)} para ${esc3(nxt(b))}: ${esc3(p2Fact(eb, b.plan[Math.min(b.step, b.plan.length - 1)]))}`;
    P2.talk = P2.talk.filter(x => !x.who.includes(a) && !x.who.includes(b));
    P2.talk.push({ who: [a, b], html: `<b>${a.nm}</b>: levo o ${esc3(ea.persona)} para ${esc3(nxt(a))} — ${esc3(p2Fact(ea, a.plan[Math.min(a.step, a.plan.length - 1)]))}<br><b>${b.nm}</b>: ${reply}`, t: 5, el: null });
  }
  P2.scr.forEach(s => { s.quaternion.copy(cam.quaternion); });
}
function p2Overlays(dt) {
  const W = R.domElement.clientWidth, hud = document.getElementById("hud"), top = hud ? hud.offsetHeight + 4 : 4, wp = new THREE.Vector3();
  P2.labels.forEach(l => { let pos = l.p;
    if (l.cls === "tag") { const p = P2.people.find(q => q.tag === l); if (!p || !p.doss) { l.el.style.display = "none"; return; } p.g.getWorldPosition(wp); pos = wp.clone().setY(wp.y + 2.55);
      if (cam.position.distanceTo(wp) > 60) { l.el.style.display = "none"; return; }
      l.el.textContent = `${p.nm} · 📁 ${p.doss.persona}`; }
    const s = project(pos); l.el.style.left = s.x + "px"; l.el.style.top = s.y + "px"; l.el.style.display = s.ok ? "" : "none"; });
  // baloes (no maximo 3 ao mesmo tempo, os mais recentes)
  P2.talk.forEach(x => x.t -= dt); P2.talk.filter(x => x.t <= 0 && x.el).forEach(x => x.el.remove()); P2.talk = P2.talk.filter(x => x.t > 0);
  P2.talk.forEach((x, i) => { const show = i >= P2.talk.length - 3;
    if (!x.el) { x.el = document.createElement("div"); x.el.className = "obub3"; x.el.style.maxWidth = "min(70%, 300px)"; x.el.innerHTML = x.html; x.el.style.borderColor = x.who[0].a.c; overlay.appendChild(x.el); }
    const c = new THREE.Vector3(); x.who.forEach(p => { p.g.getWorldPosition(wp); c.add(wp); }); c.multiplyScalar(1 / x.who.length).setY(c.y + 2.7);
    const s = project(c), w = x.el.offsetWidth; x.el.style.display = show && s.ok ? "" : "none";
    x.el.style.left = Math.max(4, Math.min(W - w - 4, s.x - w / 2)) + "px"; x.el.style.top = Math.max(top, s.y - x.el.offsetHeight) + "px"; });
}
function p2HideOverlays() { P2.labels.forEach(l => l.el.style.display = "none"); P2.talk.forEach(x => x.el && (x.el.style.display = "none")); }
function updateFloor2() { if (!P2.g) return; Object.entries(P2.tex).forEach(([k, tx]) => { const g = tx.userData.c.getContext("2d"); if (k === "funil") p2DrawFunnel(g); else p2Draw(k, g); tx.needsUpdate = true; }); }
function p2Click(hit) {
  let o = hit.object; while (o && !o.userData.agent) o = o.parent; const key = o && o.userData.agent, p = P2.people.find(q => q.a.id === key) || P2.heads.find(q => q.a.id === key);
  if (!p) return;
  if (p.doss) p2Say(p, `<b>${p.nm}</b> · dossier de <b>${esc3(p.doss.persona)}</b> (${esc3(p.doss.k)})<br>Fase ${esc3(p.doss.fase)}: ${p.doss.n} op., ${p2n(p.doss.r)}R, acaso ${p2n(p.doss.p95)}R<br>${p.doss.stop === 5 ? "✅" : "❌"} ${esc3(p.doss.why)}`, 7);
  else if (p.room) p2Say(p, `<b>${p.nm}</b> · chefe de ${esc3(P2R[p.room].n)}<br>${esc3({ ideias: "Aqui nascem e morrem as hipóteses. Só passa ao backtest o que tem lógica de mercado.", backtest: "Testo cada estratégia no último ano, só nas alturas iguais à de agora.", acaso: "Se entradas ao calhas dão o mesmo, não há vantagem nenhuma.", custos: "Spread, comissões e deslize da Bybit UE: abaixo de +0,15R não paga as contas.", comite: "Só aprovo quem ganha nas duas metades do ano e bate o acaso.", real: "Aqui só conta o dinheiro que entrou mesmo na conta." }[p.room])}`, 6);
}
function goFloor(n) {
  if (!P2.g) buildFloor2();
  P2.on = n === 2; P2.g.visible = P2.on;
  if (!P2.on) { p2HideOverlays(); resize.done = false; ctl.target.set(0, 0, 0); resize(); ctl.update(); }
  else { updateFloor2(); const T = new THREE.Vector3(cam.aspect < .8 ? 2 : 3.5, P2H, 0); ctl.target.copy(T);
    if (cam.aspect < .8) cam.position.set(T.x - 50, T.y + 50, 0); else cam.position.set(T.x + 1, T.y + 30, 35); ctl.update(); }
  try { window.dispatchEvent(new CustomEvent("piso", { detail: P2.on ? 2 : 1 })); } catch (_) { }
  return P2.on;
}
function p2Leave() { if (!P2.on) return; P2.on = false; P2.g.visible = false; p2HideOverlays(); try { window.dispatchEvent(new CustomEvent("piso", { detail: 1 })); } catch (_) { } }

// ---------- ciclo ----------
function project(v) { const p = v.clone().project(cam), r = R.domElement; return { x: (p.x + 1) / 2 * r.clientWidth, y: (1 - p.y) / 2 * r.clientHeight, ok: p.z < 1 }; }
function placeOverlays(dt) {
  if (P2.on) { labels.forEach(l => l.el.style.display = "none"); people.forEach(p => p.name.style.display = "none"); bubble.style.display = "none"; if (dirBub) dirBub.style.display = "none"; p2Overlays(dt); return; }
  labels.forEach(l => { const s = project(l.p); l.el.style.left = s.x + "px"; l.el.style.top = s.y + "px";
    l.el.style.display = s.ok && !(l.maxD && cam.position.distanceTo(l.near) > l.maxD) ? "" : "none"; });
  people.forEach(p => { const s = project(p.g.position.clone().setY(p.g.position.y + 2.5)); p.name.style.left = s.x + "px"; p.name.style.top = s.y + "px"; p.name.style.display = API().sel() === p.a.id ? "" : "none";
    p.name.textContent = p.a.nm + (p.mode === "sleep" && !p.path.length ? " 💤" : ""); });
  try { placeDirBubble(dt); } catch (e) { }
  const od = API().data(); if (!od) return;
  bubble.style.display = ctl.target.x > 21 || ctl.target.x < -16 ? "none" : "";
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
  if (nowMs - (frame.tvAt || -1e9) > 30000 || tvT <= 0) { frame.tvAt = nowMs; tvT = 30; drawTV(tvTex.userData.c.getContext("2d")); tvTex.needsUpdate = true; if (mesaTex) { mesaI++; drawMesa(mesaTex.userData.c.getContext("2d")); mesaTex.needsUpdate = true; } updateRadar(); updateArena(); updateRewards(); updateSectors(); updateStrategyRoom(); updateStaff(); updateDirector(); updateAcademy(); updateMoney(); updateFloor2(); updateMission(); drawBoard(board.userData.c.getContext("2d")); board.needsUpdate = true; }
  if (radar) { radar.sweep.rotation.z -= dt * 1.4; radar.blips.children.forEach((b, i) => { if (b.geometry.type === "SphereGeometry") b.scale.setScalar(1 + Math.sin(t * 4 + i) * .15); }); }
  if (P2.on) p2Tick(dt, t);
  if (cofreScr) { cofreScr.visible = !P2.on; cofreScr.quaternion.copy(cam.quaternion); cofreScr.scale.setScalar(cam.aspect < .8 ? 1.4 : 1); }
  if (misScr) { misScr.visible = !P2.on; misScr.quaternion.copy(cam.quaternion); misScr.scale.setScalar(cam.aspect < .8 ? 1.5 : 1); }
  animateArena(dt, t); animateRewards(dt, t); secPeople.forEach(p => animate(p, dt, t)); stPeople.forEach(p => animate(p, dt, t)); staffPeople.forEach(p => animate(p, dt, t)); dirPeople.forEach(p => animate(p, dt, t)); acPeople.forEach(p => animate(p, dt, t));
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
  ctl.addEventListener("change", () => { if (P2.on) { const t = ctl.target, cx = Math.max(-19, Math.min(23, t.x)), cz = Math.max(-11, Math.min(11, t.z));
      if (cx !== t.x || cz !== t.z || t.y !== P2H) { const dx = cx - t.x, dz = cz - t.z, dy = P2H - t.y; t.set(cx, P2H, cz); cam.position.x += dx; cam.position.z += dz; cam.position.y += dy; } return; }
    const t = ctl.target, cx = Math.max(-28.5, Math.min(Math.max(48, ST_WALL + stLen + 2, acEnd + 1), t.x)), cz = t.x < -19.5 ? Math.max(-5, Math.min(5, t.z)) : Math.max(t.x > 19 ? -14 : -8.5, Math.min(t.x > 19 ? 14 : 11.5, t.z));
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
  buildRoom(); buildAccessories(); Object.keys(DESK).forEach(buildDesk); buildRadar(); buildBoard(); updateRadar(); buildArena(); buildRewards(); buildSectors(); buildStrategyRoom(); buildStaff(); buildDirector(); buildMemorial(); buildAcademy(); buildOpsMoney(); updateMoney(); buildMission(); buildCofre(); arenaSig = ""; updateArena();
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
    ray.setFromCamera(m, cam);
    if (!P2.on && misScr && ray.intersectObject(misScr, false)[0]) { showMission(); return; }
    if (!P2.on && cofreScr && ray.intersectObject(cofreScr, false)[0]) { showCofre(); return; }
    if (P2.on) { const h2 = ray.intersectObjects(P2.people.concat(P2.heads).map(p => p.g), true)[0]; if (h2) p2Click(h2); return; }
    const hit = ray.intersectObjects(people.map(p => p.g), true)[0];
    if (hit) { API().select(hit.object.userData.agent); bubAt = 0; return; }
    const sh = ray.intersectObjects(secPeople.map(p => p.g), true)[0]; if (sh) { API().openZone("sectors"); return; }
    // lutadores (arena, sala de estrategia, academia): cartao com o combate e o que fazem agora
    const fid = h => { let o = h && h.object; while (o && !o.userData.agent) o = o.parent; const k = o && o.userData.agent || ""; return /^(fx|st|ac)_/.test(k) && k !== "ac_mentor" ? k.slice(3) : null; };
    const fh = ray.intersectObjects(fighters.map(f => f.g), true)[0] || ray.intersectObjects(stPeople.map(p => p.g), true)[0] || ray.intersectObjects(acPeople.map(p => p.g), true)[0];
    if (fh) { const id = fid(fh); if (id && API().fighter) API().fighter(id); else API().openZone("arena"); return; }
    if (ray.intersectObjects(dirPeople.map(p => p.g), true)[0]) { API().openZone("diretor"); return; }
    const sf = ray.intersectObjects(staffPeople.map(p => p.g), true)[0]; if (sf) { let o = sf.object; while (o && !o.userData.agent) o = o.parent; const q = staffPeople.find(p => p.a.id === (o && o.userData.agent)); API().openZone(q ? q.staffZone : "lab"); return; }
    const zh = ray.intersectObjects(zoneHits, false)[0]; if (zh) API().openZone(zh.object.userData.zone);
  });
  new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(box);
  addEventListener("resize", resize); resize();
  clock = new THREE.Clock(); running = true; frame();
  return true;
}
// voltar a vista inicial (botao no ecra)
function resetView() { p2Leave(); resize.done = false; ctl.target.set(0, 0, 0); resize(); ctl.update(); }
function goArena() { p2Leave(); const tx = ARENA_C.x + 2, dx = tx - ctl.target.x, dz = ARENA_C.z - ctl.target.z; ctl.target.set(tx, 0, ARENA_C.z); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target), want = 30; if (d.length() > want) cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
function goRewards() { p2Leave(); const T = V(TRO_X0 + TRO_LEN / 2, TRO_ZC + .35), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target); cam.position.copy(ctl.target.clone().add(d.setLength(14 + TRO_LEN * .5))); ctl.update(); }
function goSectors() { p2Leave(); const T = V(23.8, 10.9), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target), want = 18; if (d.length() > want) cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
function goStrategy() { p2Leave(); const T = V(ST_WALL + stLen / 2 + .6, 0), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target), want = 17 + stLen * .35; cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
function goTo(x, z, want = 14) { p2Leave(); const T = V(x, z), dx = T.x - ctl.target.x, dz = T.z - ctl.target.z; ctl.target.copy(T); cam.position.x += dx; cam.position.z += dz;
  const d = cam.position.clone().sub(ctl.target); cam.position.copy(ctl.target.clone().add(d.setLength(want))); ctl.update(); }
window.Office3D = { init, supported, refresh: () => { tvT = 0; }, resetView, goArena, goRewards, goSectors, goStrategy, goMemorial, goAcademy, goDirector, goTo, goFloor, floor: () => P2.on ? 2 : 1, showMission, showCofre };
