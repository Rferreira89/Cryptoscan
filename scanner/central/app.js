// CryptoScan · Operations Center — orquestracao: carrega as fontes reais, calcula o contexto, alimenta o escritorio 3D
// e o centro de comando. So consulta e monitorizacao: nenhuma funcao envia, cancela, altera ou fecha ordens.
import * as Dd from "./dados.js";
import { AGENTES, ESTADOS, estadosAgentes, colaboracoes } from "./agentes.js";
import * as Gx from "./graficos.js";

const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = (v, d = 2) => v == null || !isFinite(v) ? "–" : Number(v).toLocaleString("pt-PT", { minimumFractionDigits: d, maximumFractionDigits: d });
const px = v => v == null || !isFinite(v) ? "–" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("pt-PT") : Number(Number(v).toPrecision(5)).toLocaleString("pt-PT", { maximumSignificantDigits: 5 });
const hora = t => t ? new Date(t * 1000).toLocaleString("pt-PT", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }) : "–";
const sg = v => v == null ? "–" : (v > 0 ? "+" : "") + num(v);
const agora = () => Date.now() / 1000;

// ---------------------------------------------------------------- estado da aplicacao
const A = window.CS_APP = {
  res: {}, aberto: { cofreScan: null, cofreOkx: null }, ctx: null, velas: {}, sel: null, filtros: { corretora: "todas", lado: "todos", estrategia: "todas", agente: "todos", nivel: "todos" },
  of: null, modo: "3d", erros: [], carregado: false,
};
const REFRESCO = { scan: 60, state: 120, okx: 120, cofreOkx: 120, cofreScan: 120, cfgOkx: 900, derivados: 600, liquidez: 900, tfshort: 1800 };

async function carregar(chave) {
  const r = await Dd.obter(Dd.FONTES[chave].url, { tentativas: 3 });
  r.pedido = agora();
  const anterior = A.res[chave];
  if (!r.ok && anterior && anterior.ok) { r.dados_anteriores = anterior.dados; r.t_anterior = anterior.pedido; }   // mostra-se como falha, nunca como atual
  A.res[chave] = r;
  if (r.ok && Dd.FONTES[chave].cifrado) await abrirCofre(chave, false);
  return r;
}

async function abrirCofre(chave, pedir) {
  const r = A.res[chave]; if (!r || !r.ok || !window.CIFRA) return;
  const env = r.dados;
  if (!(env && env.cifra === "cs1")) { A.aberto[chave] = env; return; }
  let pw = ""; try { pw = localStorage.getItem("cryptoscan_pw") || ""; } catch (_) {}
  if (!pw && !pedir) { A.aberto[chave] = null; return; }
  try { A.aberto[chave] = await window.CIFRA.json(env); } catch (_) { A.aberto[chave] = null; }
}

function contexto() {
  const t = agora(), d = k => (A.res[k] && A.res[k].ok ? A.res[k].dados : null);
  const S = d("scan"), St = d("state"), O = d("okx"), cfgOkx = d("cfgOkx"), Dv = d("derivados"), L = d("liquidez"), T = d("tfshort");
  const K = A.aberto.cofreOkx, P = A.aberto.cofreScan;
  const fontes = {}; for (const k of Object.keys(Dd.FONTES)) fontes[k] = Dd.estadoFonte(k, A.res[k], { aberto: A.aberto[k], agora: t });
  const okx = Dd.estadoOKX(A.res.okx, { res: A.res.cofreOkx, aberto: K }, t);
  const bybit = Dd.estadoBybit(A.res.scan, { res: A.res.cofreScan, aberto: P }, t);
  const opOkx = Dd.okxOperacoes(O, K), opBy = Dd.bybitOperacoes(S, P);
  const recOkx = Dd.reconciliar(opOkx.posicoes, opOkx.ordens, !!K), recBybit = Dd.reconciliar(opBy.posicoes, [], !!P);
  const eventos = Dd.eventos({ O, S, St, K });
  const estados = estadosAgentes({ fontes, O, S, St, Dv, T, cfgOkx, K, P, eventos }, t);
  const posicoes = [...opOkx.posicoes, ...opBy.posicoes], ordens = opOkx.ordens;
  return { t, S, St, O, cfgOkx, Dv, L, T, K, P, fontes, okx, bybit, opOkx, opBy, recOkx, recBybit, eventos, estados, posicoes, ordens,
           fechadas: { okx: Dd.okxFechadas(O, K), bybit: opBy.fechadas },
           estrategias: Dd.estrategias(cfgOkx, S, St), oportunidades: Dd.oportunidades(S, O), rejeicoes: Dd.rejeicoes(S),
           alertas: Dd.alertas({ okx, bybit, recOkx, recBybit, O, S, cfgOkx, agora: t }), exposicao: Dd.exposicao(posicoes), pnl: Dd.pnl(K, P),
           colab: colaboracoes(eventos, t) };
}

// ---------------------------------------------------------------- estado global
function estadoGlobal(c) {
  const crit = c.alertas.filter(a => a.nivel === "critico").length, av = c.alertas.filter(a => a.nivel === "aviso").length;
  const err = AGENTES.filter(a => c.estados[a.id].estado === "erro").length;
  if (c.okx.ligacao === "falhou" && c.bybit.ligacao === "falhou") return { k: "falha", t: "Sem ligação às corretoras" };
  if (crit || err) return { k: "critico", t: `${crit + err} problema(s) a resolver` };
  if (av) return { k: "aviso", t: `Operacional com ${av} aviso(s)` };
  return { k: "ok", t: "Operacional" };
}

const LIG = { ligado: ["ok", "Ligada"], ligado_publico: ["pub", "Ligada · conta cifrada"], atrasado: ["aviso", "Atrasada"], desatualizado: ["critico", "Desatualizada"], falhou: ["critico", "Sem ligação"] };

