"""Perguntas ao programa pelo Telegram e leitura por departamentos.

Comandos (so leitura, nada muda no registo nem no risco):
  /porque SOL   o que cada departamento ve nessa moeda e porque ha ou nao sinal
  /ringue       classificacao dos lutadores
  /macro        leitura macroeconomica
  /conta        saldo lido na Bybit pelo servidor europeu
  /hoje         resumo: operacoes abertas, sinais, campeao, macro
  /ajuda        lista de comandos

departments(row, macro, btc_c4, c4) da a leitura de cada departamento
(verde / amarelo / vermelho) e e publicada em scan.json para a pagina.
"""
import re
import time

from . import arena

PAGE = "https://rferreira89.github.io/Cryptoscan/scanner/"
G, Y, R = "verde", "amarelo", "vermelho"
DOT = {G: "🟢", Y: "🟡", R: "🔴"}
CMD = re.compile(r"^/?(porque|porquê|debate|liga|oportunidades|meta|ringue|macro|conta|hoje|ajuda|help|start)"
                 r"(?:@\w+)?(?:\s+([A-Za-z0-9]+))?\s*$", re.I)


def _pct(a, b):
    return None if not a or not b else (a / b - 1) * 100


def _f(x, n=2):
    return "–" if x is None else f"{x:.{n}f}"


# ---------- departamentos ----------

PT = {"UP": "a subir", "DOWN": "a descer", "MIXED": "mistas", "BULLISH": "de alta",
      "BEARISH": "de baixa", "NEUTRAL": "neutra", "UNCLEAR": "indefinida"}


def dep_trend(a1, a4):
    t1, s4, s1 = a1.get("ema_trend"), a4.get("structure"), a1.get("structure")
    ev = (a4.get("event") or {}) if isinstance(a4.get("event"), dict) else {}
    cor = G if t1 == "UP" and s4 == "BULLISH" else \
        R if t1 == "DOWN" and s4 == "BEARISH" else Y
    txt = (f"Diário: médias {PT.get(t1, '–')}, estrutura {PT.get(s1, '–')}; 4H: "
           f"estrutura {PT.get(s4, '–')}, força da tendência (ADX) {_f(a4.get('adx'), 0)}")
    if ev.get("type"):
        txt += (f"; {'mudança de estrutura' if ev['type'] == 'CHOCH' else 'quebra de estrutura'}"
                f" {'em alta' if ev.get('direction') == 'UP' else 'em baixa'}")
    return cor, txt


def dep_liq(a4, px):
    lq = a4.get("liquidity") or {}
    sw, ob = lq.get("sweep") or {}, lq.get("order_block") or {}
    bits, cor = [], Y
    if sw and (sw.get("bars_ago") or 0) <= 6:
        low = sw.get("side") == "LOW"
        bits.append(f"varrimento de {'mínimos' if low else 'máximos'} em "
                    f"{_f(sw.get('level'), 4).rstrip('0').rstrip('.')}"
                    f"{' (confirmado)' if sw.get('confirmed') else ''}")
        cor = G if low else R
    if ob and ob.get("zone"):
        demand = ob.get("side") == "DEMAND"
        bits.append(f"order block de {'compra' if demand else 'venda'} "
                    f"{ob['zone'][0]:g}–{ob['zone'][1]:g}")
        if cor == Y:
            cor = G if demand and ob["zone"][1] < px else R if not demand else Y
    if lq.get("fvg_below"):
        bits.append(f"fair value gap por baixo {lq['fvg_below'][0]:g}–{lq['fvg_below'][1]:g}")
    if lq.get("fvg_above"):
        bits.append(f"fair value gap por cima {lq['fvg_above'][0]:g}–{lq['fvg_above'][1]:g}")
    return cor, "; ".join(bits) or "sem zonas de liquidez relevantes perto"


def dep_vol(a4):
    v = a4.get("volume") or {}
    bs, dv, rv = v.get("buy_share"), v.get("divergence"), v.get("rvol")
    cor = G if (bs is not None and bs >= 0.55) or dv == "BULLISH" else \
        R if (bs is not None and bs <= 0.45) or dv == "BEARISH" else Y
    txt = (f"volume {_f(rv, 1)}× o normal; compradores agressivos "
           f"{'–' if bs is None else f'{bs:.0%}'}")
    if dv:
        txt += f"; divergência {'positiva' if dv == 'BULLISH' else 'negativa'}"
    return cor, txt


