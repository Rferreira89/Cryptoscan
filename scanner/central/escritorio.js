// CRYPTOSCAN ATLAS — escritorio 3D de UM SO PISO (Three.js). Concept & Creative Direction — Rui.
//
// Uma plataforma unica em grafite, com luz dourada por baixo e duas paredes de ecras (norte e oeste) atras; o resto e
// aberto, para se ver a equipa toda. Nove areas no mesmo piso, sem escadas nem outros niveis. Os agentes sao os do
// sistema (agentes.js): androides em grafite com a cor da sua area. A animacao segue o estado REAL de cada um:
//   ativo -> trabalha na estacao;  em espera -> vai sentar-se na zona de standby;  desligado -> estacao apagada;
//   erro -> anel vermelho.  Um encaminhamento real (evento com hora) faz o agente ir a estacao do destinatario, uma vez.
// Os ecras sao desenhados com dados reais (graficos.js); sem dados, mostram a indisponibilidade.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { AGENTES, AREAS, ESTADOS } from "./agentes.js";

const OURO = "#E8B84A", CIANO = "#35D6F2", GRAFITE = "#1B2028";
export const SALA = { x: [-26, 26], z: [-16, 16], parede: 8 };

// retangulo de cada area no piso (x, z) — todas no mesmo nivel
export const ZONAS = {
  tecnica:    { x: [-22.5, -16],  z: [-12.5, -5] },
  trading:    { x: [-15.5, -4],   z: [-12.5, -5] },
  cacador:    { x: [-3.5, 3.5],   z: [-12.5, -5] },
  quant:      { x: [4, 10.5],     z: [-12.5, -5] },
  estrategia: { x: [11, 17.5],    z: [-12.5, -5] },
  intel:      { x: [-22.5, -10.5], z: [-3.5, 3.6] },
  risco:      { x: [-9.8, -3.2],  z: [-3.5, 3.6] },
  comando:    { x: [-2, 9],       z: [1.2, 11] },
  exchanges:  { x: [10.2, 23],    z: [-3.5, 11] },
  standby:    { x: [-23.5, -8.5], z: [7, 14.5], nome: "Standby · em espera", cor: "#8796AA" },
  parede:     { x: [-26, 26],     z: [-16, -14], nome: "Parede de mercado", cor: CIANO },
};
for (const [k, a] of Object.entries(AREAS)) Object.assign(ZONAS[k], a);

// cadeira de cada agente (todos virados a norte, para a parede de mercado); via = ponto de acesso quando a secretaria tapa o caminho
const ESTACOES = {
  scanner: { p: [-19.2, -8] }, panico: { p: [-12.6, -8] }, recuo: { p: [-7, -8] }, macro: { p: [0, -8] }, arena: { p: [7.2, -8] }, tfshort: { p: [14.2, -8] },
  liquidez: { p: [-19.2, .6] }, noticias: { p: [-13.6, .6] }, risco: { p: [-6.5, .6] },
  exec_okx: { p: [13.6, .6] }, exec_bybit: { p: [19.4, .6] }, nucleo: { p: [19.4, 8.2], via: [16.2, 8.2] },
  diretor: { p: [3.5, 8.6], via: [9.4, 8.6] },
};
const STANDBY = [[-21.4, 9.4], [-17.9, 9.4], [-14.4, 9.4], [-10.9, 9.4], [-21.4, 12.8], [-17.9, 12.8], [-14.4, 12.8], [-10.9, 12.8]];
const CORREDOR = { norte: -4.4, sul: 4.6, passagens: [-10.2, 9.6] };

const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: o.r ?? .5, metalness: o.m ?? .35, transparent: o.op != null, opacity: o.op ?? 1, depthWrite: o.op == null || o.op > .6 });
const luz = (c, op = 1) => new THREE.MeshBasicMaterial({ color: c, toneMapped: false, transparent: op < 1, opacity: op });

// simbolo do CryptoScan Atlas (original): hexagono, meridiano de varrimento e linha de mercado com no dourado
export function desenharSimbolo(g, s, cor = OURO, cor2 = CIANO) {
  const c = s / 2, r = s * .42; g.lineJoin = "round"; g.lineCap = "round";
  g.strokeStyle = cor; g.lineWidth = s * .05; g.beginPath();
  for (let i = 0; i < 6; i++) { const a = Math.PI / 6 + i * Math.PI / 3, x = c + r * Math.cos(a), y = c + r * Math.sin(a); i ? g.lineTo(x, y) : g.moveTo(x, y); } g.closePath(); g.stroke();
  g.strokeStyle = cor2; g.lineWidth = s * .028; g.beginPath(); g.ellipse(c, c, r * .36, r * .78, 0, 0, Math.PI * 2); g.stroke();
  g.strokeStyle = cor; g.lineWidth = s * .055; g.beginPath(); g.moveTo(c - r * .55, c + r * .3); g.lineTo(c - r * .15, c - r * .05); g.lineTo(c + r * .12, c + r * .16); g.lineTo(c + r * .55, c - r * .36); g.stroke();
  g.fillStyle = cor; g.beginPath(); g.arc(c + r * .55, c - r * .36, s * .045, 0, Math.PI * 2); g.fill();
}

export class Escritorio {
  constructor(el, { onAgente = () => {}, onZona = () => {}, onAcao = () => {}, qualidade = "auto", desenharEcra = null } = {}) {
    this.m = { esq: 0, dir: 0, topo: 0, baixo: 0 };
    this.el = el; this.onAgente = onAgente; this.onZona = onZona; this.onAcao = onAcao; this.desenharEcra = desenharEcra;
    this.qualidade = qualidade === "auto" ? Escritorio.qualidadeSugerida() : qualidade;
    this.agentes = {}; this.ecras = []; this.estados = {}; this.selecionado = null; this.fila = []; this.vistos = new Set(); this.feixes = [];
    this.relogio = new THREE.Clock(); this.parado = false; this.ultimo = 0; this.fps = 0; this._fpsN = 0; this._fpsT = 0; this._primeira = true;
    this._iniciar();
  }

  static qualidadeSugerida() {
    const nav = globalThis.navigator || {}, mob = /Mobi|Android|iPhone|iPad/i.test(nav.userAgent || "");
    return mob || (nav.hardwareConcurrency || 8) <= 4 ? "baixa" : "alta";
  }

