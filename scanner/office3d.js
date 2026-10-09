// Escritorio 3D do Cryptoscan (Three.js). Os agentes e o seu estado vem da
// pagina (window.OFAPI): quem esta a trabalhar senta-se a secretaria, quem
// esta em pausa anda pelo cafe, pela sala de reuniao e pelos servidores, e de
// noite dorme no sofa. Os baloes mostram o trabalho real de cada agente.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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
  scan: { z: "ops", p: V(-9, -9.5), f: -1 }, mon: { z: "ops", p: V(-9, -5), f: -1 },
  afin: { z: "lab", p: V(-9, 2.5), f: -1 }, inv: { z: "lab", p: V(-9, 6.2), f: -1 },
  juiz: { z: "lab", p: V(-9, 9.9), f: -1 },
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

let R, scene, cam, ctl, box, overlay, clock, people = [], monTex, monOn = {}, tvTex,
  ledTex, labels = [], bubble, bubAt = 0, bubI = 0, bubWho = null, visible = true, running = false;

function supported() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); }
  catch (_) { return false; }
}

const mat = (c, e = 0, o = 1) => new THREE.MeshStandardMaterial({ color: c, emissive: e ? c : 0x000000, emissiveIntensity: e, transparent: o < 1, opacity: o, roughness: .6, metalness: .1 });
function boxM(w, h, d, m, x, y, z, parent = scene) { const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z); parent.add(b); return b; }
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
  floor.rotation.x = -Math.PI / 2; scene.add(floor);
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
    [[Z.x[0], Z.z[0]], [Z.x[1], Z.z[0]], [Z.x[1], Z.z[1]], [Z.x[0], Z.z[1]]].forEach(([x, z]) => k !== "srv" && boxM(.08, h, .08, mat(Z.c, 1.2), x, h / 2, z));
    labels.push({ el: label(Z.name, Z.c, true), p: new THREE.Vector3(cx, (k === "meet" ? 3.3 : 2.1), Z.z[0] + .2) });
  }
  // sala de reuniao: mesa oval, cadeiras, ecra
  const t = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, .08, 32), mat("#3b3f6e")); t.scale.set(1.9, 1, .9); t.position.set(7.5, .75, -8); scene.add(t);
  boxM(.2, .72, .2, mat("#222"), 7.5, .36, -8);
  tvTex = canvasTex(512, 288, drawTV);
  const tv = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 2.36), new THREE.MeshBasicMaterial({ map: tvTex })); tv.position.set(8, 1.75, -11.9); scene.add(tv);
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
    const f = new THREE.Mesh(new THREE.PlaneGeometry(.9, 2.2), new THREE.MeshBasicMaterial({ map: ledTex })); f.position.set(18.03, 1.2, z); f.rotation.y = -Math.PI / 2; scene.add(f);
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
  boxM(.3, .02, .5, mat("#ddd"), -f * .15, .79, .5, g); // teclado/papeis
  // cadeira
  const ch = new THREE.Group(); ch.position.set(-f * .95, 0, 0); g.add(ch);
  boxM(.55, .08, .55, mat("#2b2b40"), 0, .48, 0, ch); boxM(.08, .6, .55, mat("#2b2b40"), -f * .27, .8, 0, ch);
  boxM(.06, .45, .06, mat("#111"), 0, .24, 0, ch);
}

