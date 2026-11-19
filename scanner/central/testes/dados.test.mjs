// Testes do Operations Center (node --test). Dados de teste sinteticos, marcados como tal; nada disto vai para a pagina.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import * as D from "../dados.js";
import { AGENTES, ESTADOS, estadosAgentes, colaboracoes } from "../agentes.js";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const T0 = 1_794_290_834;                       // "agora" fixo nos testes
const ok = dados => ({ ok: true, dados, pedido: T0 });
const falha = erro => ({ ok: false, dados: null, erro });

const OKX = () => ({
  resumo: { t: T0 - 120, analisados: 289, pendentes: [], abertas: [] }, volta: { t: T0 - 120 },
  real: { ops: {
    PARTI: { inst: "PARTI-X", estado: "aberta", estrategia: "panico", entrada: 0.04128, stop: 0.037, alvo: 0.04982, alav: 6, risco_pct: 0.8, criado: T0 - 7000, t_fill: T0 - 5000, stop_ok: T0 - 120 },
    ZZZ: { inst: "ZZZ-X", estado: "pendente", estrategia: "recuo", lim: 1.0, stop: 0.9, alvo: 1.2, valido_ate: T0 + 3600, criado: T0 - 600 } },
    hist: [{ asset: "PENGU", estado: "fechada", motivo: "stop ou objetivo", ret_pct: -5.5, fechado: T0 - 86400 }] },
  recuo: { resumo: { btc_em_subida: false, pendentes: [], abertas: [] } }, macro: { resumo: { analisados: 175, abertas: ["AAPL"] } },
});
const SCAN = () => ({ generated_at: T0 - 60, sources: { binance: { ok: true }, okx: { ok: true } }, venue_source: { ok: true, pairs: 81 },
  counts: { deep_checked: 65, eligible: 65, long: 0, short: 0 }, market_regime: { btc: "BEAR" },
  journal: { rows: [{ asset: "SEI", strategy: "SHORT_TURTLE", side: "SHORT", mode: "REAL", status: "CLOSED", executed: true, issued_at: T0 - 9e5, closed_at: T0 - 5e5, result_r: 1.3, real_r: 1.3 },
                    { asset: "AVAX", strategy: "SHORT_TURTLE", side: "SHORT", mode: "REAL", status: "OPEN", executed: false, issued_at: T0 - 6e5 }] },
  disabled_strategies: { BREAKOUT: { motivo: "forma recente (90 dias)" } }, arena: { atualizado: T0 - 300, vivos: 10, minimo_vivos: 5, forma: { janela_dias: 90 }, classificacao: [] },
  diretor: { decisoes: [{ t: T0 - 4e6, ativo: "PUMP", lado: "LONG", decisao: "AUTORIZADO", motivos: [] }] } });
const CFG = { real: true, panico_real: false, recuo_real: true, recuo_risco_pct: 1.0, risco_pct: 2.0, risco_total_max_pct: 3.0, alavancagem: 10, travao_queda_pct: 45, so_mercado: true };

// ------------------------------------------------------------------ pedidos: tentativas controladas, sem inventar
test("obter: tenta de novo e devolve a falha com a razao (nunca dados ficticios)", async () => {
  let n = 0;
  const f = async () => { n++; throw new TypeError("Failed to fetch"); };
  const r = await D.obter("https://x/y.json", { tentativas: 3, esperaMs: 1, fetchFn: f });
  assert.equal(n, 3); assert.equal(r.ok, false); assert.equal(r.dados, null); assert.match(r.erro, /rede/);
});
test("obter: 404 nao insiste; 200 devolve os dados", async () => {
  let n = 0;
  const r404 = await D.obter("u", { esperaMs: 1, fetchFn: async () => { n++; return { ok: false, status: 404 }; } });
  assert.equal(n, 1); assert.equal(r404.erro, "HTTP 404");
  const r = await D.obter("u", { esperaMs: 1, fetchFn: async () => ({ ok: true, status: 200, json: async () => ({ a: 1 }) }) });
  assert.deepEqual(r.dados, { a: 1 });
});