// ---------------------------------------------------------------- render: cabecalho e KPIs
function renderTopo(c) {
  const g = estadoGlobal(c);
  $("#global").className = "pill " + g.k; $("#global").innerHTML = `<i></i>${esc(g.t)}`;
  $("#fontes").innerHTML = Object.entries(c.fontes).map(([k, f]) => `<button class="dot ${f.estado}" data-acao="fontes" title="${esc(Dd.FONTES[k].nome)}: ${esc(f.estado)}${f.razao ? " — " + esc(f.razao) : ""}"></button>`).join("");
  const cof = $("#cofre"), aberto = !!(c.K || c.P);
  cof.textContent = aberto ? "🔓 Cofre aberto" : "🔒 Abrir cofre"; cof.classList.toggle("on", aberto);
  const ag = AGENTES.map(a => c.estados[a.id].estado), at = ag.filter(e => (ESTADOS[e] || {}).ativo).length;
  const kp = [
    ["global", "Estado global", g.t, g.k],
    ["agentes", "Agentes", `${at} ativos · ${ag.filter(e => e === "espera" || e === "cifrado").length} em espera · ${ag.filter(e => e === "desligado").length} desligados · ${ag.filter(e => e === "erro").length} erro`, ag.includes("erro") ? "critico" : "ok"],
    ["corretora:Bybit", "Bybit UE", LIG[c.bybit.ligacao][1], LIG[c.bybit.ligacao][0]],
    ["corretora:OKX", "OKX EEA", LIG[c.okx.ligacao][1], LIG[c.okx.ligacao][0]],
    ["posicoes", "Posições reais", `${c.posicoes.length} (${c.opOkx.posicoes.length} OKX · ${c.opBy.posicoes.length} Bybit)`, ""],
    ["ordens", "Ordens pendentes", String(c.ordens.length), ""],
    ["pnl", "PnL não realizado", c.K ? `${sg(c.pnl.okx_aberto_usd)} USD (OKX)` : "🔒 cofre", c.K ? (c.pnl.okx_aberto_usd >= 0 ? "ok" : "critico") : "pub"],
    ["pnl", "PnL realizado", c.K ? `${sg(c.pnl.okx_fechado_usd)} USD (OKX, 30 últimas)` : "🔒 cofre", c.K ? (c.pnl.okx_fechado_usd >= 0 ? "ok" : "critico") : "pub"],
    ["posicoes", "Exposição", `${c.exposicao.nominal_usd != null ? num(c.exposicao.nominal_usd) + " USD · " : ""}risco ${num(c.exposicao.risco_pct)}%`, ""],
    ["posicoes", "LONG / SHORT", `${c.exposicao.long} / ${c.exposicao.short}`, ""],
    ["estrategias", "Estratégias", `${c.estrategias.filter(e => e.ativa && e.dinheiro === "real").length} reais ativas · ${c.estrategias.filter(e => !e.ativa).length} suspensas`, ""],
    ["mercado", "Oportunidades", String(c.oportunidades.filter(o => !o.perto).length) + ` · ${c.oportunidades.filter(o => o.perto).length} perto`, ""],
    ["alertas", "Alertas prioritários", String(c.alertas.filter(a => a.nivel === "critico").length), c.alertas.some(a => a.nivel === "critico") ? "critico" : "ok"],
  ];
  $("#kpis").innerHTML = kp.map(([acao, l, v, k]) => `<button class="kpi ${k}" data-acao="${esc(acao)}"><span>${esc(l)}</span><b>${esc(v)}</b></button>`).join("");
}

// ---------------------------------------------------------------- lista de agentes
function renderAgentes(c) {
  $("#lista-agentes").innerHTML = AGENTES.map(a => {
    const s = c.estados[a.id], E = ESTADOS[s.estado] || ESTADOS.desligado;
    return `<button class="ag ${A.sel && A.sel.k === "agente" && A.sel.id === a.id ? "sel" : ""}" data-acao="agente:${a.id}">
      <i style="background:${a.cor}">${esc(a.nome[0])}</i><div><b>${esc(a.nome)}</b><small>${esc(a.funcao)}</small>
      <em style="color:${E.cor}">● ${esc(E.nome)}</em><small class="act">${esc(s.atividade || "")}</small></div>
      <time>${s.t ? Dd.texIdade(s.idade) : ""}</time></button>`; }).join("");
}

// ---------------------------------------------------------------- inspector (painel lateral de detalhe)
// a area livre do palco (sem os paineis) e onde o escritorio fica centrado
function margens() {
  if (!A.of) return; const mob = innerWidth <= 860, vis = el => el && getComputedStyle(el).display !== "none";
  if (mob) return A.of.margens({ esq: 0, dir: 0, topo: 0, baixo: 0 });
  const ag = $("#agentes"), dc = $(".doca"), ins = $("#inspector");
  A.of.margens({ esq: vis(ag) ? ag.offsetWidth + 24 : 0, topo: 48, baixo: dc.classList.contains("max") ? 0 : dc.offsetHeight + 24, dir: ins.classList.contains("on") ? ins.offsetWidth + 24 : 0 });
}
function abrir(k, id, extra) { A.sel = { k, id, extra }; $("#inspector").classList.add("on"); renderInspector(); renderAgentes(A.ctx); margens();
  if (k === "agente" && A.of) A.of.focar(id); }
function fechar() { A.sel = null; $("#inspector").classList.remove("on"); renderAgentes(A.ctx); margens(); }

