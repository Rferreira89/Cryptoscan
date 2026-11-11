// CRYPTOSCAN ATLAS — centro de comando. Concept & Creative Direction — Rui.
// Carrega as fontes reais, calcula o contexto e alimenta o escritorio 3D e os paineis (operacoes, graficos, atividade,
// indicadores). So consulta e monitorizacao: nenhuma funcao envia, cancela, altera ou fecha ordens.
// O centro de comando nao depende do 3D: se o WebGL falhar, os paineis e os dados funcionam na mesma.
import * as Dd from "./dados.js";
import { AGENTES, AREAS, ESTADOS, estadosAgentes, colaboracoes } from "./agentes.js";
import * as Gx from "./graficos.js";

const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = (v, d = 2) => v == null || !isFinite(v) ? "–" : Number(v).toLocaleString("pt-PT", { minimumFractionDigits: d, maximumFractionDigits: d });
const px = v => v == null || !isFinite(v) ? "–" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("pt-PT") : Number(Number(v).toPrecision(5)).toLocaleString("pt-PT", { maximumSignificantDigits: 5 });
const hora = t => t ? new Date(t * 1000).toLocaleString("pt-PT", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }) : "–";
const hm = t => t ? new Date(t * 1000).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" }) : "–";
const sg = (v, d = 2) => v == null || !isFinite(v) ? "–" : (v > 0 ? "+" : "") + num(v, d);
const tom = v => v == null ? "" : v >= 0 ? "up" : "dn";
const agora = () => Date.now() / 1000;
const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} }, ler = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const amb = a => `<span class="amb ${a.toLowerCase()}">${a}</span>`;

const A = window.CS_APP = {
  res: {}, aberto: { cofreScan: null, cofreOkx: null }, ctx: null, velas: {}, sel: null, of: null, modo: "3d",
  f: { ambiente: "REAL", corretora: "todas", lado: "todos", estrategia: "todas", ativo: "", agente: "todos", nivel: "todos" },
  graf: { ativo: "BTC", iv: ler("atlas_iv") || "1h", rsi: true, macd: false }, ativ: "eventos",
};
const REFRESCO = { scan: 60, state: 120, okx: 120, cofreOkx: 120, cofreScan: 120, cfgOkx: 900, derivados: 600, liquidez: 900, tfshort: 1800, tfsombra: 1800 };

// ---------------------------------------------------------------- dados
async function carregar(chave) {
  const r = await Dd.obter(Dd.FONTES[chave].url, { tentativas: 3 }); r.pedido = agora();
  A.res[chave] = r;                                   // uma falha fica registada como falha: nunca se mostra a copia antiga como atual
  if (r.ok && Dd.FONTES[chave].cifrado) await abrirCofre(chave, false);
  return r;
}
async function abrirCofre(chave, pedir) {
  const r = A.res[chave]; if (!r || !r.ok || !window.CIFRA) return;
  const env = r.dados;
  if (!(env && env.cifra === "cs1")) { A.aberto[chave] = env; return; }
  if (!ler("cryptoscan_pw") && !pedir) { A.aberto[chave] = null; return; }
  try { A.aberto[chave] = await window.CIFRA.json(env); } catch (_) { A.aberto[chave] = null; }
}
async function obterVelas(at, iv = "1h") {
  const k = `${at}:${iv}`, v = A.velas[k];
  if (v && Date.now() - v.at < ({ "1h": 120e3, "4h": 600e3, "1d": 1800e3 }[iv])) return v;
  const r = await Dd.velas(at, { intervalo: iv }); r.at = Date.now(); A.velas[k] = r; return r;
}
// preco mais recente conhecido de um ativo, com a origem (nunca inventado)
function preco(ativo, pos) {
  if (pos && pos.atual) return { v: pos.atual, de: "corretora (cofre)" };
  const v = A.velas[ativo + ":1h"]; if (v && v.velas.length) return { v: v.velas[v.velas.length - 1].c, de: v.fonte };
  const u = (((A.res.scan || {}).dados || {}).universe || []).find(r => r.asset === ativo);
  return u ? { v: u.price, de: "scanner" } : { v: null, de: null };
}

function contexto() {
  const t = agora(), d = k => (A.res[k] && A.res[k].ok ? A.res[k].dados : null);
  const S = d("scan"), St = d("state"), O = d("okx"), cfgOkx = d("cfgOkx"), Dv = d("derivados"), L = d("liquidez"), T = d("tfshort"), Sb = d("tfsombra");
  const K = A.aberto.cofreOkx, P = A.aberto.cofreScan;
  const fontes = {}; for (const k of Object.keys(Dd.FONTES)) fontes[k] = Dd.estadoFonte(k, A.res[k], { aberto: A.aberto[k], agora: t });
  const okx = Dd.estadoOKX(A.res.okx, { res: A.res.cofreOkx, aberto: K }, t), bybit = Dd.estadoBybit(A.res.scan, { res: A.res.cofreScan, aberto: P }, t);
  const opOkx = Dd.okxOperacoes(O, K), opBy = Dd.bybitOperacoes(S, P);
  const recOkx = Dd.reconciliar(opOkx.posicoes, opOkx.ordens, !!K), recBybit = Dd.reconciliar(opBy.posicoes, [], !!P);
  const posicoes = [...opOkx.posicoes, ...opBy.posicoes], ordens = opOkx.ordens;
  for (const p of posicoes) { const pr = preco(p.ativo, p); p.preco = pr.v; p.preco_de = pr.de; p.R = Dd.rAtual(p, pr.v); }
  const eventos = Dd.eventos({ O, S, St, K });
  const estados = estadosAgentes({ fontes, O, S, St, Dv, T, cfgOkx, K, P, eventos }, t);
  const fr = Dd.fechadasR(O, S);
  const c = { t, S, St, O, cfgOkx, Dv, L, T, Sb, K, P, fontes, okx, bybit, opOkx, opBy, recOkx, recBybit, eventos, estados, posicoes, ordens, fr,
              frHoje: Dd.deHoje(fr, t), acum: Dd.acumulado(fr), simuladas: Dd.simuladas(O, S, T, Sb),
              fechadas: { okx: Dd.okxFechadas(O, K), bybit: opBy.fechadas }, estrategias: Dd.estrategias(cfgOkx, S, St),
              oportunidades: Dd.oportunidades(S, O), rejeicoes: Dd.rejeicoes(S), exposicao: Dd.exposicao(posicoes), pnl: Dd.pnl(K, P), colab: colaboracoes(eventos, t) };
  c.alertas = Dd.alertas({ okx, bybit, recOkx, recBybit, O, S, cfgOkx, agora: t });
  for (const a of AGENTES) estados[a.id].metrica = metrica(a.id, c);
  return c;
}

// numero-chave de cada agente para a etiqueta no escritorio (real; com tom so quando e um resultado)
function metrica(id, c) {
  const S = c.S || {}, O = c.O || {}, co = S.counts || {}, st = c.estados[id];
  if (st.estado === "erro") return { txt: "erro", tom: "dn" };
  if (st.estado === "desligado") return { txt: "desligado", tom: "" };
  switch (id) {
    case "scanner": return { txt: `${co.deep_checked ?? "–"} pares · ${(co.long || 0) + (co.short || 0)} sinais` };
    case "panico": return { txt: `${(O.resumo || {}).analisados ?? "–"} perpétuos` };
    case "recuo": return { txt: ((O.recuo || {}).resumo || {}).btc_em_subida ? "BTC em subida" : "regra inativa" };
    case "macro": return { txt: `${((O.macro || {}).resumo || {}).analisados ?? "–"} mercados` };
    case "liquidez": return { txt: `${Object.keys((c.Dv || {}).moedas || {}).length} moedas` };
    case "noticias": { const ev = S.next_event; return { txt: ev && ev.t > c.t ? `${String(ev.name).slice(0, 14)} · ${Math.round((ev.t - c.t) / 3600)} h` : "sem eventos" }; }
    case "arena": return { txt: `${(S.arena || {}).vivos ?? "–"} estratégias vivas` };
    case "tfshort": return { txt: `${Object.keys((((c.T || {}).sinais || {}).abertas) || {}).length} shorts · PAPEL` };
    case "risco": return { txt: `risco ${num(c.opOkx.posicoes.reduce((s, p) => s + (p.risco_pct || 0), 0))}%` };
    case "exec_okx": { if (c.K) return { txt: `${sg(c.K.pnl_aberto_usd)} USD`, tom: tom(c.K.pnl_aberto_usd) };
      const rs = c.opOkx.posicoes.map(p => p.R).filter(r => r != null), s = rs.reduce((a, b) => a + b, 0);
      return rs.length ? { txt: `${c.opOkx.posicoes.length} pos. · ${sg(s)}R`, tom: tom(s) } : { txt: `${c.opOkx.posicoes.length} posições` }; }
    case "exec_bybit": return { txt: `${c.opBy.posicoes.filter(p => !/núcleo/.test(p.estrategia)).length} posições` };
    case "nucleo": return { txt: c.P ? ((((c.P.nucleo || {}).plano || {}).BTC || {}).acima ? "comprado" : "fora") : "cofre fechado" };
    case "diretor": { const d = ((S.diretor || {}).decisoes || []).slice(-1)[0]; return { txt: d ? `${d.ativo} ${d.decisao === "AUTORIZADO" ? "✓" : "✗"}` : "sem decisões" }; }
  }
  return { txt: "" };
}