// ------------------------------------------------------------------ frescura e ligacao
test("frescura: atual, atrasado, desatualizado e sem hora", () => {
  assert.equal(D.frescura(T0 - 100, 1200, T0).estado, "atual");
  assert.equal(D.frescura(T0 - 2000, 1200, T0).estado, "atrasado");
  assert.equal(D.frescura(T0 - 9999, 1200, T0).estado, "desatualizado");
  assert.equal(D.frescura(null, 1200, T0).estado, "sem_hora");
});
test("OKX: falha do pedido nunca aparece como ligada", () => {
  const e = D.estadoOKX(falha("rede indisponivel"), { res: falha("rede indisponivel"), aberto: null }, T0);
  assert.equal(e.ligacao, "falhou"); assert.match(e.razao, /indisponível/);
});
test("OKX: cofre fechado = ligada so na parte publica, com a razao", () => {
  const e = D.estadoOKX(ok(OKX()), { res: ok({ cifra: "cs1" }), aberto: null }, T0);
  assert.equal(e.ligacao, "ligado_publico"); assert.match(e.razao, /cifrados/);
});
test("OKX: leitura privada velha = desatualizada (posicoes antigas nunca passam por atuais)", () => {
  const e = D.estadoOKX(ok(OKX()), { res: ok({ cifra: "cs1" }), aberto: { t: T0 - 40000 } }, T0);
  assert.equal(e.ligacao, "desatualizado");
});
test("OKX: agente e conta recentes = ligada", () => {
  assert.equal(D.estadoOKX(ok(OKX()), { res: ok({ cifra: "cs1" }), aberto: { t: T0 - 300 } }, T0).ligacao, "ligado");
});
test("Bybit: o scanner sem acesso a Bybit UE aparece como falha", () => {
  const s = SCAN(); s.venue_source.ok = false;
  assert.equal(D.estadoBybit(ok(s), null, T0).ligacao, "falhou");
  assert.equal(D.estadoBybit(ok(SCAN()), null, T0).ligacao, "ligado_publico");
});