POS = {"LONG_BUILDUP": "compradores a abrir posições",
       "SHORT_COVERING": "vendedores a fechar posições",
       "SHORT_BUILDUP": "vendedores a abrir posições",
       "LONG_LIQUIDATION": "compradores a sair (desalavancagem)", "FLAT": "estável"}


def dep_deriv(d):
    if not d:
        return Y, "sem dados de derivados para esta moeda"
    fl, pos = d.get("flags") or [], d.get("positioning")
    if "CROWDED_LONGS" in fl or "FUNDING_EXTREME_POSITIVE" in fl or pos == "SHORT_BUILDUP":
        cor = R
    elif "CROWDED_SHORTS" in fl or "FUNDING_EXTREME_NEGATIVE" in fl or \
            pos in ("LONG_BUILDUP", "SHORT_COVERING") or (d.get("funding_rate") or 0) < 0:
        cor = G
    else:
        cor = Y
    fr, oc = d.get("funding_rate"), d.get("oi_chg_24h_pct")
    frs = "–" if fr is None else f"{fr * 100:.4f}%"
    ocs = "–" if oc is None else f"{oc:+.1f}%"
    txt = (f"funding {frs} (percentil {d.get('funding_pctile', '–')}); posições "
           f"abertas {ocs} em 24h — {POS.get(pos, '–')}; long/short {_f(d.get('ls_ratio'))}")
    if fl:
        txt += f"; alertas: {', '.join(fl)}"
    return cor, txt + f" ({d.get('venue', '–')})"


def dep_sr(a4, px):
    sup = [x for x in [a4.get("swing_low")] + ((a4.get("liquidity") or {}).get("pools_below") or [])
           if x and x < px]
    res = [x for x in [a4.get("swing_high")] + ((a4.get("liquidity") or {}).get("pools_above") or [])
           if x and x > px]
    s, r = (max(sup) if sup else None), (min(res) if res else None)
    ds, dr = (None if s is None else (px / s - 1) * 100), (None if r is None else (r / px - 1) * 100)
    if dr is not None and dr < 2:
        cor = R
    elif ds is not None and ds < 3 and (dr is None or dr > 2 * ds):
        cor = G
    else:
        cor = Y
    ss = "–" if s is None else f"{s:g} ({ds:.1f}% abaixo)"
    rs_ = "–" if r is None else f"{r:g} ({dr:.1f}% acima)"
    return cor, f"suporte {ss}; resistência {rs_}"


def dep_rs(c4, btc_c4):
    if not c4 or not btc_c4 or len(c4) < 181 or len(btc_c4) < 181:
        return Y, "sem histórico suficiente para comparar com o BTC"
    mine = _pct(c4[-1]["c"], c4[-181]["c"])
    btc = _pct(btc_c4[-1]["c"], btc_c4[-181]["c"])
    diff = mine - btc
    cor = G if diff > 5 else R if diff < -5 else Y
    return cor, f"30 dias: moeda {mine:+.1f}%, BTC {btc:+.1f}% ({diff:+.1f} pontos)"


MEST = {"favoravel": (G, "favorável"), "neutro": (Y, "neutra"), "medo": (R, "medo")}


def dep_macro(m):
    if not m or not m.get("estado"):
        return Y, "sem dados macro do servidor europeu"
    cor, nome = MEST[m["estado"]]
    return cor, (f"{nome}: S&P 500 {_f(m.get('sp_24h_pct'), 1)}% em 24h, dólar "
                 f"{_f(m.get('dxy_5d_pct'), 1)}% em 5 dias, VIX {_f(m.get('vix'), 1)}")


def dep_moment(a4):
    rsi = a4.get("rsi")
    cor = G if rsi is not None and rsi < 35 else R if rsi is not None and rsi > 70 else Y
    return cor, (f"RSI 4H {_f(rsi, 0)}"
                 + (" — zona de sobrevenda que os campeões procuram" if cor == G else
                    " — esticada, sem margem" if cor == R else ""))


def departments(row, macro=None, btc_c4=None, c4=None):
    an = row.get("analysis") or {}
    a1, a4, px = an.get("1d") or {}, an.get("4h") or {}, row.get("price")
    if not a4:
        return []
    out = []
    for nome, fn in (("Tendência e estrutura", lambda: dep_trend(a1, a4)),
                     ("Liquidez e smart money", lambda: dep_liq(a4, px)),
                     ("Volume e fluxo", lambda: dep_vol(a4)),
                     ("Derivados", lambda: dep_deriv(row.get("derivatives"))),
                     ("Suportes e resistências", lambda: dep_sr(a4, px)),
                     ("Força relativa", lambda: dep_rs(c4, btc_c4)),
                     ("Sobrevenda", lambda: dep_moment(a4)),
                     ("Macroeconomia", lambda: dep_macro(macro))):
        try:
            cor, txt = fn()
        except Exception:
            cor, txt = Y, "leitura indisponível"
        out.append({"dep": nome, "cor": cor, "texto": txt})
    return out