function renderInspector() {
  const c = A.ctx, S = A.sel, el = $("#insp-corpo"); if (!S || !c) return;
  if (S.k === "agente") {
    const a = AGENTES.find(x => x.id === S.id), s = c.estados[a.id], E = ESTADOS[s.estado];
    $("#insp-titulo").textContent = `${a.nome} · ${a.funcao}`;
    el.innerHTML = `<div class="badge" style="border-color:${E.cor};color:${E.cor}">● ${esc(E.nome)}</div>
      <dl><dt>Atividade atual</dt><dd>${esc(s.atividade || "–")}</dd>
      <dt>Última atualização</dt><dd>${s.t ? `${hora(s.t)} (${Dd.texIdade(s.idade)})` : "sem hora publicada"}</dd>
      <dt>Ligação ao sistema</dt><dd>${s.ligado === false ? '<span class="dn">sem ligação</span>' : '<span class="up">ligado</span>'}</dd>
      ${s.proxima ? `<dt>Próxima passagem prevista</dt><dd>${hora(s.proxima)}</dd>` : ""}
      <dt>Componente real</dt><dd><code>${esc(a.componente)}</code></dd><dt>Estação</dt><dd>${esc((ZONAS_NOMES[a.zona]) || a.zona)}</dd></dl>
      <h4>Histórico recente (eventos reais)</h4>${lista(s.historico.map(e => [hora(e.t), e.texto]), "Sem eventos registados para este agente.")}
      <div class="acoes"><button data-acao="focar:${a.id}">Ver na sala</button><button data-acao="eventos:${a.id}">Todos os eventos</button></div>`;
  } else if (S.k === "corretora") {
    const ex = S.id === "OKX" ? c.okx : c.bybit, ops = S.id === "OKX" ? c.opOkx : c.opBy, rec = S.id === "OKX" ? c.recOkx : c.recBybit;
    const priv = S.id === "OKX" ? c.K : c.P, [lk, lt] = LIG[ex.ligacao];
    $("#insp-titulo").textContent = S.id === "OKX" ? "OKX EEA · conta real" : "Bybit UE · conta real";
    const conta = S.id === "OKX"
      ? (c.K ? `<div class="kv"><div><span>Valor da conta</span><b>${num(c.K.equity_usd)} USD</b></div><div><span>Em aberto</span><b class="${c.K.pnl_aberto_usd >= 0 ? "up" : "dn"}">${sg(c.K.pnl_aberto_usd)} USD</b></div><div><span>Fechado (30 últimas)</span><b class="${c.K.pnl_fechado_usd >= 0 ? "up" : "dn"}">${sg(c.K.pnl_fechado_usd)} USD</b></div><div><span>Margem usada</span><b>${num((c.K.posicoes || []).reduce((s, p) => s + (p.margem_usd || 0), 0))} USD</b></div></div>
         <small>Moedas: ${(c.K.moedas || []).map(m => `${esc(m.ccy)} ${num(m.eq, 4)} (livre ${num(m.disponivel, 4)})`).join(" · ") || "–"}</small>` : `<p class="nota">🔒 Saldo, quantidades e PnL estão cifrados. <button data-acao="cofre">Abrir cofre</button></p>`)
      : (c.P && c.P.conta ? `<div class="kv"><div><span>Valor da conta</span><b>${num(c.P.conta.equity)} USD</b></div><div><span>USDC livre</span><b>${num(c.P.conta.usdc_free)}</b></div><div><span>Leitura</span><b>${Dd.texIdade(Dd.idade(c.P.conta.t))}</b></div></div>` : `<p class="nota">🔒 Saldo e posições da Bybit estão cifrados. <button data-acao="cofre">Abrir cofre</button></p>`);
    el.innerHTML = `<div class="badge ${lk}">● ${esc(lt)}</div>${ex.razao ? `<p class="nota">${esc(ex.razao)}</p>` : ""}
      <dl><dt>Última passagem do agente</dt><dd>${ex.agente.t ? `${hora(ex.agente.t)} (${Dd.texIdade(ex.agente.idade)})` : "–"}</dd>
      <dt>Última leitura privada da conta</dt><dd>${ex.conta && ex.conta.t ? `${hora(ex.conta.t)} (${Dd.texIdade(ex.conta.idade)})` : ex.conta ? esc(ex.conta.razao || ex.conta.estado) : "–"}</dd>
      <dt>Último pedido desta página</dt><dd>${hora((A.res[S.id === "OKX" ? "okx" : "scan"] || {}).pedido)}${(A.res[S.id === "OKX" ? "okx" : "scan"] || {}).tentativas > 1 ? ` · ${(A.res[S.id === "OKX" ? "okx" : "scan"]).tentativas} tentativas` : ""}</dd></dl>
      ${conta}
      <h4>Posições (${ops.posicoes.length})</h4>${tabelaPos(ops.posicoes)}
      ${S.id === "OKX" ? `<h4>Ordens pendentes (${ops.ordens.length})</h4>${tabelaOrd(ops.ordens)}` : `<h4>Sinais reais não executados (${ops.sinais_nao_executados.length})</h4>${lista(ops.sinais_nao_executados.map(s => [`${s.ativo} ${s.lado}`, `${s.estrategia} · ${s.motivo}`]), "Nenhum.")}`}
      <h4>Reconciliação com a corretora</h4>${rec.estado === "por_verificar" ? `<p class="nota">${esc(rec.razao)}</p>` : lista(rec.itens.map(i => [`<span class="${i.estado === "confere" ? "up" : "dn"}">${i.estado === "confere" ? "✓" : "✗"}</span> ${esc(i.ativo)}`, esc(i.texto)]), "Sem posições nem ordens para comparar.", true)}
      <h4>Histórico de operações</h4>${S.id === "OKX" ? historicoOkx(c) : lista(c.fechadas.bybit.slice(0, 12).map(f => [`${f.ativo} ${f.lado}`, `${f.estrategia} · ${f.R != null ? sg(f.R) + "R" : "–"} · ${hora(f.t)}`]), "Sem operações fechadas.")}`;
  } else if (S.k === "posicao") {
    const p = c.posicoes.find(x => x.corretora === S.id.split(":")[0] && x.ativo === S.id.split(":")[1]);
    if (!p) { el.innerHTML = `<p class="nota">Esta posição já não está aberta.</p>`; return; }
    $("#insp-titulo").textContent = `${p.ativo} · ${p.lado} · ${p.corretora}`;
    const e = p.entrada || p.entrada_corretora, at = p.atual || (A.velas[p.ativo + ":1h"] && (A.velas[p.ativo + ":1h"].velas.slice(-1)[0] || {}).c);
    const R = e && p.stop && at ? (p.lado === "LONG" ? (at - e) / (e - p.stop) : (e - at) / (p.stop - e)) : null;
    el.innerHTML = `<div class="kv"><div><span>Estratégia</span><b>${esc(p.estrategia)}</b></div><div><span>Instrumento</span><b>${esc(p.inst || p.ativo)}</b></div>
      <div><span>Quantidade</span><b>${p.quantidade != null ? num(p.quantidade, 4) : "🔒"}</b></div><div><span>Entrada</span><b>${px(e)}</b></div>
      <div><span>Preço atual</span><b>${px(at)}</b>${!p.atual && at ? `<small style="display:block;color:var(--fr);font-size:10.5px">último fecho 1H · ${esc((A.velas[p.ativo + ":1h"] || {}).fonte || "")}</small>` : ""}</div><div><span>R atual</span><b class="${R >= 0 ? "up" : "dn"}">${R == null ? "–" : sg(R) + "R"}</b></div>
      <div><span>Stop-loss</span><b>${px(p.stop)}</b></div><div><span>Take-profit</span><b>${px(p.alvo)}</b></div>
      <div><span>PnL não realizado</span><b class="${p.pnl_usd >= 0 ? "up" : "dn"}">${p.pnl_usd != null ? sg(p.pnl_usd) + " USD (" + sg(p.pnl_pct) + "%)" : "🔒"}</b></div>
      <div><span>Margem · alavancagem</span><b>${p.margem_usd != null ? num(p.margem_usd) + " USD · " : ""}${p.alav || "–"}x</b></div>
      <div><span>Risco planeado</span><b>${p.risco_pct != null ? num(p.risco_pct) + "% da conta" : "–"}</b></div><div><span>Liquidação</span><b>${px(p.liquidacao)}</b></div></div>
      <dl><dt>Stop confirmado na corretora</dt><dd>${p.stop_confirmado ? `${hora(p.stop_confirmado)} (${Dd.texIdade(Dd.idade(p.stop_confirmado))})` : p.corretora === "OKX" ? '<span class="dn">sem confirmação</span>' : "–"}</dd>
      <dt>Aberta desde</dt><dd>${hora(p.desde)}</dd>${p.sair_em ? `<dt>Saída por tempo</dt><dd>${hora(p.sair_em)}</dd>` : ""}<dt>Fonte</dt><dd>${esc(p.fonte)}${p.parcial ? " · execução parcial" : ""}</dd></dl>
      <div class="graf" data-graf="${esc(p.ativo)}" data-inst="${esc(p.inst || "")}" data-linhas='${JSON.stringify([{ nome: "entrada", v: e, cor: "#C9D6E8" }, { nome: "stop", v: p.stop, cor: "#F0616D" }, { nome: "objetivo", v: p.alvo, cor: "#3FD68F" }])}'><canvas height="380"></canvas></div>
      <div class="acoes"><button data-acao="ativo:${esc(p.ativo)}">Análise do ativo</button></div>`;
    if (at == null && !S.reav) desenharGraficos(el).then(() => { if (A.sel === S && (A.velas[p.ativo + ":1h"] || {}).velas?.length) { S.reav = true; renderInspector(); } });
    else desenharGraficos(el);
  } else if (S.k === "ativo") {
    const at = S.id, iv = S.extra || "1h";
    $("#insp-titulo").textContent = `${at} · análise técnica`;
    const dv = Dd.derivadosDe(c.Dv, at), lq = Dd.liquidezDe(c.L, at), u = ((c.S || {}).universe || []).find(r => r.asset === at);
    el.innerHTML = `<div class="seg">${["1h", "4h", "1d"].map(x => `<button class="${x === iv ? "on" : ""}" data-acao="ativo:${esc(at)}:${x}">${x.toUpperCase()}</button>`).join("")}</div>
      <div class="graf" data-graf="${esc(at)}" data-iv="${iv}"><canvas height="460"></canvas></div>
      <div class="kv">${u ? `<div><span>Preço (scanner)</span><b>${px(u.price)}</b></div><div><span>24 h</span><b class="${u.chg_24h >= 0 ? "up" : "dn"}">${sg(u.chg_24h)}%</b></div><div><span>Volume 24 h</span><b>${num(u.volume_24h / 1e6, 1)} M$</b></div>` : ""}
      <div><span>Volatilidade (ATR 14)</span><b id="atr">–</b></div>
      ${lq ? `<div><span>Spread (liquidez)</span><b>${num(lq.spread_pct, 3)}%</b></div><div><span>Volume (liquidez)</span><b>${num(lq.volume_usd / 1e6, 1)} M$</b></div>` : `<div><span>Liquidez</span><b>sem amostras</b></div>`}</div>
      <div class="graf" data-serie="funding" data-ativo="${esc(at)}"><canvas height="150"></canvas></div>
      <div class="graf" data-serie="oi" data-ativo="${esc(at)}"><canvas height="150"></canvas></div>
      <div class="graf" data-livro="${esc(at)}"><canvas height="170"></canvas></div>
      ${dv ? `<small>Derivados: ${hora(dv.t[dv.t.length - 1])} · fonte data/derivados.json</small>` : `<small>Sem série de derivados para ${esc(at)}.</small>`}`;
    desenharGraficos(el);
  } else if (S.k === "zona") {
    $("#insp-titulo").textContent = ZONAS_NOMES[S.id] || S.id;
    const ag = AGENTES.filter(a => a.zona === S.id);
    el.innerHTML = `<p class="nota">${esc(ZONA_TXT[S.id] || "")}</p>${ag.length ? `<h4>Agentes nesta zona</h4>` + ag.map(a => { const s = c.estados[a.id], E = ESTADOS[s.estado]; return `<button class="linha" data-acao="agente:${a.id}"><b>${esc(a.nome)}</b> <span style="color:${E.cor}">● ${esc(E.nome)}</span><small>${esc(s.atividade)}</small></button>`; }).join("") : ""}
      ${S.id === "exchanges" ? `<div class="acoes"><button data-acao="corretora:OKX">OKX</button><button data-acao="corretora:Bybit">Bybit</button></div>` : ""}
      ${S.id === "global" ? `<div class="acoes"><button data-acao="mercado">Mercado global</button><button data-acao="ativo:BTC">BTC</button></div>` : ""}`;
  }
}

