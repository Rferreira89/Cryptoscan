// CryptoScan · Operations Center — camada de dados (so leitura).
//
// De onde vem cada dado (nada aqui e inventado):
//   * copias publicas que os agentes publicam no repositorio (ramos data, okx, okx-tfshort, main): estados, sinais,
//     precos, resultados em R. Sem dinheiro (engine/publico.py tira-o).
//   * cofres cifrados (cofre_scan.json, cofre_okx.json): saldos, quantidades e PnL das contas reais. So abrem com a
//     palavra-passe do Rui, neste aparelho (scanner/cifra.js). Nunca ha chaves das corretoras no browser.
//   * mercado publico das corretoras (Bybit UE, OKX EEA), sem chaves: velas, livro de ordens.
// A ligacao as corretoras e indireta: o agente de cada uma le a conta e publica o cofre. "Ligada" = a ultima leitura
// privada desse agente e recente; se o pedido falhou ou a leitura e velha, mostra-se o estado certo e a razao.
// Este modulo nao tem DOM: e testado em Node (scanner/central/testes/).

export const RAW = "https://raw.githubusercontent.com/Rferreira89/Cryptoscan/";

// periodo: de quanto em quanto tempo a fonte e atualizada (s); limite: a partir de quando a leitura ja nao e "atual".
export const FONTES = {
  scan:      { url: RAW + "data/scan.json",            nome: "Scanner Bybit (copia publica)",  periodo: 300,  limite: 1200 },
  cofreScan: { url: RAW + "data/cofre_scan.json",      nome: "Conta Bybit (cofre cifrado)",    periodo: 300,  limite: 1800, cifrado: true },
  state:     { url: RAW + "data/state.json",           nome: "Estado do motor (publico)",      periodo: 300,  limite: 1200 },
  okx:       { url: RAW + "okx/okx.json",              nome: "Agente OKX (copia publica)",     periodo: 3600, limite: 9000 },
  cofreOkx:  { url: RAW + "okx/cofre_okx.json",        nome: "Conta OKX (cofre cifrado)",      periodo: 3600, limite: 9000, cifrado: true },
  cfgOkx:    { url: RAW + "main/okx_config.json",      nome: "Configuracao OKX (main)",        periodo: 0,    limite: 0 },
  derivados: { url: RAW + "data/derivados.json",       nome: "Derivados (funding, OI)",        periodo: 3600, limite: 9000 },
  liquidez:  { url: RAW + "data/liquidez.json",        nome: "Liquidez (spread, profundidade)", periodo: 3600, limite: 9000 },
  tfshort:   { url: RAW + "okx-tfshort/okx_tfshort.json", nome: "TF-SHORT (papel)",            periodo: 86400, limite: 2 * 86400 + 7200 },
};

// ---------------------------------------------------------------- pedidos com tentativas controladas
export async function obter(url, { tentativas = 3, timeoutMs = 12000, esperaMs = 1500, fetchFn = globalThis.fetch } = {}) {
  let ultimo = null;
  for (let i = 0; i < tentativas; i++) {
    const ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const to = ctl ? setTimeout(() => ctl.abort(), timeoutMs) : null;
    try {
      const r = await fetchFn(url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(), { cache: "no-store", signal: ctl && ctl.signal });
      if (!r.ok) {
        ultimo = `HTTP ${r.status}`;
        if (r.status === 404) break;                 // nao existe: nao adianta insistir
      } else {
        return { ok: true, dados: await r.json(), erro: null, tentativas: i + 1 };
      }
    } catch (e) {
      ultimo = e && e.name === "AbortError" ? "sem resposta (tempo esgotado)" : "rede indisponivel";
    } finally { if (to) clearTimeout(to); }
    if (i < tentativas - 1) await new Promise(res => setTimeout(res, esperaMs * 2 ** i));   // 1,5 s, 3 s, ...
  }
  return { ok: false, dados: null, erro: ultimo || "falhou", tentativas };
}

// ---------------------------------------------------------------- frescura e estado de ligacao
export function idade(t, agora = Date.now() / 1000) { return t ? Math.max(0, Math.round(agora - t)) : null; }

export function frescura(t, limite, agora = Date.now() / 1000) {
  if (!t) return { estado: "sem_hora", idade: null };
  const a = idade(t, agora);
  if (!limite) return { estado: "atual", idade: a };
  if (a <= limite) return { estado: "atual", idade: a };
  if (a <= 3 * limite) return { estado: "atrasado", idade: a };
  return { estado: "desatualizado", idade: a };
}