# ---------- respostas ----------

def _row(res, asset):
    return next((r for r in (res or {}).get("universe") or []
                 if r.get("asset") == asset), None)


def _decision_line(row):
    d = row.get("decision") or {}
    dec = d.get("decision") or "–"
    if dec in ("LONG", "BUY", "VALID") or d.get("plan"):
        return "✅ Há sinal de compra ativo nesta moeda."
    act = d.get("active_signal")
    if act:
        k = act.split("-")[1] if act.count("-") >= 2 else act
        return f"📌 Já há uma operação em curso nesta moeda ({arena.persona(k)})."
    return f"⏸️ Sem sinal agora: {d.get('reason') or 'nenhuma estratégia viva encontrou entrada'}."


def why(res, asset):
    row = _row(res, asset)
    if not row:
        return (f"{asset} não está entre as moedas analisadas neste momento "
                "(as 100 mais líquidas listadas na Bybit UE em USDC).")
    deps = row.get("departamentos") or departments(row, (res or {}).get("macro"))
    L = [f"🔎 <b>{asset}</b> a {row.get('price'):g} USD ({row.get('chg_24h', 0):+.1f}% em 24h)", ""]
    for d in deps:
        L.append(f"{DOT[d['cor']]} <b>{d['dep']}</b>: {_esc(d['texto'])}")
    n = {c: sum(1 for d in deps if d["cor"] == c) for c in (G, Y, R)}
    L += ["", f"Balanço: {n[G]} 🟢 · {n[Y]} 🟡 · {n[R]} 🔴", _esc(_decision_line(row)),
          f'<a href="{PAGE}#moeda={asset}">📊 Ver gráfico e níveis</a>']
    return "\n".join(L)


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ring(res):
    ar = (res or {}).get("arena") or {}
    rows = ar.get("classificacao") or []
    champs = set(((res or {}).get("promo") or {}).get("campeoes") or [])
    vivos, mortos = [], []
    for r in rows:
        f = r.get("forma") or {}
        if r.get("estado") == "MORTA" or r.get("morte"):
            mortos.append(r)
            continue
        vivos.append((f.get("avg_r"), f.get("n") or 0, r))
    vivos.sort(key=lambda x: -(x[0] if x[0] is not None else -9))
    L = ["🥊 <b>Ringue</b> (combate de 90 dias, de hora a hora)", ""]
    for i, (avg, n, r) in enumerate(vivos[:15], 1):
        tag = "🏆" if r["id"] in champs else "⚔️"
        L.append(f"{i}. {tag} {r.get('persona')} — {_esc(r.get('name', r['id']))}: "
                 f"{'–' if avg is None else f'{avg:+.2f}R'} em {n}")
    if mortos:
        L += ["", "🕯️ Memorial: " + ", ".join(m.get("persona", m["id"]) for m in mortos)]
    L += ["", "🏆 campeão a operar · ⚔️ em combate. Precisa de 20 operações, R positivo e "
          "acima do acaso para subir."]
    return "\n".join(L)


def macro_text(res):
    m = (res or {}).get("macro")
    if not m or not m.get("estado"):
        return "Sem dados macro do servidor europeu neste momento."
    cor, nome = MEST[m["estado"]]
    return "\n".join([
        f"🌍 <b>Macroeconomia: {nome}</b> {DOT[cor]}", "",
        f"S&P 500 (futuros): {_f(m.get('sp_24h_pct'), 2)}% em 24h",
        f"Índice do dólar: {_f(m.get('dxy_5d_pct'), 2)}% em 5 dias",
        f"VIX (medo): {_f(m.get('vix'), 1)}",
        f"Juro a 10 anos EUA: {_f(m.get('us10y'), 2)}%", "",
        "Medo = VIX ≥ 25, ou S&P 500 a cair ≥ 2% em 24h, ou dólar a subir ≥ 1,5% em 5 dias.",
        "Mário só compra com macro favorável; Vicente compra depois de medo."])