function estadoGlobal(c) {
  const crit = c.alertas.filter(a => a.nivel === "critico").length, av = c.alertas.filter(a => a.nivel === "aviso").length;
  const err = AGENTES.filter(a => c.estados[a.id].estado === "erro").length;
  if (c.okx.ligacao === "falhou" && c.bybit.ligacao === "falhou") return { k: "critico", t: "Sem ligação às corretoras" };
  if (crit || err) return { k: "critico", t: `${crit + err} problema(s)` };
  if (av) return { k: "aviso", t: `Operacional · ${av} aviso(s)` };
  return { k: "ok", t: "Operacional" };
}
const LIG = { ligado: ["ok", "Ligada"], ligado_publico: ["pub", "Ligada · conta cifrada"], atrasado: ["aviso", "Atrasada"], desatualizado: ["critico", "Desatualizada"], falhou: ["critico", "Sem ligação"] };
const CURTO = { ligado: "Ligada", ligado_publico: "Ligada 🔒", atrasado: "Atrasada", desatualizado: "Desatualizada", falhou: "Sem ligação" };
const nomeAg = id => id === "centro" ? "Command Center" : ((AGENTES.find(a => a.id === id) || {}).nome || id);

// ---------------------------------------------------------------- barra superior
function renderTopo(c) {
  const g = estadoGlobal(c), ag = AGENTES.map(a => c.estados[a.id].estado), at = ag.filter(e => (ESTADOS[e] || {}).ativo).length;
  const crit = c.alertas.filter(a => a.nivel === "critico").length, av = c.alertas.filter(a => a.nivel === "aviso").length;
  const chip = (acao, rot, val, k) => `<button class="chip ${k}" data-acao="${acao}"><i></i><span>${rot}</span><b>${esc(val)}</b></button>`;
  $("#estado").innerHTML = chip("ativ:alertas", "Sistema", g.t, g.k)
    + chip("ativ:scanners", "Agentes", `${at} ativos · ${ag.filter(e => e === "espera" || e === "cifrado").length} espera${ag.includes("erro") ? ` · ${ag.filter(e => e === "erro").length} erro` : ""}${ag.includes("desligado") ? ` · ${ag.filter(e => e === "desligado").length} desl.` : ""}`, ag.includes("erro") ? "critico" : ag.includes("desligado") ? "aviso" : "ok")
    + chip("corretora:OKX", "OKX", CURTO[c.okx.ligacao] + (c.okx.agente.idade != null ? ` · ${Dd.texIdade(c.okx.agente.idade).replace("há ", "")}` : ""), LIG[c.okx.ligacao][0])
    + chip("corretora:Bybit", "Bybit", CURTO[c.bybit.ligacao] + (c.bybit.agente.idade != null ? ` · ${Dd.texIdade(c.bybit.agente.idade).replace("há ", "")}` : ""), LIG[c.bybit.ligacao][0])
    + chip("ativ:alertas", "Alertas", crit ? `${crit} prioritário(s)` : av ? `${av} aviso(s)` : "nenhum", crit ? "critico" : av ? "aviso" : "ok");
  const cof = $("#cofre"), ab = !!(c.K || c.P); cof.textContent = ab ? "🔓 Cofre aberto" : "🔒 Abrir cofre"; cof.classList.toggle("on", ab);
}

// ---------------------------------------------------------------- indicadores financeiros (cada um com a origem; contas nunca somadas)
function renderFin(c) {
  const k = (rot, val, orig, t = "", acao = "ops") => `<button class="fin ${t}" data-acao="${acao}"><span>${rot}</span><b>${val}</b><small>${orig}</small></button>`;
  const rsO = c.opOkx.posicoes.map(p => p.R).filter(r => r != null), sO = rsO.reduce((a, b) => a + b, 0);
  const hojeR = c.frHoje.reduce((s, f) => s + f.R, 0), totR = c.fr.reduce((s, f) => s + f.R, 0);
  $("#fin").innerHTML =
    k("PnL realizado", c.K ? `${sg(c.pnl.okx_fechado_usd)} USD` : `${sg(totR)}R`, c.K ? "REAL · OKX · conta (30 últimas)" : `REAL · ${c.fr.length} fechadas · hoje ${sg(hojeR)}R`, tom(c.K ? c.pnl.okx_fechado_usd : totR), "ativ:resultado")
    + k("PnL não realizado", c.K ? `${sg(c.pnl.okx_aberto_usd)} USD` : rsO.length ? `${sg(sO)}R` : "–", c.K ? "REAL · OKX · conta" : "REAL · OKX · preço público", tom(c.K ? c.pnl.okx_aberto_usd : rsO.length ? sO : null))
    + k("Equity OKX", c.K ? `${num(c.pnl.okx_equity_usd)} USD` : "🔒", c.K ? `conta · ${Dd.texIdade(Dd.idade(c.K.t))}` : "cofre fechado", "", c.K ? "corretora:OKX" : "cofre")
    + k("Equity Bybit", c.P && c.P.conta ? `${num(c.pnl.bybit_equity_usd)} USD` : "🔒", c.P && c.P.conta ? `conta · ${Dd.texIdade(Dd.idade(c.P.conta.t))}` : "cofre fechado", "", c.P ? "corretora:Bybit" : "cofre")
    + k("Exposição", `${num(c.exposicao.risco_pct)}% risco`, c.exposicao.nominal_usd != null ? `nominal ${num(c.exposicao.nominal_usd)} USD · OKX` : "risco planeado das posições reais")
    + k("Posições", `${c.posicoes.length}`, `${c.opOkx.posicoes.length} OKX · ${c.opBy.posicoes.length} Bybit · ${c.ordens.length} ordens`)
    + k("LONG / SHORT", `${c.exposicao.long} / ${c.exposicao.short}`, "posições reais");
  const at = AGENTES.filter(a => (ESTADOS[c.estados[a.id].estado] || {}).ativo).length;
  $("#resumo-sala").textContent = `${at} em operação · ${AGENTES.filter(a => ["espera", "cifrado"].includes(c.estados[a.id].estado)).length} em espera`;
}

// ---------------------------------------------------------------- agentes
function renderAgentes(c) {
  $("#lista-agentes").innerHTML = AGENTES.map(a => {
    const s = c.estados[a.id], E = ESTADOS[s.estado] || ESTADOS.desligado, m = s.metrica || {};
    return `<button class="ag ${A.sel && A.sel.k === "agente" && A.sel.id === a.id ? "sel" : ""}" data-acao="agente:${a.id}" title="${esc(s.atividade || "")}">
      <i style="--c:${a.cor}">${esc(a.nome[0])}<u style="background:${s.ligado === false ? "var(--dn)" : "var(--up)"}"></u></i>
      <div><b>${esc(a.nome)}</b><small>${esc(AREAS[a.zona].nome)}</small></div>
      <div class="d"><em style="color:${E.cor}">${esc(E.nome)}</em><small class="${m.tom || ""}">${esc(m.txt || "")}</small></div></button>`; }).join("");
}