// hora da ultima atualizacao de cada fonte, lida do proprio ficheiro
export function horaDe(chave, d) {
  if (!d) return null;
  switch (chave) {
    case "scan": case "cofreScan": return Math.max(d.generated_at || 0, d.monitored_at || 0) || null;
    case "state": { const s = d.scan_times || []; return s.length ? s[s.length - 1] : null; }
    case "okx": return Math.max((d.volta || {}).t || 0, (d.resumo || {}).t || 0) || null;
    case "cofreOkx": return d.t || null;
    case "derivados": return d.t || null;
    case "liquidez": return null;
    default: return d.t || null;
  }
}

export function texIdade(s) {
  if (s == null) return "sem hora";
  if (s < 90) return `há ${s} s`;
  if (s < 5400) return `há ${Math.round(s / 60)} min`;
  if (s < 172800) return `há ${Math.round(s / 3600)} h`;
  return `há ${Math.round(s / 86400)} dias`;
}

// estado de uma fonte depois do pedido: ligado | atrasado | desatualizado | bloqueado | falhou
export function estadoFonte(chave, res, { aberto = null, agora = Date.now() / 1000 } = {}) {
  const f = FONTES[chave] || {};
  if (!res || !res.ok) return { estado: "falhou", razao: (res && res.erro) || "sem pedido", t: null, idade: null };
  if (f.cifrado && !aberto) return { estado: "bloqueado", razao: "dados cifrados: abre o cofre com a palavra-passe", t: null, idade: null };
  const t = horaDe(chave, f.cifrado ? aberto : res.dados);
  const fr = frescura(t, f.limite, agora);
  const e = fr.estado === "atual" ? "ligado" : fr.estado === "sem_hora" ? "ligado" : fr.estado;
  const razao = e === "ligado" ? null : `última atualização ${texIdade(fr.idade)} (esperado de ${Math.round(f.periodo / 60)} em ${Math.round(f.periodo / 60)} min)`;
  return { estado: e, razao, t, idade: fr.idade };
}

// ---------------------------------------------------------------- estado das corretoras
// OKX: o agente de hora a hora le a conta (cofre_okx) e publica o okx.json. A ligacao so e "ligada" se o agente
// correu ha pouco E a leitura privada (cofre) e recente. Sem palavra-passe: estado publico do agente, saldo bloqueado.
export function estadoOKX(pub, priv, agora = Date.now() / 1000) {
  const ep = estadoFonte("okx", pub, { agora });
  const out = { corretora: "OKX", agente: ep, conta: null, ligacao: "falhou", razao: ep.razao };
  if (ep.estado === "falhou") { out.razao = `cópia do agente OKX indisponível: ${ep.razao}`; return out; }
  if (priv && priv.res) {
    const ec = estadoFonte("cofreOkx", priv.res, { aberto: priv.aberto, agora });
    out.conta = ec;
    if (ec.estado === "bloqueado") { out.ligacao = ep.estado === "ligado" ? "ligado_publico" : ep.estado; out.razao = ec.razao; return out; }
    if (ec.estado === "falhou") { out.ligacao = "falhou"; out.razao = `conta OKX: ${ec.razao}`; return out; }
    out.ligacao = ep.estado === "ligado" && ec.estado === "ligado" ? "ligado" : (ec.estado !== "ligado" ? ec.estado : ep.estado);
    out.razao = out.ligacao === "ligado" ? null : (ec.estado !== "ligado" ? `leitura da conta ${texIdade(ec.idade)}` : ep.razao);
    return out;
  }
  out.ligacao = ep.estado === "ligado" ? "ligado_publico" : ep.estado;
  return out;
}