def account_text(res):
    c = (res or {}).get("conta")
    if not c:
        return ("Sem leitura recente da conta. O servidor europeu lê-a de 15 em 15 "
                "minutos; se isto se repetir, avisa.")
    age = round((time.time() - (c.get("t") or 0)) / 60)
    cap = ((res or {}).get("config") or {}).get("capital_usdc")
    return "\n".join([
        "💼 <b>Conta Bybit</b> (só leitura)", "",
        f"Valor total: {_f(c.get('equity'))} USD",
        f"USDC livre: {_f(c.get('usdc_free'))}",
        f"Capital usado nos sinais: {_f(cap)} USDC",
        f"Lida há {age} min pelo servidor europeu."])


def today(res, state):
    led = (state or {}).get("ledger") or []
    now = time.time()
    px = {r["asset"]: r.get("price") for r in (res or {}).get("universe") or []}
    L = ["📋 <b>Resumo</b>", ""]
    mine = [r for r in led if r.get("status") == "OPEN" and r.get("executed")
            and r.get("user_result_r") is None]
    if mine:
        L.append("<b>As tuas operações abertas</b>")
        for r in mine:
            e, s, p = r.get("exec_price") or r.get("entry"), r.get("stop"), px.get(r["asset"])
            rr = None if not (e and s and p) or e == s else (p - e) / (e - s)
            usd = None if rr is None else rr * (r.get("risk_usdc") or 0)
            ps = "–" if p is None else f"{p:g}"
            L.append(f"• {r['asset']} ({arena.persona(r.get('strategy', ''))}): entrada {e:g}, "
                     f"agora {ps}" + ("" if rr is None else f" → {rr:+.2f}R ({usd:+.2f} USDC)"))
    else:
        L.append("Sem operações tuas abertas.")
    new = [r for r in led if now - (r.get("issued_at") or 0) < 86400 and r.get("mode") == "REAL"]
    L += ["", f"Sinais reais nas últimas 24h: {len(new)}"
          + (f" ({', '.join(r['asset'] for r in new)})" if new else "")]
    lost = [x for x in ((res or {}).get("promo") or {}).get("perdidas_7d") or []
            if now - x["t"] < 86400]
    if lost:
        L.append(f"Oportunidades recusadas nas últimas 24h: {len(lost)} "
                 f"({', '.join(x['asset'] for x in lost)})")
    ch = ((res or {}).get("promo") or {}).get("campeao")
    if ch:
        L.append(f"Campeão principal: {arena.persona(ch)}")
    m = (res or {}).get("macro") or {}
    if m.get("estado"):
        L.append(f"Macro: {MEST[m['estado']][1]} {DOT[MEST[m['estado']][0]]}")
    c = (res or {}).get("conta")
    if c:
        L.append(f"Conta: {_f(c.get('equity'))} USD · {_f(c.get('usdc_free'))} USDC livres")
    return "\n".join(L)


def debate_text(res, asset):
    row = _row(res, asset)
    if not row or not row.get("debate"):
        return f"Sem mesa redonda para {asset} neste momento (só as moedas analisadas, no scan seguinte)."
    v = row["debate"]
    yes = [x for x in v if x["voto"] != "não"]
    L = [f"🗣️ <b>Mesa redonda: {asset}</b> a {row.get('price'):g} USD", "",
         f"{len(yes)} de {len(v)} lutadores operavam agora (✅ compra · 🔻 venda a descoberto).", ""]
    for x in v:
        ic = {"entra": "✅", "vende": "🔻"}.get(x["voto"], "❌")
        L.append(f"{ic} <b>{_esc(x['persona'])}</b>: {_esc(x['razao'])}")
    return "\n".join(L)


def mesa_text(res):
    m = (res or {}).get("mesa") or []
    if not m:
        return "A mesa redonda ainda não tem moedas em discussão."
    L = ["🗣️ <b>Mesa redonda</b>: as moedas mais discutidas agora", ""]
    for x in m:
        L.append(f"• {x['asset']}: {x['a_favor']} de {x['votantes']} entravam (RSI 4H {x['rsi']:g})")
    L += ["", "Pormenor de uma moeda: /debate MOEDA"]
    return "\n".join(L)