  _iniciar() {
    const alta = this.qualidade === "alta";
    const R = this.R = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    R.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, alta ? 2 : 1.25));
    R.outputColorSpace = THREE.SRGBColorSpace; R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.12;
    R.shadowMap.enabled = alta; R.shadowMap.type = THREE.PCFSoftShadowMap;
    this.el.appendChild(R.domElement); R.domElement.style.display = "block";
    const S = this.cena = new THREE.Scene(); S.background = new THREE.Color("#06080C");
    const w = this.el.clientWidth || 800, h = this.el.clientHeight || 600, a = w / h, f = 26;
    const C = this.cam = new THREE.OrthographicCamera(-f * a, f * a, f, -f, -300, 500);
    C.position.set(60, 52, 60); C.updateProjectionMatrix();
    const ctl = this.ctl = new OrbitControls(C, R.domElement);
    ctl.target.set(0, 1.5, 0); ctl.enableDamping = true; ctl.dampingFactor = .08; ctl.minZoom = .4; ctl.maxZoom = 5;
    ctl.minPolarAngle = .5; ctl.maxPolarAngle = 1.15; ctl.minAzimuthAngle = Math.PI / 4 - .62; ctl.maxAzimuthAngle = Math.PI / 4 + .62;   // rotacao controlada: as paredes ficam sempre atras
    ctl.screenSpacePanning = true; ctl.update();
    ctl.addEventListener("start", () => { this._interagiu = true; });
    ctl.addEventListener("change", () => { const t = ctl.target; t.x = Math.max(-26, Math.min(26, t.x)); t.z = Math.max(-16, Math.min(16, t.z)); });
    this._luzes(); this._plataforma(); this._paredes(); this._areas(); this._comando(); this._standby(); this._infra(); this._postos();
    if (alta) {
      this.comp = new EffectComposer(R); this.comp.addPass(new RenderPass(S, C));
      this.comp.addPass(new UnrealBloomPass(new THREE.Vector2(w / 2, h / 2), .62, .55, .8)); this.comp.addPass(new OutputPass());
    }
    this.overlay = document.createElement("div"); this.overlay.className = "of-overlay"; this.el.appendChild(this.overlay);
    for (const a2 of AGENTES) this._etiqueta(a2);
    this.ray = new THREE.Raycaster(); this.ptr = new THREE.Vector2();
    let down = null;
    R.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
    R.domElement.addEventListener("pointerup", e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 6) this._clique(e); down = null; });
    this._ro = new ResizeObserver(() => this.redimensionar()); this._ro.observe(this.el);
    document.addEventListener("visibilitychange", this._vis = () => { this.parado = document.hidden; if (!this.parado) this._loop(); });
    this._loop();
  }

  _luzes() {
    const S = this.cena;
    S.add(new THREE.HemisphereLight("#C4D4EE", "#12161E", .9)); S.add(new THREE.AmbientLight("#5A6478", .35));
    const sol = new THREE.DirectionalLight("#FFF1D6", 1.35); sol.position.set(34, 56, 26); sol.castShadow = this.qualidade === "alta";
    Object.assign(sol.shadow.camera, { left: -36, right: 36, top: 30, bottom: -30, near: 1, far: 160 }); sol.shadow.mapSize.set(2048, 2048); sol.shadow.bias = -.0004; S.add(sol);
    const frio = new THREE.DirectionalLight(CIANO, .22); frio.position.set(-30, 18, -20); S.add(frio);
  }

  _caixa(w, h, d, m, x, y, z, pai = this.cena, sombra = true) {
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z);
    b.castShadow = sombra && this.qualidade === "alta"; b.receiveShadow = this.qualidade === "alta"; pai.add(b); return b;
  }
  _textura(w, h) {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; t.userData.c = c; return t;
  }
  _textoChao(txt, cor, x, z, larg = 9, op = .8) {
    const c = document.createElement("canvas"); c.width = 1024; c.height = 96; const g = c.getContext("2d");
    let fs = 54; g.font = `600 ${fs}px Inter, system-ui, sans-serif`; while (g.measureText(txt).width > 1000 && fs > 26) { fs -= 3; g.font = `600 ${fs}px Inter, system-ui, sans-serif`; }
    g.fillStyle = cor; g.globalAlpha = op; g.fillText(txt, 6, 66);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(larg, larg * 96 / 1024), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false, toneMapped: false }));
    m.rotation.x = -Math.PI / 2; m.position.set(x + larg / 2, .035, z); this.cena.add(m); return m;
  }

  // ---------- plataforma unica: laje em grafite com luz dourada por baixo
  _plataforma() {
    const S = this.cena, W = 52, D = 32;
    const solo = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.MeshStandardMaterial({ color: "#07090D", roughness: .9, metalness: .1 }));
    solo.rotation.x = -Math.PI / 2; solo.position.y = -2.2; S.add(solo);
    const gr = new THREE.GridHelper(240, 60, "#161C28", "#10141C"); gr.position.y = -2.19; gr.material.transparent = true; gr.material.opacity = .7; S.add(gr);
    // halo dourado no solo, por baixo da laje
    const hc = document.createElement("canvas"); hc.width = hc.height = 256; const hg = hc.getContext("2d");
    const rg = hg.createRadialGradient(128, 128, 30, 128, 128, 128); rg.addColorStop(0, "rgba(232,184,74,.55)"); rg.addColorStop(.6, "rgba(232,184,74,.16)"); rg.addColorStop(1, "rgba(232,184,74,0)");
    hg.fillStyle = rg; hg.fillRect(0, 0, 256, 256);
    const halo = new THREE.Mesh(new THREE.PlaneGeometry(W * 1.5, D * 1.7), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(hc), transparent: true, depthWrite: false, toneMapped: false }));
    halo.rotation.x = -Math.PI / 2; halo.position.y = -2.17; S.add(halo);
    this._caixa(W + 1.2, 1.5, D + 1.2, mat("#12161D", { r: .45, m: .6 }), 0, -.76, 0, S, false);
    this._caixa(W + .6, .12, D + .6, luz(OURO), 0, -1.56, 0, S, false);                               // friso dourado inferior
    const chao = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshStandardMaterial({ color: "#232833", roughness: .38, metalness: .55 }));
    chao.rotation.x = -Math.PI / 2; chao.receiveShadow = true; S.add(chao);
    const g2 = new THREE.GridHelper(52, 26, "#2E3644", "#2A313D"); g2.position.y = .006; g2.scale.z = D / W; g2.material.transparent = true; g2.material.opacity = .45; S.add(g2);
    // friso dourado no bordo da laje (frente e direita) e guarda de vidro baixa
    for (const [w, d, x, z] of [[W + 1.2, .1, 0, D / 2 + .55], [.1, D + 1.2, W / 2 + .55, 0]]) this._caixa(w, .06, d, luz(OURO), x, .02, z, S, false);
    const vidro = mat("#9FD8F0", { op: .1, r: .05, m: .9 });
    this._caixa(W, .9, .08, vidro, 0, .45, D / 2 + .3, S, false); this._caixa(.08, .9, D, vidro, W / 2 + .3, .45, 0, S, false);
    // corredores de circulacao: linhas de luz ciano embutidas
    for (const z of [CORREDOR.norte, CORREDOR.sul]) this._caixa(48, .012, .07, luz(CIANO, .55), 0, .012, z, S, false);
    for (const x of CORREDOR.passagens) this._caixa(.07, .012, CORREDOR.sul - CORREDOR.norte, luz(CIANO, .55), x, .012, (CORREDOR.norte + CORREDOR.sul) / 2, S, false);
    // assinatura discreta no bordo sul
    this._textoChao("CRYPTOSCAN ATLAS  ·  Concept & Creative Direction — Rui", OURO, 9, 15.2, 16, .7);
  }

  // ---------- paredes de mercado (norte e oeste): ecras grandes com dados reais
  _paredes() {
    const S = this.cena, H = SALA.parede, par = mat("#151A22", { r: .6, m: .5 });
    this._caixa(53.2, H, .6, par, -.3, H / 2, -16.3, S); this._caixa(.6, H, 32, par, -26.3, H / 2, 0, S);
    this._caixa(53.2, .1, .7, luz(CIANO), -.3, H + .05, -16.3, S, false); this._caixa(.7, .1, 32.6, luz(CIANO), -26.3, H + .05, 0, S, false);
    const moldura = mat("#0A0D12", { r: .3, m: .7 });
    const ecra = (id, larg, alt, pos, rotY, px) => {
      const tex = this._textura(px[0], px[1]), g = new THREE.Group(); g.position.set(...pos); g.rotation.y = rotY; S.add(g);
      this._caixa(larg + .3, alt + .3, .12, moldura, 0, 0, -.07, g, false);
      this._caixa(larg + .3, .04, .14, luz(CIANO, .8), 0, -alt / 2 - .17, -.06, g, false);
      const tela = new THREE.Mesh(new THREE.PlaneGeometry(larg, alt), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
      tela.userData.zona = "parede"; tela.userData.ecra = id; g.add(tela); this.ecras.push({ id, tex });
    };
    const y = 4.15, A = 5.3;
    ecra("resultado", 10.6, A, [-19.6, y, -15.94], 0, [1100, 550]);
    ecra("btc", 12, A, [-7.6, y, -15.94], 0, [1240, 550]);
    ecra("mapa", 11, A, [4.7, y, -15.94], 0, [1140, 550]);
    ecra("quantw", 12.6, A, [17.3, y, -15.94], 0, [1300, 550]);
    ecra("atividade", 10.4, A, [-25.94, y, -9.4], Math.PI / 2, [1080, 550]);
    ecra("riscow", 8.4, A, [-25.94, y, .6], Math.PI / 2, [880, 550]);
    ecra("corretoras", 8.8, A, [-25.94, y, 10], Math.PI / 2, [920, 550]);
    // letreiro no topo da parede norte
    const c = document.createElement("canvas"); c.width = 1024; c.height = 96; const g = c.getContext("2d");
    desenharSimbolo(g, 96); g.font = "700 46px Inter, system-ui, sans-serif"; g.fillStyle = "#E9EEF6"; g.fillText("CRYPTOSCAN", 112, 64); g.fillStyle = OURO; g.fillText("ATLAS", 452, 64);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const let1 = new THREE.Mesh(new THREE.PlaneGeometry(10.6, 1), new THREE.MeshBasicMaterial({ map: t, transparent: true, toneMapped: false })); let1.position.set(-20, 7.35, -15.95); S.add(let1);
  }

  // ---------- areas funcionais: incrustacao no piso, contorno e nome (identidade propria, mesmo piso)
  _areas() {
    this.zonaMesh = {};
    for (const [k, z] of Object.entries(ZONAS)) {
      if (k === "parede") continue;
      const w = z.x[1] - z.x[0], d = z.z[1] - z.z[0], cx = (z.x[0] + z.x[1]) / 2, cz = (z.z[0] + z.z[1]) / 2, c = new THREE.Color(z.cor);
      const base = new THREE.Color("#262C38").lerp(c, .09);
      const tap = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshStandardMaterial({ color: base, roughness: .55, metalness: .35 }));
      tap.rotation.x = -Math.PI / 2; tap.position.set(cx, .015, cz); tap.receiveShadow = true; tap.userData.zona = k; this.cena.add(tap); this.zonaMesh[k] = tap;
      const pts = [[z.x[0], z.z[0]], [z.x[1], z.z[0]], [z.x[1], z.z[1]], [z.x[0], z.z[1]], [z.x[0], z.z[0]]].map(([x, y]) => new THREE.Vector3(x, .03, y));
      this.cena.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: .7 })));
      this._caixa(Math.min(w, 2.4), .02, .09, luz(z.cor), z.x[0] + Math.min(w, 2.4) / 2, .03, z.z[1] - .05, this.cena, false);       // marcador da area
      this._textoChao(z.nome.toUpperCase(), z.cor, z.x[0] + .25, z.z[1] - .62, Math.min(w - .4, 7.5), .9);
    }
  }

  // ---------- estacao: secretaria em L leve, 3 monitores (o do meio com dados), cadeira e anel de estado
  _secretaria(id, x, z, cor) {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.scale.setScalar(1.12); this.cena.add(g);
    const tampo = mat("#2C3340", { r: .3, m: .6 }), perna = mat("#10141A", { m: .7, r: .4 });
    this._caixa(3.5, .09, 1.45, tampo, 0, .8, -1.05, g); this._caixa(.1, .78, 1.3, perna, -1.65, .39, -1.05, g); this._caixa(.1, .78, 1.3, perna, 1.65, .39, -1.05, g);
    this._caixa(3.5, .5, .06, perna, 0, .5, -1.74, g);
    const borda = new THREE.Mesh(new THREE.BoxGeometry(3.5, .035, .05), luz(cor)); borda.position.set(0, .83, -.33); g.add(borda);
    const tex = this._textura(512, 320), mons = [];
    [[-1.14, .34], [0, 0], [1.14, -.34]].forEach(([dx, ry], i) => {
      const m = new THREE.Group(); m.position.set(dx, 1.42, -1.45); m.rotation.y = ry; g.add(m);
      this._caixa(1.1, .7, .05, mat("#06080C", { r: .3, m: .7 }), 0, 0, -.03, m);
      const tela = new THREE.Mesh(new THREE.PlaneGeometry(1.03, .63), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false, color: i === 1 ? "#FFFFFF" : "#AEBBCB" }));
      tela.position.z = .002; m.add(tela); mons.push(tela); this._caixa(.07, .4, .07, perna, 0, -.5, -.05, m);
    });
    this._caixa(.9, .03, .32, mat("#0C0F14", { r: .5 }), 0, .86, -.72, g, false);                       // teclado
    const cad = new THREE.Group(); cad.position.set(0, 0, 0); g.add(cad);
    this._caixa(.66, .1, .62, mat("#161B23"), 0, .5, 0, cad); this._caixa(.66, .8, .1, mat("#161B23"), 0, .98, .32, cad); this._caixa(.09, .46, .09, perna, 0, .24, 0, cad);
    const anel = new THREE.Mesh(new THREE.RingGeometry(1.0, 1.13, 48), luz("#8796AA", .9)); anel.material.side = THREE.DoubleSide;
    anel.rotation.x = -Math.PI / 2; anel.position.set(0, .04, .05); g.add(anel);
    const hit = new THREE.Mesh(new THREE.BoxGeometry(3.7, 2.2, 3.1), new THREE.MeshBasicMaterial({ visible: false })); hit.position.set(0, 1.1, -.6); hit.userData.agente = id; g.add(hit);
    this.ecras.push({ id, tex });
    return { g, anel, mons, tex };
  }

  // ---------- androide: corpo em grafite, cabeca com visor na cor do estado, ombros e peito na cor da area
  _androide(cor) {
    const g = new THREE.Group(), s = this.qualidade === "alta";
    const corpo = mat("#3A414E", { r: .35, m: .7 }), escuro = mat("#1A1F27", { r: .5, m: .6 }), acento = mat(cor, { r: .35, m: .5 });
    const tronco = new THREE.Mesh(new THREE.CylinderGeometry(.27, .33, .7, 14), corpo); tronco.position.y = 1.02; g.add(tronco);
    const peito = new THREE.Mesh(new THREE.BoxGeometry(.3, .07, .02), luz(cor)); peito.position.set(0, 1.14, -.3); g.add(peito);
    const cab = new THREE.Group(); cab.position.y = 1.66; g.add(cab);
    const cabeca = new THREE.Mesh(new THREE.BoxGeometry(.46, .4, .42), corpo); cab.add(cabeca);
    const visor = new THREE.Mesh(new THREE.BoxGeometry(.36, .12, .03), luz(cor)); visor.position.set(0, .02, -.215); cab.add(visor);
    const pesc = new THREE.Mesh(new THREE.CylinderGeometry(.09, .09, .12, 8), escuro); pesc.position.y = 1.42; g.add(pesc);
    const ant = new THREE.Mesh(new THREE.CylinderGeometry(.012, .012, .22, 6), escuro); ant.position.set(.16, .3, 0); cab.add(ant);
    const farol = new THREE.Mesh(new THREE.SphereGeometry(.05, 10, 8), luz("#3FD68F")); farol.position.set(.16, .43, 0); cab.add(farol);
    const bracos = [-1, 1].map(sg => { const b = new THREE.Group(); b.position.set(sg * .36, 1.3, 0); g.add(b);
      const omb = new THREE.Mesh(new THREE.SphereGeometry(.12, 12, 8), acento); b.add(omb);
      const sup = new THREE.Mesh(new THREE.CylinderGeometry(.07, .065, .42, 8), corpo); sup.position.set(0, -.2, -.08); sup.rotation.x = .5; b.add(sup);
      const an = new THREE.Mesh(new THREE.CylinderGeometry(.06, .055, .42, 8), corpo); an.position.set(0, -.36, -.36); an.rotation.x = 1.45; b.add(an);
      const mao = new THREE.Mesh(new THREE.BoxGeometry(.11, .08, .14), escuro); mao.position.set(0, -.38, -.6); b.add(mao); return b; });
    const pernas = new THREE.Group(); g.add(pernas);
    [-1, 1].forEach(sg => { const c = new THREE.Mesh(new THREE.BoxGeometry(.19, .17, .62), escuro); c.position.set(sg * .14, .63, -.22); pernas.add(c);
      const p = new THREE.Mesh(new THREE.BoxGeometry(.17, .56, .17), corpo); p.position.set(sg * .14, .3, -.52); pernas.add(p); });
    g.traverse(o => { if (o.isMesh) o.castShadow = s; });
    return { g, cab, bracos, pernas, tronco, farol, visor, peito, corpo };
  }

  _postos() {
    for (const a of AGENTES) {
      const e = ESTACOES[a.id]; if (!e) continue;
      const s = this._secretaria(a.id, e.p[0], e.p[1], a.cor), p = this._androide(a.cor);
      const casa = new THREE.Vector3(e.p[0], 0, e.p[1]);
      p.g.position.copy(casa); this.cena.add(p.g); p.g.traverse(o => { o.userData.agente = a.id; });
      this.agentes[a.id] = { def: a, s, p, casa, via: e.via ? new THREE.Vector3(e.via[0], 0, e.via[1]) : null, fase: Math.random() * 6.28, andar: null, lugar: "estacao", assento: null };
    }
  }

  _etiqueta(a) {
    const d = document.createElement("button"); d.className = "of-tag"; d.type = "button";
    d.innerHTML = `<span class="n"><i></i><b>${a.nome}</b></span><span class="m"></span>`;
    d.addEventListener("click", ev => { ev.stopPropagation(); this.onAgente(a.id); });
    this.overlay.appendChild(d); const ag = this.agentes[a.id]; if (ag) ag.tag = d;
  }

  // ---------- command center: mesa em anel dourada, holograma do sistema e simbolo no piso
  _comando() {
    const g = new THREE.Group(); g.position.set(3.5, 0, 5.2); this.cena.add(g);
    const anel = new THREE.Mesh(new THREE.TorusGeometry(3.1, .5, 10, 64, Math.PI * 1.3), mat("#2C3340", { r: .3, m: .65 }));
    anel.rotation.x = -Math.PI / 2; anel.rotation.z = Math.PI * .35 + Math.PI; anel.position.y = .8; anel.scale.z = .22; anel.castShadow = this.qualidade === "alta"; g.add(anel);
    const friso = new THREE.Mesh(new THREE.TorusGeometry(3.62, .03, 6, 96, Math.PI * 1.3), luz(OURO)); friso.rotation.copy(anel.rotation); friso.position.y = .84; g.add(friso);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(1.25, 1.5, .45, 48), mat("#161B23", { m: .7 })); base.position.y = .225; g.add(base);
    const topo = new THREE.Mesh(new THREE.CylinderGeometry(1.27, 1.27, .03, 48), luz(OURO, .9)); topo.position.y = .46; g.add(topo);
    this.holo = new THREE.Group(); this.holo.position.y = 2.15; g.add(this.holo);
    this.holoEsfera = new THREE.Mesh(new THREE.IcosahedronGeometry(.95, 2), new THREE.MeshBasicMaterial({ color: CIANO, wireframe: true, transparent: true, opacity: .4, toneMapped: false })); this.holo.add(this.holoEsfera);
    this.holoAneis = [1.3, 1.55].map((r, i) => { const t = new THREE.Mesh(new THREE.TorusGeometry(r, .016, 6, 96), luz(i ? CIANO : OURO, .85)); t.rotation.x = Math.PI / 2 + (i ? .4 : -.25); this.holo.add(t); return t; });
    const feixe = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.25, 1.5, 32, 1, true), new THREE.MeshBasicMaterial({ color: CIANO, transparent: true, opacity: .06, side: THREE.DoubleSide, depthWrite: false, toneMapped: false }));
    feixe.position.y = 1.25; g.add(feixe);
    const hit = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 3.4, 12), new THREE.MeshBasicMaterial({ visible: false })); hit.position.y = 1.7; hit.userData.zona = "comando"; g.add(hit);
    // consola do comando: estado do sistema (textura real)
    const tex = this._textura(720, 380); this.ecras.push({ id: "sistema", tex });
    const cons = new THREE.Mesh(new THREE.PlaneGeometry(2.7, 1.42), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false })); cons.position.set(0, 1.55, -3.35); cons.rotation.x = -.3; cons.userData.zona = "comando"; g.add(cons);
    this._caixa(2.9, 1.6, .06, mat("#0A0D12", { m: .7 }), 0, 1.53, -3.42, g, false).rotation.x = -.3;
    // simbolo no piso
    const c = document.createElement("canvas"); c.width = c.height = 256; desenharSimbolo(c.getContext("2d"), 256);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const sm = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 2.6), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false, toneMapped: false, opacity: .9 }));
    sm.rotation.x = -Math.PI / 2; sm.position.set(-3.6, .04, 3.6); g.add(sm);
  }

  _standby() {
    const m = mat("#2A303B", { r: .6, m: .3 }), enc = mat("#1C2129", { r: .7 });
    for (const z of [9.4, 12.8]) { this._caixa(12, .42, .95, m, -16.2, .25, z + .05, this.cena); this._caixa(12, .7, .16, enc, -16.2, .62, z + .56, this.cena); this._caixa(12, .03, .05, luz("#8796AA", .7), -16.2, .47, z - .42, this.cena, false); }
    this._caixa(4.2, .08, 1.2, mat("#2C3340", { r: .3, m: .6 }), -16.2, .42, 11.1, this.cena);
  }

  // ---------- infraestrutura: servidores com farol por corretora e cofre das contas (clicaveis)
  _infra() {
    this.torres = {};
    [["OKX", 24.2, -1.5, "#DCE6F2"], ["Bybit", 24.2, 5.5, "#F2C96B"]].forEach(([k, x, z, cor]) => {
      const t = new THREE.Group(); t.position.set(x, 0, z); this.cena.add(t); t.userData.leds = [];
      for (let i = 0; i < 3; i++) { this._caixa(.95, 2.7, .95, mat("#10141A", { m: .75, r: .35 }), 0, 1.35, (i - 1) * 1.08, t);
        for (let j = 0; j < 8; j++) { const led = new THREE.Mesh(new THREE.BoxGeometry(.02, .035, .62), luz("#2A3A52")); led.position.set(-.49, .45 + j * .28, (i - 1) * 1.08); t.add(led); t.userData.leds.push(led); } }
      const farol = new THREE.Mesh(new THREE.CylinderGeometry(.13, .13, 1, 16), luz("#4A5566")); farol.position.set(0, 3.3, 0); t.add(farol);
      this._caixa(.98, .05, 3.3, luz(cor, .9), 0, 2.74, 0, t, false);
      const c = document.createElement("canvas"); c.width = 256; c.height = 64; const g = c.getContext("2d"); g.font = "700 44px Inter, system-ui"; g.fillStyle = cor; g.textAlign = "center"; g.fillText(k.toUpperCase(), 128, 48);
      const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace;
      const pl = new THREE.Mesh(new THREE.PlaneGeometry(2.2, .55), new THREE.MeshBasicMaterial({ map: tx, transparent: true, toneMapped: false })); pl.rotation.y = -Math.PI / 2; pl.position.set(-.5, 3.05, 0); t.add(pl);
      const hit = new THREE.Mesh(new THREE.BoxGeometry(1.6, 3.6, 3.6), new THREE.MeshBasicMaterial({ visible: false })); hit.position.y = 1.8; hit.userData.acao = "corretora:" + k; t.add(hit);
      this.torres[k] = { g: t, farol };
    });
    // cofre das contas (dados privados cifrados): clicar abre ou fecha o cofre
    const cf = new THREE.Group(); cf.position.set(-23.6, 0, 5.2); this.cena.add(cf);
    this._caixa(1.9, 2.3, 1.7, mat("#161B23", { m: .8, r: .3 }), 0, 1.15, 0, cf);
    this._caixa(.05, 1.9, 1.35, mat("#232A35", { m: .8, r: .25 }), .96, 1.15, 0, cf, false);
    const roda = new THREE.Mesh(new THREE.TorusGeometry(.33, .05, 8, 28), luz(OURO)); roda.rotation.y = Math.PI / 2; roda.position.set(1.0, 1.2, 0); cf.add(roda); this.cofreRoda = roda;
    this.cofreLuz = this._caixa(.04, .08, .5, luz("#F0616D"), .99, 1.95, 0, cf, false);
    const hit = new THREE.Mesh(new THREE.BoxGeometry(2.2, 2.6, 2), new THREE.MeshBasicMaterial({ visible: false })); hit.position.y = 1.3; hit.userData.acao = "cofre"; cf.add(hit);
    this._textoChao("COFRE DAS CONTAS", OURO, -24.6, 6.7, 3.6, .8);
  }

  // ---------- dados: estados, metricas, ecras e encaminhamentos reais
  atualizar({ estados = {}, colaboracoes = [], ligacoes = {}, cofreAberto = false } = {}) {
    this.estados = estados; let livre = 0;
    for (const a of AGENTES) {
      const A = this.agentes[a.id]; if (!A) continue;
      const st = estados[a.id] || { estado: "desligado" }, E = ESTADOS[st.estado] || ESTADOS.desligado;
      A.st = st; A.s.anel.material.color.set(E.cor); A.p.visor.material.color.set(st.estado === "desligado" ? "#2A3140" : E.cor);
      A.p.farol.material.color.set(st.ligado === false ? "#F0616D" : "#3FD68F");
      const on = !["desligado", "erro"].includes(st.estado);
      A.s.mons.forEach((m, i) => m.material.color.set(on ? (i === 1 ? "#FFFFFF" : "#AEBBCB") : "#232934"));
      A.p.corpo.color.set(st.estado === "desligado" ? "#252A33" : "#3A414E"); A.p.peito.material.color.set(st.estado === "desligado" ? "#2A3140" : a.cor);
      if (A.tag) { A.tag.dataset.estado = st.estado; A.tag.querySelector("i").style.background = E.cor; A.tag.title = `${a.nome} — ${E.nome}: ${st.atividade || ""}`;
        const m = A.tag.querySelector(".m"), mt = st.metrica || {}; m.textContent = mt.txt || E.nome; m.dataset.tom = mt.tom || ""; }
      // lugar segundo o estado real: em espera vai para o standby (se houver assento), o resto fica na estacao
      const quer = (st.estado === "espera" || st.estado === "cifrado") && livre < STANDBY.length ? "standby" : "estacao";
      const assento = quer === "standby" ? livre++ : null;
      if (quer !== A.lugar || assento !== A.assento) {
        const alvo = quer === "standby" ? new THREE.Vector3(STANDBY[assento][0], 0, STANDBY[assento][1]) : A.casa.clone();
        A.lugar = quer; A.assento = assento; A.posto = alvo;
        if (this._primeira || document.hidden) { A.p.g.position.copy(alvo); A.p.g.rotation.y = 0; A.andar = null; }
        else A.mudar = true;
      }
      if (!A.posto) A.posto = A.casa.clone();
    }
    this._primeira = false;
    for (const [k, T] of Object.entries(this.torres)) { const l = ligacoes[k] || "falhou"; T.estado = l;
      T.farol.material.color.set(l === "ligado" ? "#3FD68F" : l === "ligado_publico" ? CIANO : l === "falhou" ? "#F0616D" : OURO); }
    this.cofreLuz.material.color.set(cofreAberto ? "#3FD68F" : "#F0616D");
    for (const c of colaboracoes.slice().sort((a, b) => a.t - b.t)) { const k = `${c.de}>${c.para}@${c.t}`; if (this.vistos.has(k)) continue; this.vistos.add(k); if (this.agentes[c.de]) this.fila.push(c); }
    this.redesenharEcras();
  }

  redesenharEcras() {
    if (!this.desenharEcra) return;
    for (const e of this.ecras) { const c = e.tex.userData.c, g = c.getContext("2d"); try { this.desenharEcra(e, g, c.width, c.height); } catch (_) { g.fillStyle = "#0A0D12"; g.fillRect(0, 0, c.width, c.height); } e.tex.needsUpdate = true; }
  }

  destacar(id) { const A = this.agentes[id]; if (A) A.destaque = 3; }

  // ---------- circulacao pelos corredores
  _corr(p) { return p.z < -2 ? CORREDOR.norte : CORREDOR.sul; }
  _caminho(a, b, viaA, viaB) {
    const pts = [a.clone()], ca = this._corr(a), cb = this._corr(b);
    if (viaA) pts.push(viaA.clone());
    const xa = (viaA || a).x, xb = (viaB || b).x;
    pts.push(new THREE.Vector3(xa, 0, ca));
    if (ca !== cb) { const mx = (xa + xb) / 2, px = CORREDOR.passagens.reduce((m, x) => Math.abs(x - mx) < Math.abs(m - mx) ? x : m); pts.push(new THREE.Vector3(px, 0, ca), new THREE.Vector3(px, 0, cb)); }
    pts.push(new THREE.Vector3(xb, 0, cb)); if (viaB) pts.push(viaB.clone()); pts.push(b.clone());
    return pts;
  }
  _destino(para) {
    if (para === "centro") return { p: new THREE.Vector3(-.6, 0, 6.2), via: null };
    const B = this.agentes[para]; if (!B) return null;
    return { p: B.casa.clone().add(new THREE.Vector3(1.5, 0, .9)), via: null };
  }
  _visita(c) {
    const A = this.agentes[c.de], d = this._destino(c.para); if (!A || !d || A.andar) return false;
    const de = A.p.g.position.clone(); de.y = 0;
    const ida = this._caminho(de, d.p, A.lugar === "estacao" ? A.via : null, d.via);
    A.andar = { pts: ida, i: 0, fase: "ida", espera: 0, volta: null, visita: true };
    this._feixe(de, d.p, A.def.cor); A.destaque = 4; return true;
  }
  _feixe(a, b, cor) {
    const meio = a.clone().add(b).multiplyScalar(.5); meio.y = 3.2 + a.distanceTo(b) * .07;
    const curva = new THREE.QuadraticBezierCurve3(a.clone().setY(1.7), meio, b.clone().setY(1.7));
    const m = new THREE.Mesh(new THREE.TubeGeometry(curva, 40, .03, 6, false), new THREE.MeshBasicMaterial({ color: cor, transparent: true, opacity: .9, toneMapped: false, depthWrite: false }));
    const pulso = new THREE.Mesh(new THREE.SphereGeometry(.15, 12, 8), luz("#FFFFFF")); this.cena.add(m, pulso); this.feixes.push({ m, pulso, curva, t: 0 });
  }

  _animar(dt, t) {
    this._fAt = (this._fAt || 0) - dt;
    if (this.fila.length && this._fAt <= 0 && Object.values(this.agentes).filter(a => a.andar && a.andar.visita).length < 2) { const c = this.fila.shift(); if (this._visita(c)) this._fAt = 5; }
    for (const f of this.feixes) { f.t += dt / 2.2; f.pulso.position.copy(f.curva.getPoint(Math.min(1, f.t))); f.m.material.opacity = Math.max(0, .9 - Math.max(0, f.t - 1) * .9); }
    this.feixes.filter(f => f.t > 2).forEach(f => { this.cena.remove(f.m, f.pulso); f.m.geometry.dispose(); }); this.feixes = this.feixes.filter(f => f.t <= 2);
    const vel = 3.4;
    for (const A of Object.values(this.agentes)) {
      const P = A.p, st = (A.st || {}).estado || "espera", ph = A.fase + t;
      if (A.mudar && !A.andar) { A.mudar = false; const de = P.g.position.clone(); de.y = 0;
        A.andar = { pts: this._caminho(de, A.posto, A.lugar === "standby" ? A.via : null, A.lugar === "estacao" ? A.via : null), i: 0, fase: "mudanca" }; }
      if (A.andar) {
        const W = A.andar;
        if (W.fase === "espera") { W.espera -= dt; P.bracos[1].rotation.x = -.9 + Math.sin(t * 3) * .2; P.cab.rotation.y = Math.sin(t * 1.5) * .3;
          if (W.espera <= 0) { const de = P.g.position.clone(); de.y = 0; W.pts = this._caminho(de, A.posto, null, A.lugar === "estacao" ? A.via : null); W.i = 0; W.fase = "volta"; } }
        else {
          const alvo = W.pts[Math.min(W.i + 1, W.pts.length - 1)], pos = P.g.position, d = alvo.clone().sub(pos); d.y = 0;
          if (d.length() < .08) { W.i++; if (W.i >= W.pts.length - 1) { if (W.fase === "ida") { W.fase = "espera"; W.espera = 4; } else { pos.copy(A.posto); P.g.rotation.y = 0; A.andar = null; P.pernas.position.y = 0; P.pernas.rotation.x = 0; } } }
          else { pos.add(d.normalize().multiplyScalar(Math.min(d.length(), vel * dt))); P.g.rotation.y = Math.atan2(-d.x, -d.z); }
          if (A.andar) { pos.y = .12 + Math.abs(Math.sin(t * 9)) * .05; P.pernas.position.y = .1; P.bracos.forEach((b, i) => { b.rotation.x = Math.sin(t * 9 + i * Math.PI) * .5 + .4; }); P.cab.rotation.set(0, 0, 0); }
        }
        continue;
      }
      P.g.position.y = 0;
      const ativo = (ESTADOS[st] || {}).ativo && A.lugar === "estacao";
      if (st === "desligado") { P.cab.rotation.set(.38, 0, 0); P.tronco.rotation.x = .1; P.bracos.forEach(b => { b.rotation.x = .9; }); A.s.anel.material.opacity = .35; continue; }
      P.tronco.rotation.x = 0;
      if (ativo && ["analisar", "calcular", "procurar"].includes(st)) { P.bracos.forEach((b, i) => { b.rotation.x = Math.sin(ph * 14 + i * 2.1) * .07; }); P.cab.rotation.set(.08, Math.sin(ph * .7) * (st === "procurar" ? .5 : .22), 0); }
      else if (ativo && (st === "monitorizar" || st === "risco")) { P.bracos.forEach((b, i) => { b.rotation.x = i ? Math.sin(ph * 6) * .05 : .15; }); P.cab.rotation.set(.05, Math.sin(ph * .45) * .6, 0); }
      else if (ativo && st === "comunicar") { P.cab.rotation.set(0, Math.sin(ph * .9) * .3, 0); P.bracos[1].rotation.x = -.5 + Math.sin(ph * 2.2) * .35; P.bracos[0].rotation.x = 0; }
      else if (st === "erro") { P.cab.rotation.set(0, Math.sin(ph * 3) * .25, 0); P.bracos.forEach(b => { b.rotation.x = -.2; }); }
      else { P.cab.rotation.set(-.06, Math.sin(ph * .25) * .14, 0); P.bracos.forEach(b => { b.rotation.x = .6; }); P.tronco.rotation.x = -.05 + Math.sin(ph * 1.1) * .01; }
      A.destaque = Math.max(0, (A.destaque || 0) - dt);
      const pulso = st === "erro" ? .5 + .5 * Math.sin(t * 6) : A.destaque > 0 ? .6 + .4 * Math.sin(t * 10) : ativo ? .78 + .22 * Math.sin(ph * 2) : .5;
      A.s.anel.material.opacity = pulso; A.s.anel.scale.setScalar(A.destaque > 0 ? 1.15 : 1);
    }
    if (this.holo) { this.holo.rotation.y += dt * .25; this.holoAneis[0].rotation.z += dt * .4; this.holoAneis[1].rotation.z -= dt * .3; }
    for (const T of Object.values(this.torres)) T.g.userData.leds.forEach((l, i) => { const ok = T.estado === "ligado" || T.estado === "ligado_publico";
      l.material.color.set(ok ? (Math.sin(t * 2 + i * 1.7) > .2 ? "#3FD68F" : "#1E5A43") : T.estado === "falhou" ? "#5A1E24" : "#5A4A1E"); });
  }

  _etiquetas() {
    const w = this.el.clientWidth, h = this.el.clientHeight, v = new THREE.Vector3(), z = this.cam.zoom;
    for (const A of Object.values(this.agentes)) {
      if (!A.tag) continue;
      A.p.g.getWorldPosition(v); v.y += 2.55; v.project(this.cam);
      const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h, vis = v.z < 1 && x > -40 && x < w + 40 && y > -20 && y < h + 20;
      A.tag.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`; A.tag.style.display = vis ? "" : "none";
      A.tag.classList.toggle("compacta", z * h / 52 * 5.5 < 70 || (A.lugar === "standby" && z < 1.5 && !A.andar)); A.tag.classList.toggle("sel", this.selecionado === A.def.id);
    }
  }

  _loop() {
    if (this.parado || this._destruido) return;
    requestAnimationFrame(() => this._loop());
    const agora = performance.now(), lim = this.qualidade === "alta" ? 1000 / 60 : 1000 / 30;
    if (agora - this.ultimo < lim - 1) return;
    const dt = Math.min(.1, (agora - (this.ultimo || agora)) / 1000); this.ultimo = agora;
    this._animar(dt, this.relogio.getElapsedTime()); this.ctl.update(); this._focoTick(dt);
    if (this.comp) this.comp.render(); else this.R.render(this.cena, this.cam);
    this._etiquetas();
    this._fpsN++; if (agora - this._fpsT > 1000) { this.fps = Math.round(this._fpsN * 1000 / (agora - this._fpsT)); this._fpsN = 0; this._fpsT = agora; this._adaptar(); }
  }

  // ---------- detalhe adaptativo: se o aparelho nao aguenta, tira bloom e sombras e baixa a resolucao (os dados nao param)
  _adaptar() {
    this._lentos = this.fps < (this.qualidade === "alta" ? 24 : 14) ? (this._lentos || 0) + 1 : 0;
    if (this._lentos < 5) return; this._lentos = 0;
    if (this.qualidade === "alta") { this.qualidade = "baixa"; this.comp = null; this.R.shadowMap.enabled = false; this.R.setPixelRatio(Math.min(1.25, globalThis.devicePixelRatio || 1)); }
    else if (this.R.getPixelRatio() > .76) this.R.setPixelRatio(Math.max(.75, this.R.getPixelRatio() - .25));
    this.redimensionar(); if (this.onDegradar) this.onDegradar(this.qualidade);
  }

  // ---------- camara: foco numa area ou agente, regresso a vista geral, margens dos paineis
  focar(alvo) {
    this._interagiu = alvo !== "tudo"; let p = null, zoom = 1.9;
    if (this.agentes[alvo]) { p = this.agentes[alvo].p.g.position.clone(); zoom = 2.8; this.selecionado = alvo; }
    else if (alvo === "parede") { p = new THREE.Vector3(-4, 0, -9); zoom = 1.25; }
    else if (ZONAS[alvo]) { const z = ZONAS[alvo]; p = new THREE.Vector3((z.x[0] + z.x[1]) / 2, 0, (z.z[0] + z.z[1]) / 2); zoom = Math.max(1.5, Math.min(2.6, 30 / Math.max(z.x[1] - z.x[0], z.z[1] - z.z[0]))); }
    else if (alvo === "tudo") { p = new THREE.Vector3(0, 0, 0); zoom = this.zoomInteiro(); this.selecionado = null; this._az = true; }
    if (!p) return; p.y = 1.5;
    this._foco = { de: this.ctl.target.clone(), para: p, z0: this.cam.zoom, z1: zoom, t: 0 };
  }
  _focoTick(dt) {
    const F = this._foco; if (!F) return; F.t = Math.min(1, F.t + dt / .9); const k = F.t < .5 ? 2 * F.t * F.t : 1 - (-2 * F.t + 2) ** 2 / 2;
    const alvo = F.de.clone().lerp(F.para, k), mov = alvo.sub(this.ctl.target);
    this.ctl.target.add(mov); this.cam.position.add(mov); this.cam.zoom = F.z0 + (F.z1 - F.z0) * k; this.cam.updateProjectionMatrix();
    if (F.t >= 1) { this._foco = null; if (this._az) { this._az = false; const t = this.ctl.target; this.cam.position.set(t.x + 60, t.y + 52, t.z + 60); } }
  }
  margens(m) { this.m = { ...this.m, ...m }; this.redimensionar(); }
  zoomInteiro() {
    const w = this.el.clientWidth, h = this.el.clientHeight, vw = Math.max(200, w - this.m.esq - this.m.dir), vh = Math.max(160, h - this.m.topo - this.m.baixo);
    return Math.max(.3, Math.min(1.6, Math.min(vw * 52 / (62 * h), vh * 52 / (41 * h))));
  }
  redimensionar() {
    const w = this.el.clientWidth, h = this.el.clientHeight; if (!w || !h) return;
    const a = w / h, f = 26; Object.assign(this.cam, { left: -f * a, right: f * a, top: f, bottom: -f });
    this.cam.setViewOffset(w, h, -(this.m.esq - this.m.dir) / 2, -(this.m.topo - this.m.baixo) / 2, w, h);
    if (!this._interagiu && !this._foco) this.cam.zoom = this.zoomInteiro();
    this.cam.updateProjectionMatrix(); this.R.setSize(w, h, false); this.R.domElement.style.width = w + "px"; this.R.domElement.style.height = h + "px";
    if (this.comp) this.comp.setSize(w, h);
  }

  _clique(e) {
    const r = this.R.domElement.getBoundingClientRect();
    this.ptr.set((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(this.ptr, this.cam);
    for (const h of this.ray.intersectObjects(this.cena.children, true)) {
      let o = h.object; while (o && !o.userData.agente && !o.userData.zona && !o.userData.acao) o = o.parent;
      if (!o) continue;
      if (o.userData.agente) return this.onAgente(o.userData.agente);
      if (o.userData.acao) return this.onAcao(o.userData.acao);
      return this.onZona(o.userData.zona, o.userData.ecra);
    }
  }

  destruir() {
    this._destruido = true; this._ro.disconnect(); document.removeEventListener("visibilitychange", this._vis);
    this.cena.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) [].concat(o.material).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); }); });
    this.R.dispose(); this.R.domElement.remove(); this.overlay.remove();
  }
}