// ------------------------------------------------------------------ posicoes, ordens e reconciliacao
test("OKX: posicoes e ordens vem do estado do agente; quantidades so com o cofre", () => {
  const o = D.okxOperacoes(OKX(), null);
  assert.equal(o.posicoes.length, 1); assert.equal(o.posicoes[0].ativo, "PARTI"); assert.equal(o.posicoes[0].quantidade, undefined);
  assert.equal(o.ordens.length, 1); assert.equal(o.ordens[0].estrategia, "H46 recuo");
});
test("reconciliacao: sem cofre fica por verificar (nao se afirma que confere)", () => {
  const o = D.okxOperacoes(OKX(), null);
  assert.equal(D.reconciliar(o.posicoes, o.ordens, null).estado, "por_verificar");
});
test("reconciliacao: confere, posicao so na corretora, so no estado interno e entrada diferente", () => {
  const K = { t: T0, posicoes: [{ asset: "PARTI", inst: "PARTI-X", contratos: 10, entrada: 0.04128 }, { asset: "XYZ", inst: "XYZ-X", contratos: -3, entrada: 2 }], ordens: [{ asset: "ZZZ", preco: 1.0, contratos: 5, lado: "buy" }] };
  let o = D.okxOperacoes(OKX(), K), r = D.reconciliar(o.posicoes, o.ordens, K);
  const por = a => r.itens.find(i => i.ativo === a);
  assert.equal(por("PARTI").estado, "confere"); assert.equal(por("XYZ").estado, "so_corretora"); assert.equal(por("ZZZ").estado, "confere");
  assert.equal(o.posicoes.find(p => p.ativo === "XYZ").lado, "SHORT");
  const K2 = { t: T0, posicoes: [{ asset: "PARTI", contratos: 10, entrada: 0.05 }], ordens: [] };
  o = D.okxOperacoes(OKX(), K2); r = D.reconciliar(o.posicoes, o.ordens, K2);
  assert.equal(r.itens.find(i => i.ativo === "PARTI").estado, "difere"); assert.equal(r.itens.find(i => i.ativo === "ZZZ").estado, "so_interno");
  const K3 = { t: T0, posicoes: [], ordens: [] };
  o = D.okxOperacoes(OKX(), K3); r = D.reconciliar(o.posicoes, o.ordens, K3);
  assert.equal(r.itens.find(i => i.ativo === "PARTI").estado, "so_interno"); assert.equal(r.estado, "discrepancia");
});
test("piloto OKX: posicao do piloto conta como seguida, com o estado do stop lido na OKX (18/11, RENDER)", () => {
  const Pi = { t: T0 - 60, ops: [{ base: "RENDER", inst: "RENDER-USD_UM_XPERP-310711", estrategia: "bbc2557ab78e", lado: "SHORT", estado: "aberta",
                                   preco_efetivo: 1.485, stop: 1.511, alvo: null, alav: 5, stop_estado: "confirmado", stop_cobertura: 1, t_execucao: T0 - 3000 },
                                 { base: "OLD", estado: "fechada", lado: "LONG" }] };
  const K = { t: T0, posicoes: [{ asset: "PARTI", inst: "PARTI-X", contratos: 10, entrada: 0.04128 },
                                { asset: "RENDER", inst: "RENDER-USD_UM_XPERP-310711", contratos: -6, entrada: 1.485 }], ordens: [{ asset: "ZZZ", preco: 1.0, contratos: 5, lado: "buy" }] };
  const o = D.okxOperacoes(OKX(), K, Pi), r = D.reconciliar(o.posicoes, o.ordens, K);
  const p = o.posicoes.find(x => x.ativo === "RENDER");
  assert.equal(p.fonte, "estado do piloto"); assert.equal(p.stop, 1.511); assert.equal(p.stop_estado, "confirmado"); assert.ok(p.stop_confirmado);
  assert.equal(p.lado, "SHORT"); assert.equal(r.itens.find(i => i.ativo === "RENDER").estado, "confere");
  assert.equal(o.posicoes.filter(x => x.ativo === "OLD").length, 0);
  const sem = D.okxOperacoes(OKX(), K, { t: T0, ops: [{ ...Pi.ops[0], stop_estado: "inexistente" }] }).posicoes.find(x => x.ativo === "RENDER");
  assert.equal(sem.stop_confirmado, null); assert.equal(sem.stop_estado, "inexistente");
  assert.equal(D.okxOperacoes(OKX(), K, null).posicoes.find(x => x.ativo === "RENDER").fonte, "só na corretora");   // sem o ficheiro do piloto: aviso mantem-se
});
test("rotulos do executor OKX antigo: nome real, desconhecida nunca vira H40 (18/11, XLM espelho)", () => {
  assert.equal(D.rotuloOKX({ estrategia: "espelho", estrategia_bybit: "SHORT_TURTLE" }), "Espelho da arena (SHORT_TURTLE)");
  assert.equal(D.rotuloOKX({ estrategia: "espelho" }), "Espelho da arena");
  assert.equal(D.rotuloOKX({ estrategia: "recuo" }), "H46 recuo");
  assert.equal(D.rotuloOKX({ estrategia: "panico" }), "H40 pânico");
  assert.equal(D.rotuloOKX({ estrategia: "xpto" }), "desconhecida (xpto)");
  assert.equal(D.rotuloOKX({}), "desconhecida (sem nome)");
  const O = OKX(); O.real.ops.XLM = { inst: "XLM-X", estado: "aberta", estrategia: "espelho", estrategia_bybit: "SHORT_TURTLE", lado: "SHORT", entrada: 0.13745, stop: 0.15363 };
  const p = D.okxOperacoes(O, null).posicoes.find(x => x.ativo === "XLM");
  assert.equal(p.estrategia, "Espelho da arena (SHORT_TURTLE)"); assert.equal(p.lado, "SHORT");
  const Pi = { t: T0, ops: [{ base: "SPCX", inst: "SPCX-X", estrategia: "29933c49ce9e", lado: "LONG", estado: "aberta", preco_efetivo: 142.89, stop: 137.92, stop_estado: "confirmado" }] };
  assert.equal(D.okxOperacoes(O, null, Pi).posicoes.find(x => x.ativo === "SPCX").estrategia, "Piloto · 29933c49ce9e");
});
test("operacoes reais fechadas: piloto incluido e Bybit so com o R da corretora (19/11)", () => {
  const Pi = { t: 1795075980, ops: [
    { id: "29933c49ce9e|SPCX|1794974400", base: "SPCX", estado: "fechada", lado: "LONG", estrategia: "29933c49ce9e", preco_efetivo: 142.89,
      preco_saida: 146.32, r: 0.581, motivo_saida: "espelho do papel (tempo)", t_execucao: 1794989209, t_fecho: 1795075614 },
    { id: "bbc2557ab78e|RENDER|1794956400", base: "RENDER", estado: "fechada", lado: "SHORT", estrategia: "bbc2557ab78e", r: 1.143, t_fecho: 1794976399 },
    { id: "x|Y|1", base: "YYY", estado: "fechada", lado: "LONG", estrategia: "x", r: -1, pnl_por_confirmar: true, t_fecho: 1795000000 },
    { id: "a|B|1", base: "BBB", estado: "aberta", lado: "LONG", estrategia: "a" }] };
  const f = D.okxFechadas({ real: { hist: [{ asset: "HUMA", estado: "fechada", estrategia: "panico", R: -0.98, fechado: 1793000000 }] } }, null, Pi).publico;
  assert.deepEqual(f.map(x => x.ativo), ["SPCX", "YYY", "RENDER", "HUMA"]);          // do mais recente para o mais antigo
  const spcx = f[0];
  assert.equal(spcx.executor, "piloto"); assert.equal(spcx.R, 0.581); assert.equal(spcx.saida, 146.32); assert.ok(spcx.confirmado);
  assert.equal(f[1].R, null); assert.equal(f[1].confirmado, false);                    // por confirmar: nunca um R inventado
  assert.equal(f[3].executor, "executor antigo");
  const S = { journal: { rows: [
    { mode: "REAL", status: "CLOSED", executed: true, asset: "BTC", strategy: "SHORT_TURTLE", side: "SHORT", result_r: 1.47, real_r: 0.09, closed_at: 1794689886 },
    { mode: "REAL", status: "CLOSED", executed: true, asset: "SEI", strategy: "SHORT_TURTLE", side: "SHORT", result_r: 1.307, real_r: null, closed_at: 1793400000 }] } };
  const fr = D.fechadasR(null, S, Pi);
  assert.deepEqual(fr.map(x => [x.ativo, x.R]), [["BTC", 0.09], ["RENDER", 1.143], ["SPCX", 0.581]]);   // SEI fica de fora
  const by = D.bybitOperacoes(S, null).fechadas;
  assert.equal(by.find(x => x.ativo === "BTC").R, 0.09);                               // o da corretora, nao o do modelo (1,47)
  const sei = by.find(x => x.ativo === "SEI");
  assert.equal(sei.R, null); assert.equal(sei.R_modelo, 1.307); assert.equal(sei.estado, "por confirmar na corretora");
  const d = D.desempenho("Piloto · 29933c49ce9e", { Pi });
  assert.deepEqual(d.map(x => [x.ambiente, x.n, x.r_medio]), [["REAL", 1, 0.581]]);
});

