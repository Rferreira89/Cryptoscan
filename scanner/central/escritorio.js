// CryptoScan · Operations Center — escritorio 3D de UM SO PISO (Three.js).
//
// Um espaco aberto, sem escadas nem outros pisos: centro de comando ao meio, mesa de operacoes, analise quantitativa,
// gestao de risco, monitorizacao das corretoras, zona de colaboracao e a parede de monitorizacao global a norte.
// Os agentes sao os do sistema (agentes.js); a animacao de cada um segue o estado REAL que publicou. Deslocacoes entre
// estacoes so acontecem quando ha um encaminhamento real (evento com hora) e cada um passa uma so vez.
// Os ecras sao desenhados com os dados reais (graficos.js); sem dados, mostram a indisponibilidade.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { AGENTES, ESTADOS } from "./agentes.js";

export const ZONAS = {
  comando:     { nome: "Centro de comando",              x: [-9, 9],    z: [-6.5, 6.5], cor: "#3EE0C4" },
  operacoes:   { nome: "Mesa de operações",              x: [-31, -11], z: [-17, -3],   cor: "#5AA9FF" },
  quant:       { nome: "Análise quantitativa",           x: [11, 31],   z: [-17, -3],   cor: "#B59CFF" },
  risco:       { nome: "Gestão de risco",                x: [-31, -11], z: [3, 17],     cor: "#F5B83D" },
  exchanges:   { nome: "Monitorização das corretoras",   x: [11, 31],   z: [3, 17],     cor: "#E6EDF7" },
  colaboracao: { nome: "Colaboração entre agentes",      x: [-9, 9],    z: [9, 18],     cor: "#7FE3FF" },
  global:      { nome: "Monitorização global",           x: [-31, 31],  z: [-20, -18],  cor: "#5AA9FF" },
};

// estacao de cada agente: posicao da cadeira e para onde olha (angulo em y)
const ESTACOES = {
  scanner:    { p: [-26, -12.5], r: Math.PI },  panico: { p: [-20, -12.5], r: Math.PI }, recuo: { p: [-14.5, -12.5], r: Math.PI },
  macro:      { p: [-18, -6.5],  r: Math.PI },
  arena:      { p: [16, -12.5],  r: Math.PI },  tfshort: { p: [23, -12.5], r: Math.PI },
  risco:      { p: [-24, 10],    r: 0 },        liquidez: { p: [-17, 10], r: 0 },
  exec_okx:   { p: [16.5, 10],   r: 0 },        exec_bybit: { p: [25, 10], r: 0 }, nucleo: { p: [25, 14.5], r: 0 },
  diretor:    { p: [0, 3.2],     r: 0 },
  noticias:   { p: [-5.5, 14.5], r: Math.PI / 2 },
};
const CENTRO = new THREE.Vector3(0, 0, 0);

const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: o.r ?? .55, metalness: o.m ?? .15, emissive: o.e ? c : 0x000000,
  emissiveIntensity: o.e || 0, transparent: o.op != null, opacity: o.op ?? 1, depthWrite: o.op == null || o.op > .6 });

export class Escritorio {
  constructor(el, { onAgente = () => {}, onZona = () => {}, qualidade = "auto", desenharEcra = null } = {}) {
    this.m = { esq: 0, dir: 0, topo: 0, baixo: 0 };
    this.el = el; this.onAgente = onAgente; this.onZona = onZona; this.desenharEcra = desenharEcra;
    this.qualidade = qualidade === "auto" ? Escritorio.qualidadeSugerida() : qualidade;
    this.agentes = {}; this.ecras = []; this.estados = {}; this.selecionado = null; this.fila = []; this.vistos = new Set();
    this.relogio = new THREE.Clock(); this.parado = false; this.ultimo = 0; this.fps = 0; this._fpsN = 0; this._fpsT = 0;
    this._iniciar();
  }

  static qualidadeSugerida() {
    const nav = globalThis.navigator || {}, mob = /Mobi|Android|iPhone|iPad/i.test(nav.userAgent || "");
    return mob || (nav.hardwareConcurrency || 8) <= 4 ? "baixa" : "alta";
  }

