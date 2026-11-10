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
  journal: { rows: [{ asset: "SEI", strategy: "SHORT_TURTLE", side: "SHORT", mode: "REAL", status: "CLOSED", executed: true, issued_at: T0 - 9e5, closed_at: T0 - 5e5, result_r: 1.3 },
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
test("velas: posicao OKX tenta primeiro o instrumento da OKX", async () => {
  const pedidos = [];
  const r = await D.velas("PARTI", { inst: "PARTI-USD_UM_XPERP-311010", fetchFn: async u => { pedidos.push(u);
    return { ok: true, json: async () => ({ code: "0", data: Array.from({ length: 40 }, (_, i) => [String((40 - i) * 3600e3), "1", "2", "0.5", "1.5", "10"]) }) }; } });
  assert.match(pedidos[0], /eea\.okx\.com.*PARTI-USD_UM_XPERP-311010/); assert.match(r.fonte, /OKX/); assert.equal(r.velas.length, 40);
  assert.ok(r.velas[0].t < r.velas[1].t);
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
test("escritorio: um so piso (sem escadas nem outros pisos)", () => {
  const src = fs.readFileSync(path.join(AQUI, "..", "escritorio.js"), "utf8");
  assert.ok(!/escada|stairs|piso\s*[2-9]|P[0-4]H|floor[2-9]/i.test(src.replace(/UM SO PISO|sem escadas nem outros pisos/g, "")));
  assert.equal((src.match(/new THREE\.PlaneGeometry\(66, 42\)/g) || []).length, 1);
});