test("piloto: preco atual e R da posicao aberta vem do estado do piloto (18/11)", () => {
  const Pi = { t: 2_000_000_000, ops: [{ base: "SPCX", inst: "SPCX-X", estrategia: "29933c49ce9e", lado: "LONG", estado: "aberta",
    preco_efetivo: 142.89, stop: 137.92, stop_estado: "confirmado", preco_atual: 145.37, t_preco: 2_000_000_000 - 60, r_aberto: 0.499 }] };
  const p = D.okxOperacoes(null, null, Pi, 2_000_000_000).posicoes.find(x => x.ativo === "SPCX");
  assert.equal(p.preco_atual, 145.37); assert.equal(p.preco_t, 2_000_000_000 - 60); assert.equal(p.R, 0.499);
  const sem = D.okxOperacoes(null, null, { t: 1, ops: [{ ...Pi.ops[0], preco_atual: undefined, r_aberto: undefined }] }, 2).posicoes[0];
  assert.equal(sem.preco_atual, null); assert.equal(sem.R, null);
});

test("frescura das operacoes OKX: indisponivel nao e fechada; dados antigos nao passam por atuais (18/11)", () => {
  const O = OKX(); O.real.ops.XLM = { inst: "XLM-X", estado: "aberta", estrategia: "espelho", estrategia_bybit: "SHORT_TURTLE", lado: "SHORT", entrada: 0.13745, stop: 0.15363 };
  const tO = D.horaDe("okx", O);
  // piloto indisponivel (pedido falhou): a fonte fica marcada, a XLM do agente continua com a hora dela
  let r = D.okxOperacoes(O, null, null, tO + 60);
  assert.equal(r.fontes.piloto.estado, "indisponivel"); assert.deepEqual(r.faltam, ["piloto"]);
  const x = r.posicoes.find(p => p.ativo === "XLM");
  assert.equal(x.dados_estado, "atual"); assert.equal(x.dados_t, tO);
  assert.match(D.textoDados(x.dados_estado, x.dados_t, tO + 60), /^dados de \d\d:\d\d$/);
  // piloto lido mas antigo: posicao marcada como desatualizada, nunca como atual
  const Pi = { t: tO - 4 * 5400, ops: [{ base: "SPCX", inst: "SPCX-X", estrategia: "29933c49ce9e", lado: "LONG", estado: "aberta", preco_efetivo: 142.89, stop: 137.92, stop_estado: "confirmado" }] };
  r = D.okxOperacoes(O, null, Pi, tO);
  const s = r.posicoes.find(p => p.ativo === "SPCX");
  assert.equal(s.dados_estado, "desatualizado"); assert.deepEqual(r.antigas, ["piloto"]);
  assert.match(D.textoDados(s.dados_estado, s.dados_t, tO), /DESATUALIZADOS/);
  // piloto sem hora: nunca "atual"
  r = D.okxOperacoes(O, null, { ops: Pi.ops }, tO);
  assert.equal(r.posicoes.find(p => p.ativo === "SPCX").dados_estado, "sem_hora");
  // piloto atual e sem operacoes abertas: nada falta (e "sem posicoes", nao "sem dados")
  r = D.okxOperacoes(O, null, { t: tO, ops: [{ base: "RENDER", estado: "fechada" }] }, tO);
  assert.deepEqual(r.faltam, []); assert.deepEqual(r.antigas, []); assert.equal(r.posicoes.filter(p => p.ativo === "RENDER").length, 0);
  // os dois indisponiveis
  r = D.okxOperacoes(null, null, null, tO);
  assert.deepEqual(r.faltam.sort(), ["agente", "piloto"]); assert.equal(r.posicoes.length, 0);
  assert.equal(D.textoDados("indisponivel", null), "dados indisponíveis");
});
test("Bybit: so conta como posicao real o que o motor executou; sinais nao executados ficam a parte", () => {
  const b = D.bybitOperacoes(SCAN(), null);
  assert.equal(b.posicoes.length, 0); assert.equal(b.sinais_nao_executados.length, 1); assert.equal(b.fechadas[0].R, 1.3);
});