// ---------- pessoas ----------
function label(text, color, zone) {
  const el = document.createElement("div"); el.textContent = text;
  el.style.cssText = `position:absolute;transform:translate(-50%,-100%);pointer-events:none;white-space:nowrap;font:${zone ? "700 11px" : "700 11px"} system-ui,sans-serif;color:${color};text-shadow:0 0 6px ${color}88,0 1px 2px #000`;
  overlay.appendChild(el); return el;
}
function makePerson(a) {
  const [hair, skin] = LOOK[a.id], g = new THREE.Group(), shirt = mat(a.c, .25), pants = mat("#1d1d33");
  const legL = new THREE.Group(), legR = new THREE.Group(); legL.position.set(-.11, .72, 0); legR.position.set(.11, .72, 0);
  boxM(.15, .7, .17, pants, 0, -.35, 0, legL); boxM(.15, .7, .17, pants, 0, -.35, 0, legR); g.add(legL, legR);
  boxM(.46, .58, .26, shirt, 0, 1.02, 0, g);
  const armL = new THREE.Group(), armR = new THREE.Group(); armL.position.set(-.3, 1.27, 0); armR.position.set(.3, 1.27, 0);
  boxM(.12, .5, .14, shirt, 0, -.25, 0, armL); boxM(.12, .5, .14, shirt, 0, -.25, 0, armR);
  boxM(.11, .1, .12, mat(skin), 0, -.53, 0, armL); boxM(.11, .1, .12, mat(skin), 0, -.53, 0, armR); g.add(armL, armR);
  const head = new THREE.Mesh(new THREE.SphereGeometry(.19, 16, 12), mat(skin)); head.position.y = 1.52; g.add(head);
  const hr = new THREE.Mesh(new THREE.SphereGeometry(.2, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2), mat(hair)); hr.position.y = 1.54; g.add(hr);
  const badge = boxM(.1, .12, .01, mat("#fff", .8), .1, 1.1, .135, g);
  const ring = new THREE.Mesh(new THREE.RingGeometry(.42, .5, 32), new THREE.MeshBasicMaterial({ color: 0xFFA94D, transparent: true, opacity: 0 }));
  ring.rotation.x = -Math.PI / 2; ring.position.y = .03; g.add(ring);
  g.traverse(o => { o.userData.agent = a.id; });
  g.scale.setScalar(1.45); scene.add(g);
  const desk = DESK[a.id], seat = desk.p.clone().add(V(-desk.f * .95, 0));
  g.position.copy(seat);
  return { a, g, legL, legR, armL, armR, head, ring, zone: desk.z, path: [], mode: "work", spot: null, wait: 0, sit: true, seat, face: desk.f > 0 ? Math.PI / 2 : -Math.PI / 2, name: label(a.nm, a.c) };
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
  const walking = p.path.length > 0, sw = walking ? Math.sin(t * 9 + p.a.id.length) * .6 : 0;
  if (!walking) p.g.rotation.y = p.mode === "work" ? p.face : (p.spot != null && SPOTS[p.spot].r != null ? SPOTS[p.spot].r : p.g.rotation.y);
  const sit = p.sit && !walking;
  p.g.position.y = sit ? -.36 : 0;
  p.legL.rotation.x = sit ? -Math.PI / 2 : sw; p.legR.rotation.x = sit ? -Math.PI / 2 : -sw;
  const typing = p.mode === "work" && sit;
  p.armL.rotation.x = typing ? -1.1 + Math.sin(t * 14) * .12 : (walking ? -sw : (p.spot != null && SPOTS[p.spot].k === "cafe" ? -1.2 : 0));
  p.armR.rotation.x = typing ? -1.1 + Math.cos(t * 14) * .12 : (walking ? sw : 0);
  p.head.rotation.x = p.mode === "sleep" && !walking ? .5 : (typing ? .1 : 0);
  p.ring.material.opacity = API().sel() === p.a.id ? .9 : 0;
}