// ---------------------------------------------------------------- painel de operacoes
function barra(p) {
  const e = p.entrada || p.entrada_corretora; if (!e || !p.stop || !p.alvo || !p.preco) return "";
  const lo = Math.min(p.stop, p.alvo), hi = Math.max(p.stop, p.alvo), pos = v => Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100)), inv = p.lado === "SHORT";
  const f = v => inv ? 100 - pos(v) : pos(v);
  return `<div class="barra" title="stop ${px(p.stop)} · entrada ${px(e)} · objetivo ${px(p.alvo)}"><span class="ent" style="left:${f(e)}%"></span><span class="at ${tom(p.R)}" style="left:${f(p.preco)}%"></span></div>`;
}
function renderOps(c) {
  const F = A.f, el = $("#ops-corpo");
  $$("#ops-tabs button").forEach(b => { b.classList.toggle("on", b.dataset.amb === F.ambiente);
    b.querySelector("b").textContent = b.dataset.amb === "REAL" ? c.posicoes.length + c.ordens.length : c.simuladas.filter(s => s.ambiente === b.dataset.amb).length; });
  const filt = p => (F.corretora === "todas" || (p.corretora || p.origem || "").includes(F.corretora)) && (F.lado === "todos" || (p.lado || "LONG") === F.lado)
    && (F.estrategia === "todas" || (p.estrategia || p.origem) === F.estrategia) && (!F.ativo || p.ativo.toUpperCase().includes(F.ativo.toUpperCase()));
  const base = F.ambiente === "REAL" ? [...c.posicoes, ...c.ordens] : c.simuladas.filter(s => s.ambiente === F.ambiente);
  const est = [...new Set(base.map(p => p.estrategia || p.origem))];
  if (F.estrategia !== "todas" && !est.includes(F.estrategia)) F.estrategia = "todas";
  $("#ops-filtros").innerHTML = sel("corretora", ["todas", "OKX", "Bybit"]) + sel("lado", ["todos", "LONG", "SHORT"]) + sel("estrategia", ["todas", ...est])
    + `<input type="search" data-filtro="ativo" placeholder="ativo" value="${esc(F.ativo)}" aria-label="Filtrar por ativo">`;
  if (F.ambiente !== "REAL") {
    const L = base.filter(filt);
    el.innerHTML = L.length ? `<div class="tw"><table><tr><th>Ativo</th><th>Lado</th><th>Estratégia</th><th>Entrada</th><th>Stop</th><th></th></tr>${L.map(s => `<tr data-acao="ativo:${esc(s.ativo)}"><td><b>${esc(s.ativo)}</b></td><td class="${s.lado === "LONG" ? "up" : "dn"}">${s.lado}</td><td>${esc(s.origem)}</td><td>${px(s.entrada)}</td><td>${px(s.stop)}</td><td>${amb(s.ambiente)}</td></tr>`).join("")}</table></div>
      <p class="nota">${F.ambiente === "PAPEL" ? "Simulação ao vivo, sem dinheiro." : "O que a estratégia faria; sem ordens."} Nunca se soma ao real.</p>` : `<p class="nota">Sem posições em ${F.ambiente.toLowerCase()} com estes filtros.</p>`;
    return;
  }
  const P = c.posicoes.filter(filt), O = c.ordens.filter(filt);
  const rec = p => { const r = (p.corretora === "OKX" ? c.recOkx : c.recBybit); const i = r.itens.find(x => x.ativo === p.ativo); return r.estado === "por_verificar" ? ["", "por reconciliar (cofre fechado)"] : i && i.estado !== "confere" ? ["dn", i.texto] : ["up", "reconciliada com a corretora"]; };
  el.innerHTML = (P.length ? P.map(p => { const [rk, rt] = rec(p); return `<button class="pos ${A.sel && A.sel.k === "posicao" && A.sel.id === p.corretora + ":" + p.ativo ? "sel" : ""}" data-acao="posicao:${p.corretora}:${esc(p.ativo)}">
      <div class="l1"><b>${esc(p.ativo)}</b><span class="lado ${p.lado === "LONG" ? "up" : "dn"}">${p.lado}</span><span class="cx ${p.corretora.toLowerCase()}">${p.corretora}</span>${amb("REAL")}<span class="sp"></span>
        <strong class="${tom(p.pnl_usd ?? p.R)}">${p.pnl_usd != null ? sg(p.pnl_usd) + " USD" : p.R != null ? sg(p.R) + "R" : "–"}</strong></div>
      <div class="l2"><span>Entrada <b>${px(p.entrada || p.entrada_corretora)}</b></span><span>Atual <b>${px(p.preco)}</b></span><span>Stop <b class="dn">${px(p.stop)}</b></span><span>Objetivo <b class="up">${px(p.alvo)}</b></span></div>
      ${barra(p)}<div class="l3"><span>${esc(p.estrategia)}</span><span class="${rk}">● ${esc(rt)}</span>${p.corretora === "OKX" ? `<span class="${p.stop_confirmado ? "" : "dn"}">stop ${p.stop_confirmado ? "confirmado " + Dd.texIdade(Dd.idade(p.stop_confirmado)) : "por confirmar"}</span>` : ""}</div></button>`; }).join("") : `<p class="nota">Sem posições reais abertas${F.corretora !== "todas" ? " na " + F.corretora : ""}.</p>`)
    + `<h4>Ordens pendentes (${O.length})</h4>` + (O.length ? O.map(o => `<div class="ord"><b>${esc(o.ativo)}</b><span class="cx ${o.corretora.toLowerCase()}">${o.corretora}</span><span>limite ${px(o.preco || o.preco_corretora)}</span><span>stop ${px(o.stop)}</span><span>até ${hm(o.valida_ate)}</span>${o.cancelamento_pedido ? "<span class='dn'>cancelamento pedido</span>" : ""}</div>`).join("") : `<p class="nota">Nenhuma.</p>`)
    + `<h4>Execuções recentes</h4>` + lista([...c.fr].reverse().filter(f => F.corretora === "todas" || f.corretora === F.corretora).slice(0, 6).map(f => [`${f.corretora} ${f.ativo}`, `<span class="${tom(f.R)}">${sg(f.R)}R</span> · ${esc(f.estrategia)} · ${hora(f.t)}`]), "Sem operações fechadas.", true);
}
function sel(k, ops, rot = x => x) { return `<label>${k}<select data-filtro="${k}">${ops.map(o => `<option value="${esc(o)}" ${A.f[k] === o ? "selected" : ""}>${esc(rot(o))}</option>`).join("")}</select></label>`; }
function lista(rows, vazio, html = false, acoes = null) {
  if (!rows.length) return `<p class="nota">${esc(vazio)}</p>`;
  return `<ul class="lst">${rows.map(([a, b], i) => `<li ${acoes && acoes[i] ? `data-acao="${esc(acoes[i])}"` : ""}><b>${html ? a : esc(a)}</b><span>${html ? b : esc(b)}</span></li>`).join("")}</ul>`;
}

// ---------------------------------------------------------------- painel de graficos
function ativosGrafico(c) {
  const s = new Set(["BTC", "ETH", "SOL"]); c.posicoes.forEach(p => s.add(p.ativo)); c.ordens.forEach(p => s.add(p.ativo));
  c.oportunidades.slice(0, 8).forEach(o => s.add(o.ativo));
  ((c.S || {}).universe || []).slice().sort((a, b) => (b.volume_24h || 0) - (a.volume_24h || 0)).slice(0, 25).forEach(u => s.add(u.asset));
  s.add(A.graf.ativo); return [...s];
}
function ajustar(cv, h) { const w = cv.parentElement.clientWidth || 320; h = h || cv.parentElement.clientHeight || +cv.getAttribute("height") || 300; const d = Math.min(2, devicePixelRatio || 1);
  cv.width = w * d; cv.height = h * d; cv.style.width = w + "px"; cv.style.height = h + "px"; const g = cv.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0); return [g, w, h]; }
function linhasDe(c, at, velas) {
  const L = [], p = c.posicoes.find(x => x.ativo === at);
  if (p) L.push({ nome: "entrada", v: p.entrada || p.entrada_corretora, cor: "#DCE6F2" }, { nome: "stop", v: p.stop, cor: "#F0616D" }, { nome: "objetivo", v: p.alvo, cor: "#3FD68F" });
  else { const sr = Dd.suporteResistencia(velas); if (sr) L.push({ nome: `mín. ${sr.n} velas`, v: sr.suporte, cor: "#4F8CFF" }, { nome: `máx. ${sr.n} velas`, v: sr.resistencia, cor: "#4F8CFF" }); }
  return L;
}
async function renderGraf() {
  const c = A.ctx, G = A.graf; if (!c) return;
  $("#graf-ativo").innerHTML = ativosGrafico(c).map(a => `<option ${a === G.ativo ? "selected" : ""}>${esc(a)}</option>`).join("");
  $$("#graf-iv button").forEach(b => b.classList.toggle("on", b.dataset.iv === G.iv));
  $("#graf-rsi").classList.toggle("on", G.rsi); $("#graf-macd").classList.toggle("on", G.macd);
  const cv = $("#graf-cv"), pedido = `${G.ativo}:${G.iv}`; let [g, w, h] = ajustar(cv);
  if (!A.velas[pedido]) Gx.indisponivel(g, w, h, `${G.ativo} · a carregar velas…`, "OKX → Binance");
  const r = await obterVelas(G.ativo, G.iv); if (pedido !== `${A.graf.ativo}:${A.graf.iv}`) return;
  [g, w, h] = ajustar(cv);
  if (!r.velas.length) Gx.indisponivel(g, w, h, `${G.ativo}: gráfico indisponível`, r.erro);
  else Gx.velasCompleto(g, w, h, r.velas, { titulo: `${G.ativo} · ${G.iv.toUpperCase()}`, fonte: r.fonte, rsiOn: G.rsi, macdOn: G.macd, linhas: linhasDe(c, G.ativo, r.velas) });
  const dv = Dd.derivadosDe(c.Dv, G.ativo), lq = Dd.liquidezDe(c.L, G.ativo), atr = r.velas.length ? Dd.atrPct(r.velas) : null, ult = a => a.filter(x => x != null).slice(-1)[0];
  $("#graf-pe").innerHTML = `<span>Volatilidade <b>${atr == null ? "–" : num(atr) + "%"}</b></span><span>Funding <b>${dv ? num(ult(dv.funding), 4) + "%" : "–"}</b></span><span>OI <b>${dv ? num(ult(dv.oi), 0) + " M$" : "–"}</b></span><span>Spread <b>${lq ? num(lq.spread_pct, 3) + "%" : "–"}</b></span>
    <button data-acao="ativo:${esc(G.ativo)}:${G.iv}">Detalhe e livro de ordens</button>`;
}
function verAtivo(at, iv) { A.graf.ativo = at; if (iv) A.graf.iv = iv; renderGraf(); if (innerWidth <= 900) vistaMovel("graficos"); }