// ------------------------------------------------------------------ estrategias e alertas reais
test("estrategias: H40 suspensa e H46 ativa lidas da configuracao real", () => {
  const e = D.estrategias(CFG, SCAN(), {});
  assert.equal(e.find(x => x.nome === "H40 pânico").ativa, false); assert.equal(e.find(x => x.nome.startsWith("H46")).ativa, true);
  assert.equal(e.find(x => x.nome === "BREAKOUT").ativa, false);
});
test("alertas: stop por confirmar e falha de ligacao sao criticos", () => {
  const O = OKX(); delete O.real.ops.PARTI.stop_ok;
  const al = D.alertas({ okx: { ligacao: "falhou", razao: "x" }, bybit: { ligacao: "ligado" }, O, S: SCAN(), cfgOkx: CFG, agora: T0 });
  assert.ok(al.some(a => a.nivel === "critico" && /stop ainda não confirmado/.test(a.texto)));
  assert.ok(al.some(a => a.nivel === "critico" && /OKX: x/.test(a.texto)));
});

// ------------------------------------------------------------------ indicadores
test("indicadores: medias, RSI e MACD", () => {
  const v = Array.from({ length: 60 }, (_, i) => 100 + i);
  assert.equal(D.mm(v, 3)[2], 101); assert.equal(D.rsi(v, 14).at(-1), 100);
  const m = D.macd(v); assert.ok(m.linha.at(-1) > 0); assert.ok(m.sinal.at(-1) != null);
  const c = v.map((x, i) => ({ t: i, o: x, h: x + 1, l: x - 1, c: x }));
  assert.ok(D.atrPct(c) > 0);
});
test("velas: sem nenhuma fonte devolve vazio com a razao", async () => {
  const r = await D.velas("BTC", { fetchFn: async () => { throw new TypeError("x"); } });
  assert.equal(r.velas.length, 0); assert.equal(r.fonte, null); assert.match(r.erro, /nenhuma fonte/);
});
test("velas: so fontes que o browser deixa ler (OKX global, Binance); Bybit UE e OKX EEA bloqueiam CORS", async () => {
  const pedidos = [];
  const r = await D.velas("PARTI", { fetchFn: async u => { pedidos.push(u);
    return { ok: true, json: async () => ({ code: "0", data: Array.from({ length: 40 }, (_, i) => [String((40 - i) * 3600e3), "1", "2", "0.5", "1.5", "10"]) }) }; } });
  assert.match(pedidos[0], /www\.okx\.com.*PARTI-USDT-SWAP/); assert.match(r.fonte, /OKX/); assert.equal(r.velas.length, 40);
  assert.ok(r.velas[0].t < r.velas[1].t);
  const src = fs.readFileSync(path.join(AQUI, "..", "dados.js"), "utf8");
  assert.ok(!src.includes("api.bybit.eu") && !src.includes("eea.okx.com"));
});
test("livro: OKX e depois Binance; sem nenhum, indisponivel com razao", async () => {
  const L = await D.livro("BTC", { fetchFn: async u => ({ ok: true, json: async () => u.includes("okx") ? { code: "0", data: [{ ts: "1", bids: [["1", "2"]], asks: [["1.1", "2"]] }] } : {} }) });
  assert.match(L.fonte, /OKX/);
  const L2 = await D.livro("BTC", { fetchFn: async () => { throw new TypeError("x"); } });
  assert.equal(L2.fonte, null); assert.match(L2.erro, /indisponível/);
});

