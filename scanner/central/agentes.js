// CryptoScan · Operations Center — os agentes REAIS do sistema e o estado de cada um.
//
// Cada agente corresponde a um componente que existe e corre (workflow ou modulo). O estado visual vem SO dos dados
// que esse componente publicou e da hora a que o fez: quem nao publicou ha muito aparece desligado, quem falhou aparece
// com erro, quem corre de hora a hora aparece em espera entre passagens (com a proxima passagem prevista).
// Nada aqui muda a logica dos agentes nem cria atividade: so le.
import { frescura, texIdade, idade } from "./dados.js";

export const ESTADOS = {
  analisar:      { nome: "A analisar",               cor: "#5AA9FF", ativo: true },
  procurar:      { nome: "A procurar oportunidades", cor: "#3EE0C4", ativo: true },
  monitorizar:   { nome: "A monitorizar posições",   cor: "#3FD68F", ativo: true },
  calcular:      { nome: "A executar cálculos",      cor: "#B59CFF", ativo: true },
  risco:         { nome: "A avaliar risco",          cor: "#F5B83D", ativo: true },
  comunicar:     { nome: "A comunicar resultados",   cor: "#7FE3FF", ativo: true },
  espera:        { nome: "Em espera",                cor: "#8796AA", ativo: false },
  cifrado:       { nome: "Sem acesso (cofre fechado)", cor: "#6E7FA3", ativo: false },
  desligado:     { nome: "Desligado",                cor: "#4A5566", ativo: false },
  erro:          { nome: "Com erro",                 cor: "#F0616D", ativo: false },
};

// zona da estacao no escritorio (escritorio.js) e o componente real que o agente representa
export const AGENTES = [
  { id: "scanner",    nome: "Sofia",  funcao: "Scanner de mercado · Bybit UE",            zona: "operacoes", cor: "#5AA9FF", componente: "scan.yml · engine/scanner.py (de 5 em 5 min)", fonte: "scan" },
  { id: "panico",     nome: "Nuno",   funcao: "Caçador de pânico · OKX (H40)",            zona: "operacoes", cor: "#3EE0C4", componente: "okx-agente.yml · tools/okx_agente.py (de hora a hora)", fonte: "okx" },
  { id: "recuo",      nome: "Rita",   funcao: "Recuo na subida · OKX (H46)",              zona: "operacoes", cor: "#45C9A6", componente: "tools/okx_recuo.py (com o agente OKX)", fonte: "okx" },
  { id: "macro",      nome: "Mateus", funcao: "Ações, índices e metais · OKX (papel)",    zona: "operacoes", cor: "#E9A15B", componente: "agente macro OKX (com o agente OKX)", fonte: "okx" },
  { id: "diretor",    nome: "Diana",  funcao: "Diretora de estratégia",                   zona: "comando",   cor: "#C8D3E6", componente: "engine/diretor (decisões do scanner)", fonte: "scan" },
  { id: "risco",      nome: "Óscar",  funcao: "Gestor de risco",                          zona: "risco",     cor: "#F5B83D", componente: "okx_config.json · engine/risco.py", fonte: "okx" },
  { id: "liquidez",   nome: "Leo",    funcao: "Liquidez e derivados",                     zona: "risco",     cor: "#8FB5FF", componente: "engine/derivhist.py · engine/liquidez.py", fonte: "derivados" },
  { id: "exec_okx",   nome: "Inês",   funcao: "Execução e posições · OKX",                zona: "exchanges", cor: "#E6EDF7", componente: "tools/okx_exec.py (de hora a hora)", fonte: "okx" },
  { id: "exec_bybit", nome: "Ivo",    funcao: "Execução e posições · Bybit UE",           zona: "exchanges", cor: "#F7A600", componente: "executar.yml · engine/executor.py", fonte: "scan" },
  { id: "nucleo",     nome: "Bento",  funcao: "Tendência BTC (núcleo) · Bybit UE",        zona: "exchanges", cor: "#F2B13C", componente: "engine/nucleo (dados só no cofre)", fonte: "cofreScan" },
  { id: "arena",      nome: "Clara",  funcao: "Análise quantitativa · Arena",             zona: "quant",     cor: "#B59CFF", componente: "arena.yml (de hora a hora)", fonte: "scan" },
  { id: "tfshort",    nome: "Tiago",  funcao: "TF-SHORT · OKX (papel e sombra)",          zona: "quant",     cor: "#9C8CFF", componente: "okx-tfshort-papel.yml (diário)", fonte: "tfshort" },
  { id: "noticias",   nome: "Nádia",  funcao: "Calendário macro e notícias",              zona: "colaboracao", cor: "#7FE3FF", componente: "engine/eventos (com o scanner)", fonte: "scan" },
];

