// (10/11) Evidencia visual do Operations Center com dados REAIS e rede real (corre no GitHub, ramo escritorio-v2).
// Cofre fechado: as capturas nao tem saldos nem quantidades. Regista erros de consola, fontes das velas e desempenho.
const { chromium } = require("playwright"); const fs = require("fs");
const URL = process.env.URL || "http://127.0.0.1:8000/index.html", OUT = process.env.OUT || "capturas";
fs.mkdirSync(OUT, { recursive: true });
const rel = { erros: [], avisos: [], pedidos_falhados: [], passos: [] };
async function sessao(nome, vp, passos, extra = {}) {
  const b = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1.5, ...extra }); const p = await ctx.newPage();
  p.on("console", m => { if (m.type() === "error") rel.erros.push(`${nome}: ${m.text()}`); if (m.type() === "warning") rel.avisos.push(`${nome}: ${m.text()}`); });
  p.on("pageerror", e => rel.erros.push(`${nome} PAGEERROR: ${e.message}`));
  p.on("requestfailed", r => rel.pedidos_falhados.push(`${nome}: ${r.url().slice(0, 120)} ${r.failure() && r.failure().errorText}`));
  await p.goto(URL, { waitUntil: "domcontentloaded" }); await p.waitForFunction(() => document.body.classList.contains("carregado"), null, { timeout: 60000 }); await p.waitForTimeout(6000);
  for (const [n, f] of passos) { try { await f(p); await p.waitForTimeout(2200); await p.screenshot({ path: `${OUT}/${nome}-${n}.jpg`, type: "jpeg", quality: 82 }); rel.passos.push(`${nome}-${n}: ok`); } catch (e) { rel.passos.push(`${nome}-${n}: FALHOU ${e.message.slice(0, 160)}`); } }
  rel[nome] = await p.evaluate(() => { const A = window.CS_APP, c = A.ctx || {}; return { fps: A.of ? A.of.fps : null, qualidade: A.of ? A.of.qualidade : "2d",
    fontes: Object.fromEntries(Object.entries(c.fontes || {}).map(([k, f]) => [k, f.estado + (f.razao ? " (" + f.razao + ")" : "")])),
    okx: c.okx && c.okx.ligacao, bybit: c.bybit && c.bybit.ligacao, velas: Object.fromEntries(Object.entries(A.velas).map(([k, v]) => [k, v.fonte || v.erro])),
    agentes: Object.fromEntries(Object.entries(c.estados || {}).map(([k, s]) => [k, s.estado])), posicoes: (c.posicoes || []).map(p => `${p.corretora} ${p.ativo} ${p.lado}`),
    botoes_sem_acao: [...document.querySelectorAll("button")].filter(b => !b.hasAttribute("data-acao") && !b.hasAttribute("data-tab") && !b.hasAttribute("data-min") && !b.hasAttribute("data-max") && !b.dataset.vista && b.id !== "insp-fechar" && !b.closest(".of-overlay")).map(b => b.outerHTML.slice(0, 80)) }; });
  await b.close();
}
(async () => {
  const c = s => p => p.click(s);
  await sessao("desktop", { width: 1600, height: 960 }, [
    ["1-visao-geral", async () => {}],
    ["2-agente-ines", c("[data-acao='agente:exec_okx']")],
    ["3-okx", c("[data-acao='corretora:OKX']")],
    ["4-posicao-parti", async p => { await p.click(".doca [data-tab='posicoes']"); await p.click("tr[data-acao^='posicao:OKX']"); await p.waitForTimeout(4000); }],
    ["5-ativo", async p => { await p.click("#insp-corpo [data-acao^='ativo:']"); await p.waitForTimeout(5000); }],
    ["5b-ativo-btc-4h", async p => { await p.evaluate(() => { const b = document.createElement("button"); b.dataset.acao = "ativo:BTC:4h"; document.body.appendChild(b); b.click(); b.remove(); }); await p.waitForTimeout(5000); }],
    ["6-mercado-global", async p => { await p.click("#insp-fechar"); await p.click(".doca [data-tab='mercado']"); await p.click(".doca [data-max]"); }],
    ["7-zona-comando", async p => { await p.click(".doca [data-max]"); await p.click(".doca [data-min]"); await p.click("[data-acao='zona:comando']"); await p.waitForTimeout(1500); }],
    ["8-zona-corretoras", async p => { await p.click("#insp-fechar"); await p.click("[data-acao='zona:exchanges']"); }],
    ["9-fontes", async p => { await p.click("#insp-fechar"); await p.click(".doca [data-min]"); await p.click(".doca [data-tab='fontes']"); }],
  ]);
  await sessao("alta", { width: 1600, height: 960 }, [["visao-geral-3d-alta", async p => { await p.click("[data-vista='alta']"); await p.waitForTimeout(5000); }]]);
  await sessao("telemovel", { width: 390, height: 844 }, [["1-inicio", async () => {}], ["2-agente", c("[data-acao='agente:panico']")], ["3-2d", async p => { await p.click("#insp-fechar"); await p.click("[data-vista='2d']"); }]], { isMobile: true, hasTouch: true });
  fs.writeFileSync(`${OUT}/relatorio.json`, JSON.stringify(rel, null, 1));
  console.log("ERROS", JSON.stringify(rel.erros, null, 1)); console.log("PEDIDOS FALHADOS", JSON.stringify(rel.pedidos_falhados.slice(0, 30), null, 1)); console.log("PASSOS", JSON.stringify(rel.passos, null, 1));
  for (const k of ["desktop", "alta", "telemovel"]) console.log(k.toUpperCase(), JSON.stringify(rel[k]));
})();
