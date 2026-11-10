// CryptoScan · Operations Center — graficos em canvas (velas, medias, volume, RSI, MACD, series, livro).
// Desenham so o que recebem; sem dados, desenham a indisponibilidade e a razao (nunca numeros de enfeite).
import { mm, rsi, macd } from "./dados.js";

export const COR = { fundo: "#070C14", grelha: "#132033", texto: "#C9D6E8", fraco: "#6F8199", sobe: "#3FD68F", desce: "#F0616D",
                     mm20: "#5AA9FF", mm50: "#F5B83D", acento: "#3EE0C4", violeta: "#B59CFF" };

const fmt = v => v == null || !isFinite(v) ? "–" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("pt-PT") : Number(v).toPrecision(5).replace(/\.?0+$/, "");

export function indisponivel(g, w, h, titulo, razao) {
  g.fillStyle = COR.fundo; g.fillRect(0, 0, w, h);
  g.strokeStyle = COR.grelha; g.setLineDash([6, 6]); g.strokeRect(8.5, 8.5, w - 17, h - 17); g.setLineDash([]);
  g.fillStyle = COR.texto; g.font = `600 ${Math.max(12, h / 16)}px Inter, system-ui, sans-serif`; g.textAlign = "center";
  g.fillText(titulo, w / 2, h / 2 - 6);
  g.fillStyle = COR.fraco; g.font = `${Math.max(10, h / 22)}px Inter, system-ui, sans-serif`;
  quebra(g, razao || "sem dados", w - 40).forEach((l, i) => g.fillText(l, w / 2, h / 2 + 18 + i * (h / 18)));
  g.textAlign = "left";
}

function quebra(g, t, max) {
  const out = []; let cur = "";
  for (const p of String(t).split(" ")) { const n = cur ? cur + " " + p : p; if (g.measureText(n).width > max && cur) { out.push(cur); cur = p; } else cur = n; }
  if (cur) out.push(cur); return out.slice(0, 3);
}