// ---------------------------------------------------------------- painel de atividade
function renderAtiv(c) {
  const el = $("#ativ-corpo"), t = A.ativ, S = c.S || {}, co = S.counts || {};
  $$("#ativ-tabs button").forEach(b => b.classList.toggle("on", b.dataset.ativ === t));
  if (t === "eventos") {
    const ev = c.eventos.filter(e => A.f.agente === "todos" || e.agente === A.f.agente || e.para === A.f.agente).slice(0, 60);
    el.innerHTML = `<div class="filtros">${sel("agente", ["todos", ...AGENTES.map(a => a.id)], id => id === "todos" ? "todos os agentes" : nomeAg(id))}</div>`
      + lista(ev.map(e => [hora(e.t), `<b class="quem">${esc(nomeAg(e.agente))}${e.para ? " → " + esc(nomeAg(e.para)) : ""}</b> ${esc(e.texto)}`]), "Sem eventos.", true, ev.map(e => `agente:${e.agente}`));
  } else if (t === "oportunidades") {
    el.innerHTML = lista(c.oportunidades.map(o => [`${o.ativo} ${o.lado}`, `${o.fonte}: ${o.texto}${o.perto ? " (ainda não é sinal)" : ""}`]), "Nenhuma oportunidade nesta passagem.", false, c.oportunidades.map(o => `oportunidade:${o.ativo}`));
  } else if (t === "sinais") {
    const rows = ((S.journal || {}).rows || []).slice(-25).reverse();
    el.innerHTML = `<div class="duas"><section><h4>Gerados (journal do motor)</h4>${lista(rows.map(r => [`${r.asset} ${r.side}`, `${r.strategy} · ${r.executed ? "executado" : "não executado"} · ${r.status} · ${hora(r.issued_at)} ${amb(r.mode === "REAL" ? "REAL" : "PAPEL")}`]), "Sem sinais no journal.", true, rows.map(r => `ativo:${r.asset}`))}
      <p class="nota">Nesta passagem: ${co.long ?? 0} LONG, ${co.short ?? 0} SHORT, ${(co.watchlist || 0) + (co.watch_short || 0)} a vigiar, ${co.no_trade ?? "–"} sem operação.</p></section>
      <section><h4>Rejeitados e motivos</h4>${lista(c.rejeicoes.map(r => [String(r.n), r.motivo]), "Sem rejeições registadas.")}</section></div>`;
  } else if (t === "alertas") {
    const al = c.alertas.filter(a => A.f.nivel === "todos" || a.nivel === A.f.nivel);
    el.innerHTML = `<div class="filtros">${sel("nivel", ["todos", "critico", "aviso", "info"])}</div>` + (al.length ? `<ul class="lst">${al.map((a, i) => `<li class="${a.nivel}" data-acao="alerta:${c.alertas.indexOf(a)}"><b>${esc(a.nivel.toUpperCase())}</b><span>${esc(a.texto)} <small>· ${esc(a.origem)}</small></span></li>`).join("")}</ul>` : `<p class="nota">Sem alertas.</p>`);
  } else if (t === "scanners") {
    const R = (c.O || {}).resumo || {}, MR = ((c.O || {}).macro || {}).resumo || {};
    el.innerHTML = `<div class="duas"><section><h4>Mercados e scanners</h4>${lista([
      ["Cripto global", `${co.moedas_descoberta_externa ?? co.pairs_seen ?? "–"} moedas de descoberta externa · ${co.pares_bybit_ue ?? "–"} pares na Bybit UE · ${Object.entries(S.sources || {}).map(([n, s]) => `${n} ${s.ok ? "✓" : "✗"}`).join(" ")}`],
      ["Bybit UE spot", `${(S.venue_source || {}).pairs ?? "–"} pares ${(S.venue_source || {}).ok ? "✓" : "✗"} · ${co.deep_checked ?? "–"}/${co.eligible ?? "–"} analisados`],
      ["OKX perpétuos", `${R.analisados ?? "–"} analisados · ${hora(R.t)}`], ["OKX ações, índices, metais", `${MR.analisados ?? "–"} analisados · ${(MR.abertas || []).length} em tendência ${amb("PAPEL")}`],
      ["Regime BTC", (S.market_regime || {}).btc || "–"]], "–", true)}</section>
      <section><h4>Agentes · próximas atualizações</h4>${lista(AGENTES.map(a => { const s = c.estados[a.id]; return [a.nome, `<span style="color:${ESTADOS[s.estado].cor}">${esc(ESTADOS[s.estado].nome)}</span>${s.t ? " · " + Dd.texIdade(s.idade) : ""}${s.proxima ? " · próxima " + hm(s.proxima) : ""}`]; }), "–", true, AGENTES.map(a => `agente:${a.id}`))}</section></div>`;
  } else if (t === "estrategias") {
    el.innerHTML = `<div class="tw"><table><tr><th>Estratégia</th><th>Corretora</th><th>Ambiente</th><th>Estado</th><th>Notas</th></tr>${c.estrategias.map((e, i) => `<tr data-acao="estrategia:${i}"><td><b>${esc(e.nome)}</b></td><td>${esc(e.corretora)}</td><td>${amb(e.dinheiro === "real" ? "REAL" : "PAPEL")}</td><td class="${e.ativa ? "up" : "dn"}">${e.ativa ? "ativa" : "suspensa"}</td><td>${esc(e.razao || "")}</td></tr>`).join("")}</table></div>`;
  } else if (t === "resultado") {
    el.innerHTML = `<div class="duas"><section><div class="graf fixo"><canvas id="cv-acum" height="150"></canvas></div></section><section>${lista([...c.fr].reverse().slice(0, 12).map(f => [`${f.corretora} ${f.ativo}`, `<span class="${tom(f.R)}">${sg(f.R)}R</span> · ${esc(f.estrategia)} · ${hora(f.t)} ${amb("REAL")}`]), "Sem operações reais fechadas.", true)}</section></div>`;
    const [g, w, h] = ajustar($("#cv-acum"), 150); Gx.serie(g, w, h, c.acum.map(x => x.t), c.acum.map(x => x.v), { titulo: `Resultado real acumulado (${c.fr.length} operações fechadas)`, unidade: "R", cor: "#E8B84A", fonte: "OKX + Bybit · público", zero: true });
  } else if (t === "fontes") {
    el.innerHTML = `<div class="tw"><table><tr><th>Fonte</th><th>Estado</th><th>Última atualização</th><th>Último pedido</th><th>Razão</th></tr>${Object.entries(c.fontes).map(([k, f]) => `<tr><td>${esc(Dd.FONTES[k].nome)}</td><td class="st-${f.estado}">${esc(f.estado)}</td><td>${f.t ? hora(f.t) + " (" + Dd.texIdade(f.idade) + ")" : "–"}</td><td>${hm((A.res[k] || {}).pedido)}${(A.res[k] || {}).tentativas > 1 ? ` (${A.res[k].tentativas} tentativas)` : ""}</td><td>${esc(f.razao || "")}</td></tr>`).join("")}</table></div>
      <small class="nota">As corretoras são lidas pelos agentes (chaves só nos segredos do GitHub); esta página lê o que eles publicam. ${A.of ? `3D ${A.of.qualidade} · ${A.of.fps} fps.` : "3D desligado."}</small>`;
  }
}

// ---------------------------------------------------------------- janela de detalhe (sobreposta ao escritorio)
function abrir(k, id, extra) { A.sel = { k, id, extra }; $("#detalhe").classList.add("on"); renderDetalhe(); if (A.ctx) { renderAgentes(A.ctx); if (k === "posicao") renderOps(A.ctx); }
  if (k === "agente" && A.of) { A.of.focar(id); A.of.destacar(id); } margens(); }
function fechar() { A.sel = null; $("#detalhe").classList.remove("on"); if (A.ctx) { renderAgentes(A.ctx); renderOps(A.ctx); } if (A.of) A.of.selecionado = null; margens(); }