const ZONAS_NOMES = { comando: "Centro de comando", operacoes: "Mesa de operações", quant: "Análise quantitativa", risco: "Gestão de risco", exchanges: "Monitorização das corretoras", colaboracao: "Colaboração entre agentes", global: "Monitorização global" };
const ZONA_TXT = {
  comando: "Painel central de atividade e alertas, consolas das corretoras e a diretora de estratégia.",
  operacoes: "Scanner da Bybit, caçador de pânico e recuo na OKX, agente macro (ações, índices e metais).",
  quant: "Arena de estratégias e TF-SHORT (papel e sombra).", risco: "Gestor de risco e liquidez/derivados.",
  exchanges: "Execução e posições reais na OKX e na Bybit, núcleo BTC, servidores e faróis de ligação.",
  colaboracao: "Encaminhamentos reais entre agentes e calendário macro.", global: "Mapa do mercado, BTC e estado dos mercados monitorizados.",
};

function lista(rows, vazio, html = false) {
  if (!rows.length) return `<p class="nota">${esc(vazio)}</p>`;
  return `<ul class="lst">${rows.map(([a, b]) => `<li><b>${html ? a : esc(a)}</b><span>${html ? b : esc(b)}</span></li>`).join("")}</ul>`;
}
function tabelaPos(P) {
  if (!P.length) return `<p class="nota">Sem posições abertas.</p>`;
  return `<div class="tw"><table><tr><th>Ativo</th><th>Lado</th><th>Estratégia</th><th>Entrada</th><th>Stop</th><th>Objetivo</th><th>Qtd</th><th>PnL</th></tr>${P.map(p => `<tr data-acao="posicao:${p.corretora}:${esc(p.ativo)}"><td><b>${esc(p.ativo)}</b></td><td class="${p.lado === "LONG" ? "up" : "dn"}">${p.lado}</td><td>${esc(p.estrategia)}</td><td>${px(p.entrada || p.entrada_corretora)}</td><td>${px(p.stop)}</td><td>${px(p.alvo)}</td><td>${p.quantidade != null ? num(p.quantidade, 4) : "🔒"}</td><td class="${p.pnl_usd >= 0 ? "up" : "dn"}">${p.pnl_usd != null ? sg(p.pnl_usd) + " USD" : "🔒"}</td></tr>`).join("")}</table></div>`;
}
function tabelaOrd(O) {
  if (!O.length) return `<p class="nota">Sem ordens pendentes.</p>`;
  return `<div class="tw"><table><tr><th>Ativo</th><th>Lado</th><th>Estratégia</th><th>Preço</th><th>Stop</th><th>Válida até</th><th>Qtd</th></tr>${O.map(o => `<tr><td><b>${esc(o.ativo)}</b></td><td>${o.lado || "LONG"}</td><td>${esc(o.estrategia)}</td><td>${px(o.preco || o.preco_corretora)}</td><td>${px(o.stop)}</td><td>${hora(o.valida_ate)}${o.cancelamento_pedido ? " · cancelamento pedido" : ""}</td><td>${o.quantidade != null ? num(o.quantidade, 4) : "🔒"}</td></tr>`).join("")}</table></div>`;
}
function historicoOkx(c) {
  const F = c.fechadas.okx;
  const priv = F.privado.length ? `<div class="tw"><table><tr><th>Fechada (conta)</th><th>Entrada</th><th>Saída</th><th>PnL</th><th>Hora</th></tr>${F.privado.slice(0, 10).map(f => `<tr><td>${esc(f.ativo)}</td><td>${px(f.entrada)}</td><td>${px(f.saida)}</td><td class="${f.pnl_usd >= 0 ? "up" : "dn"}">${sg(f.pnl_usd)} USD</td><td>${hora(f.t)}</td></tr>`).join("")}</table></div>` : "";
  return priv + lista(F.publico.slice(0, 10).map(h => [`${h.ativo} · ${h.estado}`, `${h.motivo || ""}${h.ret_pct != null ? ` · ${sg(h.ret_pct)}%` : ""} · ${hora(h.t)}`]), "Sem operações no histórico do agente.");
}