export function estadoBybit(pub, priv, agora = Date.now() / 1000) {
  const ep = estadoFonte("scan", pub, { agora });
  const out = { corretora: "Bybit", agente: ep, conta: null, ligacao: "falhou", razao: ep.razao };
  if (ep.estado === "falhou") { out.razao = `cópia do scanner indisponível: ${ep.razao}`; return out; }
  const D = pub.dados || {};
  const venue = D.venue_source || {};
  if (venue.ok === false) { out.ligacao = "falhou"; out.razao = "o scanner não conseguiu ler a Bybit UE na última passagem"; return out; }
  if (priv && priv.res) {
    const ec = estadoFonte("cofreScan", priv.res, { aberto: priv.aberto, agora });
    out.conta = ec;
    const K = priv.aberto && priv.aberto.conta;
    if (ec.estado === "bloqueado") { out.ligacao = ep.estado === "ligado" ? "ligado_publico" : ep.estado; out.razao = ec.razao; return out; }
    if (ec.estado === "falhou") { out.ligacao = "falhou"; out.razao = `conta Bybit: ${ec.razao}`; return out; }
    if (!K || K.ok === false) { out.ligacao = "falhou"; out.razao = `conta Bybit: ${(K && (K.error || K.erro)) || "sem leitura da conta"}`; return out; }
    const fk = frescura(K.t, FONTES.cofreScan.limite, agora);
    out.ligacao = ep.estado === "ligado" && fk.estado === "atual" ? "ligado" : (fk.estado !== "atual" ? fk.estado : ep.estado);
    out.razao = out.ligacao === "ligado" ? null : `leitura da conta ${texIdade(fk.idade)}`;
    return out;
  }
  out.ligacao = ep.estado === "ligado" ? "ligado_publico" : ep.estado;
  return out;
}

// ---------------------------------------------------------------- posicoes e ordens (normalizadas)
// lado: o executor OKX so abre LONG (net mode); a posicao privada traz o sinal da quantidade.
export function okxOperacoes(O, K) {
  const ops = ((O || {}).real || {}).ops || {};
  const pos = [], ordens = [];
  for (const [a, o] of Object.entries(ops)) {
    const base = { corretora: "OKX", ativo: a, inst: o.inst, estrategia: o.estrategia === "recuo" ? "H46 recuo" : "H40 pânico",
                   lado: "LONG", entrada: o.entrada || null, stop: o.stop || null, alvo: o.alvo || null, alav: o.alav || null,
                   risco_pct: o.risco_pct ?? null, stop_confirmado: o.stop_ok || null, desde: o.t_fill || o.criado || null,
                   sair_em: o.sair_em || null, parcial: !!o.parcial, fonte: "estado do agente" };
    if (o.estado === "aberta") pos.push(base);
    else if (o.estado === "pendente") ordens.push({ ...base, preco: o.lim, valida_ate: o.valido_ate, cancelamento_pedido: o.cancelar_pedido || null });
  }
  if (K) {
    for (const p of K.posicoes || []) {
      let x = pos.find(q => q.ativo === p.asset);
      if (!x) { x = { corretora: "OKX", ativo: p.asset, inst: p.inst, estrategia: "não seguida pelo agente", lado: p.contratos < 0 ? "SHORT" : "LONG", fonte: "só na corretora" }; pos.push(x); }
      Object.assign(x, { quantidade: Math.abs(p.contratos), entrada_corretora: p.entrada, atual: p.atual, valor_usd: p.valor_usd,
                         margem_usd: p.margem_usd, pnl_usd: p.pnl_usd, pnl_pct: p.pnl_pct, alav: p.alav || x.alav, liquidacao: p.liquidacao,
                         lado: p.contratos < 0 ? "SHORT" : x.lado });
    }
    for (const q of K.ordens || []) {
      let x = ordens.find(o => o.ativo === q.asset);
      if (!x) { x = { corretora: "OKX", ativo: q.asset, estrategia: "não seguida pelo agente", fonte: "só na corretora" }; ordens.push(x); }
      Object.assign(x, { preco_corretora: q.preco, quantidade: q.contratos, lado: q.lado === "sell" ? "SHORT" : "LONG" });
    }
  }
  return { posicoes: pos, ordens };
}

export function okxFechadas(O, K) {
  const hist = (((O || {}).real || {}).hist || []).filter(h => h.estado === "fechada" || h.estado === "cancelada");
  const pub = hist.map(h => ({ corretora: "OKX", ativo: h.asset, estado: h.estado, motivo: h.motivo || null, ret_pct: h.ret_pct ?? null,
                               R: h.R ?? null, t: h.fechado || h.t_fill || h.criado || null, estrategia: h.estrategia === "recuo" ? "H46 recuo" : "H40 pânico" }));
  const priv = ((K || {}).fechadas || []).map(f => ({ corretora: "OKX", ativo: f.asset, estado: "fechada", entrada: f.entrada, saida: f.saida, pnl_usd: f.pnl_usd, t: f.t }));
  return { publico: pub.sort((a, b) => (b.t || 0) - (a.t || 0)), privado: priv.sort((a, b) => (b.t || 0) - (a.t || 0)) };
}