  _iniciar() {
    const alta = this.qualidade === "alta";
    const R = this.R = new THREE.WebGLRenderer({ antialias: alta, powerPreference: "high-performance", alpha: false });
    R.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, alta ? 2 : 1.25));
    R.outputColorSpace = THREE.SRGBColorSpace; R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.05;
    R.shadowMap.enabled = alta; R.shadowMap.type = THREE.PCFSoftShadowMap;
    this.el.appendChild(R.domElement); R.domElement.style.display = "block";
    const S = this.cena = new THREE.Scene(); S.background = new THREE.Color("#05080E"); S.fog = new THREE.Fog("#05080E", 90, 170);
    const w = this.el.clientWidth || 800, h = this.el.clientHeight || 600, a = w / h, f = 26;
    const C = this.cam = new THREE.OrthographicCamera(-f * a, f * a, f, -f, -200, 400);
    C.position.set(48, 46, 48); C.zoom = a < .9 ? .55 : .82; C.updateProjectionMatrix();
    const ctl = this.ctl = new OrbitControls(C, R.domElement);
    ctl.target.set(0, 0, 0); ctl.enableDamping = true; ctl.dampingFactor = .08; ctl.minZoom = .45; ctl.maxZoom = 4;
    ctl.addEventListener("start", () => { this._interagiu = true; }); ctl.minPolarAngle = .45; ctl.maxPolarAngle = 1.12; ctl.screenSpacePanning = true; ctl.update();
    ctl.addEventListener("change", () => { const t = ctl.target; t.x = Math.max(-30, Math.min(30, t.x)); t.z = Math.max(-20, Math.min(20, t.z)); t.y = 0; });
    this._luzes(); this._arquitetura(); this._zonas(); this._comando(); this._paredeGlobal(); this._colaboracao(); this._postosAgentes();
    if (alta) {
      this.comp = new EffectComposer(R); this.comp.addPass(new RenderPass(S, C));
      this.comp.addPass(new UnrealBloomPass(new THREE.Vector2(w / 2, h / 2), .55, .5, .82)); this.comp.addPass(new OutputPass());
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
    S.add(new THREE.HemisphereLight("#B4C8E4", "#101826", .95)); S.add(new THREE.AmbientLight("#40506A", .35));
    const sol = new THREE.DirectionalLight("#DDE8FF", 1.25); sol.position.set(30, 50, 22); sol.castShadow = this.qualidade === "alta";
    Object.assign(sol.shadow.camera, { left: -40, right: 40, top: 30, bottom: -30, near: 1, far: 140 }); sol.shadow.mapSize.set(2048, 2048); sol.shadow.bias = -.0004;
    S.add(sol);
    const azul = new THREE.DirectionalLight("#5AA9FF", .12); azul.position.set(-30, 20, -30); S.add(azul);
  }

  _caixa(w, h, d, m, x, y, z, pai = this.cena, sombra = true) {
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); b.position.set(x, y, z);
    b.castShadow = sombra && this.qualidade === "alta"; b.receiveShadow = this.qualidade === "alta"; pai.add(b); return b;
  }

  _arquitetura() {
    const S = this.cena;
    // laje unica, piso polido escuro com grelha subtil
    const chao = new THREE.Mesh(new THREE.PlaneGeometry(66, 42), new THREE.MeshStandardMaterial({ color: "#0B111B", roughness: .32, metalness: .45 }));
    chao.rotation.x = -Math.PI / 2; chao.receiveShadow = true; S.add(chao); this.chao = chao;
    const grelha = new THREE.GridHelper(66, 33, "#14243A", "#0F1A2A"); grelha.position.y = .005; grelha.material.transparent = true; grelha.material.opacity = .55; S.add(grelha);
    this._caixa(66.6, .5, 42.6, mat("#070B12"), 0, -.26, 0, S, false);
    // paredes baixas e vidro no perimetro (sem tapar a vista isometrica)
    const parede = mat("#101827", { r: .8 }), vidro = mat("#7FB7FF", { op: .08, r: .05, m: .9 });
    this._caixa(66, 4.2, .4, parede, 0, 2.1, -20.8, S);                  // norte (suporta a parede de ecras)
    this._caixa(.4, 4.2, 42, parede, -33, 2.1, 0, S);                    // oeste
    this._caixa(.15, 2.6, 42, vidro, 33, 1.3, 0, S, false);              // leste em vidro
    this._caixa(66, 1.1, .15, vidro, 0, .55, 20.9, S, false);            // sul (guarda baixa)
    // colunas e faixas de luz suspensas
    const col = mat("#141E2E", { r: .4, m: .5 });
    for (const x of [-22, 0, 22]) for (const z of [-19.6, 20.2]) this._caixa(.8, 4.4, .8, col, x, 2.2, z, S);
    // corredores (faixas mais claras no chao)
    const corr = mat("#0F1826", { r: .3, m: .5 });
    this._caixa(66, .02, 3.2, corr, 0, .012, 0, S, false); this._caixa(3.2, .02, 42, corr, 0, .013, 0, S, false);
    this._caixa(66, .02, 2.4, corr, 0, .012, -19, S, false);
  }

  _zonas() {
    this.zonaMesh = [];
    for (const [k, z] of Object.entries(ZONAS)) {
      if (k === "global") continue;
      const w = z.x[1] - z.x[0], d = z.z[1] - z.z[0], cx = (z.x[0] + z.x[1]) / 2, cz = (z.z[0] + z.z[1]) / 2;
      const c = new THREE.Color(z.cor);
      const tapete = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshStandardMaterial({ color: c.clone().multiplyScalar(.13), roughness: .6, metalness: .25 }));
      const pl = new THREE.PointLight(c, this.qualidade === "alta" ? 18 : 10, 18, 1.6); pl.position.set(cx, 5, cz); this.cena.add(pl);
      tapete.rotation.x = -Math.PI / 2; tapete.position.set(cx, .02, cz); tapete.receiveShadow = true; tapete.userData.zona = k; this.cena.add(tapete); this.zonaMesh.push(tapete);
      const pts = [[z.x[0], z.z[0]], [z.x[1], z.z[0]], [z.x[1], z.z[1]], [z.x[0], z.z[1]], [z.x[0], z.z[0]]].map(([x, y]) => new THREE.Vector3(x, .04, y));
      const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: .55 }));
      this.cena.add(ln);
      // nome da zona no chao, legivel na vista isometrica
      const tc = document.createElement("canvas"); tc.width = 1024; tc.height = 128; const tg = tc.getContext("2d");
      tg.font = "600 64px Inter, system-ui, sans-serif"; tg.fillStyle = z.cor; tg.globalAlpha = .85; tg.fillText(z.nome.toUpperCase(), 8, 86);
      const tt = new THREE.CanvasTexture(tc); tt.colorSpace = THREE.SRGBColorSpace;
      const rot = new THREE.Mesh(new THREE.PlaneGeometry(13, 1.6), new THREE.MeshBasicMaterial({ map: tt, transparent: true, depthWrite: false, toneMapped: false }));
      rot.rotation.order = "YXZ"; rot.rotation.set(-Math.PI / 2, Math.PI / 4, 0); rot.position.set(z.x[0] + 5.2, .05, z.z[1] - 1.4); this.cena.add(rot);
      // divisorias de vidro baixas no lado virado ao corredor
      if (k !== "comando" && k !== "colaboracao") {
        const vidro = mat(z.cor, { op: .06, r: .05, m: .9 }), zf = cz < 0 ? z.z[1] : z.z[0];
        this._caixa(w * .7, 1.2, .06, vidro, cx, .6, zf, this.cena, false);
      }
    }
  }

  // ---------- secretaria com 3 monitores; o monitor do meio tem textura de dados
  _secretaria(id, x, z, r, cor) {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = r; g.scale.setScalar(1.25); this.cena.add(g);
    const tampo = mat("#1A2433", { r: .35, m: .4 }), perna = mat("#0D131D", { m: .6 });
    this._caixa(3.4, .08, 1.5, tampo, 0, .78, -.9, g); this._caixa(.08, .76, 1.3, perna, -1.6, .38, -.9, g); this._caixa(.08, .76, 1.3, perna, 1.6, .38, -.9, g);
    const borda = new THREE.Mesh(new THREE.BoxGeometry(3.4, .03, .04), new THREE.MeshBasicMaterial({ color: cor, toneMapped: false })); borda.position.set(0, .8, -.15); g.add(borda);
    const tex = this._textura(512, 320), mons = [];
    [[-1.12, .32], [0, 0], [1.12, -.32]].forEach(([dx, ry], i) => {
      const m = new THREE.Group(); m.position.set(dx, 1.35, -1.35); m.rotation.y = ry; g.add(m);
      this._caixa(1.06, .66, .05, mat("#06090F", { r: .3, m: .6 }), 0, 0, -.03, m);
      const tela = new THREE.Mesh(new THREE.PlaneGeometry(1, .6), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
      tela.position.z = .002; m.add(tela); mons.push(tela);
      if (i !== 1) tela.material = new THREE.MeshBasicMaterial({ map: tex, toneMapped: false, color: "#B8C6D8" });
      this._caixa(.06, .4, .06, perna, 0, -.5, -.05, m);
    });
    // cadeira
    const cad = new THREE.Group(); cad.position.set(0, 0, .15); g.add(cad);
    this._caixa(.62, .1, .6, mat("#121A26"), 0, .5, 0, cad); this._caixa(.62, .75, .1, mat("#121A26"), 0, .95, .3, cad);
    this._caixa(.08, .46, .08, perna, 0, .24, 0, cad);
    // anel de estado no chao e indicador de ligacao
    const anel = new THREE.Mesh(new THREE.RingGeometry(.95, 1.08, 48), new THREE.MeshBasicMaterial({ color: "#8796AA", toneMapped: false, transparent: true, opacity: .85, side: THREE.DoubleSide }));
    anel.rotation.x = -Math.PI / 2; anel.position.set(0, .03, .2); g.add(anel);
    const zonaHit = new THREE.Mesh(new THREE.BoxGeometry(3.6, 2.2, 3), new THREE.MeshBasicMaterial({ visible: false }));
    zonaHit.position.set(0, 1.1, -.4); zonaHit.userData.agente = id; g.add(zonaHit);
    this.ecras.push({ id, tex, tipo: "agente" });
    return { g, cad, anel, mons, tex, hit: zonaHit };
  }

  _textura(w, h) {
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; t.userData.c = c; return t;
  }

  // ---------- figura humana estilizada (sentada), com bracos e cabeca animaveis
  _pessoa(cor) {
    const g = new THREE.Group();
    const roupa = mat(new THREE.Color(cor).multiplyScalar(.55).getStyle(), { r: .7 }), pele = mat("#C9A68A", { r: .8 }), escuro = mat("#161E2B", { r: .8 });
    const tronco = new THREE.Mesh(new THREE.CylinderGeometry(.24, .3, .72, 12), roupa); tronco.position.y = 1.02; g.add(tronco);
    const ombros = new THREE.Mesh(new THREE.SphereGeometry(.3, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2), roupa); ombros.position.y = 1.3; ombros.scale.set(1, .45, .8); g.add(ombros);
    const cab = new THREE.Group(); cab.position.y = 1.62; g.add(cab);
    const cabeca = new THREE.Mesh(new THREE.SphereGeometry(.19, 20, 14), pele); cab.add(cabeca);
    const cabelo = new THREE.Mesh(new THREE.SphereGeometry(.2, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2.1), escuro); cabelo.position.y = .02; cabelo.rotation.x = .25; cab.add(cabelo);
    const visor = new THREE.Mesh(new THREE.BoxGeometry(.26, .05, .03), new THREE.MeshBasicMaterial({ color: cor, toneMapped: false })); visor.position.set(0, .02, -.18); cab.add(visor);
    const bracos = [-1, 1].map(s => { const b = new THREE.Group(); b.position.set(s * .3, 1.28, 0); g.add(b);
      const sup = new THREE.Mesh(new THREE.CylinderGeometry(.07, .07, .42, 8), roupa); sup.position.set(0, -.18, -.08); sup.rotation.x = .5; b.add(sup);
      const ant = new THREE.Mesh(new THREE.CylinderGeometry(.06, .06, .4, 8), roupa); ant.position.set(0, -.34, -.34); ant.rotation.x = 1.45; b.add(ant);
      const mao = new THREE.Mesh(new THREE.SphereGeometry(.07, 8, 6), pele); mao.position.set(0, -.36, -.55); b.add(mao); return b; });
    const pernas = new THREE.Group(); g.add(pernas);
    [-1, 1].forEach(s => { const c = new THREE.Mesh(new THREE.BoxGeometry(.18, .16, .62), escuro); c.position.set(s * .13, .62, -.22); pernas.add(c);
      const p = new THREE.Mesh(new THREE.BoxGeometry(.16, .55, .16), escuro); p.position.set(s * .13, .3, -.52); pernas.add(p); });
    const luz = new THREE.Mesh(new THREE.SphereGeometry(.07, 12, 8), new THREE.MeshBasicMaterial({ color: cor, toneMapped: false })); luz.position.y = 2.05; g.add(luz);
    g.traverse(o => { if (o.isMesh) { o.castShadow = this.qualidade === "alta"; } });
    return { g, cab, bracos, pernas, tronco, luz, roupa };
  }

  _postosAgentes() {
    for (const a of AGENTES) {
      const e = ESTACOES[a.id]; if (!e) continue;
      const s = this._secretaria(a.id, e.p[0], e.p[1], e.r, a.cor);
      const p = this._pessoa(a.cor);
      p.g.position.set(0, 0, .15); s.g.add(p.g); p.g.userData.agente = a.id;
      p.g.traverse(o => { o.userData.agente = a.id; });
      const casa = new THREE.Vector3(); s.g.localToWorld(casa.set(0, 0, .15));
      this.agentes[a.id] = { def: a, s, p, casa: casa.clone(), fase: Math.random() * 6.28, andar: null, base: e };
    }
  }

  _etiqueta(a) {
    const d = document.createElement("button"); d.className = "of-tag"; d.type = "button";
    d.innerHTML = `<i></i><b>${a.nome}</b><span>${a.funcao.split(" · ")[0]}</span>`;
    d.addEventListener("click", ev => { ev.stopPropagation(); this.onAgente(a.id); });
    this.overlay.appendChild(d); const ag = this.agentes[a.id]; if (ag) ag.tag = d;
  }

  // ---------- centro de comando: mesa em anel, holograma e painel central de atividade e alertas
  _comando() {
    const g = new THREE.Group(); this.cena.add(g);
    const anel = new THREE.Mesh(new THREE.TorusGeometry(4.2, .55, 10, 64, Math.PI * 1.45), mat("#162133", { r: .3, m: .55 }));
    anel.rotation.x = -Math.PI / 2; anel.rotation.z = Math.PI * .275 + Math.PI; anel.position.y = .78; anel.scale.z = .25; anel.castShadow = this.qualidade === "alta"; g.add(anel);
    const borda = new THREE.Mesh(new THREE.TorusGeometry(4.75, .025, 6, 96, Math.PI * 1.45), new THREE.MeshBasicMaterial({ color: "#3EE0C4", toneMapped: false }));
    borda.rotation.copy(anel.rotation); borda.position.y = .82; g.add(borda);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.9, .5, 48), mat("#0E1622", { m: .6 })); base.position.y = .25; g.add(base);
    this.holo = new THREE.Group(); this.holo.position.y = 2.2; g.add(this.holo);
    const esfera = new THREE.Mesh(new THREE.IcosahedronGeometry(1.05, 2), new THREE.MeshBasicMaterial({ color: "#3EE0C4", wireframe: true, transparent: true, opacity: .35, toneMapped: false }));
    this.holo.add(esfera); this.holoEsfera = esfera;
    this.holoAneis = [1.45, 1.75].map((r, i) => { const t = new THREE.Mesh(new THREE.TorusGeometry(r, .015, 6, 96), new THREE.MeshBasicMaterial({ color: i ? "#5AA9FF" : "#3EE0C4", toneMapped: false, transparent: true, opacity: .8 }));
      t.rotation.x = Math.PI / 2 + (i ? .35 : -.2); this.holo.add(t); return t; });
    const feixe = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.5, 1.6, 32, 1, true), new THREE.MeshBasicMaterial({ color: "#3EE0C4", transparent: true, opacity: .06, side: THREE.DoubleSide, depthWrite: false, toneMapped: false }));
    feixe.position.y = 1.3; g.add(feixe);
    // painel central de atividade e alertas (ecra curvo a norte do anel)
    const tex = this._textura(1400, 520); this.texAtividade = tex;
    const geo = new THREE.CylinderGeometry(7.6, 7.6, 3.3, 48, 1, true, Math.PI * 1.03, Math.PI * .44);
    const tela = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, side: THREE.BackSide, toneMapped: false }));
    tela.position.set(1.3, 2.6, 1.3); tela.userData.zona = "comando"; g.add(tela); this.telaAtividade = tela;
    const moldura = new THREE.Mesh(new THREE.CylinderGeometry(7.68, 7.68, 3.45, 48, 1, true, Math.PI * 1.03, Math.PI * .44), mat("#0B111A", { m: .5 }));
    moldura.material.side = THREE.FrontSide; moldura.position.copy(tela.position); g.add(moldura);
    this.ecras.push({ id: "atividade", tex, tipo: "atividade" });
    // consolas do anel (corretoras) com textura de estado
    this.texCorretoras = this._textura(640, 360);
    const cons = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.35), new THREE.MeshBasicMaterial({ map: this.texCorretoras, toneMapped: false }));
    cons.position.set(0, 1.45, 4.55); cons.rotation.x = -.35; cons.rotation.y = Math.PI; g.add(cons);
    this.ecras.push({ id: "corretoras", tex: this.texCorretoras, tipo: "corretoras" });
  }

  _paredeGlobal() {
    const g = new THREE.Group(); this.cena.add(g);
    this.texGlobal = {};
    [["mapa", -18.5, 18, "mapa"], ["btc", 0, 15, "btc"], ["mercados", 18.5, 18, "mercados"]].forEach(([k, x, w, tipo]) => {
      const tex = this._textura(1280, 560); this.texGlobal[k] = tex;
      this._caixa(w + .4, 6.9, .2, mat("#05080D", { m: .6, r: .3 }), x, 3.95, -20.5, g);
      const tela = new THREE.Mesh(new THREE.PlaneGeometry(w, 6.5), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
      tela.position.set(x, 3.95, -20.38); tela.userData.zona = "global"; tela.userData.ecra = k; g.add(tela);
      this.ecras.push({ id: k, tex, tipo });
    });
  }

  _colaboracao() {
    const g = new THREE.Group(); g.position.set(1.5, 0, 13.5); this.cena.add(g);
    const mesa = new THREE.Mesh(new THREE.CylinderGeometry(2.6, 2.6, .08, 48), mat("#1A2433", { r: .3, m: .45 })); mesa.scale.z = .55; mesa.position.y = .76; mesa.castShadow = this.qualidade === "alta"; g.add(mesa);
    this._caixa(.4, .74, .4, mat("#0D131D"), 0, .37, 0, g);
    const tex = this._textura(1024, 480); this.texColab = tex;
    this._caixa(6.6, 3.2, .12, mat("#05080D"), 0, 2.1, 3.6, g);
    const tela = new THREE.Mesh(new THREE.PlaneGeometry(6.3, 2.95), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
    tela.position.set(0, 2.1, 3.53); tela.rotation.y = Math.PI; tela.userData.zona = "colaboracao"; g.add(tela);
    for (let i = 0; i < 6; i++) { const a = i / 6 * Math.PI * 2, c = new THREE.Group(); c.position.set(Math.cos(a) * 3.1, 0, Math.sin(a) * 1.75); g.add(c);
      this._caixa(.55, .08, .55, mat("#121A26"), 0, .5, 0, c); }
    this.ecras.push({ id: "colaboracao", tex, tipo: "colaboracao" });
    // racks de servidores e torres de estado das corretoras
    this.torres = {};
    [["OKX", 13.5, 15.5, "#E6EDF7"], ["Bybit", 29.5, 6, "#F7A600"]].forEach(([k, x, z, cor]) => {
      const t = new THREE.Group(); t.position.set(x, 0, z); this.cena.add(t);
      for (let i = 0; i < 2; i++) { this._caixa(.9, 2.4, .9, mat("#0C121C", { m: .7, r: .35 }), i * 1.05, 1.2, 0, t);
        for (let j = 0; j < 7; j++) { const led = new THREE.Mesh(new THREE.BoxGeometry(.6, .03, .02), new THREE.MeshBasicMaterial({ color: "#2A3A52", toneMapped: false })); led.position.set(i * 1.05, .4 + j * .3, .46); t.add(led); (t.userData.leds ||= []).push(led); } }
      const farol = new THREE.Mesh(new THREE.CylinderGeometry(.12, .12, .9, 16), new THREE.MeshBasicMaterial({ color: "#4A5566", toneMapped: false })); farol.position.set(.52, 2.95, 0); t.add(farol);
      this.torres[k] = { g: t, farol, cor };
    });
  }

  // ---------- dados: estados dos agentes, ecras e encaminhamentos reais
  atualizar({ estados = {}, colaboracoes = [], ligacoes = {} } = {}) {
    this.estados = estados;
    for (const [id, A] of Object.entries(this.agentes)) {
      const st = estados[id] || { estado: "desligado" }, E = ESTADOS[st.estado] || ESTADOS.desligado;
      A.st = st; A.s.anel.material.color.set(E.cor); A.p.luz.material.color.set(st.ligado === false ? "#F0616D" : E.cor);
      const on = !["desligado", "erro"].includes(st.estado);
      A.s.mons.forEach((m, i) => { m.material.color.set(on ? (i === 1 ? "#FFFFFF" : "#B8C6D8") : "#2A3140"); });
      const cinza = st.estado === "desligado";
      A.p.roupa.color.set(cinza ? "#2B3340" : new THREE.Color(A.def.cor).multiplyScalar(.55));
      if (A.tag) { A.tag.dataset.estado = st.estado; A.tag.querySelector("i").style.background = E.cor; A.tag.title = `${A.def.nome} — ${E.nome}: ${st.atividade || ""}`; }
    }
    for (const [k, T] of Object.entries(this.torres || {})) {
      const l = ligacoes[k] || "falhou", cor = l === "ligado" ? "#3FD68F" : l === "ligado_publico" ? "#3EE0C4" : l === "falhou" ? "#F0616D" : "#F5B83D";
      T.farol.material.color.set(cor); T.estado = l;
    }
    for (const c of colaboracoes.slice().sort((a, b) => a.t - b.t)) {
      const k = `${c.de}>${c.para}@${c.t}`; if (this.vistos.has(k)) continue; this.vistos.add(k);
      if (this.agentes[c.de]) this.fila.push(c);
    }
    this.redesenharEcras();
  }

  redesenharEcras() {
    if (!this.desenharEcra) return;
    for (const e of this.ecras) { const c = e.tex.userData.c, g = c.getContext("2d"); try { this.desenharEcra(e, g, c.width, c.height); } catch (err) { g.fillStyle = "#300"; g.fillRect(0, 0, c.width, c.height); } e.tex.needsUpdate = true; }
  }

  // ---------- caminhar ate outra estacao (so encaminhamentos reais), com regresso
  _destino(para) {
    if (para === "centro") return new THREE.Vector3(0, 0, 5.2);
    const B = this.agentes[para]; if (!B) return null;
    const v = new THREE.Vector3(); B.s.g.localToWorld(v.set(1.2, 0, .9)); return v;
  }
  _caminho(a, b) {
    const pts = [a.clone()], corr = new THREE.Vector3(a.x, 0, Math.sign(a.z || 1) * Math.min(Math.abs(a.z), 1.2));
    if (Math.abs(a.z) > 2) pts.push(new THREE.Vector3(a.x, 0, a.z > 0 ? 1.2 : -1.2));
    if (Math.abs(b.z) > 2) pts.push(new THREE.Vector3(b.x, 0, b.z > 0 ? 1.2 : -1.2));
    pts.push(b.clone()); void corr; return pts;
  }
  _iniciarDeslocacao(c) {
    const A = this.agentes[c.de], alvo = this._destino(c.para); if (!A || !alvo || A.andar) return false;
    const ida = this._caminho(A.casa, alvo);
    A.andar = { pts: ida, i: 0, fase: "ida", espera: 0, c, volta: ida.slice().reverse() };
    A.p.g.removeFromParent(); this.cena.add(A.p.g); A.p.g.position.copy(A.casa); A.p.g.rotation.y = A.base.r;
    this._feixe(A.casa, alvo, A.def.cor);
    if (this.onDeslocacao) this.onDeslocacao(c);
    return true;
  }
  _feixe(a, b, cor) {
    const meio = a.clone().add(b).multiplyScalar(.5); meio.y = 4 + a.distanceTo(b) * .08;
    const curva = new THREE.QuadraticBezierCurve3(a.clone().setY(1.6), meio, b.clone().setY(1.6));
    const geo = new THREE.TubeGeometry(curva, 40, .035, 6, false);
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: cor, transparent: true, opacity: .9, toneMapped: false, depthWrite: false }));
    this.cena.add(m); const pulso = new THREE.Mesh(new THREE.SphereGeometry(.16, 12, 8), new THREE.MeshBasicMaterial({ color: "#FFFFFF", toneMapped: false })); this.cena.add(pulso);
    (this.feixes ||= []).push({ m, pulso, curva, t: 0 });
  }

  _animar(dt, t) {
    // fila de encaminhamentos: no maximo 2 deslocacoes ao mesmo tempo, espacadas
    this._fAt = (this._fAt || 0) - dt;
    if (this.fila.length && this._fAt <= 0 && Object.values(this.agentes).filter(a => a.andar).length < 2) {
      const c = this.fila.shift(); if (this._iniciarDeslocacao(c)) this._fAt = 5; }
    for (const f of this.feixes || []) { f.t += dt / 2.2; const p = f.curva.getPoint(Math.min(1, f.t)); f.pulso.position.copy(p); f.m.material.opacity = Math.max(0, .9 - Math.max(0, f.t - 1) * .9); }
    (this.feixes || []).filter(f => f.t > 2).forEach(f => { this.cena.remove(f.m, f.pulso); f.m.geometry.dispose(); });
    this.feixes = (this.feixes || []).filter(f => f.t <= 2);
    const vel = 3.2;
    for (const A of Object.values(this.agentes)) {
      const P = A.p, st = (A.st || {}).estado || "espera", ph = A.fase + t;
      if (A.andar) {
        const W = A.andar;
        if (W.fase === "espera") { W.espera -= dt; P.bracos[1].rotation.x = -.9 + Math.sin(t * 3) * .2; if (W.espera <= 0) { W.fase = "volta"; W.pts = W.volta; W.i = 0; } }
        else {
          const alvo = W.pts[Math.min(W.i + 1, W.pts.length - 1)], pos = P.g.position, d = alvo.clone().sub(pos); d.y = 0;
          if (d.length() < .08) { W.i++; if (W.i >= W.pts.length - 1) { if (W.fase === "ida") { W.fase = "espera"; W.espera = 4; } else { P.g.removeFromParent(); A.s.g.add(P.g); P.g.position.set(0, 0, .15); P.g.rotation.y = 0; A.andar = null; P.pernas.position.y = 0; P.g.position.y = 0; } } }
          else { const passo = Math.min(d.length(), vel * dt); pos.add(d.normalize().multiplyScalar(passo)); P.g.rotation.y = Math.atan2(-d.x, -d.z); }
          P.g.position.y = .1 + Math.abs(Math.sin(t * 9)) * .05; P.pernas.position.y = .12;
          P.bracos.forEach((b, i) => { b.rotation.x = Math.sin(t * 9 + i * Math.PI) * .5 + .4; });
        }
        continue;
      }
      // sentado: animacao segundo o estado real
      const ativo = (ESTADOS[st] || {}).ativo;
      if (st === "desligado") { P.cab.rotation.x = .35; P.tronco.rotation.x = .12; P.bracos.forEach(b => { b.rotation.x = .9; }); continue; }
      P.tronco.rotation.x = 0;
      if (ativo && ["analisar", "calcular", "procurar"].includes(st)) {
        P.bracos.forEach((b, i) => { b.rotation.x = Math.sin(ph * 14 + i * 2.1) * .07; });
        P.cab.rotation.y = Math.sin(ph * .7) * (st === "procurar" ? .45 : .2); P.cab.rotation.x = .08;
      } else if (st === "monitorizar" || st === "risco") {
        P.bracos.forEach((b, i) => { b.rotation.x = i ? Math.sin(ph * 6) * .05 : .15; });
        P.cab.rotation.y = Math.sin(ph * .45) * .55; P.cab.rotation.x = .05;
      } else if (st === "comunicar") {
        P.cab.rotation.y = Math.sin(ph * .9) * .3; P.bracos[1].rotation.x = -.5 + Math.sin(ph * 2.2) * .35; P.bracos[0].rotation.x = 0;
      } else if (st === "erro") {
        P.cab.rotation.y = Math.sin(ph * 3) * .25; P.bracos.forEach(b => { b.rotation.x = -.2; });
      } else {   // espera / cifrado: recostado, respiracao lenta
        P.cab.rotation.y = Math.sin(ph * .25) * .12; P.cab.rotation.x = -.06; P.bracos.forEach(b => { b.rotation.x = .55; });
        P.tronco.rotation.x = -.06 + Math.sin(ph * 1.1) * .01;
      }
      const pulso = st === "erro" ? .5 + .5 * Math.sin(t * 6) : ativo ? .75 + .25 * Math.sin(ph * 2) : .55;
      A.s.anel.material.opacity = pulso; P.luz.scale.setScalar(ativo ? 1 + .15 * Math.sin(ph * 3) : 1);
    }
    if (this.holo) { this.holo.rotation.y += dt * .25; this.holoAneis[0].rotation.z += dt * .4; this.holoAneis[1].rotation.z -= dt * .3; }
    for (const T of Object.values(this.torres || {})) (T.g.userData.leds || []).forEach((l, i) => {
      const ok = T.estado === "ligado" || T.estado === "ligado_publico"; l.material.color.set(ok ? ((Math.sin(t * 2 + i * 1.7) > .2) ? "#3FD68F" : "#1E5A43") : T.estado === "falhou" ? "#5A1E24" : "#5A4A1E"); });
  }

  _etiquetas() {
    const w = this.el.clientWidth, h = this.el.clientHeight, v = new THREE.Vector3(), z = this.cam.zoom;
    for (const A of Object.values(this.agentes)) {
      if (!A.tag) continue;
      A.p.g.getWorldPosition(v); v.y += 2.45; v.project(this.cam);
      const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h, vis = v.z < 1 && x > -40 && x < w + 40 && y > -20 && y < h + 20;
      A.tag.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`; A.tag.style.display = vis ? "" : "none";
      A.tag.classList.toggle("compacta", z < .75); A.tag.classList.toggle("sel", this.selecionado === A.def.id);
    }
  }

  _loop() {
    if (this.parado || this._destruido) return;
    requestAnimationFrame(() => this._loop());
    const agora = performance.now(), lim = this.qualidade === "alta" ? 1000 / 60 : 1000 / 30;
    if (agora - this.ultimo < lim - 1) return;
    const dt = Math.min(.1, (agora - (this.ultimo || agora)) / 1000); this.ultimo = agora;
    const t = this.relogio.getElapsedTime();
    this._animar(dt, t); this.ctl.update(); this._focoTick(dt);
    if (this.comp) this.comp.render(); else this.R.render(this.cena, this.cam);
    this._etiquetas();
    this._fpsN++; if (agora - this._fpsT > 1000) { this.fps = Math.round(this._fpsN * 1000 / (agora - this._fpsT)); this._fpsN = 0; this._fpsT = agora; }
  }

  // ---------- navegacao
  focar(alvo) {
    this._interagiu = alvo !== "tudo";
    let p = null, zoom = 1.6;
    if (this.agentes[alvo]) { p = this.agentes[alvo].casa.clone(); zoom = 2.4; this.selecionado = alvo; }
    else if (ZONAS[alvo]) { const z = ZONAS[alvo]; p = new THREE.Vector3((z.x[0] + z.x[1]) / 2, 0, (z.z[0] + z.z[1]) / 2); zoom = alvo === "global" ? 1.25 : alvo === "comando" ? 1.9 : 1.75; if (alvo === "global") p.z = -14; }
    else if (alvo === "tudo") { p = CENTRO.clone(); zoom = this.zoomInteiro(); this.selecionado = null; }
    if (!p) return;
    this._foco = { de: this.ctl.target.clone(), para: p, z0: this.cam.zoom, z1: zoom, t: 0 };
  }
  _focoTick(dt) {
    const F = this._foco; if (!F) return; F.t = Math.min(1, F.t + dt / .9); const k = F.t < .5 ? 2 * F.t * F.t : 1 - (-2 * F.t + 2) ** 2 / 2;
    const d = F.para.clone().sub(F.de).multiplyScalar(k), alvo = F.de.clone().add(d), mov = alvo.clone().sub(this.ctl.target);
    this.ctl.target.add(mov); this.cam.position.add(mov); this.cam.zoom = F.z0 + (F.z1 - F.z0) * k; this.cam.updateProjectionMatrix();
    if (F.t >= 1) this._foco = null;
  }

  _clique(e) {
    const r = this.R.domElement.getBoundingClientRect();
    this.ptr.set((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(this.ptr, this.cam);
    const hits = this.ray.intersectObjects(this.cena.children, true);
    for (const h of hits) {
      let o = h.object; while (o && !o.userData.agente && !o.userData.zona) o = o.parent;
      if (!o) continue;
      if (o.userData.agente) { this.onAgente(o.userData.agente); return; }
      if (o.userData.zona) { this.onZona(o.userData.zona, o.userData.ecra); return; }
    }
  }

  margens(m) { this.m = { ...this.m, ...m }; this.redimensionar(); }
  zoomInteiro() {
    const w = this.el.clientWidth, h = this.el.clientHeight, vw = Math.max(200, w - this.m.esq - this.m.dir), vh = Math.max(160, h - this.m.topo - this.m.baixo);
    return Math.max(.35, Math.min(1.4, Math.min(vw * 52 / (80 * h), vh * 52 / (46 * h))));
  }
  redimensionar() {
    const w = this.el.clientWidth, h = this.el.clientHeight; if (!w || !h) return;
    const a = w / h, f = 26; Object.assign(this.cam, { left: -f * a, right: f * a, top: f, bottom: -f });
    const ox = (this.m.esq - this.m.dir) / 2, oy = (this.m.topo - this.m.baixo) / 2;
    this.cam.setViewOffset(w, h, -ox, -oy, w, h); this.cam.updateProjectionMatrix();
    if (!this._interagiu && !this._foco) { this.cam.zoom = this.zoomInteiro(); this.cam.updateProjectionMatrix(); }
    this.R.setSize(w, h, false); this.R.domElement.style.width = w + "px"; this.R.domElement.style.height = h + "px";
    if (this.comp) this.comp.setSize(w, h);
  }

  destruir() {
    this._destruido = true; this._ro.disconnect(); document.removeEventListener("visibilitychange", this._vis);
    this.cena.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) [].concat(o.material).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); }); });
    this.R.dispose(); this.R.domElement.remove(); this.overlay.remove();
  }
}