// ------------------------------------------------------------------ agentes: estado visual = estado real
const ctx = (extra = {}) => {
  const fontes = { scan: D.estadoFonte("scan", ok(SCAN()), { agora: T0 }), okx: D.estadoFonte("okx", ok(OKX()), { agora: T0 }),
                   derivados: D.estadoFonte("derivados", ok({ t: T0 - 300 }), { agora: T0 }), tfshort: D.estadoFonte("tfshort", ok({}), { agora: T0 }),
                   cofreScan: D.estadoFonte("cofreScan", ok({ cifra: "cs1" }), { agora: T0 }), ...(extra.fontes || {}) };
  return { fontes, O: OKX(), S: SCAN(), St: {}, Dv: { t: T0 - 300, moedas: { BTC: [] } }, T: {}, cfgOkx: CFG, K: null, P: null, eventos: [], ...extra, fontes };
};
test("agentes: todos os agentes tem nome, funcao, componente real e estado conhecido", () => {
  const e = estadosAgentes(ctx(), T0);
  for (const a of AGENTES) { assert.ok(a.nome && a.funcao && a.componente); assert.ok(ESTADOS[e[a.id].estado], a.id); }
});
test("agentes: executora OKX monitoriza quando ha posicao real; risco avalia", () => {
  const e = estadosAgentes(ctx(), T0);
  assert.equal(e.exec_okx.estado, "monitorizar"); assert.match(e.exec_okx.atividade, /PARTI/);
  assert.equal(e.risco.estado, "risco"); assert.match(e.risco.atividade, /teto 3%/);
});
test("agentes: sem dados recentes aparecem desligados; fonte em falha aparece com erro", () => {
  const O = OKX(); O.resumo.t = T0 - 50000; O.volta.t = T0 - 50000;
  const e = estadosAgentes(ctx({ O, fontes: { okx: D.estadoFonte("okx", ok(O), { agora: T0 }) } }), T0);
  assert.equal(e.panico.estado, "desligado"); assert.equal(e.exec_okx.estado, "desligado");
  const e2 = estadosAgentes(ctx({ fontes: { okx: D.estadoFonte("okx", falha("HTTP 500"), { agora: T0 }) } }), T0);
  assert.equal(e2.panico.estado, "erro"); assert.match(e2.panico.atividade, /HTTP 500/);
});
test("agentes: entre passagens horarias ficam em espera com a proxima passagem", () => {
  const O = OKX(); O.resumo.t = T0 - 2400; O.volta.t = T0 - 2400;
  const e = estadosAgentes(ctx({ O, fontes: { okx: D.estadoFonte("okx", ok(O), { agora: T0 }) } }), T0);
  assert.equal(e.panico.estado, "espera"); assert.equal(e.panico.proxima, T0 - 2400 + 3600);
});
test("agentes: nucleo sem cofre = sem acesso (nunca inventa o estado)", () => {
  assert.equal(estadosAgentes(ctx(), T0).nucleo.estado, "cifrado");
});
test("colaboracao: so encaminhamentos reais com hora, dentro da janela", () => {
  const ev = D.eventos({ O: OKX(), S: SCAN() });
  const c = colaboracoes(ev, T0, 6 * 3600);
  assert.ok(c.length > 0); assert.ok(c.every(x => x.de && x.para && x.t >= T0 - 6 * 3600));
  assert.ok(c.some(x => x.de === "panico" || x.de === "recuo"));
  assert.equal(colaboracoes([], T0).length, 0);
});