// Bybit: o journal publico diz o que o motor executou (sem tamanhos); o cofre traz as posicoes reais (execucao.abertas)
export function bybitOperacoes(S, P) {
  const rows = ((S || {}).journal || {}).rows || [];
  const pos = rows.filter(r => r.mode === "REAL" && r.status === "OPEN" && r.executed === true).map(r => ({
    corretora: "Bybit", ativo: r.asset, estrategia: r.strategy, lado: r.side, entrada: r.exec_price || r.entry || null,
    stop: r.stop || null, alvo: (r.tp || [])[0] || null, desde: r.opened_at || r.issued_at, risco_pct: r.risk_pct ?? null, fonte: "journal do motor" }));
  const naoExec = rows.filter(r => r.mode === "REAL" && r.status === "OPEN" && r.executed !== true).map(r => ({
    corretora: "Bybit", ativo: r.asset, estrategia: r.strategy, lado: r.side, desde: r.issued_at, motivo: r.recusada || r.reason || "sinal real não executado" }));
  if (P) {
    for (const o of ((P.execucao || {}).abertas || [])) {
      let x = pos.find(q => q.ativo === o.asset && (q.lado || "LONG") === (o.lado || "LONG"));
      if (!x) { x = { corretora: "Bybit", ativo: o.asset, estrategia: o.estrategia || o.strategy || "não identificada", lado: o.lado || "LONG", fonte: "só na conta" }; pos.push(x); }
      Object.assign(x, { quantidade: o.qty ?? null, entrada_corretora: o.entrada ?? null });
    }
    const nuc = ((P.nucleo || {}).pos) || {};
    for (const [a, v] of Object.entries(nuc)) {
      if (!v) continue;
      pos.push({ corretora: "Bybit", ativo: a, estrategia: "Tendência BTC (núcleo)", lado: "LONG", entrada_corretora: v.entrada ?? null,
                 quantidade: v.qty ?? null, fonte: "conta (núcleo)" });
    }
  }
  const fech = rows.filter(r => r.mode === "REAL" && r.status === "CLOSED" && r.executed === true).map(r => ({
    corretora: "Bybit", ativo: r.asset, estrategia: r.strategy, lado: r.side, R: r.result_r ?? null, t: r.closed_at }))
    .sort((a, b) => (b.t || 0) - (a.t || 0));
  return { posicoes: pos, sinais_nao_executados: naoExec, fechadas: fech };
}

// Reconciliacao: estado interno do CryptoScan contra o que a corretora diz (so quando o cofre esta aberto).
export const TOL = 0.005;
export function reconciliar(posicoes, ordens, privadoAberto) {
  if (!privadoAberto) return { estado: "por_verificar", razao: "abre o cofre para comparar com a corretora", itens: [] };
  const itens = [];
  for (const p of posicoes) {
    if (p.fonte === "só na corretora" || p.fonte === "só na conta") itens.push({ ativo: p.ativo, corretora: p.corretora, estado: "so_corretora", texto: "posição na corretora que o estado interno não segue" });
    else if (p.fonte === "conta (núcleo)") itens.push({ ativo: p.ativo, corretora: p.corretora, estado: "confere", texto: "núcleo lido na conta" });
    else if (p.quantidade == null) itens.push({ ativo: p.ativo, corretora: p.corretora, estado: "so_interno", texto: "o estado interno diz aberta mas a corretora não mostra posição" });
    else if (p.entrada && p.entrada_corretora && Math.abs(p.entrada_corretora / p.entrada - 1) > TOL)
      itens.push({ ativo: p.ativo, corretora: p.corretora, estado: "difere", texto: `entrada difere (${p.entrada} interno vs ${p.entrada_corretora} corretora)` });
    else itens.push({ ativo: p.ativo, corretora: p.corretora, estado: "confere", texto: "posição, entrada e quantidade conferem" });
  }
  for (const o of ordens) {
    if (o.fonte === "só na corretora") itens.push({ ativo: o.ativo, corretora: o.corretora, estado: "so_corretora", texto: "ordem na corretora que o estado interno não segue" });
    else if (o.preco_corretora == null) itens.push({ ativo: o.ativo, corretora: o.corretora, estado: "so_interno", texto: "ordem pendente no estado interno, não visível na corretora" });
    else itens.push({ ativo: o.ativo, corretora: o.corretora, estado: "confere", texto: "ordem pendente confere" });
  }
  const mau = itens.filter(i => i.estado !== "confere");
  return { estado: mau.length ? "discrepancia" : "confere", razao: mau.length ? `${mau.length} discrepância(s)` : null, itens };
}