// painel completo: velas + MM20/MM50 + volume (+ RSI e MACD se houver altura)
export function velasCompleto(g, w, h, dados, { titulo = "", fonte = "", rsiOn = true, macdOn = true, linhas = [] } = {}) {
  const C = (dados || []).slice(-120);
  if (C.length < 30) return indisponivel(g, w, h, titulo || "Gráfico", "sem velas desta fonte");
  g.fillStyle = COR.fundo; g.fillRect(0, 0, w, h);
  const pad = 8, topo = 26, dir = 54;
  const hR = rsiOn ? h * .16 : 0, hM = macdOn ? h * .16 : 0, hV = h * .12;
  const hP = h - topo - hR - hM - hV - pad * 2;
  const x0 = pad, x1 = w - dir, bw = (x1 - x0) / C.length;
  const fechos = (dados || []).map(c => c.c), off = fechos.length - C.length;
  const m20 = mm(fechos, 20).slice(off), m50 = mm(fechos, 50).slice(off);
  let lo = Math.min(...C.map(c => c.l)), hi = Math.max(...C.map(c => c.h));
  for (const l of linhas) if (l.v != null) { lo = Math.min(lo, l.v); hi = Math.max(hi, l.v); }
  const y = v => topo + (hi - v) / (hi - lo || 1) * hP;
  g.strokeStyle = COR.grelha; g.lineWidth = 1; g.fillStyle = COR.fraco; g.font = "10px Inter, system-ui, sans-serif";
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4, yy = Math.round(y(v)) + .5; g.beginPath(); g.moveTo(x0, yy); g.lineTo(x1, yy); g.stroke(); g.fillText(fmt(v), x1 + 4, yy + 3); }
  C.forEach((c, i) => {
    const cx = x0 + i * bw + bw / 2, up = c.c >= c.o; g.strokeStyle = g.fillStyle = up ? COR.sobe : COR.desce;
    g.beginPath(); g.moveTo(cx, y(c.h)); g.lineTo(cx, y(c.l)); g.stroke();
    const yo = y(c.o), yc = y(c.c); g.fillRect(cx - Math.max(1, bw * .35), Math.min(yo, yc), Math.max(2, bw * .7), Math.max(1, Math.abs(yc - yo)));
  });
  const linha = (arr, cor, yf) => { g.strokeStyle = cor; g.lineWidth = 1.4; g.beginPath(); let on = false;
    arr.forEach((v, i) => { if (v == null) return; const xx = x0 + i * bw + bw / 2, yy = yf(v); if (!on) { g.moveTo(xx, yy); on = true; } else g.lineTo(xx, yy); }); g.stroke(); g.lineWidth = 1; };
  linha(m20, COR.mm20, y); linha(m50, COR.mm50, y);
  for (const l of linhas) if (l.v != null) {
    const yy = Math.round(y(l.v)) + .5; g.strokeStyle = l.cor; g.setLineDash([5, 4]); g.beginPath(); g.moveTo(x0, yy); g.lineTo(x1, yy); g.stroke(); g.setLineDash([]);
    g.fillStyle = l.cor; g.fillText(`${l.nome} ${fmt(l.v)}`, x0 + 4, yy - 3);
  }
  // volume
  const yV = topo + hP + pad, maxV = Math.max(...C.map(c => c.v)) || 1;
  C.forEach((c, i) => { g.fillStyle = (c.c >= c.o ? COR.sobe : COR.desce) + "66"; const hh = c.v / maxV * hV; g.fillRect(x0 + i * bw + 1, yV + hV - hh, Math.max(1, bw - 2), hh); });
  let yy = yV + hV + pad;
  if (rsiOn) {
    const r = rsi(fechos, 14).slice(off), yr = v => yy + (100 - v) / 100 * hR;
    g.strokeStyle = COR.grelha; [30, 70].forEach(v => { g.beginPath(); g.moveTo(x0, yr(v)); g.lineTo(x1, yr(v)); g.stroke(); });
    linha(r, COR.violeta, yr); g.fillStyle = COR.fraco; g.fillText(`RSI 14 ${fmt(r[r.length - 1])}`, x1 + 4, yy + 10); yy += hR + 2;
  }
  if (macdOn) {
    const M = macd(fechos), L = M.linha.slice(off), S = M.sinal.slice(off), H = M.hist.slice(off);
    const vals = [...L, ...S, ...H].filter(v => v != null), mx = Math.max(...vals.map(Math.abs)) || 1, ym = v => yy + hM / 2 - v / mx * (hM / 2);
    H.forEach((v, i) => { if (v == null) return; g.fillStyle = (v >= 0 ? COR.sobe : COR.desce) + "88"; const a = ym(0), b = ym(v); g.fillRect(x0 + i * bw + 1, Math.min(a, b), Math.max(1, bw - 2), Math.abs(b - a)); });
    linha(L, COR.mm20, ym); linha(S, COR.mm50, ym); g.fillStyle = COR.fraco; g.fillText("MACD 12/26/9", x1 + 4, yy + 10);
  }
  // cabecalho
  const u = C[C.length - 1], p0 = C[0].o, ch = (u.c / p0 - 1) * 100;
  g.fillStyle = COR.texto; g.font = "600 13px Inter, system-ui, sans-serif"; g.fillText(titulo, x0 + 2, 17);
  const tw = g.measureText(titulo).width;
  g.fillStyle = ch >= 0 ? COR.sobe : COR.desce; g.font = "12px Inter, system-ui, sans-serif"; g.fillText(`${fmt(u.c)}  ${ch >= 0 ? "+" : ""}${ch.toFixed(2)}% (janela)`, x0 + tw + 12, 17);
  g.fillStyle = COR.fraco; g.textAlign = "right"; g.fillText(`${fonte} · MM20 MM50`, w - 6, 17); g.textAlign = "left";
}

