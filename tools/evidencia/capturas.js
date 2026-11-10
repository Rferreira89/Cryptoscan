// (10/11) Evidencia visual do CryptoScan Atlas com dados REAIS e rede real (corre no GitHub, ramo atlas).
// Cofre fechado: as capturas nao tem saldos nem quantidades. Regista erros de consola, layout sem scroll, botoes e desempenho.
const { chromium } = require("playwright"); const fs = require("fs");
const URL = process.env.URL || "http://127.0.0.1:8000/index.html", OUT = process.env.OUT || "capturas";
fs.mkdirSync(OUT, { recursive: true });
const rel = { erros: [], pedidos_falhados: [], passos: [] };
async function sessao(nome, vp, passos, extra = {}) {
  const b = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1, ...extra }); const p = await ctx.newPage();
  p.on("console", m => { if (m.type() === "error") rel.erros.push(`${nome}: ${m.text()}`); });
  p.on("pageerror", e => rel.erros.push(`${nome} PAGEERROR: ${e.message}`));
  p.on("requestfailed", r => rel.pedidos_falhados.push(`${nome}: ${r.url().slice(0, 120)} ${r.failure() && r.failure().errorText}`));
  await p.goto(URL, { waitUntil: "domcontentloaded" }); await p.waitForFunction(() => document.body.classList.contains("carregado"), null, { timeout: 60000 }); await p.waitForTimeout(9000);
  for (const [n, f] of passos) { try { await f(p); await p.waitForTimeout(2500); await p.screenshot({ path: `${OUT}/${nome}-${n}.jpg`, type: "jpeg", quality: 84 }); rel.passos.push(`${nome}-${n}: ok`); } catch (e) { rel.passos.push(`${nome}-${n}: FALHOU ${e.message.slice(0, 160)}`); } }
  rel[nome] = await p.evaluate(() => { const A = window.CS_APP, c = A.ctx || {}, attrs = ["data-acao", "data-amb", "data-ativ", "data-iv", "data-vista", "data-min", "data-m"]; return {
    fps: A.of ? A.of.fps : null, qualidade: A.of ? A.of.qualidade : "2d", scroll_pagina: document.documentElement.scrollHeight > innerHeight + 2, largura_ok: document.documentElement.scrollWidth <= innerWidth + 2,
    fontes: Object.fromEntries(Object.entries(c.fontes || {}).map(([k, f]) => [k, f.estado])), okx: c.okx && c.okx.ligacao, bybit: c.bybit && c.bybit.ligacao,
    velas: Object.fromEntries(Object.entries(A.velas).map(([k, v]) => [k, v.fonte || v.erro])), agentes: Object.fromEntries(Object.entries(c.estados || {}).map(([k, s]) => [k, s.estado + " | " + ((s.metrica || {}).txt || "")])),
    posicoes: (c.posicoes || []).map(p => `${p.corretora} ${p.ativo} ${p.lado} R=${p.R == null ? "?" : p.R.toFixed(2)} (${p.preco_de})`), simuladas: (c.simuladas || []).length, fechadas_reais: (c.fr || []).length,
    botoes_sem_acao: [...document.querySelectorAll("button")].filter(b => !attrs.some(a => b.hasAttribute(a)) && !b.id && !b.closest(".of-overlay")).map(b => b.outerHTML.slice(0, 80)) }; });
  await b.close();
}
(async () => {
  const c = s => p => p.click(s);
  await sessao("1920", { width: 1920, height: 1080 }, [
    ["01-visao-geral", async () => {}],
    ["02-agente", c("[data-acao='agente:exec_okx']")],
    ["03-okx", c("#estado [data-acao='corretora:OKX']")],
    ["04-posicao", async p => { await p.click("#ops-corpo .pos"); await p.waitForTimeout(4000); }],
    ["05-grafico-btc-4h", async p => { await p.click("#det-fechar"); await p.selectOption("#graf-ativo", "BTC"); await p.click("#graf-iv [data-iv='4h']"); await p.click("#graf-macd"); await p.waitForTimeout(4000); }],
    ["06-area-trading", c("#zonas [data-acao='zona:trading']")],
    ["07-parede", async p => { await p.click("#det-fechar"); await p.click("#zonas [data-acao='zona:parede']"); }],
    ["08-estrategia", async p => { await p.click("#det-fechar"); await p.click("#zonas [data-acao='tudo']"); await p.click("#ativ-tabs [data-ativ='estrategias']"); await p.click("#ativ-corpo tr[data-acao]"); }],
    ["09-papel-e-resultado", async p => { await p.click("#det-fechar"); await p.click("#ops-tabs [data-amb='PAPEL']"); await p.click("#ativ-tabs [data-ativ='resultado']"); }],
    ["10-alertas-e-ativo", async p => { await p.click("#ops-tabs [data-amb='REAL']"); await p.click("#ativ-tabs [data-ativ='oportunidades']"); await p.click("#ativ-corpo li[data-acao]").catch(() => {}); await p.waitForTimeout(3000); }],
  ]);
  await sessao("1440", { width: 1440, height: 900 }, [["01-visao-geral", async () => {}], ["02-posicao", async p => { await p.click("#ops-corpo .pos"); await p.waitForTimeout(3000); }]]);
  await sessao("3d-alta", { width: 1920, height: 1080 }, [["visao-geral", async p => { await p.click("[data-vista='alta']"); await p.waitForTimeout(6000); }]]);
  await sessao("telemovel", { width: 390, height: 844 }, [["01-inicio", async () => {}], ["02-graficos", c("#nav-m [data-m='graficos']")], ["03-atividade", c("#nav-m [data-m='atividade']")], ["04-equipa-e-agente", async p => { await p.click("#nav-m [data-m='agentes']"); await p.click("[data-acao='agente:panico']"); }]], { isMobile: true, hasTouch: true });
  await sessao("sem-3d", { width: 1440, height: 900 }, [["2d", async p => { await p.click("[data-vista='2d']"); }]]);
  fs.writeFileSync(`${OUT}/relatorio.json`, JSON.stringify(rel, null, 1));
  console.log("ERROS", JSON.stringify(rel.erros, null, 1)); console.log("PEDIDOS FALHADOS", JSON.stringify(rel.pedidos_falhados.slice(0, 30), null, 1)); console.log("PASSOS", JSON.stringify(rel.passos, null, 1));
  for (const k of ["1920", "1440", "3d-alta", "telemovel", "sem-3d"]) console.log("SESSAO " + k, JSON.stringify(rel[k]));
})();