// ---------------------------------------------------------------- estrategias (ativas / suspensas), lidas da configuracao real
export function estrategias(cfgOkx, S, St) {
  const out = [];
  const c = cfgOkx || {};
  if (cfgOkx) {
    out.push({ nome: "H40 pânico", corretora: "OKX", dinheiro: "real", ativa: !!(c.real && c.panico_real), razao: c.panico_real ? (c.so_mercado ? "só o pânico do mercado todo" : null) : "suspensa (panico_real desligado)" });
    out.push({ nome: "H46 recuo na subida", corretora: "OKX", dinheiro: "real", ativa: !!(c.real && c.recuo_real), razao: c.recuo_real ? `risco ${c.recuo_risco_pct}%` : "suspensa (recuo_real desligado)" });
  }
  const dis = (S || {}).disabled_strategies || {};
  for (const [k, v] of Object.entries(dis)) out.push({ nome: k, corretora: "Bybit", dinheiro: "real", ativa: false, razao: (v && (v.motivo || v.reason)) || "desligada" });
  const sus = (St || {}).suspensos || {};
  for (const [k, v] of Object.entries(sus)) if (!out.find(x => x.nome === k)) out.push({ nome: k, corretora: "Bybit", dinheiro: "real", ativa: false, razao: String(v) });
  const pp = (S || {}).papel_panico; if (pp) out.push({ nome: "H45 pânico Bybit", corretora: "Bybit", dinheiro: "papel", ativa: true, razao: "só papel" });
  const pf = (S || {}).papel_fases; if (pf) out.push({ nome: `Fases (${pf.fase || "?"})`, corretora: "Bybit", dinheiro: "papel", ativa: true, razao: "só papel" });
  return out;
}

// ---------------------------------------------------------------- oportunidades, rejeicoes e alertas (reais)
export function oportunidades(S, O) {
  const out = [];
  for (const q of (((S || {}).radar || {}).quebras || []).filter(x => x.ok)) out.push({ fonte: "Scanner Bybit", ativo: q.asset, texto: `${q.estado} (${q.dist_pct}% do nível)`, lado: "SHORT" });
  for (const a of ((O || {}).resumo || {}).pendentes || []) out.push({ fonte: "Agente OKX (papel H40)", ativo: a, texto: "sinal de pânico nesta hora", lado: "LONG" });
  for (const r of (((O || {}).radar || {}).lista || []).slice(0, 6)) out.push({ fonte: "Radar OKX", ativo: r.a, texto: `falta: ${(r.falta || []).join("; ")}`, lado: "LONG", perto: true });
  return out;
}

export function rejeicoes(S) {
  const rows = ((S || {}).journal || {}).rows || [];
  const m = {};
  for (const r of rows) if (r.recusada || (r.mode === "REAL" && r.executed === false)) { const k = r.recusada || r.reason || "não executado"; m[k] = (m[k] || 0) + 1; }
  for (const [k, v] of Object.entries((S || {}).disabled_strategies || {})) { const k2 = `estratégia desligada: ${(v && v.motivo) || "arena"}`; m[k2] = (m[k2] || 0) + 1; }
  return Object.entries(m).map(([motivo, n]) => ({ motivo, n })).sort((a, b) => b.n - a.n);
}