// ------------------------------------------------------------------ cofre: o formato do engine/cifra.py abre no browser
test("cofre: envelope do engine/cifra.py abre com scanner/cifra.js e alimenta a reconciliacao", async () => {
  const env = JSON.parse(fs.readFileSync(path.join(AQUI, "cofre_teste.json"), "utf8"));
  const store = { cryptoscan_pw: "palavra-de-teste" };
  const sandbox = { window: {}, TextEncoder, TextDecoder, atob, crypto: globalThis.crypto, Uint8Array, localStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } }, document: {} };
  vm.runInNewContext(fs.readFileSync(path.join(AQUI, "..", "..", "cifra.js"), "utf8"), sandbox);
  const K = await sandbox.window.CIFRA.json(env);
  assert.equal(K.posicoes[0].asset, "PARTI");
  const o = D.okxOperacoes(OKX(), K);
  assert.equal(D.reconciliar(o.posicoes, o.ordens, K).itens.find(i => i.ativo === "PARTI").estado, "confere");
  await assert.rejects(sandbox.window.CIFRA.abrir(env, "errada"));
});

// ------------------------------------------------------------------ seguranca: so leitura, sem credenciais no frontend
test("frontend: sem chaves, sem pedidos privados, sem ordens", () => {
  const dir = path.join(AQUI, "..");
  const src = fs.readdirSync(dir).filter(f => f.endsWith(".js")).map(f => fs.readFileSync(path.join(dir, f), "utf8")).join("\n")
    + fs.readFileSync(path.join(dir, "..", "index.html"), "utf8");
  assert.ok(!/\bsecret\b|api[_-]?secret|OKX_API|BYBIT_API/i.test(src), "credenciais no frontend");
  for (const proibido of ["OK-ACCESS-KEY", "X-BAPI-API-KEY", "api_key", "apiKey", "passphrase", "/trade/order", "cancel-order", "close-position",
                          "/v5/order/", "withdraw", "transfer", "method: \"POST\"", "method:'POST'", "method:\"POST\""])
    assert.ok(!src.includes(proibido), `encontrado no frontend: ${proibido}`);
});
test("escritorio Atlas: um so piso, nove areas, sem escadas nem outros niveis", async () => {
  const src = fs.readFileSync(path.join(AQUI, "..", "escritorio.js"), "utf8");
  assert.ok(!/escada|stairs|segundo piso|piso\s*[2-9]|floor[2-9]/i.test(src.replace(/sem escadas nem outros niveis/g, "")));
  assert.equal((src.match(/new THREE\.PlaneGeometry\(W, D\)/g) || []).length, 1);            // uma unica laje
  const { AREAS } = await import("../agentes.js");
  assert.deepEqual(Object.keys(AREAS).sort(), ["cacador", "comando", "estrategia", "exchanges", "intel", "quant", "risco", "tecnica", "trading"]);
  for (const a of AGENTES) assert.ok(AREAS[a.zona], `${a.id} sem area`);
  for (const k of Object.keys(AREAS)) assert.ok(new RegExp(`\\b${k}:\\s*\\{ x:`).test(src), `area ${k} sem lugar no piso`);
});

// ------------------------------------------------------------------ ambientes e resultado
test("ambientes: papel e sombra separados do real, cada um com a origem", () => {
  const O = OKX(); O.resumo.abertas = ["BCH"]; O.macro.abertas = { AAPL: {} };
  const s = D.simuladas(O, { papel_fases: { lateral: { abertas: ["ETH"] } } }, { sinais: { abertas: { DOGE: { entrada: 1, stop: 1.2, t: T0 } } } }, { estado: { abertas: { SUI: { px_fill: 2, stop: 2.4, t_fill: T0 } } } });
  assert.deepEqual([...new Set(s.map(x => x.ambiente))].sort(), ["PAPEL", "SOMBRA"]);
  assert.ok(s.every(x => x.origem && x.ativo && x.lado)); assert.equal(s.find(x => x.ativo === "SUI").ambiente, "SOMBRA");
  assert.ok(!s.some(x => x.ativo === "PARTI"));                                                // a posicao real nao entra aqui
});
test("resultado: R das fechadas reais (OKX pelo preco de saida, Bybit pelo journal) e R atual", () => {
  const O = OKX(); O.real.hist = [{ asset: "PENGU", estado: "fechada", entrada: 100, stop: 90, saida: 90, fechado: T0 - 100, estrategia: "panico" }, { asset: "X", estado: "cancelada", fechado: T0 }];
  const f = D.fechadasR(O, SCAN());
  assert.deepEqual(f.map(x => [x.corretora, x.R]), [["Bybit", 1.3], ["OKX", -1]]);
  assert.deepEqual(D.acumulado(f).map(x => Math.round(x.v * 100) / 100), [1.3, 0.3]);
  assert.equal(D.deHoje(f, T0).length, 1);
  assert.equal(D.rAtual({ lado: "LONG", entrada: 100, stop: 90 }, 105), 0.5); assert.equal(D.rAtual({ lado: "SHORT", entrada: 100, stop: 110 }, 105), -0.5);
  assert.equal(D.rAtual({ lado: "LONG", entrada: 100, stop: 90 }, null), null);
});
test("desempenho: cada numero traz o ambiente (backtest nunca passa por real)", () => {
  const S = SCAN(); S.arena.classificacao = [{ id: "SHORT_TURTLE", estado: "A COMPETIR", n: 4, wins: 2, avg_r: 0.3 }];
  const d = D.desempenho("SHORT_TURTLE", { O: OKX(), S });
  assert.deepEqual(d.map(x => x.ambiente), ["REAL", "BACKTEST"]); assert.equal(d[0].n, 1);
});
test("suporte e resistencia: minimo e maximo das ultimas velas", () => {
  const v = Array.from({ length: 60 }, (_, i) => ({ h: 10 + i, l: 5 + i }));
  assert.deepEqual(D.suporteResistencia(v, 50), { suporte: 15, resistencia: 69, n: 50 });
});