function renderDetalhe() {
  const c = A.ctx, S = A.sel, el = $("#det-corpo"); if (!S || !c) return;
  const T = t => { $("#det-titulo").textContent = t; };
  if (S.k === "agente") {
    const a = AGENTES.find(x => x.id === S.id), s = c.estados[a.id], E = ESTADOS[s.estado];
    T(`${a.nome} · ${a.funcao}`);
    el.innerHTML = `<div class="badge" style="border-color:${E.cor};color:${E.cor}">● ${esc(E.nome)}</div>
      <dl><dt>Área</dt><dd>${esc(AREAS[a.zona].nome)}</dd><dt>Atividade</dt><dd>${esc(s.atividade || "–")}</dd>
      <dt>Última atividade</dt><dd>${s.t ? `${hora(s.t)} (${Dd.texIdade(s.idade)})` : "sem hora publicada"}</dd>
      <dt>Ligação</dt><dd>${s.ligado === false ? '<span class="dn">sem ligação</span>' : '<span class="up">ligado</span>'}</dd>
      ${s.proxima ? `<dt>Próxima passagem</dt><dd>${hora(s.proxima)}</dd>` : ""}<dt>Componente real</dt><dd><code>${esc(a.componente)}</code></dd></dl>
      <h4>Histórico recente (eventos reais)</h4>${lista(s.historico.map(e => [hora(e.t), e.texto]), "Sem eventos registados para este agente.")}
      <div class="acoes"><button data-acao="zona:${a.zona}">Ver a área</button><button data-acao="eventos:${a.id}">Todos os eventos</button></div>`;
  } else if (S.k === "corretora") {
    const ok = S.id === "OKX", ex = ok ? c.okx : c.bybit, ops = ok ? c.opOkx : c.opBy, rec = ok ? c.recOkx : c.recBybit, [lk, lt] = LIG[ex.ligacao], rk = ok ? "okx" : "scan";
    T(ok ? "OKX EEA · conta real" : "Bybit UE · conta real");
    const conta = ok
      ? (c.K ? `<div class="kv"><div><span>Equity</span><b>${num(c.K.equity_usd)} USD</b></div><div><span>Não realizado</span><b class="${tom(c.K.pnl_aberto_usd)}">${sg(c.K.pnl_aberto_usd)} USD</b></div><div><span>Realizado (30 últimas)</span><b class="${tom(c.K.pnl_fechado_usd)}">${sg(c.K.pnl_fechado_usd)} USD</b></div><div><span>Margem usada</span><b>${num((c.K.posicoes || []).reduce((s, p) => s + (p.margem_usd || 0), 0))} USD</b></div></div>
         <small class="nota">Saldos: ${(c.K.moedas || []).map(m => `${esc(m.ccy)} ${num(m.eq, 4)} (disponível ${num(m.disponivel, 4)})`).join(" · ") || "–"}</small>` : `<p class="nota">🔒 Equity, saldo, quantidades e PnL estão cifrados. <button data-acao="cofre">Abrir cofre</button></p>`)
      : (c.P && c.P.conta ? `<div class="kv"><div><span>Equity</span><b>${num(c.P.conta.equity)} USD</b></div><div><span>USDC disponível</span><b>${num(c.P.conta.usdc_free)}</b></div><div><span>Leitura</span><b>${Dd.texIdade(Dd.idade(c.P.conta.t))}</b></div></div>` : `<p class="nota">🔒 Equity e posições da Bybit estão cifrados. <button data-acao="cofre">Abrir cofre</button></p>`);
    el.innerHTML = `<div class="badge ${lk}">● ${esc(lt)}</div>${ex.razao ? `<p class="nota">${esc(ex.razao)}</p>` : ""}
      <dl><dt>Última passagem do agente</dt><dd>${ex.agente.t ? `${hora(ex.agente.t)} (${Dd.texIdade(ex.agente.idade)})` : "–"}</dd>
      <dt>Última leitura da conta</dt><dd>${ex.conta && ex.conta.t ? `${hora(ex.conta.t)} (${Dd.texIdade(ex.conta.idade)})` : ex.conta ? esc(ex.conta.razao || ex.conta.estado) : "–"}</dd>
      <dt>Último pedido desta página</dt><dd>${hora((A.res[rk] || {}).pedido)}${(A.res[rk] || {}).tentativas > 1 ? ` · ${A.res[rk].tentativas} tentativas` : ""}</dd></dl>${conta}
      <h4>Posições (${ops.posicoes.length})</h4>${lista(ops.posicoes.map(p => [`${p.ativo} ${p.lado}`, `${p.estrategia} · entrada ${px(p.entrada || p.entrada_corretora)} · stop ${px(p.stop)} · ${p.pnl_usd != null ? sg(p.pnl_usd) + " USD" : p.R != null ? sg(p.R) + "R" : "–"}`]), "Sem posições abertas.", false, ops.posicoes.map(p => `posicao:${p.corretora}:${p.ativo}`))}
      ${ok ? `<h4>Ordens pendentes (${ops.ordens.length})</h4>${lista(ops.ordens.map(o => [o.ativo, `limite ${px(o.preco || o.preco_corretora)} · até ${hora(o.valida_ate)}`]), "Nenhuma.")}` : `<h4>Sinais reais não executados (${ops.sinais_nao_executados.length})</h4>${lista(ops.sinais_nao_executados.map(s => [`${s.ativo} ${s.lado}`, `${s.estrategia} · ${s.motivo}`]), "Nenhum.")}`}
      <h4>Reconciliação com a corretora</h4>${rec.estado === "por_verificar" ? `<p class="nota">${esc(rec.razao)}</p>` : lista(rec.itens.map(i => [`<span class="${i.estado === "confere" ? "up" : "dn"}">${i.estado === "confere" ? "✓" : "✗"}</span> ${esc(i.ativo)}`, esc(i.texto)]), "Sem posições nem ordens para comparar.", true)}
      <h4>Histórico</h4>${ok && c.fechadas.okx.privado.length ? lista(c.fechadas.okx.privado.slice(0, 8).map(f => [f.ativo, `${px(f.entrada)} → ${px(f.saida)} · <span class="${tom(f.pnl_usd)}">${sg(f.pnl_usd)} USD</span> · ${hora(f.t)}`]), "", true) : ""}
      ${lista((ok ? c.fechadas.okx.publico : c.fechadas.bybit).slice(0, 10).map(h => [`${h.ativo}${h.estado ? " · " + h.estado : ""}`, `${h.motivo || h.estrategia || ""}${h.ret_pct != null ? ` · ${sg(h.ret_pct)}%` : ""}${h.R != null ? ` · ${sg(h.R)}R` : ""} · ${hora(h.t)}`]), "Sem histórico.")}`;
  } else if (S.k === "posicao") {
    const [cx, at] = S.id.split(":"), p = c.posicoes.find(x => x.corretora === cx && x.ativo === at);
    if (!p) { T(at); el.innerHTML = `<p class="nota">Esta posição já não está aberta.</p>`; return; }
    T(`${p.ativo} · ${p.lado} · ${p.corretora}`); const e = p.entrada || p.entrada_corretora;
    const ds = p.preco && p.stop ? Math.abs(p.preco / p.stop - 1) * 100 : null, da = p.preco && p.alvo ? Math.abs(p.alvo / p.preco - 1) * 100 : null;
    el.innerHTML = `${amb("REAL")} <span class="cx ${cx.toLowerCase()}">${cx}</span>
      <div class="kv"><div><span>Estratégia</span><b>${esc(p.estrategia)}</b></div><div><span>Instrumento</span><b>${esc(p.inst || p.ativo)}</b></div>
      <div><span>Quantidade</span><b>${p.quantidade != null ? num(p.quantidade, 4) : "🔒"}</b></div><div><span>Entrada</span><b>${px(e)}</b></div>
      <div><span>Preço atual</span><b>${px(p.preco)}</b><small>${esc(p.preco_de || "indisponível")}</small></div><div><span>Resultado</span><b class="${tom(p.R)}">${p.R == null ? "–" : sg(p.R) + "R"}</b></div>
      <div><span>Stop-loss</span><b class="dn">${px(p.stop)}</b><small>${ds == null ? "" : "a " + num(ds) + "%"}</small></div><div><span>Take-profit</span><b class="up">${px(p.alvo)}</b><small>${da == null ? "" : "a " + num(da) + "%"}</small></div>
      <div><span>PnL não realizado</span><b class="${tom(p.pnl_usd)}">${p.pnl_usd != null ? sg(p.pnl_usd) + " USD (" + sg(p.pnl_pct) + "%)" : "🔒"}</b></div>
      <div><span>Margem · alavancagem</span><b>${p.margem_usd != null ? num(p.margem_usd) + " USD · " : ""}${p.alav || "–"}x</b></div>
      <div><span>Risco planeado</span><b>${p.risco_pct != null ? num(p.risco_pct) + "% da conta" : "–"}</b></div><div><span>Liquidação</span><b>${px(p.liquidacao)}</b></div></div>${barra(p)}
      <dl><dt>Stop confirmado na corretora</dt><dd>${p.stop_confirmado ? `${hora(p.stop_confirmado)} (${Dd.texIdade(Dd.idade(p.stop_confirmado))})` : cx === "OKX" ? '<span class="dn">sem confirmação</span>' : "–"}</dd>
      <dt>Aberta desde</dt><dd>${hora(p.desde)}</dd>${p.sair_em ? `<dt>Saída por tempo</dt><dd>${hora(p.sair_em)}</dd>` : ""}<dt>Origem</dt><dd>${esc(p.fonte)}${p.parcial ? " · execução parcial" : ""}</dd></dl>
      <div class="acoes"><button data-acao="grafico:${esc(p.ativo)}">Ver no painel de gráficos</button><button data-acao="ativo:${esc(p.ativo)}">Análise do ativo</button></div>`;
    verAtivo(p.ativo);
  } else if (S.k === "ativo") {
    const at = S.id, dv = Dd.derivadosDe(c.Dv, at), lq = Dd.liquidezDe(c.L, at), u = ((c.S || {}).universe || []).find(r => r.asset === at), op = c.oportunidades.filter(o => o.ativo === at);
    T(`${at} · análise`);
    el.innerHTML = `${op.length ? `<h4>Oportunidade</h4>${lista(op.map(o => [o.lado, `${o.fonte}: ${o.texto}`]), "")}` : ""}
      <div class="kv">${u ? `<div><span>Preço (scanner)</span><b>${px(u.price)}</b></div><div><span>24 h</span><b class="${tom(u.chg_24h)}">${sg(u.chg_24h)}%</b></div><div><span>Volume 24 h</span><b>${num(u.volume_24h / 1e6, 1)} M$</b></div>` : `<div><span>Scanner</span><b>fora do universo</b></div>`}
      ${lq ? `<div><span>Spread</span><b>${num(lq.spread_pct, 3)}%</b></div>` : `<div><span>Liquidez</span><b>sem amostras</b></div>`}</div>
      <div class="graf fixo" data-serie="funding" data-ativo="${esc(at)}"><canvas height="140"></canvas></div><div class="graf fixo" data-serie="oi" data-ativo="${esc(at)}"><canvas height="140"></canvas></div>
      <div class="graf fixo" data-livro="${esc(at)}"><canvas height="170"></canvas></div>
      <small class="nota">${dv ? `Derivados: ${hora(dv.t[dv.t.length - 1])} · derivados.json` : `Sem série de derivados para ${esc(at)}.`}</small>`;
    series(el); verAtivo(at, S.extra);
  } else if (S.k === "zona") {
    const Z = AREAS[S.id] || { nome: S.id === "standby" ? "Standby · em espera" : "Parede de mercado" }, ag = AGENTES.filter(a => a.zona === S.id);
    T(Z.nome);
    el.innerHTML = `<p class="nota">${esc(ZONA_TXT[S.id] || "")}</p>${ag.length ? `<h4>Agentes desta área</h4>` + lista(ag.map(a => [a.nome, `${ESTADOS[c.estados[a.id].estado].nome} · ${c.estados[a.id].atividade || ""}`]), "", false, ag.map(a => `agente:${a.id}`)) : S.id in AREAS ? `<p class="nota">Nenhum agente implementado nesta área.</p>` : ""}
      ${S.id === "standby" ? lista(AGENTES.filter(a => ["espera", "cifrado"].includes(c.estados[a.id].estado)).map(a => [a.nome, c.estados[a.id].atividade || ""]), "Ninguém em espera.", false) : ""}
      <div class="acoes">${{ exchanges: `<button data-acao="corretora:OKX">OKX</button><button data-acao="corretora:Bybit">Bybit</button>`, risco: `<button data-acao="ativ:alertas">Alertas</button>`, quant: `<button data-acao="ativ:estrategias">Estratégias</button>`, estrategia: `<button data-acao="amb:PAPEL">Papel</button><button data-acao="amb:SOMBRA">Sombra</button>`,
        tecnica: `<button data-acao="grafico:BTC">Gráfico BTC</button>`, intel: `<button data-acao="ativ:scanners">Scanners</button>`, cacador: `<button data-acao="ativ:oportunidades">Oportunidades</button>`, trading: `<button data-acao="ops">Operações</button>`, comando: `<button data-acao="ativ:eventos">Eventos</button>` }[S.id] || ""}</div>`;
  } else if (S.k === "alerta") {
    const a = c.alertas[+S.id]; T("Alerta"); if (!a) { el.innerHTML = `<p class="nota">Este alerta já não está ativo.</p>`; return; }
    const m = a.texto.match(/^(OKX|Bybit) ([A-Z0-9]+):/), pos = m && c.posicoes.find(p => p.corretora === m[1] && p.ativo === m[2]);
    el.innerHTML = `<div class="badge ${a.nivel === "critico" ? "critico" : a.nivel === "aviso" ? "aviso" : "pub"}">● ${esc(a.nivel.toUpperCase())}</div><p>${esc(a.texto)}</p>
      <dl><dt>Origem</dt><dd>${esc(a.origem)}</dd><dt>Verificado</dt><dd>${hora(c.t)}</dd></dl>
      <div class="acoes">${pos ? `<button data-acao="posicao:${pos.corretora}:${esc(pos.ativo)}">Ver a posição</button>` : ""}${/^OKX/.test(a.texto) ? `<button data-acao="corretora:OKX">OKX</button>` : ""}${/^Bybit/.test(a.texto) ? `<button data-acao="corretora:Bybit">Bybit</button>` : ""}<button data-acao="ativ:fontes">Fontes de dados</button></div>`;
  } else if (S.k === "estrategia") {
    const e = c.estrategias[+S.id]; if (!e) return; T(`Estratégia · ${e.nome}`);
    const d = Dd.desempenho(e.nome, c);
    el.innerHTML = `<div class="badge ${e.ativa ? "ok" : "critico"}">● ${e.ativa ? "ativa" : "suspensa"}</div> ${amb(e.dinheiro === "real" ? "REAL" : "PAPEL")}
      <dl><dt>Corretora</dt><dd>${esc(e.corretora)}</dd><dt>Notas</dt><dd>${esc(e.razao || "–")}</dd></dl>
      <h4>Desempenho medido (por ambiente)</h4>${d.length ? `<div class="tw"><table><tr><th>Ambiente</th><th>Operações</th><th>R médio</th><th>Acerto</th><th>PF</th></tr>${d.map(x => `<tr><td>${amb(x.ambiente)} <small>${esc(x.nota || "")}</small></td><td>${x.n}</td><td class="${tom(x.r_medio)}">${x.r_medio == null ? "–" : sg(x.r_medio, 3) + "R"}</td><td>${x.acerto_pct == null ? "–" : x.acerto_pct + "%"}</td><td>${x.pf ?? "–"}</td></tr>`).join("")}</table></div>` : `<p class="nota">Sem medições publicadas para esta estratégia.</p>`}
      <p class="nota">Lido da configuração e dos registos publicados. Esta página não altera estratégias.</p>`;
  }
}
const ZONA_TXT = {
  comando: "Consolida o estado do sistema e as decisões da direção de estratégia.", trading: "Operações em dinheiro real na OKX: pânico (H40) e recuo na subida (H46).",
  intel: "Derivados (funding, open interest), liquidez e calendário macro.", quant: "Arena: re-simulações das estratégias (BACKTEST), expectativa em R e sobrevivência.",
  tecnica: "Scanner técnico dos pares da Bybit UE, de 5 em 5 minutos.", risco: "Risco por operação, risco aberto, travão e alertas.",
  exchanges: "Execução, posições e reconciliação com a OKX e a Bybit; núcleo BTC.", estrategia: "Estratégias em desenvolvimento, só em PAPEL e SOMBRA.",
  cacador: "Caça de oportunidades fora da cripto: ações, índices e metais na OKX (PAPEL).", standby: "Agentes entre passagens: vêm para aqui quando estão em espera.", parede: "Resultado real, BTC, mapa do mercado, arena, atividade, risco e corretoras.",
};
async function series(root) {
  for (const box of root.querySelectorAll(".graf[data-serie], .graf[data-livro]")) {
    const cv = box.querySelector("canvas"); let [g, w, h] = ajustar(cv, +cv.getAttribute("height"));
    if (box.dataset.serie) { const dv = Dd.derivadosDe(A.ctx.Dv, box.dataset.ativo), fu = box.dataset.serie === "funding";
      if (!dv) Gx.indisponivel(g, w, h, fu ? "Funding" : "Open Interest", "sem série para este ativo");
      else Gx.serie(g, w, h, dv.t, fu ? dv.funding : dv.oi, { titulo: fu ? "Funding (%)" : "Open Interest (M$)", unidade: fu ? "%" : " M$", cor: fu ? "#7FA8FF" : "#35D6F2", fonte: "derivados.json", zero: fu }); }
    else { Gx.indisponivel(g, w, h, "Livro de ordens", "a carregar…"); const L = await Dd.livro(box.dataset.livro); [g, w, h] = ajustar(cv, +cv.getAttribute("height")); Gx.livroOrdens(g, w, h, L, { titulo: `Livro de ordens · ${box.dataset.livro}` }); }
  }
}