export function alertas({ okx, bybit, recOkx, recBybit, O, S, cfgOkx, agora = Date.now() / 1000 }) {
  const out = [];
  const add = (nivel, texto, origem) => out.push({ nivel, texto, origem });
  if (okx && okx.ligacao === "falhou") add("critico", `OKX: ${okx.razao}`, "ligação");
  else if (okx && ["atrasado", "desatualizado"].includes(okx.ligacao)) add("aviso", `OKX: dados ${okx.ligacao} (${okx.razao})`, "ligação");
  if (bybit && bybit.ligacao === "falhou") add("critico", `Bybit: ${bybit.razao}`, "ligação");
  else if (bybit && ["atrasado", "desatualizado"].includes(bybit.ligacao)) add("aviso", `Bybit: dados ${bybit.ligacao} (${bybit.razao})`, "ligação");
  for (const r of [recOkx, recBybit]) for (const i of (r && r.itens) || []) if (i.estado !== "confere") add("critico", `${i.corretora} ${i.ativo}: ${i.texto}`, "reconciliação");
  for (const [a, o] of Object.entries(((O || {}).real || {}).ops || {})) {
    if (o.estado === "aberta" && o.stop_ok && agora - o.stop_ok > 3 * 3600) add("aviso", `OKX ${a}: stop confirmado ${texIdade(idade(o.stop_ok, agora))}`, "proteção");
    if (o.estado === "aberta" && !o.stop_ok) add("critico", `OKX ${a}: stop ainda não confirmado na corretora`, "proteção");
    if (o.stop_insuficiente) add("critico", `OKX ${a}: o stop não protege a posição toda`, "proteção");
  }
  if ((S || {}).halt) add("critico", `Motor Bybit em travão: ${JSON.stringify(S.halt).slice(0, 80)}`, "risco");
  const ev = (S || {}).next_event;
  if (ev && ev.t && ev.t - agora < 6 * 3600 && ev.t > agora) add("info", `Evento macro: ${ev.name} em ${Math.round((ev.t - agora) / 60)} min`, "calendário");
  if (cfgOkx && !cfgOkx.real) add("aviso", "OKX: execução real desligada na configuração", "configuração");
  const ord = { critico: 0, aviso: 1, info: 2 };
  return out.sort((a, b) => ord[a.nivel] - ord[b.nivel]);
}

// ---------------------------------------------------------------- exposicao e indicadores-chave
export function exposicao(posicoes) {
  const L = posicoes.filter(p => p.lado === "LONG"), Sh = posicoes.filter(p => p.lado === "SHORT");
  const nominal = posicoes.reduce((s, p) => s + (p.valor_usd || 0), 0);
  const temNominal = posicoes.some(p => p.valor_usd != null);
  const risco = posicoes.reduce((s, p) => s + (p.risco_pct || 0), 0);
  return { long: L.length, short: Sh.length, nominal_usd: temNominal ? nominal : null, risco_pct: Math.round(risco * 100) / 100 };
}

export function pnl(K, P) {
  const okxAberto = K ? K.pnl_aberto_usd : null, okxFechado = K ? K.pnl_fechado_usd : null;
  return { okx_aberto_usd: okxAberto ?? null, okx_fechado_usd: okxFechado ?? null, okx_equity_usd: K ? K.equity_usd : null,
           bybit_equity_usd: P && P.conta ? (P.conta.equity ?? null) : null, bybit_livre_usd: P && P.conta ? (P.conta.usdc_free ?? null) : null };
}