// ---------- ciclo ----------
function project(v) { const p = v.clone().project(cam), r = R.domElement; return { x: (p.x + 1) / 2 * r.clientWidth, y: (1 - p.y) / 2 * r.clientHeight, ok: p.z < 1 }; }
function placeOverlays(dt) {
  labels.forEach(l => { const s = project(l.p); l.el.style.left = s.x + "px"; l.el.style.top = s.y + "px"; l.el.style.display = s.ok ? "" : "none"; });
  people.forEach(p => { const s = project(p.g.position.clone().setY(p.g.position.y + 2.7)); p.name.style.left = s.x + "px"; p.name.style.top = s.y + "px"; p.name.style.display = API().sel() === p.a.id ? "" : "none";
    p.name.textContent = p.a.nm + (p.mode === "sleep" && !p.path.length ? " 💤" : ""); });
  const od = API().data(); if (!od) return;
  bubAt -= dt; const sel = API().sel();
  if (bubAt <= 0 || (sel && bubWho !== sel)) {
    const cand = sel ? people.filter(p => p.a.id === sel) : people.filter(p => od[p.a.id].on || Math.random() < .3);
    const p = cand[(bubI++) % Math.max(1, cand.length)] || people[0]; bubWho = p.a.id; bubAt = 4.5;
    const o = od[p.a.id]; bubble.innerHTML = `<b>${p.a.nm}</b><br>${o.msgs[bubI % o.msgs.length]}`; bubble.style.borderColor = p.a.c;
  }
  const p = people.find(q => q.a.id === bubWho); if (!p) return;
  const s = project(p.g.position.clone().setY(p.g.position.y + 2.9)); const w = bubble.offsetWidth, W = R.domElement.clientWidth;
  bubble.style.left = Math.max(4, Math.min(W - w - 4, s.x - w / 2)) + "px"; bubble.style.top = Math.max(4, s.y - bubble.offsetHeight) + "px";
}
let ledT = 0, tvT = 0;
function frame() {
  if (!running) return; requestAnimationFrame(frame);
  const open = document.getElementById("s-escritorio").open;
  if (!open || !visible || document.hidden) return;
  const dt = Math.min(.1, clock.getDelta()), t = clock.elapsedTime;
  people.forEach(p => { if (!p.path.length || (stateOf(p.a.id) === "work" && p.mode !== "work")) decide(p); animate(p, dt, t); });
  // monitores ligados so para quem esta a trabalhar e sentado
  monTex.userData.draw(monTex.userData.c.getContext("2d"), t); monTex.needsUpdate = true;
  people.forEach(p => { const on = p.mode === "work" && p.sit && !p.path.length, m = monOn[p.a.id].material;
    if (on && m.map !== monTex) { m.map = monTex; m.color.set(0xffffff); m.needsUpdate = true; } else if (!on && m.map) { m.map = null; m.color.set(0x0b1424); m.needsUpdate = true; } });
  ledT -= dt; if (ledT <= 0) { ledT = .35; drawLeds(ledTex.userData.c.getContext("2d")); ledTex.needsUpdate = true; }
  tvT -= dt; if (tvT <= 0) { tvT = 30; drawTV(tvTex.userData.c.getContext("2d")); tvTex.needsUpdate = true; }
  ctl.update(); R.render(scene, cam); placeOverlays(dt);
}
function resize() { const w = box.clientWidth, h = Math.round(w * (w < 600 ? .95 : .62)); R.setSize(w, h, false); R.domElement.style.width = w + "px"; R.domElement.style.height = h + "px"; cam.aspect = w / h; cam.updateProjectionMatrix(); }

function init(container) {
  if (!supported()) return false;
  box = container; box.innerHTML = ""; box.style.position = "relative";
  R = new THREE.WebGLRenderer({ antialias: true, alpha: false }); R.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  R.setClearColor(0x0a0820); R.domElement.style.borderRadius = "12px"; R.domElement.style.display = "block"; R.domElement.style.touchAction = "none";
  box.appendChild(R.domElement);
  overlay = document.createElement("div"); overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden;border-radius:12px"; box.appendChild(overlay);
  bubble = document.createElement("div"); bubble.className = "obub3"; overlay.appendChild(bubble);
  const det = document.createElement("div"); det.id = "odetail"; box.parentNode.insertBefore(det, box.nextSibling);
  scene = new THREE.Scene(); scene.fog = new THREE.Fog(0x0a0820, 38, 70);
  cam = new THREE.PerspectiveCamera(42, 1.3, .1, 200); cam.position.set(9, 17, 19);
  ctl = new OrbitControls(cam, R.domElement); ctl.target.set(0, 0, 0); ctl.enableDamping = true; ctl.minDistance = 10; ctl.maxDistance = 48;
  ctl.maxPolarAngle = 1.25; ctl.minPolarAngle = .35; ctl.enablePan = false;
  scene.add(new THREE.HemisphereLight(0xb9a8ff, 0x1a1150, 1.1));
  const dl = new THREE.DirectionalLight(0xffffff, .9); dl.position.set(8, 20, 10); scene.add(dl);
  const pl1 = new THREE.PointLight(0xff6fb5, 30, 26); pl1.position.set(0, 4, 0); scene.add(pl1);
  const pl2 = new THREE.PointLight(0x4fd1c5, 25, 24); pl2.position.set(-10, 4, -6); scene.add(pl2);
  monTex = canvasTex(256, 160, drawMon);
  buildRoom(); Object.keys(DESK).forEach(buildDesk);
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
    if (hit) { API().select(hit.object.userData.agent); bubAt = 0; }
  });
  new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(box);
  addEventListener("resize", resize); resize();
  clock = new THREE.Clock(); running = true; frame();
  return true;
}
window.Office3D = { init, supported };