// ---------------------------------------------------------------- doca inferior (separadores)
function renderDoca(c) {
  const tab = $(".doca .tabs .on").dataset.tab, el = $("#doca-corpo"), F = A.filtros;
  if (tab === "posicoes") {
    const est = [...new Set([...c.posicoes, ...c.ordens].map(p => p.estrategia))];
    const filt = p => (F.corretora === "todas" || p.corretora === F.corretora) && (F.lado === "todos" || (p.lado || "LONG") === F.lado) && (F.estrategia === "todas" || p.estrategia === F.estrategia);
    el.innerHTML = `<div class="filtros">${sel("corretora", ["todas", "OKX", "Bybit"])}${sel("lado", ["todos", "LONG", "SHORT"])}${sel("estrategia", ["todas", ...est])}</div>
      <h4>Posições reais abertas</h4>${tabelaPos(c.posicoes.filter(filt))}<h4>Ordens pendentes</h4>${tabelaOrd(c.ordens.filter(filt))}
      <h4>Últimas operações</h4>${lista([...c.fechadas.okx.publico.filter(h => h.estado === "fechada").map(h => ({ ...h, txt: `${h.motivo || ""}${h.ret_pct != null ? " · " + sg(h.ret_pct) + "%" : ""}` })), ...c.fechadas.bybit.map(f => ({ ...f, txt: `${f.estrategia} · ${f.R != null ? sg(f.R) + "R" : "–"}` }))]
        .filter(x => F.corretora === "todas" || x.corretora === F.corretora).sort((a, b) => (b.t || 0) - (a.t || 0)).slice(0, 10).map(x => [`${x.corretora} ${x.ativo}`, `${x.txt} · ${hora(x.t)}`]), "Sem operações fechadas.")}`;
  } else if (tab === "eventos") {
    const ev = c.eventos.filter(e => F.agente === "todos" || e.agente === F.agente || e.para === F.agente);
    el.innerHTML = `<div class="filtros">${sel("agente", ["todos", ...AGENTES.map(a => a.id)], id => id === "todos" ? "todos os agentes" : (AGENTES.find(a => a.id === id) || {}).nome)}</div>
      ${lista(ev.slice(0, 60).map(e => [hora(e.t), `${nomeAg(e.agente)}${e.para ? " → " + nomeAg(e.para) : ""}: ${e.texto}`]), "Sem eventos.")}`;
  } else if (tab === "alertas") {
    const al = c.alertas.filter(a => F.nivel === "todos" || a.nivel === F.nivel);
    el.innerHTML = `<div class="filtros">${sel("nivel", ["todos", "critico", "aviso", "info"])}</div>${al.length ? `<ul class="lst">${al.map(a => `<li class="${a.nivel}"><b>${esc(a.nivel.toUpperCase())} · ${esc(a.origem)}</b><span>${esc(a.texto)}</span></li>`).join("")}</ul>` : `<p class="nota">Sem alertas.</p>`}`;
  } else if (tab === "mercado") {
    const S = c.S || {}, co = S.counts || {}, R = (c.O || {}).resumo || {}, MR = ((c.O || {}).macro || {}).resumo || {};
    const prox = Object.entries(Dd.FONTES).filter(([, f]) => f.periodo).map(([k, f]) => { const t = c.fontes[k].t; return [f.nome, t ? `próxima ≈ ${hora(t + f.periodo)}` : esc(c.fontes[k].estado)]; });
    el.innerHTML = `<div class="grelha3">
      <section><h4>Mercados monitorizados</h4>${lista([
        ["Cripto global (scanner)", `${co.pairs_seen ?? "–"} pares vistos · ${Object.entries(S.sources || {}).map(([n, s]) => `${n} ${s.ok ? "✓" : "✗"}`).join(" ")}`],
        ["Bybit UE (spot USDC)", `${(S.venue_source || {}).pairs ?? "–"} pares ${(S.venue_source || {}).ok ? "✓" : "✗"}`],
        ["OKX EEA perpétuos de cripto", `${R.analisados ?? "–"} analisados`],
        ["OKX ações, índices e metais", `${MR.analisados ?? "–"} analisados (${(MR.abertas || []).length} em tendência)`]], "–")}</section>
      <section><h4>Ativos em análise e sinais</h4>${lista([["Elegíveis / analisados", `${co.eligible ?? "–"} / ${co.deep_checked ?? "–"}`], ["Sinais gerados (LONG/SHORT)", `${co.long ?? 0} / ${co.short ?? 0}`],
        ["A vigiar", `${(co.watchlist || 0) + (co.watch_short || 0)}`], ["Sem operação", `${co.no_trade ?? "–"}`], ["Regime BTC", (S.market_regime || {}).btc || "–"]], "–")}</section>
      <section><h4>Oportunidades detetadas</h4>${lista(c.oportunidades.slice(0, 10).map(o => [`${o.ativo} ${o.lado}`, `${o.fonte}: ${o.texto}`]), "Nenhuma oportunidade nesta passagem.")}</section>
      <section><h4>Sinais rejeitados e motivos</h4>${lista(c.rejeicoes.slice(0, 8).map(r => [String(r.n), r.motivo]), "Sem rejeições registadas.")}</section>
      <section><h4>Estratégias em avaliação (arena)</h4>${lista((((S.arena || {}).classificacao) || []).filter(x => x.estado !== "MORTA").slice(0, 8).map(x => [x.id, `${x.estado} · n ${x.n} · ${x.avg_r == null ? "–" : sg(x.avg_r) + "R"}`]), "Sem dados da arena.")}</section>
      <section><h4>Atividade dos agentes · próximas atualizações</h4>${lista(Object.entries(ESTADOS).map(([k, E]) => [E.nome, String(AGENTES.filter(a => c.estados[a.id].estado === k).length)]).filter(x => x[1] !== "0"), "–")}${lista(prox, "–")}</section></div>
      <h4>Mapa do mercado (24 h, preços do scanner)</h4><div class="mapa">${((S.universe || []).slice().sort((a, b) => (b.volume_24h || 0) - (a.volume_24h || 0)).slice(0, 40)).map(u => `<button data-acao="ativo:${esc(u.asset)}" style="--k:${Math.max(-1, Math.min(1, (u.chg_24h || 0) / 8))}"><b>${esc(u.asset)}</b>${sg(u.chg_24h)}%</button>`).join("") || '<p class="nota">Sem universo publicado.</p>'}</div>`;
  } else if (tab === "estrategias") {
    el.innerHTML = `<div class="tw"><table><tr><th>Estratégia</th><th>Corretora</th><th>Dinheiro</th><th>Estado</th><th>Notas</th></tr>${c.estrategias.map(e => `<tr><td><b>${esc(e.nome)}</b></td><td>${esc(e.corretora)}</td><td>${esc(e.dinheiro)}</td><td class="${e.ativa ? "up" : "dn"}">${e.ativa ? "ativa" : "suspensa"}</td><td>${esc(e.razao || "")}</td></tr>`).join("")}</table></div><small>Lido de okx_config.json (main), scan.json e state.json. Esta página não altera nenhuma estratégia.</small>`;
  } else if (tab === "fontes") {
    el.innerHTML = `<div class="tw"><table><tr><th>Fonte</th><th>Estado</th><th>Última atualização</th><th>Último pedido</th><th>Razão</th></tr>${Object.entries(c.fontes).map(([k, f]) => `<tr><td>${esc(Dd.FONTES[k].nome)}</td><td class="st-${f.estado}">${esc(f.estado)}</td><td>${f.t ? hora(f.t) + " (" + Dd.texIdade(f.idade) + ")" : "–"}</td><td>${hora((A.res[k] || {}).pedido)}${(A.res[k] || {}).tentativas > 1 ? ` (${A.res[k].tentativas} tentativas)` : ""}</td><td>${esc(f.razao || "")}</td></tr>`).join("")}</table></div>
      <small>As corretoras são lidas pelos agentes (com as chaves só nos segredos do GitHub); a página lê o que eles publicam. Os cofres abrem só neste aparelho com a tua palavra-passe. ${A.of ? `3D: ${A.of.qualidade} · ${A.of.fps} fps.` : "3D desligado."}</small>`;
  }
}
const nomeAg = id => id === "centro" ? "Centro de comando" : ((AGENTES.find(a => a.id === id) || {}).nome || id);
function sel(k, ops, rot = x => x) { return `<label>${k}<select data-filtro="${k}">${ops.map(o => `<option value="${esc(o)}" ${A.filtros[k] === o ? "selected" : ""}>${esc(rot(o))}</option>`).join("")}</select></label>`; }