// ---------------------------------------------------------------- linha do tempo de eventos REAIS (com hora)
export function eventos({ O, S, St, K }) {
  const ev = [];
  const add = (t, agente, para, texto, tipo) => { if (t) ev.push({ t, agente, para, texto, tipo }); };
  const R = (O || {}).resumo || {};
  add(R.t, "panico", null, `Varreu ${R.analisados || 0} perpétuos de cripto na OKX${(R.pendentes || []).length ? `; sinal em ${R.pendentes.join(", ")}` : ""}`, "analise");
  for (const [a, o] of Object.entries(((O || {}).real || {}).ops || {})) {
    add(o.criado, o.estrategia === "recuo" ? "recuo" : "panico", "exec_okx", `${a}: sinal ${o.estrategia === "recuo" ? "H46" : "H40"} entregue à execução (ordem limite)`, "encaminhamento");
    add(o.criado && o.criado + 1, "risco", "exec_okx", `${a}: risco ${o.risco_pct ?? "?"}% da conta aprovado, stop e objetivo anexados`, "risco");
    add(o.t_fill, "exec_okx", "centro", `${a}: compra executada a ${o.entrada}`, "execucao");
    add(o.stop_ok, "exec_okx", "centro", `${a}: stop confirmado na OKX`, "protecao");
    add(o.cancelar_pedido, "exec_okx", "centro", `${a}: pedido de cancelamento da entrada (estratégia suspensa)`, "execucao");
  }
  for (const h of (((O || {}).real || {}).hist || []).slice(-10)) add(h.fechado, "exec_okx", "centro", `${h.asset}: ${h.estado}${h.motivo ? " — " + h.motivo : ""}${h.ret_pct != null ? ` (${h.ret_pct > 0 ? "+" : ""}${h.ret_pct}%)` : ""}`, "execucao");
  const rc = (O || {}).recuo || {};
  if ((rc.resumo || {}).t) add(rc.resumo.t, "recuo", null, `Recuo na subida: ${(rc.abertas || []).length} em papel, ${(rc.pend || []).length || Object.keys(rc.pend || {}).length} pendentes`, "analise");
  const MR = ((O || {}).macro || {}).resumo || {};
  if (MR.t) add(MR.t, "macro", null, `${(MR.abertas || []).length} de ${MR.analisados || 0} ações e matérias-primas em subida (papel)`, "analise");
  if (S) {
    add(S.generated_at, "scanner", null, `Passagem do scanner: regime BTC ${(S.market_regime || {}).btc || "?"}`, "analise");
    for (const r of ((S.journal || {}).rows || []).slice(-8)) {
      add(r.issued_at, "scanner", "diretor", `${r.asset} ${r.side} (${r.strategy}): sinal enviado ao diretor`, "encaminhamento");
      if (r.executed) add(r.opened_at || r.issued_at, "exec_bybit", "centro", `${r.asset}: executada na Bybit`, "execucao");
      if (r.closed_at) add(r.closed_at, "exec_bybit", "centro", `${r.asset}: fechada${r.result_r != null ? ` (${r.result_r > 0 ? "+" : ""}${r.result_r}R)` : ""}`, "execucao");
    }
    for (const d of ((S.diretor || {}).decisoes || []).slice(-6)) add(d.t, "diretor", d.decisao === "AUTORIZADO" ? "exec_bybit" : null, `${d.ativo} ${d.lado}: ${d.decisao}`, "decisao");
    const ev = S.next_event; if (ev && ev.name) add(S.generated_at, "noticias", null, `Próximo evento: ${ev.name}`, "analise");
  }
  if (K) add(K.t, "exec_okx", "centro", "Leitura privada da conta OKX (saldo, posições, ordens)", "leitura");
  return ev.sort((a, b) => b.t - a.t);
}

// ---------------------------------------------------------------- indicadores tecnicos (para os ecras)
export function mm(v, n) { const out = []; let s = 0; for (let i = 0; i < v.length; i++) { s += v[i]; if (i >= n) s -= v[i - n]; out.push(i >= n - 1 ? s / n : null); } return out; }
export function mme(v, n) { const k = 2 / (n + 1), out = []; let e = null; for (let i = 0; i < v.length; i++) { e = e == null ? v[i] : v[i] * k + e * (1 - k); out.push(i >= n - 1 ? e : null); } return out; }
export function rsi(v, n = 14) {
  const out = new Array(v.length).fill(null); if (v.length <= n) return out;
  let g = 0, p = 0;
  for (let i = 1; i <= n; i++) { const d = v[i] - v[i - 1]; if (d >= 0) g += d; else p -= d; }
  g /= n; p /= n; out[n] = p === 0 ? 100 : 100 - 100 / (1 + g / p);
  for (let i = n + 1; i < v.length; i++) { const d = v[i] - v[i - 1]; g = (g * (n - 1) + Math.max(d, 0)) / n; p = (p * (n - 1) + Math.max(-d, 0)) / n; out[i] = p === 0 ? 100 : 100 - 100 / (1 + g / p); }
  return out;
}
export function macd(v, a = 12, b = 26, c = 9) {
  const ea = mme(v, a), eb = mme(v, b), linha = v.map((_, i) => ea[i] != null && eb[i] != null ? ea[i] - eb[i] : null);
  const idx = linha.findIndex(x => x != null), sig = new Array(v.length).fill(null);
  if (idx >= 0) { const s = mme(linha.slice(idx), c); s.forEach((x, i) => { sig[idx + i] = x; }); }
  return { linha, sinal: sig, hist: linha.map((x, i) => x != null && sig[i] != null ? x - sig[i] : null) };
}
export function atrPct(c, n = 14) {
  if (c.length < n + 1) return null; let s = 0;
  for (let i = c.length - n; i < c.length; i++) s += Math.max(c[i].h - c[i].l, Math.abs(c[i].h - c[i - 1].c), Math.abs(c[i].l - c[i - 1].c));
  return 100 * (s / n) / c[c.length - 1].c;
}