// ---------------------------------------------------------------- ecras do escritorio (texturas com dados reais)
function desenharEcra(e, g, w, h) {
  const c = A.ctx; if (!c) return Gx.indisponivel(g, w, h, "A carregar…", "");
  const T = (t, rows, o) => Gx.ecraTabela(g, w, h, t, rows, o), O = c.O || {}, S = c.S || {}, cf = c.cfgOkx || {};
  const C = { ouro: "#E8B84A", ciano: "#35D6F2", azul: "#4F8CFF" };
  switch (e.id) {
    case "scanner": return T("Scanner técnico · Bybit UE", ((S.mesa || []).slice(0, 7)).map(m => [m.asset, `RSI ${num(m.rsi, 1)} · ${m.a_favor}/${m.votantes} a favor`, m.rsi < 30 ? Gx.COR.sobe : Gx.COR.texto]).concat((S.mesa || []).length ? [] : [["Sem mesa publicada", ""]]), { cor: C.ciano, rodape: `${(S.counts || {}).deep_checked ?? "–"} pares · ${hora(S.generated_at)}` });
    case "panico": return T("Radar de pânico · OKX", (((O.radar || {}).lista) || []).slice(0, 8).map(r => [r.a, `queda 3d ${r.q}% · funding ${num((r.f || 0) * 100, 3)}%`, C.ciano]), { cor: C.ciano, rodape: `${(O.resumo || {}).analisados ?? "–"} perpétuos · ${hora((O.resumo || {}).t)} · H40 ${cf.panico_real ? "REAL" : "suspensa em real"}` });
    case "recuo": { const r = (O.recuo || {}).resumo || {}; return T("Recuo na subida · H46", [["BTC em subida", r.btc_em_subida ? "sim" : "não", r.btc_em_subida ? Gx.COR.sobe : Gx.COR.fraco], ["Pendentes", String((r.pendentes || []).length)], ["Abertas (PAPEL)", String((r.abertas || []).length)], ["Medidas", String((r.metricas || {}).n ?? 0)], ["Real", cf.recuo_real ? `ligado · risco ${cf.recuo_risco_pct}%` : "suspenso"]], { cor: C.ciano }); }
    case "macro": { const M = (O.macro || {}).resumo || {}; return T("Ações, índices e metais · PAPEL", [["Analisados", String(M.analisados ?? "–")], ["Em tendência", String((M.abertas || []).length)], ...(M.abertas || []).slice(0, 5).map(a => ["  " + a, "acima da MM50", Gx.COR.sobe])], { cor: C.azul, rodape: "OKX · simulação" }); }
    case "diretor": return T("Decisões da direção", ((S.diretor || {}).decisoes || []).slice(-8).reverse().map(d => [`${d.ativo} ${d.lado}`, `${d.decisao} · ${hora(d.t)}`, d.decisao === "AUTORIZADO" ? Gx.COR.sobe : Gx.COR.desce]), { cor: C.ouro });
    case "risco": { const ab = c.opOkx.posicoes.reduce((s, p) => s + (p.risco_pct || 0), 0); return T("Gestão de risco", [["Risco aberto OKX", `${num(ab)}% / teto ${cf.risco_total_max_pct ?? "–"}%`, ab > (cf.risco_total_max_pct || 3) ? Gx.COR.desce : Gx.COR.sobe], ["Por operação", `${cf.risco_pct ?? "–"}% (máx ${cf.risco_max_pct ?? "–"}%)`], ["Alavancagem", `${cf.alavancagem ?? "–"}x`], ["Travão", `queda de ${cf.travao_queda_pct ?? "–"}%`], ["LONG / SHORT", `${c.exposicao.long} / ${c.exposicao.short}`]], { cor: C.ouro, rodape: "okx_config.json" }); }
    case "liquidez": { const d = Dd.derivadosDe(c.Dv, "BTC"); return d ? Gx.serie(g, w, h, d.t, d.funding, { titulo: "BTC · funding (%)", unidade: "%", cor: C.azul, fonte: "derivados.json", zero: true }) : Gx.indisponivel(g, w, h, "Derivados", "sem série publicada"); }
    case "noticias": { const ev = S.next_event; return T("Calendário macro", [["Próximo evento", ev ? ev.name : "nenhum"], ["Quando", ev ? hora(ev.t) : "–"], ["Janela de risco", S.event_block ? "ativa" : "não", S.event_block ? C.ouro : Gx.COR.sobe]], { cor: C.azul }); }
    case "exec_okx": return T("OKX · posições REAIS", [...c.opOkx.posicoes.map(p => [`${p.ativo} ${p.lado}`, p.pnl_pct != null ? `${sg(p.pnl_pct)}%` : p.R != null ? `${sg(p.R)}R · stop ${px(p.stop)}` : `stop ${px(p.stop)}`, (p.pnl_pct ?? p.R) == null ? Gx.COR.texto : (p.pnl_pct ?? p.R) >= 0 ? Gx.COR.sobe : Gx.COR.desce]), ...c.opOkx.ordens.map(o => [`${o.ativo} (ordem)`, `a ${px(o.preco)}`, C.ouro])].concat(c.opOkx.posicoes.length || c.opOkx.ordens.length ? [] : [["Sem posições nem ordens", "", Gx.COR.fraco]]), { cor: "#DCE6F2", rodape: `${LIG[c.okx.ligacao][1]} · ${hora(c.okx.agente.t)}` });
    case "exec_bybit": return T("Bybit UE · operações REAIS", [...c.opBy.posicoes.map(p => [`${p.ativo} ${p.lado}`, p.estrategia]), ...c.opBy.sinais_nao_executados.slice(0, 4).map(s => [`${s.ativo} ${s.lado}`, "sinal não executado", Gx.COR.fraco])].concat(c.opBy.posicoes.length ? [] : [["Sem posições do motor", "", Gx.COR.fraco]]), { cor: C.ouro, rodape: LIG[c.bybit.ligacao][1] });
    case "nucleo": { if (!c.P) return Gx.indisponivel(g, w, h, "Núcleo BTC", "dados só no cofre cifrado"); const N = (((c.P.nucleo || {}).plano || {}).BTC) || {}; return T("Tendência BTC · núcleo", [["Estado", N.acima ? "comprado" : "fora", N.acima ? Gx.COR.sobe : Gx.COR.fraco], ["Média 50 dias", px(N.media)]], { cor: C.ouro }); }
    case "arena": return T("Arena · BACKTEST", (((S.arena || {}).classificacao) || []).filter(x => x.estado !== "MORTA").slice(0, 8).map(x => [x.id.slice(0, 24), `${x.avg_r == null ? "–" : sg(x.avg_r) + "R"} · n ${x.n}`, x.avg_r > 0 ? Gx.COR.sobe : Gx.COR.fraco]), { cor: C.azul, rodape: `${(S.arena || {}).vivos ?? "–"} vivas · ${hora((S.arena || {}).atualizado)}` });
    case "tfshort": { const ab = Object.entries((((c.T || {}).sinais || {}).abertas) || {}); return T("TF-SHORT · PAPEL", ab.slice(0, 8).map(([a, v]) => [a, `entrada ${px(v.entrada)} · stop ${px(v.stop)}`, Gx.COR.desce]).concat(ab.length ? [] : [["Sem posições em papel", ""]]), { cor: C.azul }); }
    case "sistema": { const gl = estadoGlobal(c); return T("Command Center", [["Sistema", gl.t, gl.k === "ok" ? Gx.COR.sobe : gl.k === "aviso" ? C.ouro : Gx.COR.desce], ["OKX", LIG[c.okx.ligacao][1]], ["Bybit", LIG[c.bybit.ligacao][1]], ["Posições reais", String(c.posicoes.length)], ["Alertas", String(c.alertas.filter(a => a.nivel !== "info").length)]], { cor: C.ouro, rodape: hora(c.t) }); }
    case "resultado": {
      g.fillStyle = "#06090E"; g.fillRect(0, 0, w, h); g.fillStyle = C.ouro; g.fillRect(0, 0, w, 5);
      const tot = c.fr.reduce((s, f) => s + f.R, 0), hj = c.frHoje.reduce((s, f) => s + f.R, 0);
      g.fillStyle = Gx.COR.fraco; g.font = "600 24px Inter, system-ui"; g.fillText("RESULTADO REAL · FECHADAS", 28, 48);
      g.fillStyle = tot >= 0 ? Gx.COR.sobe : Gx.COR.desce; g.font = "700 92px Inter, system-ui"; g.fillText(c.K ? `${sg(c.K.pnl_fechado_usd)} USD` : `${sg(tot)}R`, 26, 148);
      g.fillStyle = Gx.COR.texto; g.font = "24px Inter, system-ui"; g.fillText(`${c.fr.length} operações · hoje ${sg(hj)}R (${c.frHoje.length})${c.K ? " · OKX, conta" : " · OKX + Bybit, público"}`, 28, 190);
      if (c.acum.length >= 2) { const x0 = 28, x1 = w - 28, y0 = 225, y1 = h - 30, vs = c.acum.map(a => a.v), lo = Math.min(0, ...vs), hi = Math.max(0, ...vs), Y = v => y0 + (hi - v) / (hi - lo || 1) * (y1 - y0), X = i => x0 + i / (vs.length - 1) * (x1 - x0);
        g.strokeStyle = "#2A3344"; g.beginPath(); g.moveTo(x0, Y(0)); g.lineTo(x1, Y(0)); g.stroke();
        g.strokeStyle = C.ouro; g.lineWidth = 4; g.beginPath(); vs.forEach((v, i) => i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))); g.stroke(); g.lineWidth = 1;
        vs.forEach((v, i) => { g.fillStyle = c.fr[i].R >= 0 ? Gx.COR.sobe : Gx.COR.desce; g.beginPath(); g.arc(X(i), Y(v), 6, 0, 7); g.fill(); }); }
      else { g.fillStyle = Gx.COR.fraco; g.fillText("Ainda sem operações suficientes para a curva.", 28, 300); }
      return;
    }
    case "btc": { const v = A.velas["BTC:4h"]; return v && v.velas.length ? Gx.velasCompleto(g, w, h, v.velas, { titulo: "BTC · 4H", fonte: v.fonte }) : Gx.indisponivel(g, w, h, "BTC · 4H", (v && v.erro) || "a carregar velas…"); }
    case "mapa": {
      const U = (S.universe || []).slice().sort((a, b) => (b.volume_24h || 0) - (a.volume_24h || 0)).slice(0, 40);
      g.fillStyle = "#06090E"; g.fillRect(0, 0, w, h); g.fillStyle = C.ciano; g.fillRect(0, 0, w, 5); g.fillStyle = Gx.COR.texto; g.font = "700 28px Inter, system-ui"; g.fillText("Mercado cripto · 24 h", 24, 46);
      g.font = "18px Inter"; g.fillStyle = Gx.COR.fraco; g.textAlign = "right"; g.fillText(`scanner · ${hora(S.generated_at)}`, w - 24, 46); g.textAlign = "left";
      if (!U.length) return Gx.indisponivel(g, w, h, "Mercado", "universo não publicado");
      const cols = 8, cw = (w - 40) / cols, ch = (h - 80) / 5;
      U.forEach((u, i) => { const x = 20 + (i % cols) * cw, y = 64 + Math.floor(i / cols) * ch, k = Math.max(-1, Math.min(1, (u.chg_24h || 0) / 8));
        g.fillStyle = k >= 0 ? `rgba(63,214,143,${.12 + .55 * k})` : `rgba(240,97,109,${.12 - .55 * k})`; g.fillRect(x + 3, y + 3, cw - 6, ch - 6);
        g.fillStyle = "#E8F0FA"; g.font = "700 22px Inter"; g.fillText(u.asset, x + 12, y + ch / 2); g.font = "18px Inter"; g.fillText(`${sg(u.chg_24h)}%`, x + 12, y + ch / 2 + 26); });
      return;
    }
    case "quantw": return T("Investigação quantitativa · arena (BACKTEST)", (((S.arena || {}).classificacao) || []).filter(x => x.estado !== "MORTA").slice(0, 8).map(x => [x.id.slice(0, 28), `${x.estado} · n ${x.n} · ${x.avg_r == null ? "–" : sg(x.avg_r) + "R"} · acerto ${x.n ? Math.round(100 * x.wins / x.n) : "–"}%`, x.avg_r > 0 ? Gx.COR.sobe : Gx.COR.fraco]), { cor: C.azul, rodape: `re-simulação de 90 dias · não são operações reais · ${hora((S.arena || {}).atualizado)}` });
    case "atividade": {
      g.fillStyle = "#06090E"; g.fillRect(0, 0, w, h); g.fillStyle = C.ciano; g.fillRect(0, 0, w, 5);
      g.fillStyle = Gx.COR.texto; g.font = "700 30px Inter, system-ui"; g.fillText("Atividade", 26, 48);
      g.font = "21px Inter, system-ui"; c.eventos.slice(0, 13).forEach((ev, i) => { g.fillStyle = Gx.COR.fraco; g.fillText(hora(ev.t), 26, 92 + i * 34); g.fillStyle = Gx.COR.texto; g.fillText(`${nomeAg(ev.agente)}: ${ev.texto}`.slice(0, 70), 170, 92 + i * 34); });
      return;
    }
    case "riscow": return T("Risco e alertas", [["Risco aberto", `${num(c.exposicao.risco_pct)}%`], ["LONG / SHORT", `${c.exposicao.long} / ${c.exposicao.short}`], ...c.alertas.slice(0, 6).map(a => [a.nivel.toUpperCase(), a.texto.slice(0, 34), a.nivel === "critico" ? Gx.COR.desce : a.nivel === "aviso" ? C.ouro : C.ciano])].concat(c.alertas.length ? [] : [["Alertas", "nenhum", Gx.COR.sobe]]), { cor: C.ouro });
    case "corretoras": return T("Corretoras", [["OKX EEA", LIG[c.okx.ligacao][1], c.okx.ligacao === "falhou" ? Gx.COR.desce : Gx.COR.sobe], ["  agente", Dd.texIdade(c.okx.agente.idade)], ["  posições · ordens", `${c.opOkx.posicoes.length} · ${c.opOkx.ordens.length}`], ["Bybit UE", LIG[c.bybit.ligacao][1], c.bybit.ligacao === "falhou" ? Gx.COR.desce : Gx.COR.sobe], ["  scanner", Dd.texIdade(c.bybit.agente.idade)], ["  posições", String(c.opBy.posicoes.length)], ["Reconciliação", c.recOkx.estado.replace("_", " "), c.recOkx.estado === "discrepancia" ? Gx.COR.desce : Gx.COR.texto]], { cor: "#DCE6F2" });
    default: return Gx.indisponivel(g, w, h, e.id, "sem conteúdo");
  }
}