// ---------------------------------------------------------------- graficos do inspector (dados reais, com fonte)
async function obterVelas(at, iv = "1h") {
  const k = `${at}:${iv}`, v = A.velas[k];
  if (v && Date.now() - v.at < ({ "1h": 120e3, "4h": 600e3, "1d": 1800e3 }[iv])) return v;
  const r = await Dd.velas(at, { intervalo: iv }); r.at = Date.now(); A.velas[k] = r; return r;
}
function ajustar(cv) { const w = cv.parentElement.clientWidth || 320, h = +cv.getAttribute("height"); const d = Math.min(2, devicePixelRatio || 1);
  cv.width = w * d; cv.height = h * d; cv.style.width = w + "px"; cv.style.height = h + "px"; const g = cv.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0); return [g, w, h]; }
async function desenharGraficos(root) {
  for (const box of root.querySelectorAll(".graf")) {
    const cv = box.querySelector("canvas"); let [g, w, h] = ajustar(cv);
    if (box.dataset.graf) {
      Gx.indisponivel(g, w, h, "A carregar velas…", "OKX → Binance");
      const r = await obterVelas(box.dataset.graf, box.dataset.iv || "1h"); [g, w, h] = ajustar(cv);
      if (!r.velas.length) Gx.indisponivel(g, w, h, `${box.dataset.graf}: gráfico indisponível`, r.erro);
      else { Gx.velasCompleto(g, w, h, r.velas, { titulo: `${box.dataset.graf} · ${(box.dataset.iv || "1h").toUpperCase()}`, fonte: r.fonte, linhas: box.dataset.linhas ? JSON.parse(box.dataset.linhas) : [] });
             const a = Dd.atrPct(r.velas); const x = root.querySelector("#atr"); if (x) x.textContent = a == null ? "–" : num(a) + "% por vela"; }
    } else if (box.dataset.serie) {
      const dv = Dd.derivadosDe(A.ctx.Dv, box.dataset.ativo), fu = box.dataset.serie === "funding";
      if (!dv) Gx.indisponivel(g, w, h, fu ? "Funding" : "Open Interest", "sem série para este ativo em derivados.json");
      else Gx.serie(g, w, h, dv.t, fu ? dv.funding : dv.oi, { titulo: fu ? "Funding (%, 8 h)" : "Open Interest (M$)", unidade: fu ? "%" : " M$", cor: fu ? Gx.COR.violeta : Gx.COR.acento, fonte: "derivados.json", zero: fu });
    } else if (box.dataset.livro) {
      Gx.indisponivel(g, w, h, "Livro de ordens", "a carregar…");
      const L = await Dd.livro(box.dataset.livro); [g, w, h] = ajustar(cv); Gx.livroOrdens(g, w, h, L, { titulo: `Livro de ordens · ${box.dataset.livro}` });
    }
  }
}