// ---------------------------------------------------------------- mercado publico (velas e livro), com fonte indicada
export const MERCADO = {
  bybit: "https://api.bybit.eu/v5/market/",
  okx: "https://eea.okx.com/api/v5/market/",
  binance: "https://data-api.binance.vision/api/v3/",
};
export async function velas(ativo, { inst = null, intervalo = "1h", n = 200, fetchFn = globalThis.fetch } = {}) {
  const tentar = async (fonte, url, conv) => {
    try {
      const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 8000);
      const r = await fetchFn(url, { cache: "no-store", signal: ctl.signal }); clearTimeout(to);
      if (!r.ok) return null; const c = conv(await r.json());
      return c && c.length > 30 ? { fonte, velas: c } : null;
    } catch (_) { return null; }
  };
  const bi = { "1h": "60", "4h": "240", "1d": "D" }[intervalo], ob = { "1h": "1H", "4h": "4H", "1d": "1Dutc" }[intervalo];
  const tent = [
    () => tentar("Bybit UE (spot USDC)", `${MERCADO.bybit}kline?category=spot&symbol=${ativo}USDC&interval=${bi}&limit=${n}`,
      j => j.retCode === 0 ? j.result.list.map(x => ({ t: +x[0] / 1000, o: +x[1], h: +x[2], l: +x[3], c: +x[4], v: +x[5] })).reverse() : null),
    () => tentar(`OKX EEA (${inst || ativo + "-USDT-SWAP"})`, `${MERCADO.okx}candles?instId=${encodeURIComponent(inst || ativo + "-USDT-SWAP")}&bar=${ob}&limit=${Math.min(n, 300)}`,
      j => j.code === "0" ? j.data.map(x => ({ t: +x[0] / 1000, o: +x[1], h: +x[2], l: +x[3], c: +x[4], v: +x[5] })).reverse() : null),
    () => tentar("Binance (global, USDT)", `${MERCADO.binance}klines?symbol=${ativo}USDT&interval=${intervalo}&limit=${n}`,
      j => Array.isArray(j) ? j.map(x => ({ t: x[0] / 1000, o: +x[1], h: +x[2], l: +x[3], c: +x[4], v: +x[5] })) : null),
  ];
  const ordem = inst ? [tent[1], tent[0], tent[2]] : tent;
  for (const f of ordem) { const r = await f(); if (r) return r; }
  return { fonte: null, velas: [], erro: "nenhuma fonte de velas respondeu (rede ou bloqueio do browser)" };
}

export async function livro(ativo, { fetchFn = globalThis.fetch } = {}) {
  try {
    const r = await fetchFn(`${MERCADO.bybit}orderbook?category=spot&symbol=${ativo}USDC&limit=25`, { cache: "no-store" });
    const j = await r.json();
    if (j.retCode !== 0 || !j.result || !(j.result.b || []).length) return { fonte: null, erro: "livro indisponível para este ativo na Bybit UE" };
    return { fonte: "Bybit UE (spot USDC)", t: +j.result.ts / 1000, bids: j.result.b.map(x => [+x[0], +x[1]]), asks: j.result.a.map(x => [+x[0], +x[1]]) };
  } catch (_) { return { fonte: null, erro: "livro indisponível (rede ou bloqueio do browser)" }; }
}

// derivados.json: series por moeda com campos [t, preco, oi_musd, funding_ppm, ls_x100, ...]
export function derivadosDe(Dv, ativo) {
  if (!Dv || !Dv.moedas || !Dv.moedas[ativo]) return null;
  const c = Dv.campos, i = k => c.indexOf(k), s = Dv.moedas[ativo];
  return { t: s.map(x => x[i("t")]), oi: s.map(x => x[i("oi_musd")]), funding: s.map(x => x[i("funding_ppm")] == null ? null : x[i("funding_ppm")] / 1e4),
           ls: s.map(x => x[i("ls_x100")] == null ? null : x[i("ls_x100")] / 100) };
}

export function liquidezDe(L, ativo) {
  const a = (((L || {}).hoje || {}).amostras || {})[ativo];
  if (!a || !a.length) return null;
  const u = a[a.length - 1];
  // engine/liquidez.py: cada amostra e [volume 24 h em USD, spread em %, preco parado]
  return { volume_usd: u[0], spread_pct: u[1], parado: !!u[2], amostras: a.length, dia: L.hoje.dia };
}