const proxima = (t, periodo, agora) => {
  if (!t || !periodo) return null;
  let p = t + periodo; while (p < agora) p += periodo;
  return p;
};

// devolve { estado, atividade, t, idade, proxima, ligado, historico[] } para cada agente
export function estadosAgentes(ctx, agora = Date.now() / 1000) {
  const { fontes = {}, O, S, St, Dv, T, cfgOkx, K, P, eventos = [] } = ctx;
  const out = {};
  const f = k => fontes[k] || { estado: "falhou", razao: "sem pedido" };
  const base = (fonte, periodo, limite) => {
    const ef = f(fonte);
    if (ef.estado === "falhou") return { estado: "erro", atividade: `fonte indisponível: ${ef.razao}`, ligado: false };
    if (ef.estado === "bloqueado") return { estado: "cifrado", atividade: "os dados deste agente estão no cofre cifrado", ligado: true };
    return null;
  };
  const porIdade = (t, periodo, limite, ativo, textoAtivo, textoEspera) => {
    const fr = frescura(t, limite, agora);
    if (fr.estado === "sem_hora") return { estado: "espera", atividade: textoEspera || "sem hora de atualização publicada", t: null, ligado: true };
    if (fr.estado === "desatualizado") return { estado: "desligado", atividade: `sem atividade ${texIdade(fr.idade)} (esperado de ${Math.round(periodo / 60)} em ${Math.round(periodo / 60)} min)`, t, ligado: false };
    if (fr.estado === "atrasado") return { estado: "espera", atividade: `atrasado: última atividade ${texIdade(fr.idade)}`, t, ligado: true, atrasado: true };
    // atual: ativo se a ultima passagem foi ha pouco (dentro de 1/4 do periodo ou 10 min), senao em espera
    const recente = fr.idade <= Math.max(600, periodo / 4);
    return recente ? { estado: ativo, atividade: textoAtivo, t, ligado: true }
                   : { estado: "espera", atividade: textoEspera, t, ligado: true, proxima: proxima(t, periodo, agora) };
  };
  const R = (O || {}).resumo || {}, ops = ((O || {}).real || {}).ops || {}, tO = R.t || ((O || {}).volta || {}).t;
  const abertas = Object.entries(ops).filter(([, o]) => o.estado === "aberta"), pend = Object.entries(ops).filter(([, o]) => o.estado === "pendente");

  out.scanner = base("scan") || (() => {
    const bad = Object.entries((S || {}).sources || {}).filter(([, s]) => !s.ok).map(([n]) => n);
    if (bad.length) return { estado: "erro", atividade: `fontes de preços em falha: ${bad.join(", ")}`, t: (S || {}).generated_at, ligado: true };
    const c = (S || {}).counts || {};
    return porIdade((S || {}).generated_at, 300, 1200, "procurar",
      `analisou ${c.deep_checked ?? "?"} de ${c.eligible ?? "?"} pares elegíveis; ${(c.long || 0) + (c.short || 0)} sinais novos, ${(c.watchlist || 0) + (c.watch_short || 0)} a vigiar`,
      "entre passagens (de 5 em 5 min)");
  })();

  out.panico = base("okx") || porIdade(tO, 3600, 9000, (R.pendentes || []).length ? "analisar" : "procurar",
    `varreu ${R.analisados ?? "?"} perpétuos${(R.pendentes || []).length ? `; sinal (papel) em ${R.pendentes.join(", ")}` : "; sem pânico nesta hora"}${cfgOkx && !cfgOkx.panico_real ? " · H40 suspensa em real" : ""}`,
    `aguarda a próxima passagem horária${cfgOkx && !cfgOkx.panico_real ? " · H40 suspensa em real (só papel)" : ""}`);

  const rc = (O || {}).recuo || {}, rr = rc.resumo || {};
  out.recuo = base("okx") || porIdade(tO, 3600, 9000, (rr.pendentes || []).length ? "analisar" : "procurar",
    `${rr.btc_em_subida ? "BTC em subida" : "BTC sem subida: regra inativa"}; ${(rr.abertas || []).length} abertas, ${(rr.pendentes || []).length} pendentes`,
    `aguarda a próxima passagem horária${cfgOkx ? (cfgOkx.recuo_real ? ` · real ligado (risco ${cfgOkx.recuo_risco_pct}%)` : " · suspensa") : ""}`);

  const MR = ((O || {}).macro || {}).resumo || {};
  out.macro = base("okx") || porIdade(tO, 3600, 9000, "analisar", `${(MR.abertas || []).length} de ${MR.analisados ?? "?"} ações, índices e metais em tendência (papel)`, "aguarda a próxima passagem horária (papel)");

  out.exec_okx = base("okx") || (() => {
    const s = porIdade(tO, 3600, 9000, "monitorizar", "", "");
    if (s.estado === "desligado" || s.estado === "erro") return s;
    const priv = K ? ` · conta lida ${texIdade(idade(K.t, agora))}` : "";
    if (abertas.length) return { ...s, estado: s.estado === "espera" && s.atrasado ? "espera" : "monitorizar", atividade: `${abertas.length} posição(ões) real(is) sob gestão: ${abertas.map(([a]) => a).join(", ")} · stops confirmados de hora a hora${priv}` };
    if (pend.length) return { ...s, estado: "monitorizar", atividade: `${pend.length} ordem(ns) de entrada pendente(s): ${pend.map(([a]) => a).join(", ")}${priv}` };
    return { ...s, estado: "espera", atividade: `sem posições nem ordens reais${priv}` };
  })();

  out.risco = base("okx") || (() => {
    const s = porIdade(tO, 3600, 9000, "risco", "", "");
    if (s.estado === "desligado" || s.estado === "erro") return s;
    const c = cfgOkx || {};
    const aberto = abertas.reduce((x, [, o]) => x + (o.risco_pct || 0), 0);
    const t = `risco aberto OKX ${aberto.toFixed(2)}% (teto ${c.risco_total_max_pct ?? "?"}%) · ${c.risco_pct ?? "?"}% por operação · alavancagem ${c.alavancagem ?? "?"}x · travão a ${c.travao_queda_pct ?? "?"}%`;
    return { ...s, estado: abertas.length || pend.length ? "risco" : "espera", atividade: t };
  })();

  out.liquidez = base("derivados") || porIdade((Dv || {}).t, 3600, 9000, "calcular",
    `funding, open interest e long/short de ${Object.keys((Dv || {}).moedas || {}).length} moedas`, "aguarda a próxima recolha horária");

  out.exec_bybit = base("scan") || (() => {
    const rows = ((S || {}).journal || {}).rows || [], ab = rows.filter(r => r.mode === "REAL" && r.status === "OPEN" && r.executed === true);
    const auto = (St || {}).auto || {};
    const s = porIdade((S || {}).generated_at, 300, 1200, "monitorizar", "", "");
    if (s.estado === "desligado" || s.estado === "erro") return s;
    if (ab.length) return { ...s, estado: "monitorizar", atividade: `${ab.length} posição(ões) real(is): ${ab.map(r => `${r.asset} ${r.side}`).join(", ")}` };
    return { ...s, estado: "espera", atividade: `sem operações abertas pelo motor · modo automático ${auto.ligado ? "ligado" : "desligado"}` };
  })();

  out.nucleo = (() => {
    const ef = f("cofreScan");
    if (ef.estado === "falhou") return { estado: "erro", atividade: `cofre indisponível: ${ef.razao}`, ligado: false };
    if (!P) return { estado: "cifrado", atividade: "posição e plano do núcleo só no cofre cifrado", ligado: true };
    const N = (((P.nucleo || {}).plano || {}).BTC) || {};
    const s = porIdade(P.generated_at, 300, 1800, N.acima ? "monitorizar" : "espera", "", "");
    if (s.estado === "desligado") return s;
    return { ...s, estado: N.acima ? "monitorizar" : "espera", atividade: N.acima ? "BTC acima da média de 50 dias: núcleo comprado" : `à espera: BTC abaixo da média de 50 dias${N.media ? ` (${Math.round(N.media)})` : ""}` };
  })();

  out.diretor = base("scan") || (() => {
    const d = ((S || {}).diretor || {}).decisoes || [];
    const u = d[d.length - 1];
    if (!u) return { estado: "espera", atividade: "sem decisões publicadas", ligado: true };
    const a = idade(u.t, agora);
    return { estado: a < 1800 ? "comunicar" : "espera", t: u.t, ligado: true,
             atividade: `última decisão ${texIdade(a)}: ${u.ativo} ${u.lado} ${u.decisao}${(u.motivos || []).length ? ` (${u.motivos[0]})` : ""}` };
  })();

  out.arena = base("scan") || (() => {
    const A = (S || {}).arena || {};
    return porIdade(A.atualizado, 3600, 9000, "calcular", `${A.vivos ?? "?"} estratégias vivas na arena (mínimo ${A.minimo_vivos ?? "?"}); forma nos últimos ${(A.forma || {}).janela_dias ?? "?"} dias`,
      `${A.vivos ?? "?"} estratégias vivas; próximo combate de hora a hora`);
  })();

  out.tfshort = base("tfshort") || (() => {
    const ab = Object.keys((((T || {}).sinais || {}).abertas) || {});
    const ts = ab.map(a => T.sinais.abertas[a].t).filter(Boolean);
    const t = ts.length ? Math.max(...ts) : null;
    return porIdade(t, 86400, 3 * 86400, "analisar", `${ab.length} shorts em papel`, `${ab.length} shorts em papel; passa uma vez por dia`);
  })();

  out.noticias = base("scan") || (() => {
    const ev = (S || {}).next_event;
    const s = porIdade((S || {}).generated_at, 300, 1200, "analisar", "", "");
    if (s.estado === "desligado" || s.estado === "erro") return s;
    const bloq = (S || {}).event_block;
    return { ...s, estado: bloq ? "comunicar" : "espera",
             atividade: ev ? `${bloq ? "janela de risco: " : "próximo: "}${ev.name} ${ev.t > agora ? `em ${Math.round((ev.t - agora) / 3600 * 10) / 10} h` : ""}` : "sem eventos de risco no calendário" };
  })();

  for (const a of AGENTES) {
    const x = out[a.id] || { estado: "desligado", atividade: "sem dados" };
    x.idade = idade(x.t, agora);
    x.historico = eventos.filter(e => e.agente === a.id || e.para === a.id).slice(0, 12);
    out[a.id] = x;
  }
  return out;
}

// cadeia de colaboracao: so encaminhamentos REAIS (eventos com "para") nas ultimas horas
export function colaboracoes(eventos, agora = Date.now() / 1000, janela = 6 * 3600) {
  return eventos.filter(e => e.para && agora - e.t <= janela).map(e => ({ de: e.agente, para: e.para, t: e.t, texto: e.texto }));
}