// ---------------------------------------------------------------- ciclo, 3D e eventos
let _evVistos = null;
function renderTudo() {
  const c = A.ctx = contexto();
  renderTopo(c); renderFin(c); renderAgentes(c); renderOps(c); renderAtiv(c);
  if (A.sel && !["ativo"].includes(A.sel.k)) renderDetalhe();
  if (A.of) { A.of.atualizar({ estados: c.estados, colaboracoes: c.colab, ligacoes: { OKX: c.okx.ligacao, Bybit: c.bybit.ligacao }, cofreAberto: !!(c.K || c.P) });
    const novos = c.eventos.filter(e => _evVistos && !_evVistos.has(e.t + e.agente + e.texto)); novos.slice(0, 3).forEach(e => A.of.destacar(e.agente)); }   // um evento novo destaca o agente responsavel
  _evVistos = new Set(c.eventos.map(e => e.t + e.agente + e.texto));
  $("#sinc").textContent = `sinc. ${new Date().toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
  document.body.classList.add("carregado");
}
async function velasPosicoes() { const c = A.ctx; if (!c) return; await Promise.all([...new Set(c.posicoes.map(p => p.ativo))].slice(0, 8).map(a => obterVelas(a, "1h"))); }

async function arrancar() {
  ligarEventos(); iniciar3D(ler("cs_vista") || "auto");
  await Promise.all(Object.keys(Dd.FONTES).map(k => carregar(k)));
  renderTudo(); renderGraf();
  velasPosicoes().then(renderTudo);
  obterVelas("BTC", "4h").then(() => A.of && A.of.redesenharEcras());
  for (const [k, s] of Object.entries(REFRESCO)) setInterval(async () => { if (document.hidden) return; await carregar(k); renderTudo(); }, s * 1000);
  setInterval(async () => { if (document.hidden) return; await velasPosicoes(); await obterVelas("BTC", "4h"); renderTudo(); renderGraf(); }, 120000);
  setInterval(() => { if (!document.hidden && A.ctx) { const c = contexto(); A.ctx = c; renderTopo(c); } }, 30000);
}

function margens() {
  if (!A.of) return; const d = $("#detalhe"), mob = innerWidth <= 900;
  A.of.margens({ esq: 0, topo: mob ? 0 : 92, baixo: 0, dir: !mob && d.classList.contains("on") ? d.offsetWidth + 16 : 0 });
}
async function iniciar3D(q) {
  const palco = $("#cena"); palco.querySelectorAll(".sem3d").forEach(x => x.remove());
  if (A.of) { A.of.destruir(); A.of = null; }
  if (q === "2d") { document.body.classList.add("modo2d"); marcarVista("2d"); return; }
  document.body.classList.remove("modo2d");
  try {
    const { Escritorio } = await import("./escritorio.js");
    A.of = new Escritorio(palco, { qualidade: q === "baixa" || q === "alta" ? q : "auto", desenharEcra,
      onAgente: id => abrir("agente", id), onAcao: a => acao(a),
      onZona: (z, ecra) => { if (ecra === "btc") verAtivo("BTC", "4h"); else if (ecra === "resultado") ativ("resultado"); else if (ecra === "atividade") ativ("eventos"); else if (ecra === "riscow") ativ("alertas"); else if (ecra === "quantw") ativ("estrategias"); else if (ecra === "corretoras") abrir("corretora", "OKX"); else if (ecra === "mapa") ativ("scanners"); else { abrir("zona", z); A.of.focar(z); } } });
    A.of.onDegradar = v => marcarVista(v);
    marcarVista(A.of.qualidade); margens();
    if (A.ctx) A.of.atualizar({ estados: A.ctx.estados, colaboracoes: A.ctx.colab, ligacoes: { OKX: A.ctx.okx.ligacao, Bybit: A.ctx.bybit.ligacao }, cofreAberto: !!(A.ctx.K || A.ctx.P) });
  } catch (e) {
    console.warn("3D indisponível:", e && e.message); document.body.classList.add("modo2d"); marcarVista("2d");
    palco.insertAdjacentHTML("beforeend", `<p class="sem3d">O 3D não arrancou neste aparelho (${esc((e && e.message) || "WebGL")}). O centro de comando funciona na mesma.</p>`);
  }
}
function marcarVista(v) { $$("#vista button").forEach(b => b.classList.toggle("on", b.dataset.vista === v)); }
function ativ(t) { A.ativ = t; $("#atividade").classList.remove("min"); if (A.ctx) renderAtiv(A.ctx); if (innerWidth <= 900) vistaMovel("atividade"); }
function vistaMovel(v) { document.body.dataset.m = v; $$("#nav-m button").forEach(b => b.classList.toggle("on", b.dataset.m === v)); if (v === "graficos") renderGraf(); if (A.of) A.of.redimensionar(); }

async function acao(txt) {
  const [k, x, y] = txt.split(":");
  if (k === "agente") abrir("agente", x);
  else if (k === "corretora") { abrir("corretora", x); A.f.corretora = x; A.f.ambiente = "REAL"; renderOps(A.ctx); }
  else if (k === "posicao") abrir("posicao", `${x}:${y}`);
  else if (k === "ativo") abrir("ativo", x, y);
  else if (k === "oportunidade") abrir("ativo", x);
  else if (k === "grafico") verAtivo(x, y);
  else if (k === "alerta") abrir("alerta", x);
  else if (k === "estrategia") abrir("estrategia", x);
  else if (k === "zona") { abrir("zona", x); A.of && A.of.focar(x); }
  else if (k === "tudo") { A.of && A.of.focar("tudo"); }
  else if (k === "eventos") { A.f.agente = x; ativ("eventos"); }
  else if (k === "ativ") ativ(x);
  else if (k === "amb") { A.f.ambiente = x; renderOps(A.ctx); if (innerWidth <= 900) vistaMovel("operacoes"); }
  else if (k === "ops") { A.f.ambiente = "REAL"; renderOps(A.ctx); $("#operacoes").classList.remove("min"); if (innerWidth <= 900) vistaMovel("operacoes"); }
  else if (k === "cofre") await alternarCofre();
}

function arrastar(sep, eixo, aplicar) {
  sep.addEventListener("pointerdown", ev => { ev.preventDefault(); sep.setPointerCapture(ev.pointerId); sep.classList.add("on");
    const mover = e => { aplicar(eixo === "x" ? e.clientX : e.clientY); A.of && A.of.redimensionar(); };
    const fim = () => { sep.classList.remove("on"); sep.removeEventListener("pointermove", mover); sep.removeEventListener("pointerup", fim); renderGraf(); margens(); };
    sep.addEventListener("pointermove", mover); sep.addEventListener("pointerup", fim); });
}

function ligarEventos() {
  document.addEventListener("click", ev => { const b = ev.target.closest("[data-acao]"); if (b) acao(b.dataset.acao); });
  document.addEventListener("change", e => { const s = e.target.closest("[data-filtro]"); if (!s || s.type === "search") return; A.f[s.dataset.filtro] = s.value; renderOps(A.ctx); renderAtiv(A.ctx); });
  document.addEventListener("input", e => { const s = e.target.closest("input[data-filtro]"); if (!s) return; A.f.ativo = s.value; renderOps(A.ctx); const n = $("#ops-filtros input"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } });
  $$("#ops-tabs button").forEach(b => b.addEventListener("click", () => { A.f.ambiente = b.dataset.amb; renderOps(A.ctx); }));
  $$("#ativ-tabs button").forEach(b => b.addEventListener("click", () => ativ(b.dataset.ativ)));
  $("#graf-ativo").addEventListener("change", e => verAtivo(e.target.value));
  $$("#graf-iv button").forEach(b => b.addEventListener("click", () => { A.graf.iv = b.dataset.iv; guardar("atlas_iv", b.dataset.iv); renderGraf(); }));
  $("#graf-rsi").addEventListener("click", () => { A.graf.rsi = !A.graf.rsi; renderGraf(); });
  $("#graf-macd").addEventListener("click", () => { A.graf.macd = !A.graf.macd; renderGraf(); });
  $("#det-fechar").addEventListener("click", fechar);
  $$("[data-min]").forEach(b => b.addEventListener("click", () => { const p = b.closest(".painel"); p.classList.toggle("min"); b.textContent = p.classList.contains("min") ? "▢" : "–"; b.title = p.classList.contains("min") ? "Expandir" : "Minimizar"; document.body.classList.toggle("ativ-min", $("#atividade").classList.contains("min")); document.body.classList.toggle("ops-min", $("#operacoes").classList.contains("min")); document.body.classList.toggle("graf-min", $("#graficos").classList.contains("min")); A.of && A.of.redimensionar(); renderGraf(); }));
  $$("#vista button").forEach(b => b.addEventListener("click", () => { guardar("cs_vista", b.dataset.vista); iniciar3D(b.dataset.vista); }));
  $$("#nav-m button").forEach(b => b.addEventListener("click", () => vistaMovel(b.dataset.m)));
  const R = document.documentElement.style, cl = (v, a, b) => Math.max(a, Math.min(b, v));
  for (const k of ["--wr", "--hb", "--ho"]) { const v = ler("atlas" + k); if (v) R.setProperty(k, v); }
  const def = (k, v) => { R.setProperty(k, v); guardar("atlas" + k, v); };
  arrastar($("#sep-v"), "x", x => def("--wr", cl(innerWidth - x - 3, 300, innerWidth * .5) + "px"));
  arrastar($("#sep-h"), "y", y => def("--hb", cl(innerHeight - y - 3, 120, innerHeight * .55) + "px"));
  arrastar($("#sep-o"), "y", y => { const r = $("#col-dir").getBoundingClientRect(); def("--ho", cl((y - r.top) / r.height * 100, 20, 78) + "%"); });
  addEventListener("keydown", e => { if (e.key === "Escape") fechar(); });
  addEventListener("resize", () => { margens(); renderGraf(); });
  setInterval(() => { $("#relogio").textContent = new Date().toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" }) + " · " + new Date().toISOString().slice(11, 16) + " UTC"; }, 1000);
  vistaMovel("operacoes");
}

async function alternarCofre() {
  if (A.aberto.cofreOkx || A.aberto.cofreScan) { if (window.CIFRA) window.CIFRA.esquecer(); A.aberto = { cofreScan: null, cofreOkx: null }; renderTudo(); return; }
  await abrirCofre("cofreOkx", true); await abrirCofre("cofreScan", false); renderTudo();
}

arrancar().catch(e => { console.error(e); const el = document.getElementById("erro-arranque"); if (el) { el.hidden = false; el.textContent = "Erro ao arrancar: " + (e && e.message); } });