def opportunities(res, n=8):
    """Moedas mais perto de dar sinal: sobrevenda (compras) e sobrecompra (vendas)."""
    rows = [r for r in (res or {}).get("universe") or []
            if ((r.get("analysis") or {}).get("4h") or {}).get("rsi") is not None and r.get("eligible")]
    if not rows:
        return "Sem dados do último scan."
    rsi = lambda r: r["analysis"]["4h"]["rsi"]
    yes = lambda r: sum(1 for x in r.get("debate") or [] if x["voto"] != "não")
    lo = sorted(rows, key=rsi)[:n]
    hi = sorted(rows, key=rsi, reverse=True)[:3]
    L = ["🎯 <b>Oportunidades mais perto</b>", "", "<b>Compras</b> (os campeões entram com RSI 4H abaixo de 30 a virar):"]
    for r in lo:
        gap = rsi(r) - 30
        L.append(f"• {r['asset']}: RSI {rsi(r):.0f}" + (" — já em sobrevenda, à espera da viragem" if gap <= 0
                                                      else f" — faltam {gap:.0f} pontos")
                 + (f" · {yes(r)} lutador(es) a operar" if yes(r) else ""))
    L += ["", "<b>Vendas a descoberto</b> (sobrecompra, RSI acima de 70):"]
    for r in hi:
        L.append(f"• {r['asset']}: RSI {rsi(r):.0f}" + ("" if rsi(r) >= 70 else f" — faltam {70 - rsi(r):.0f} pontos"))
    L += ["", "Detalhe: /debate MOEDA · /porque MOEDA"]
    return "\n".join(L)


GOAL = 1_000_000


def goal_text(res):
    from . import meta
    m = meta.progress((res or {}).get("meta_base"), ((res or {}).get("conta") or {}).get("equity")
                      or ((res or {}).get("config") or {}).get("capital_usdc"))
    if not m:
        return "Sem capital lido ainda."
    L = [f"🏁 <b>Meta: o primeiro milhão</b>", "",
         f"Capital agora: {m['capital']:,.2f} USDC".replace(",", " "),
         f"Progresso: {m['pct']:.4f}% · próximo marco: {m['marco']:,} USDC ({m['falta_marco']:,.2f} em falta)".replace(",", " "),
         "", "<b>Quanto tempo, ao ritmo composto de</b>:"]
    for r, meses in m["cenarios"]:
        L.append(f"• {r:.0f}% ao mês → {meses / 12:.1f} anos")
    L += ["", "Com honestidade: 5% ao mês de forma consistente já é excelente. O programa persegue a "
          "meta com disciplina (só estratégias que batem o acaso, risco limitado), nunca aumentando "
          "o risco para encurtar o caminho: uma perda grande atrasa a meta mais do que qualquer ganho a acelera."]
    return "\n".join(L)


HELP = "\n".join([
    "🤖 <b>Perguntas ao Cryptoscan</b>", "",
    "/porque SOL — o que cada departamento vê numa moeda",
    "/ringue — classificação dos lutadores",
    "/debate MOEDA — o que cada lutador faria nessa moeda (/debate sozinho: as mais quentes)",
    "/liga — liga semanal dos lutadores",
    "/oportunidades — moedas mais perto de dar sinal",
    "/meta — caminho até ao primeiro milhão",
    "/macro — macroeconomia agora",
    "/conta — saldo na Bybit",
    "/hoje — resumo do dia", "",
    "Registo: /preco MOEDA preço · /fechei MOEDA preço · /capital valor",
    "Execução: botão ⚡ Executar nos alertas · /parar fecha o que o programa abriu",
    "As respostas chegam em cerca de 1 minuto."])


def answer(text, res, state):
    """Resposta (HTML) a um comando de consulta, ou None se nao for um."""
    m = CMD.match((text or "").strip())
    if not m:
        return None
    c, arg = m.group(1).lower(), (m.group(2) or "").upper()
    if c in ("porque", "porquê"):
        return why(res, arg) if arg else "Diz-me a moeda, por exemplo: /porque SOL"
    if c == "debate":
        return debate_text(res, arg) if arg else mesa_text(res)
    if c == "oportunidades":
        return opportunities(res)
    if c == "meta":
        return goal_text(res)
    if c == "liga":
        from . import liga
        return _esc(liga.text((res or {}).get("liga")) or "A liga ainda não tem dados.")
    if c == "ringue":
        return ring(res)
    if c == "macro":
        return macro_text(res)
    if c == "conta":
        return account_text(res)
    if c == "hoje":
        return today(res, state)
    return HELP


def why_buttons(asset):
    """Linha de botoes para os alertas: porque e grafico."""
    return [{"text": "❓ Porquê", "callback_data": f"q|p|{asset}"},
            {"text": "📊 Gráfico", "url": f"{PAGE}#moeda={asset}"}]