// serie simples (funding, OI): linha com zero, ultimo valor e titulo
export function serie(g, w, h, xs, ys, { titulo = "", unidade = "", cor = COR.acento, fonte = "", zero = false } = {}) {
  const pts = (ys || []).map((v, i) => [xs[i], v]).filter(p => p[1] != null);
  if (pts.length < 3) return indisponivel(g, w, h, titulo, "sem série para este ativo");
  g.fillStyle = COR.fundo; g.fillRect(0, 0, w, h);
  const pad = 10, topo = 24, x0 = pad, x1 = w - 56, y0 = topo, y1 = h - pad;
  let lo = Math.min(...pts.map(p => p[1])), hi = Math.max(...pts.map(p => p[1])); if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0], X = t => x0 + (t - t0) / (t1 - t0 || 1) * (x1 - x0), Y = v => y0 + (hi - v) / (hi - lo || 1) * (y1 - y0);
  g.strokeStyle = COR.grelha; for (let i = 0; i <= 3; i++) { const yy = y0 + (y1 - y0) * i / 3; g.beginPath(); g.moveTo(x0, yy); g.lineTo(x1, yy); g.stroke(); }
  if (zero && lo < 0 && hi > 0) { g.strokeStyle = COR.fraco; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x0, Y(0)); g.lineTo(x1, Y(0)); g.stroke(); g.setLineDash([]); }
  const grd = g.createLinearGradient(0, y0, 0, y1); grd.addColorStop(0, cor + "55"); grd.addColorStop(1, cor + "00");
  g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1]))); g.lineTo(X(t1), y1); g.lineTo(X(t0), y1); g.closePath(); g.fillStyle = grd; g.fill();
  g.strokeStyle = cor; g.lineWidth = 1.6; g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1]))); g.stroke(); g.lineWidth = 1;
  const u = pts[pts.length - 1][1];
  g.fillStyle = COR.texto; g.font = "600 12px Inter, system-ui, sans-serif"; g.fillText(titulo, x0, 16);
  g.fillStyle = cor; g.font = "12px Inter, system-ui, sans-serif"; g.fillText(`${fmt(u)}${unidade}`, x1 + 4, Y(u) + 4);
  g.fillStyle = COR.fraco; g.font = "10px Inter, system-ui, sans-serif"; g.textAlign = "right"; g.fillText(fonte, w - 6, 16); g.textAlign = "left";
}

// livro de ordens: profundidade acumulada dos dois lados
export function livroOrdens(g, w, h, L, { titulo = "Livro de ordens" } = {}) {
  if (!L || !L.bids) return indisponivel(g, w, h, titulo, (L && L.erro) || "indisponível");
  g.fillStyle = COR.fundo; g.fillRect(0, 0, w, h);
  const acc = a => { let s = 0; return a.map(([p, q]) => [p, (s += p * q)]); };
  const B = acc(L.bids), A = acc(L.asks), mx = Math.max(B[B.length - 1][1], A[A.length - 1][1]);
  const mid = (L.bids[0][0] + L.asks[0][0]) / 2, spread = (L.asks[0][0] - L.bids[0][0]) / mid * 100;
  const x0 = 10, x1 = w - 10, cx = (x0 + x1) / 2, y0 = 28, y1 = h - 18;
  const lado = (arr, sgn, cor) => { g.beginPath(); g.moveTo(cx, y1); arr.forEach(([, v], i) => g.lineTo(cx + sgn * (i + 1) / arr.length * (cx - x0), y1 - v / mx * (y1 - y0))); g.lineTo(cx + sgn * (cx - x0), y1); g.closePath(); g.fillStyle = cor + "44"; g.fill(); g.strokeStyle = cor; g.stroke(); };
  lado(B, -1, COR.sobe); lado(A, 1, COR.desce);
  g.fillStyle = COR.texto; g.font = "600 12px Inter, system-ui, sans-serif"; g.fillText(titulo, x0, 16);
  g.fillStyle = COR.fraco; g.font = "10px Inter, system-ui, sans-serif"; g.textAlign = "center";
  g.fillText(`meio ${fmt(mid)} · spread ${spread.toFixed(3)}% · ${L.fonte}`, cx, h - 4); g.textAlign = "left";
}

// tabela compacta para ecras 3D (texto grande, poucas linhas)
export function ecraTabela(g, w, h, titulo, linhas, { cor = COR.acento, rodape = "" } = {}) {
  g.fillStyle = "#060B12"; g.fillRect(0, 0, w, h);
  g.fillStyle = cor; g.fillRect(0, 0, w, 4);
  g.fillStyle = COR.texto; g.font = `700 ${h / 12}px Inter, system-ui, sans-serif`; g.fillText(titulo, 18, h / 8.2);
  const lh = (h - h / 5 - 26) / Math.max(6, linhas.length);
  linhas.slice(0, 9).forEach(([a, b, c], i) => {
    const yy = h / 5 + 14 + i * lh;
    g.fillStyle = "#0E1724"; if (i % 2 === 0) g.fillRect(10, yy - lh * .72, w - 20, lh * .95);
    g.font = `500 ${lh * .5}px Inter, system-ui, sans-serif`; g.fillStyle = COR.texto; g.fillText(String(a).slice(0, 30), 20, yy);
    g.textAlign = "right"; g.fillStyle = c || COR.fraco; g.fillText(String(b).slice(0, 34), w - 20, yy); g.textAlign = "left";
  });
  if (rodape) { g.fillStyle = COR.fraco; g.font = `${h / 26}px Inter, system-ui, sans-serif`; g.fillText(rodape, 18, h - 10); }
}