// ---------------------------------------------------------------- ecras do escritorio 3D (texturas)
function desenharEcra(e, g, w, h) {
  const c = A.ctx; if (!c) return Gx.indisponivel(g, w, h, "A carregar…", "");
  const st = id => c.estados[id] || {};
  const T = (t, rows, o) => Gx.ecraTabela(g, w, h, t, rows, o);
  const O = c.O || {}, S = c.S || {}, K = c.K;
  switch (e.id) {
    case "scanner": { const v = A.velas["BTC:4h"]; if (v && v.velas.length) return Gx.velasCompleto(g, w, h, v.velas, { titulo: "BTC · 4H", fonte: v.fonte, rsiOn: true, macdOn: false });
      return T("Scanner Bybit UE", ((S.universe || []).slice().sort((a, b) => Math.abs(b.chg_24h || 0) - Math.abs(a.chg_24h || 0)).slice(0, 8)).map(u => [u.asset, `${px(u.price)} · ${sg(u.chg_24h)}%`, u.chg_24h >= 0 ? Gx.COR.sobe : Gx.COR.desce]), { cor: "#5AA9FF", rodape: `passagem ${hora(S.generated_at)}` }); }
    case "panico": return T("Radar de pânico · OKX", (((O.radar || {}).lista) || []).slice(0, 8).map(r => [r.a, `queda 3d ${r.q}% · funding ${num((r.f || 0) * 100, 3)}%`, "#3EE0C4"]), { cor: "#3EE0C4", rodape: `${(O.resumo || {}).analisados ?? "–"} perpétuos · ${hora((O.resumo || {}).t)}` });
    case "recuo": { const r = (O.recuo || {}).resumo || {}; return T("Recuo na subida · H46", [["BTC em subida", r.btc_em_subida ? "sim" : "não", r.btc_em_subida ? Gx.COR.sobe : Gx.COR.fraco], ["Pendentes", String((r.pendentes || []).length)], ["Abertas (papel)", String((r.abertas || []).length)], ["Operações medidas", String((r.metricas || {}).n ?? 0)], ["Real", c.cfgOkx && c.cfgOkx.recuo_real ? `ligado · risco ${c.cfgOkx.recuo_risco_pct}%` : "suspenso"]], { cor: "#45C9A6" }); }
    case "macro": { const M = (O.macro || {}).resumo || {}; return T("Ações, índices e metais", [["Analisados", String(M.analisados ?? "–")], ["Em tendência", String((M.abertas || []).length)], ...(M.abertas || []).slice(0, 5).map(a => ["  " + a, "acima da MM50", Gx.COR.sobe]), ["Fechadas (papel)", `${M.n ?? 0} · média ${M.ret_medio_pct != null ? sg(M.ret_medio_pct) + "%" : "–"}`]], { cor: "#E9A15B", rodape: "papel · OKX" }); }
    case "diretor": return T("Decisões da direção", ((S.diretor || {}).decisoes || []).slice(-8).reverse().map(d => [`${d.ativo} ${d.lado}`, `${d.decisao} · ${hora(d.t)}`, d.decisao === "AUTORIZADO" ? Gx.COR.sobe : Gx.COR.desce]), { cor: "#C8D3E6" });
    case "risco": { const cf = c.cfgOkx || {}, ab = c.opOkx.posicoes.reduce((s, p) => s + (p.risco_pct || 0), 0); return T("Gestão de risco", [["Risco aberto OKX", `${num(ab)}% / teto ${cf.risco_total_max_pct ?? "–"}%`, ab > (cf.risco_total_max_pct || 3) ? Gx.COR.desce : Gx.COR.sobe], ["Risco por operação", `${cf.risco_pct ?? "–"}% (máx ${cf.risco_max_pct ?? "–"}%)`], ["Alavancagem", `${cf.alavancagem ?? "–"}x isolada`], ["Travão", `queda de ${cf.travao_queda_pct ?? "–"}%`], ["LONG / SHORT reais", `${c.exposicao.long} / ${c.exposicao.short}`], ["Alertas críticos", String(c.alertas.filter(a => a.nivel === "critico").length), c.alertas.some(a => a.nivel === "critico") ? Gx.COR.desce : Gx.COR.sobe]], { cor: "#F5B83D", rodape: "okx_config.json (main)" }); }
    case "liquidez": { const d = Dd.derivadosDe(c.Dv, "BTC"); return d ? Gx.serie(g, w, h, d.t, d.funding, { titulo: "BTC · funding (%)", unidade: "%", cor: Gx.COR.violeta, fonte: "derivados.json", zero: true }) : Gx.indisponivel(g, w, h, "Derivados", "sem série publicada"); }
    case "exec_okx": return T("OKX · posições reais", [...c.opOkx.posicoes.map(p => [`${p.ativo} ${p.lado}`, p.pnl_pct != null ? `${sg(p.pnl_pct)}% · stop ${px(p.stop)}` : `entrada ${px(p.entrada)} · stop ${px(p.stop)}`, p.pnl_pct == null ? Gx.COR.texto : p.pnl_pct >= 0 ? Gx.COR.sobe : Gx.COR.desce]),
      ...c.opOkx.ordens.map(o => [`${o.ativo} (ordem)`, `a ${px(o.preco)}`, "#F5B83D"])].concat(c.opOkx.posicoes.length || c.opOkx.ordens.length ? [] : [["Sem posições nem ordens", "", Gx.COR.fraco]]), { cor: "#E6EDF7", rodape: `${LIG[c.okx.ligacao][1]} · ${hora(st("exec_okx").t)}` });
    case "exec_bybit": return T("Bybit UE · operações reais", [...c.opBy.posicoes.map(p => [`${p.ativo} ${p.lado}`, p.estrategia]), ...c.opBy.sinais_nao_executados.slice(0, 4).map(s => [`${s.ativo} ${s.lado}`, "sinal não executado", Gx.COR.fraco])].concat(c.opBy.posicoes.length ? [] : [["Sem posições do motor", "", Gx.COR.fraco]]), { cor: "#F7A600", rodape: LIG[c.bybit.ligacao][1] });
    case "nucleo": { if (!c.P) return Gx.indisponivel(g, w, h, "Núcleo BTC", "dados só no cofre cifrado"); const N = (((c.P.nucleo || {}).plano || {}).BTC) || {}; return T("Tendência BTC · núcleo", [["Estado", N.acima ? "comprado" : "fora", N.acima ? Gx.COR.sobe : Gx.COR.fraco], ["Média 50 dias", px(N.media)]], { cor: "#F2B13C" }); }
    case "arena": return T("Arena · classificação", (((S.arena || {}).classificacao) || []).filter(x => x.estado !== "MORTA").slice(0, 8).map(x => [x.id.slice(0, 26), `${x.estado} · n ${x.n}`, x.live ? Gx.COR.sobe : Gx.COR.fraco]), { cor: "#B59CFF", rodape: `${(S.arena || {}).vivos ?? "–"} vivas · ${hora((S.arena || {}).atualizado)}` });
    case "tfshort": { const ab = Object.entries((((c.T || {}).sinais || {}).abertas) || {}); return T("TF-SHORT · papel", ab.slice(0, 8).map(([a, v]) => [a, `entrada ${px(v.entrada)} · stop ${px(v.stop)}`, Gx.COR.desce]).concat(ab.length ? [] : [["Sem posições em papel", ""]]), { cor: "#9C8CFF" }); }
    case "noticias": { const ev = S.next_event; return T("Calendário macro", [["Próximo evento", ev ? ev.name : "nenhum"], ["Quando", ev ? hora(ev.t) : "–"], ["Janela de risco", S.event_block ? "ativa" : "não", S.event_block ? "#F5B83D" : Gx.COR.sobe]], { cor: "#7FE3FF" }); }
    case "atividade": {
      g.fillStyle = "#04080E"; g.fillRect(0, 0, w, h); g.fillStyle = "#3EE0C4"; g.fillRect(0, 0, w, 5);
      g.fillStyle = Gx.COR.texto; g.font = "700 34px Inter, system-ui"; g.fillText("Atividade e alertas", 28, 50);
      const gl = estadoGlobal(c); g.textAlign = "right"; g.fillStyle = gl.k === "ok" ? Gx.COR.sobe : gl.k === "aviso" ? "#F5B83D" : Gx.COR.desce; g.fillText(gl.t, w - 28, 50); g.textAlign = "left";
      g.font = "600 22px Inter, system-ui"; g.fillStyle = Gx.COR.fraco; g.fillText("ÚLTIMOS EVENTOS", 28, 96); g.fillText("ALERTAS", w * .62, 96);
      g.font = "21px Inter, system-ui"; c.eventos.slice(0, 11).forEach((ev, i) => { g.fillStyle = Gx.COR.fraco; g.fillText(hora(ev.t), 28, 134 + i * 34); g.fillStyle = Gx.COR.texto; g.fillText(`${nomeAg(ev.agente)}: ${ev.texto}`.slice(0, 58), 170, 134 + i * 34); });
      const al = c.alertas.slice(0, 10); if (!al.length) { g.fillStyle = Gx.COR.sobe; g.fillText("Sem alertas", w * .62, 134); }
      al.forEach((a, i) => { g.fillStyle = a.nivel === "critico" ? Gx.COR.desce : a.nivel === "aviso" ? "#F5B83D" : "#7FE3FF"; g.fillText(`● ${a.texto}`.slice(0, 44), w * .62, 134 + i * 34); });
      return;
    }
    case "corretoras": return T("Corretoras", [["OKX EEA", LIG[c.okx.ligacao][1], c.okx.ligacao === "ligado" ? Gx.COR.sobe : c.okx.ligacao === "falhou" ? Gx.COR.desce : "#3EE0C4"], ["  posições · ordens", `${c.opOkx.posicoes.length} · ${c.opOkx.ordens.length}`], ["Bybit UE", LIG[c.bybit.ligacao][1], c.bybit.ligacao === "ligado" ? Gx.COR.sobe : c.bybit.ligacao === "falhou" ? Gx.COR.desce : "#3EE0C4"], ["  posições", String(c.opBy.posicoes.length)], ["Reconciliação", c.recOkx.estado === "confere" && c.recBybit.estado !== "discrepancia" ? "confere" : c.recOkx.estado.replace("_", " "), c.recOkx.estado === "discrepancia" ? Gx.COR.desce : Gx.COR.texto]], { cor: "#3EE0C4" });
    case "mapa": {
      const U = (S.universe || []).slice().sort((a, b) => (b.volume_24h || 0) - (a.volume_24h || 0)).slice(0, 40);
      g.fillStyle = "#04080E"; g.fillRect(0, 0, w, h); g.fillStyle = Gx.COR.texto; g.font = "700 30px Inter, system-ui"; g.fillText("Mercado cripto · 24 h", 24, 44);
      g.font = "18px Inter"; g.fillStyle = Gx.COR.fraco; g.textAlign = "right"; g.fillText(`scanner · ${hora(S.generated_at)}`, w - 24, 44); g.textAlign = "left";
      if (!U.length) return Gx.indisponivel(g, w, h, "Mercado", "universo não publicado");
      const cols = 8, cw = (w - 40) / cols, ch = (h - 80) / 5;
      U.forEach((u, i) => { const x = 20 + (i % cols) * cw, y = 64 + Math.floor(i / cols) * ch, k = Math.max(-1, Math.min(1, (u.chg_24h || 0) / 8));
        g.fillStyle = k >= 0 ? `rgba(63,214,143,${.12 + .55 * k})` : `rgba(240,97,109,${.12 - .55 * k})`; g.fillRect(x + 3, y + 3, cw - 6, ch - 6);
        g.fillStyle = "#E8F0FA"; g.font = "700 22px Inter"; g.fillText(u.asset, x + 14, y + ch / 2); g.font = "18px Inter"; g.fillText(`${sg(u.chg_24h)}%`, x + 14, y + ch / 2 + 26); });
      return;
    }
    case "btc": { const v = A.velas["BTC:4h"]; return v && v.velas.length ? Gx.velasCompleto(g, w, h, v.velas, { titulo: "BTC · 4H", fonte: v.fonte }) : Gx.indisponivel(g, w, h, "BTC · 4H", (v && v.erro) || "a carregar velas…"); }
    case "mercados": return T("Mercados monitorizados", [["Cripto global (scanner)", `${(S.counts || {}).pairs_seen ?? "–"} pares`], ["Bybit UE spot USDC", `${(S.venue_source || {}).pairs ?? "–"} pares`], ["OKX perpétuos cripto", `${(O.resumo || {}).analisados ?? "–"}`], ["OKX ações/índices/metais", `${((O.macro || {}).resumo || {}).analisados ?? "–"}`], ["Regime BTC", (S.market_regime || {}).btc || "–"], ["Oportunidades", String(c.oportunidades.filter(o => !o.perto).length)], ["Próximo evento", S.next_event ? S.next_event.name : "–"]], { cor: "#5AA9FF" });
    case "colaboracao": return T("Encaminhamentos reais (6 h)", c.colab.slice(0, 8).map(x => [`${nomeAg(x.de)} → ${nomeAg(x.para)}`, `${hora(x.t)}`, "#7FE3FF"]).concat(c.colab.length ? [] : [["Sem encaminhamentos nas últimas 6 h", "os agentes estão em espera", Gx.COR.fraco]]), { cor: "#7FE3FF" });
    default: return Gx.indisponivel(g, w, h, e.id, "sem conteúdo");
  }
}