test("acumulacao: pesos em %, desvios em pp, estado reservado enquanto ha trading aberto (19/11)", () => {
  const S = { acumulacao: { modo: "sombra", estado: "reservado", posicoes_de_trading_por_fechar: true,
    pesos_alvo_pct: { BTC: 70, ETH: 15, SOL: 3.75 }, desvios_pp: {}, fora_da_bybit: ["AVAX"], ordens: { comprar: 0, vender: 0 }, t: 1 } };
  const v = D.acumulacaoVista(S);
  assert.equal(v.ativa, true);
  assert.equal(v.reservado, true);
  assert.match(v.estado, /reservado/);
  assert.deepEqual(v.linhas.map(l => [l.ativo, l.alvo_pct, l.atual_pct]), [["BTC", 70, null], ["ETH", 15, null], ["SOL", 3.75, null]]);
  const v2 = D.acumulacaoVista({ acumulacao: { modo: "sombra", estado: "ordens", pesos_alvo_pct: { BTC: 70 }, desvios_pp: { BTC: -10 } } });
  assert.equal(v2.linhas[0].atual_pct, 60);
  assert.equal(D.acumulacaoVista({}).ativa, false);
});

test("trading OKX: posicoes dos dois executores, funil do dia, sombra e contabilidade sem dinheiro (19/11)", () => {
  const t = Date.UTC(2026, 10, 19, 12) / 1000;
  const Pi = { ops: [{ base: "BASED", lado: "LONG", estrategia: "a5", estado: "aberta", r_aberto: -0.2, stop_confirmado: true },
                     { base: "SPCX", estado: "fechada" }],
    estados: { a5: "EXPERIMENTAL_REAL" },
    resumo_oportunidades: { "2026-11-19": { voltas: 30, voltas_sem_sinais: 27, por_categoria: { executada: 2, liquidez: 4, expirado: 4 } } } };
  const O = { real: { ops: { XLM: { estado: "aberta", lado: "SHORT", estrategia: "espelho", stop_ok: 123 } } } };
  const Sr = { moedas: 46, elegibilidade: { elegiveis: 46, perpetuos: 534 }, abertas: { a: {} }, fechadas: [{}],
    resumo: { "R3|4h|LONG": { n: 5, dias_independentes: 2, media_R_liquido: 0.1 } }, t };
  const C = { relatorio: { por_executor: { piloto: { n: 2, soma_r: 2.18, expectativa_r: 1.09 } } } };
  const v = D.tradingOkx({ Pi, O, Sr, C }, t);
  assert.deepEqual(v.vivas.map(x => [x.executor, x.ativo, x.lado, x.stop]), [["piloto", "BASED", "LONG", true], ["executor antigo", "XLM", "SHORT", true]]);
  assert.deepEqual([v.funil.executadas, v.funil.rejeitadas, v.funil.voltas], [2, 8, 30]);
  assert.equal(v.sombra.elegiveis, 46);
  assert.equal(v.sombra.linhas[0].k, "R3|4h|LONG");
  assert.equal(v.contas[0].soma_r, 2.18);
  const vazio = D.tradingOkx({}, t);
  assert.deepEqual([vazio.vivas.length, vazio.funil.voltas, vazio.sombra.abertas], [0, 0, 0]);
});