// ---------------------------------------------------------------- ciclo principal
function renderTudo() {
  A.ctx = contexto(); const c = A.ctx;
  renderTopo(c); renderAgentes(c); renderDoca(c); if (A.sel && A.sel.k !== "ativo" && A.sel.k !== "posicao") renderInspector();
  if (A.of) A.of.atualizar({ estados: c.estados, colaboracoes: c.colab, ligacoes: { OKX: c.okx.ligacao, Bybit: c.bybit.ligacao } });
  $("#sinc").textContent = `sincronizado ${new Date().toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
  document.body.classList.toggle("carregado", true);
}

async function arrancar() {
  ligarEventos();
  iniciar3D(localStorage.getItem("cs_vista") || "auto");
  await Promise.all(Object.keys(Dd.FONTES).map(k => carregar(k)));
  renderTudo(); A.carregado = true;
  obterVelas("BTC", "4h").then(() => { if (A.of) A.of.redesenharEcras(); });
  for (const [k, s] of Object.entries(REFRESCO)) setInterval(async () => { if (document.hidden) return; await carregar(k); renderTudo(); }, s * 1000);
  setInterval(() => { if (!document.hidden && A.ctx) { renderTopo(contexto()); } }, 30000);
  setInterval(() => { if (!document.hidden) obterVelas("BTC", "4h").then(() => A.of && A.of.redesenharEcras()); }, 600000);
}

async function iniciar3D(q) {
  const palco = $("#palco");
  if (A.of) { A.of.destruir(); A.of = null; }
  if (q === "2d") { A.modo = "2d"; document.body.classList.add("modo2d"); marcarVista("2d"); return; }
  document.body.classList.remove("modo2d");
  try {
    const { Escritorio } = await import("./escritorio.js");
    A.of = new Escritorio(palco, { qualidade: q === "baixa" || q === "alta" ? q : "auto", desenharEcra,
      onAgente: id => abrir("agente", id), onZona: (z, ecra) => { if (ecra === "btc") abrir("ativo", "BTC", "4h"); else if (ecra === "mapa" || ecra === "mercados") { tab("mercado"); } else abrir("zona", z); A.of.focar(z); } });
    A.modo = "3d"; marcarVista(A.of.qualidade); margens();
    if (A.ctx) A.of.atualizar({ estados: A.ctx.estados, colaboracoes: A.ctx.colab, ligacoes: { OKX: A.ctx.okx.ligacao, Bybit: A.ctx.bybit.ligacao } });
  } catch (e) {
    console.warn("3D indisponível:", e && e.message);
    A.modo = "2d"; document.body.classList.add("modo2d"); marcarVista("2d");
    palco.insertAdjacentHTML("beforeend", `<p class="sem3d">O 3D não arrancou neste aparelho (${esc(e && e.message || "WebGL")}). O centro de comando funciona na mesma.</p>`);
  }
}
function marcarVista(v) { $$("#vista button").forEach(b => b.classList.toggle("on", b.dataset.vista === v)); }
function tab(t) { $$(".doca .tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t)); $(".doca").classList.remove("min"); if (A.ctx) renderDoca(A.ctx); }

function ligarEventos() {
  document.addEventListener("click", async ev => {
    const b = ev.target.closest("[data-acao]"); if (!b) return;
    const [k, x, y] = b.dataset.acao.split(":");
    if (k === "agente") abrir("agente", x);
    else if (k === "corretora") abrir("corretora", x);
    else if (k === "posicao") abrir("posicao", `${x}:${y}`);
    else if (k === "ativo") abrir("ativo", x, y);
    else if (k === "focar") A.of && A.of.focar(x);
    else if (k === "eventos") { A.filtros.agente = x; tab("eventos"); }
    else if (k === "posicoes" || k === "ordens" || k === "pnl") tab("posicoes");
    else if (k === "alertas" || k === "global") tab("alertas");
    else if (k === "mercado") tab("mercado");
    else if (k === "estrategias") tab("estrategias");
    else if (k === "fontes") tab("fontes");
    else if (k === "agentes") { $("#agentes").classList.remove("min"); $("#lista-agentes").scrollTop = 0; }
    else if (k === "cofre") await alternarCofre();
    else if (k === "zona") { A.of && A.of.focar(x); abrir("zona", x); }
    else if (k === "tudo") { A.of && A.of.focar("tudo"); }
  });
  $$(".doca .tabs button").forEach(b => b.addEventListener("click", () => tab(b.dataset.tab)));
  document.addEventListener("change", e => { const s = e.target.closest("[data-filtro]"); if (!s) return; A.filtros[s.dataset.filtro] = s.value; renderDoca(A.ctx); });
  $("#insp-fechar").addEventListener("click", fechar);
  $$("[data-min]").forEach(b => b.addEventListener("click", () => { const p = b.closest(".painel"); p.classList.toggle("min"); b.textContent = p.classList.contains("min") ? "▢" : "–"; b.title = p.classList.contains("min") ? "Expandir" : "Minimizar"; margens(); }));
  $$("[data-max]").forEach(b => b.addEventListener("click", () => { const p = b.closest(".painel"); p.classList.toggle("max"); p.classList.remove("min"); margens(); }));
  addEventListener("resize", () => margens());
  $$("#vista button").forEach(b => b.addEventListener("click", () => { try { localStorage.setItem("cs_vista", b.dataset.vista); } catch (_) {} iniciar3D(b.dataset.vista); }));
  addEventListener("keydown", e => { if (e.key === "Escape") fechar(); });
  setInterval(() => { $("#relogio").textContent = new Date().toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" }) + " Lisboa · " + new Date().toISOString().slice(11, 16) + " UTC"; }, 1000);
}

async function alternarCofre() {
  const aberto = !!(A.aberto.cofreOkx || A.aberto.cofreScan);
  if (aberto) { if (window.CIFRA) window.CIFRA.esquecer(); A.aberto = { cofreScan: null, cofreOkx: null }; renderTudo(); return; }
  await abrirCofre("cofreOkx", true); await abrirCofre("cofreScan", false); renderTudo();
}

arrancar().catch(e => { console.error(e); const el = document.getElementById("erro-arranque"); if (el) { el.hidden = false; el.textContent = "Erro ao arrancar: " + (e && e.message); } });
