"""Market Scanner - Fase 1.

Passo barato: todos os pares (1 pedido por fonte) -> filtro de liquidez.
Passo profundo: so os N mais liquidos -> velas 1D/4H + validacao.
Nesta fase NAO ha sinais: so universo, liquidez e qualidade dos dados.
"""
import math
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from . import (analysis, config, consultas, debate, derivatives, diretor, europa, liga, events as calendar, ledger, short,
               arena, paper_bounce, paper_ring, paper_shadow, promo, rewards,
               liquidity, paper_trend, regime, review,
               signals,
               sources, validate, venue, volume)

MIN_VOLUME_USD = 1_000_000       # 2026-10-13: alinhado com o combate da arena (todas as moedas da Bybit UE)
MAX_SPREAD_BPS = 20
DEEP_N = 100                # cobre todos os ativos elegiveis da Bybit UE
TIMEFRAMES = ["1d", "4h"]

STABLE_OR_PEGGED = {
    "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "USDD", "USDP", "BUSD",
    "USD1", "USDS", "RLUSD", "EUR", "EURI", "EURC", "AEUR", "GBP", "BRL",
    "TRY", "WBTC", "WETH", "STETH", "WBETH", "BETH", "PAXG", "XAUT", "XUSD",
    "USDR", "USTC", "BFUSD", "USDQ", "USD0", "SUSDE", "USDTB", "MNT_USD"}
LEVERAGED = re.compile(r"(\d+[LS]|UP|DOWN|BULL|BEAR)$")
# Acoes tokenizadas vistas sem par noutra exchange (as restantes sao
# detetadas automaticamente em tokenized_stocks()).
STOCK_TOKENS = {"NVDAB", "SPCXB", "GOOGLB", "TSLAB", "AVGOB", "SNXXB",
                "KORUB", "SKHYB", "AAPLB", "AMZNB", "METAB", "MSFTB", "COINB",
                "HOODB", "PLTRB", "AMDB", "QQQB", "SPYB"}


def tokenized_stocks(data):
    """Acoes tokenizadas: Binance usa sufixo B (MSTRB), OKX prefixo X
    (XMSTR). Se os dois existem com o mesmo preco, e a mesma acao."""
    out = set(STOCK_TOKENS)
    bn, ok = data.get("binance", {}), data.get("okx", {})
    for b, t in bn.items():
        if len(b) > 2 and b.endswith("B"):
            o = ok.get("X" + b[:-1])
            if o and t["last"] and o["last"] and \
                    abs(t["last"] / o["last"] - 1) < 0.02:
                out.update((b, "X" + b[:-1]))
    return out


def liquidity_score(vol, spread_bps, n_sources):
    v = max(0.0, min(1.0, (math.log10(max(vol, 1)) - 6) / 3))    # $1M -> $1B
    s = max(0.0, min(1.0, 1 - (spread_bps - 2) / 28))            # 2 -> 30 bps
    return round(60 * v + 25 * s + 5 * min(n_sources, 3))


def collect_tickers():
    status, data = {}, {}
    for src in sources.ALL:
        try:
            data[src.name] = src.tickers()
            status[src.name] = {"ok": True, "pairs": len(data[src.name])}
        except sources.SourceError as e:
            status[src.name] = {"ok": False, "error": str(e)[:200]}
    return status, data


def build_universe(data):
    bases = set().union(*[set(d) for d in data.values()]) if data else set()
    uni, stocks = [], tokenized_stocks(data)
    for b in bases:
        if b in STABLE_OR_PEGGED or LEVERAGED.search(b) or b in stocks:
            continue
        per = {s: d[b] for s, d in data.items() if b in d}
        ok = {s: t for s, t in per.items()
              if t["last"] and t["bid"] and t["ask"] and t["ask"] >= t["bid"] > 0
              and t["vol_quote"] is not None}
        if not ok:
            continue
        vol = sum(t["vol_quote"] for t in ok.values())
        spread = min((t["ask"] - t["bid"]) / ((t["ask"] + t["bid"]) / 2) * 1e4
                     for t in ok.values())
        prices = {s: t["last"] for s, t in ok.items()}
        div, div_status = validate.price_divergence(prices)
        chgs = [t["chg_pct"] for t in ok.values() if t["chg_pct"] is not None]
        px = statistics.median(prices.values())
        if abs(px - 1) < 0.004 and chgs and max(abs(x) for x in chgs) < 0.3:
            continue                      # indexado ao dolar: nao e negociavel
        reasons = []
        if vol < MIN_VOLUME_USD:
            reasons.append("volume baixo")
        if spread > MAX_SPREAD_BPS:
            reasons.append("spread excessivo")
        if div_status == validate.INVALID:
            reasons.append("divergencia entre fontes")
        uni.append({
            "asset": b, "price": statistics.median(prices.values()),
            "chg_24h": round(statistics.median(chgs), 2) if chgs else None,
            "volume_24h": round(vol), "spread_bps": round(spread, 2),
            "sources": sorted(ok), "divergence_pct":
                None if div is None else round(div, 3),
            "liquidity_score": liquidity_score(vol, spread, len(ok)),
            "eligible": not reasons, "excluded_for": reasons})
    uni.sort(key=lambda r: -r["volume_24h"])
    return uni


def deep_check(row, src_order, now):
    """Velas + validacao para um ativo. Usa a 1a fonte que responder."""
    out = {"timeframes": {}, "flags": []}
    clean = {}
    for tf in TIMEFRAMES:
        rep, used = None, None
        best = None          # (n, velas, relatorio, fonte, indice)
        for i, src in enumerate(src_order):
            if src.name not in row["sources"]:
                continue
            try:
                raw = src.candles(row["asset"], tf)
            except sources.SourceError as e:
                if best is None:
                    rep = {"status": "DATA SOURCE ERROR",
                           "issues": [str(e)[:120]], "n": 0}
                continue
            cs, r = validate.validate_candles(
                raw, sources.TF_SECONDS[tf], now, validate.MIN_HISTORY[tf])
            if best is None or r["n"] > best[0]:
                best = (r["n"], cs, r, src.name, i)
            # historico curto nesta fonte (ativo listado ha pouco tempo):
            # tenta a seguinte e fica com a que tiver mais velas
            if r["n"] >= validate.MIN_HISTORY[tf]:
                break
        if best is not None:
            _, cs, rep, used, i = best
            if rep["status"] != validate.INVALID:
                clean[tf] = cs
            if i > 0 and "DATA SOURCE FALLBACK" not in out["flags"]:
                out["flags"].append("DATA SOURCE FALLBACK")
        rep = rep or {"status": "DATA SOURCE ERROR", "issues": ["sem fonte"],
                      "n": 0}
        rep["source"] = used
        out["timeframes"][tf] = rep
    sts = [r["status"] for r in out["timeframes"].values()]
    if any(s in (validate.INVALID, "DATA SOURCE ERROR") for s in sts):
        out["data_status"] = validate.INVALID
    elif any(s == validate.DEGRADED for s in sts) or row["divergence_pct"] and \
            row["divergence_pct"] > 0.5:
        out["data_status"] = validate.DEGRADED
    else:
        out["data_status"] = validate.VALID
    n_issues = sum(len(r["issues"]) for r in out["timeframes"].values())
    out["data_quality"] = (0 if out["data_status"] == validate.INVALID
                           else max(50, 100 - 10 * n_issues
                                    - (0 if len(row["sources"]) > 1 else 10)))
    # Sem dados validos nao ha analise (hierarquia: 1. dados validos?)
    out["_c4"] = clean.get("4h")
    out["_c1"] = clean.get("1d")
    usable = (out["data_status"] != validate.INVALID
              and len(clean) == len(TIMEFRAMES))
    out["analysis"] = analysis.multi(clean) if usable else None
    if usable:
        for tf in TIMEFRAMES:
            a = out["analysis"][tf]
            if a["ok"]:
                a["volume"] = volume.analyse(clean[tf])
                a["liquidity"] = liquidity.analyse(clean[tf])
    # Livro de ordens: so para medir slippage real de uma ordem pequena.
    out["book"] = None
    for src in src_order:
        if src.name in row["sources"] and hasattr(src, "book"):
            try:
                m = liquidity.book_metrics(*src.book(row["asset"]))
                out["book"] = dict(m, source=src.name) if m else None
            except (sources.SourceError, KeyError, IndexError, ValueError):
                continue
            break
    return out


def add_derivatives(rows, now, eu=None):
    """Derivados para os ativos analisados. Devolve o estado da fonte.
    Com dados recentes do servidor europeu, funding, OI e long/short vem
    da Binance (engine/europa.py); as liquidacoes continuam na OKX."""
    okx_err = None
    try:
        snap = derivatives.market_snapshot()
        with ThreadPoolExecutor(max_workers=4) as ex:
            res = list(ex.map(lambda r: derivatives.analyse(
                r["asset"], r["price"], snap, now), rows))
    except (sources.SourceError, KeyError, TypeError) as e:
        okx_err, res = str(e)[:200], [None] * len(rows)
    nb = 0
    for i, r in enumerate(rows):
        c = europa.coin(eu, r["asset"])
        if c:
            res[i] = europa.overlay(res[i], c, now)
            nb += res[i] is not None and res[i].get("venue") == "binance"
    for r, d in zip(rows, res):
        r["derivatives"] = d
    if okx_err and not nb:
        return {"ok": False, "error": okx_err}
    out = {"ok": True, "with_perp": sum(d is not None for d in res),
           "incomplete": sum(bool(d and d["missing"]) for d in res),
           "binance": nb}
    if okx_err:
        out["okx_error"] = okx_err
    return out


def compounding(cfg, led, since):
    """Capital composto: o capital de trabalho e o capital de partida mais
    o resultado realizado desde entao, e a margem e o limite de perda por
    operacao sao percentagens fixas dele. Cresce com os ganhos e encolhe
    com as perdas, na mesma proporcao. Devolve as chaves a atualizar."""
    base = cfg.get("capital_usdc")
    if not cfg.get("compound") or not base:
        return {}
    eq = max(base + ledger.realized_usdc(led, since), 0.0)
    return {"capital_usdc": round(eq, 2), "capital_base": base,
            "fixed_position_usdc": round(eq * cfg["stake_pct"] / 100, 2),
            "max_risk_usdc": round(eq * cfg["risk_pct_of_capital"] / 100, 2)}


def losing_streak(led):
    """Perdas seguidas nas operacoes executadas fechadas (a mais recente
    primeiro); para no primeiro ganho."""
    rows = [r for r in led if r.get("executed") is True and
            (r.get("status") == "CLOSED" or ledger.user_closed(r))]
    rows.sort(key=lambda r: r.get("user_closed_at") or r.get("closed_at") or 0)
    n = 0
    for r in reversed(rows):
        R = ledger.user_r(r)
        if R is None:
            continue
        if R > 0:
            break
        n += 1
    return n


def apply_account(state, eu, now):
    """Capital automatico (decisao do Rui, 2026-10-13: "o saldo fica sempre
    certo sem eu o enviar"): o valor total da conta Bybit lido pelo servidor
    europeu passa a ser o capital. Devolve o resumo publicado ou None."""
    acc = europa.account(eu)
    if not acc or now - (acc.get("t") or 0) > europa.MAX_AGE_LIVE:
        return None
    cap = europa.capital_from(acc)
    if cap is not None:
        state["capital"] = cap
        state["capital_t"] = int(acc["t"])   # o composto conta a partir daqui
        state["capital_auto"] = True
    state["conta_livre"] = {"t": acc["t"], "usdc": acc.get("usdc_free")}
    return {"t": acc["t"], "usdc_free": acc.get("usdc_free"),
            "equity": acc.get("equity"), "trades": acc.get("trades") or {}}


def run(now=None, state=None, cfg=None, forma=None, eu=None):
    """Devolve (resultado, estado, eventos de auditoria)."""
    now = int(now or time.time())
    state = state if state is not None else {}
    cfg = dict(cfg or config.load())
    ledger.fix_stop_exits(state)
    conta = apply_account(state, eu, now)
    state.setdefault("meta_base", {"t": int(now), "capital": (conta or {}).get("equity")
                                   or state.get("capital") or cfg.get("capital_usdc")})
    promo.EU = eu
    since = cfg.get("capital_since") or 0
    if state.get("capital"):                 # definido pelo Telegram
        cfg["capital_usdc"] = state["capital"]
        since = state.get("capital_t") or since
    cfg.update(compounding(cfg, state.get("ledger", []), since))
    # decisao do Rui (2026-10-13): depois de 2 perdas seguidas nas tuas
    # operacoes, o risco por operacao passa a metade ate haver um ganho
    if losing_streak(state.get("ledger", [])) >= 2 and cfg.get("max_risk_usdc"):
        cfg["max_risk_usdc"] = round(cfg["max_risk_usdc"] / 2, 2)
        cfg["risk_reduced"] = True
    status, data = collect_tickers()
    live = [s for s in sources.ALL if status[s.name]["ok"]]
    result = {"generated_at": now, "phase": 4, "sources": status,
              "config": cfg, "conta": conta, "meta_base": state.get("meta_base"),
              "europa": {"ok": eu is not None,
                         "t": (eu or {}).get("t"),
                         "moedas": len((eu or {}).get("moedas") or {})},
              "thresholds": {"min_volume_usd": MIN_VOLUME_USD,
                             "max_spread_bps": MAX_SPREAD_BPS,
                             "deep_n": DEEP_N},
              "signals_note": "Estrategias NAO validadas por backtest. "
                              "O score não é uma probabilidade."}
    if not live:
        result.update(status_global="DATA SOURCE ERROR", universe=[])
        return result, state, []
    try:
        ven = venue.fetch(cfg["quote"])
        result["venue_source"] = {"ok": True, "pairs": len(ven)}
    except (sources.SourceError, KeyError, TypeError) as e:
        ven = None
        result["venue_source"] = {"ok": False, "error": str(e)[:200]}

    uni = build_universe(data)
    for r in uni:
        v = ven.get(r["asset"]) if ven else None
        r["on_venue"] = v is not None
        r["venue"] = v
        if ven is not None and v is None and r["eligible"]:
            r["eligible"] = False
            r["excluded_for"].append("não listado na Bybit UE")
    eligible = [r for r in uni if r["eligible"]][:DEEP_N]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for row, deep in zip(eligible, ex.map(
                lambda r: deep_check(r, live, now), eligible)):
            row.update(deep)
    analysed = [r for r in eligible if r.get("analysis")]
    result["derivatives_source"] = (add_derivatives(analysed, now, eu) if eu
                                    else add_derivatives(analysed, now))

    # Regimes: o do BTC e contexto para todos; mudancas reduzem confianca.
    prev = state.get("regimes", {})
    regs, changed = {}, {}
    for r in analysed:
        reg = regime.classify(r["analysis"]["1d"])["regime"]
        old = prev.get(r["asset"], {})
        since = old.get("since", now) if old.get("regime") == reg else now
        regs[r["asset"]] = {"regime": reg, "since": since,
                            "previous": old.get("regime")
                            if old.get("regime") != reg else old.get("previous")}
        changed[r["asset"]] = bool(old) and now - since < 86400
    state["regimes"] = regs
    btc_reg = regs.get("BTC", {}).get("regime")
    result["market_regime"] = {"btc": btc_reg}

    daily = {r["asset"]: r.pop("_c1", None) for r in eligible}
    result["market_filter"], events = paper_trend.market_filter(
        daily.get("BTC"), state, now)
    market_ok = bool(result["market_filter"]
                     and result["market_filter"]["btc_above_sma200"])
    ev_block = calendar.block(now)
    block = (f"{ev_block['name']} dentro da janela de risco"
             if ev_block else None)
    disabled, ev = review.update(state, now)
    events += ev
    # estrategias desligadas a mao na configuracao (nao mexe no estado,
    # por isso voltam a ligar-se assim que saem da lista)
    disabled = dict(disabled)
    for name in cfg.get("disabled_strategies") or []:
        disabled.setdefault(name, {"reason": "config"})
    # regresso de uma estrategia ao vivo (PULLBACK_R2...): se o lutador que
    # regressou se qualificar no combate (e nao estiver suspenso pela prova
    # real), a estrategia de origem volta a dar sinais pelo circuito normal
    try:
        sus = promo.suspended(state)
        for k, _ in promo.qualified(state):
            b = arena.base_key(k)
            if b != k and k not in sus and (disabled.get(b) or {}).get("reason") == "arena":
                disabled.pop(b, None)
                result.setdefault("regressos_ativos", []).append(k)
    except Exception:
        pass
    result.update(next_event=calendar.next_event(now), event_block=block,
                  calendar_stale=calendar.stale(now),
                  disabled_strategies=disabled)
    # regime do BTC no espelho (para os shorts de altcoins)
    btc_reg_m, c4s = None, {r["asset"]: r.get("_c4") for r in eligible}
    if cfg.get("shorts") and daily.get("BTC") and \
            len(daily["BTC"]) >= analysis.MIN_BARS:
        btc_reg_m = regime.classify(
            analysis.timeframe(short.mirror(daily["BTC"])))["regime"]
    short_ok = bool(result["market_filter"]
                    and not result["market_filter"]["btc_above_sma200"])
    for r in eligible:
        c4 = r.pop("_c4", None)
        if ven is None:
            r["decision"] = {"decision": "NO TRADE", "validated": False,
                             "reason": "DATA SOURCE ERROR: lista da Bybit UE "
                                       "indisponível", "checks": []}
        else:
            ab = block
            if not ab:                      # evento especifico deste ativo
                e = calendar.block(now, r["asset"])
                ab = f"{e['name']} dentro da janela de risco" if e else None
            r["decision"] = signals.decide(r, c4, cfg, ven.get(r["asset"]),
                                           btc_reg, changed.get(r["asset"], False),
                                           market_ok, ab, set(disabled))
            if cfg.get("shorts") and r.get("analysis"):
                r["decision_short"] = signals.decide_short(
                    r, daily.get(r["asset"]), c4, cfg, ven.get(r["asset"]),
                    btc_reg_m, changed.get(r["asset"], False), short_ok, ab,
                    set(disabled))
    # campeao da arena: o lutador qualificado no combate com melhor R medio
    # da sinais reais pelo circuito normal (engine/promo.py)
    champs = promo.champions(state, set(disabled))
    champ = champs[0] if champs else None
    promo_rows = {}
    try:
        def block_for(a):
            if block:
                return block
            e = calendar.block(now, a)
            return e["name"] if e else None
        for a, d in promo.decisions(state, eligible, c4s, cfg, now, champs,
                                    market_ok, block_for).items():
            row = next(r for r in eligible if r["asset"] == a)
            if d["decision"] == "SHORT":           # shorts seguem o ciclo dos shorts
                row["decision_short"] = d
            else:
                row["decision"] = d
            promo_rows[a] = row
    except Exception as e:  # a promocao nunca pode parar o scan
        result["promo_erro"] = str(e)[:120]
    try:                                      # mesa redonda (so mostra)
        result["mesa"] = debate.table(eligible, c4s, state)
    except Exception as e:
        result["mesa"], result["mesa_erro"] = [], str(e)[:120]
    try:                                      # meta do primeiro milhao (so mostra)
        from . import meta
        result["meta"] = meta.progress(state.get("meta_base"), (conta or {}).get("equity")
                                       or cfg.get("capital_usdc"))
    except Exception:
        result["meta"] = None
    try:
        result["macro"] = promo.macro_summary(now)
    except Exception:                       # informativo: nunca para o scan
        result["macro"] = None
    # leitura por departamentos (pagina e /porque no Telegram)
    for r in eligible:
        try:
            r["departamentos"] = consultas.departments(
                r, result["macro"], c4s.get("BTC"), c4s.get(r["asset"]))
        except Exception:
            r["departamentos"] = []
    result["promo"] = {"campeao": champ, "campeoes": champs, "qualificados": [
        {"id": k, "avg_r": r} for k, r in promo.qualified(state)]}
    try:                                      # prova real e diversificacao
        sus = promo.suspended(state)
        prev = state.get("suspensos") or {}
        for k in set(sus) - set(prev):
            events.append({"t": now, "event": "SUSPENSO", "id": f"susp-{k}-{now}", "strategy": k,
                           "nome": arena.persona(k), "motivo": sus[k], "real": False})
        for k in set(prev) - set(sus):
            events.append({"t": now, "event": "RETOMADO", "id": f"ret-{k}-{now}", "strategy": k,
                           "nome": arena.persona(k), "real": False})
        state["suspensos"] = sus
        result["promo"]["suspensos"] = sus
        result["promo"]["familias"] = promo.family_open(state)
        result["promo"]["prova_real"] = {k: dict(zip(("n", "avg_r"), promo.live_record(state, k)))
                                         for k, _ in promo.qualified(state)}
    except Exception as e:
        result["promo"]["prova_erro"] = str(e)[:120]
    # Diretor de Trading: nenhuma entrada real passa sem a sua autorizacao
    try:
        diretor.gate(state, eligible, c4s, result["macro"], now)
        result["diretor"] = dict(diretor.summary(state, now), avaliacao=diretor.follow(state, c4s, now))
    except Exception as e:                  # falha fechada: sem diretor nao ha entradas
        result["diretor_erro"] = str(e)[:120]
        for r in eligible:
            for key in ("decision", "decision_short"):
                d = r.get(key) or {}
                if d.get("decision") in ("LONG", "SHORT"):
                    d.update(decision="NO TRADE", reason="Diretor de Trading indisponível")
    # os shorts entram como linhas proprias no ciclo de vida dos sinais
    both = eligible + [dict(r, decision=r["decision_short"])
                       for r in eligible if r.get("decision_short")]
    events += signals.update_state(state, both, cfg, now, daily)
    for a, row in promo_rows.items():     # campeao que nao virou sinal: porque?
        ds = row.get("decision_short") or {}
        d, want = (ds, "SHORT") if ds.get("score_label") == "campeão da arena" else (row["decision"], "LONG")
        if d.get("decision") != want:
            promo.lost(state, now, a, d.get("strategy"), d.get("reason") or "")
    lost = state.get("promo_lost", [])
    result["promo"]["perdidas_7d"] = [x for x in lost if now - x["t"] < 7 * 86400][-20:]
    events += calendar.open_warnings(state, now)
    # papel do Oversold Bounce (nao validada): nunca gera ordens reais
    try:
        result["paper_bounce"], ev = paper_bounce.update(
            state, eligible, c4s, market_ok, now, cfg,
            dead=arena.dead_paper(state))
        # o campeao ja da o sinal real: o aviso de papel da mesma saida seria
        # repetido (o papel continua a ser registado)
        if "BOUNCE_G0" in champs or "BOUNCE_X30" in champs:
            ev = [e for e in ev if not e["event"].startswith("BOUNCE_PAPER")]
        events += ev
    except Exception as e:  # o papel nunca pode parar o scan
        result["paper_bounce"] = {"erro": str(e)[:120]}
    # papel dos setups prontos que nao viraram sinal ("estamos a perder trades?")
    try:
        if "REJEITADOS" in (state.get("arena", {}).get("mortos") or {}):
            # morto na arena: deixa de abrir; as abertas acabam
            result["paper_shadow"] = paper_shadow.update(state, [], c4s, now)
        else:
            result["paper_shadow"] = paper_shadow.update(state, eligible, c4s, now)
    except Exception as e:  # nunca pode parar o scan
        result["paper_shadow"] = {"erro": str(e)[:120]}
    # papel automatico dos qualificados no combate (sem papel proprio)
    try:
        result["paper_ring"] = paper_ring.update(state, eligible, c4s, now, market_ok)
    except Exception as e:  # nunca pode parar o scan
        result["paper_ring"] = {"erro": str(e)[:120]}
    # arena: classificacao de todas as estrategias contra o acaso
    try:
        result["arena"] = arena.update(state, c4s, now, forma=forma)
        try:
            result["liga"] = liga.update(state, result["arena"].get("classificacao"),
                                         champs, now)
        except Exception as e:                # informativo: nunca para o scan
            result["liga_erro"] = str(e)[:120]
        try:                                  # regresso dos mortos quando o mercado muda
            reg_mkt = arena.market_regime(c4s.get("BTC"), daily.get("BTC"))
            events.extend(arena.rebirth(state, now, reg_mkt))
            result["arena_longo"] = (state.get("arena") or {}).get("longo")
            result["mercado"] = {"regime": reg_mkt, **(state.get("mercado") or {}),
                                 "renascidos": (state.get("arena") or {}).get("renascidos") or {}}
        except Exception as e:
            result["mercado_erro"] = str(e)[:120]
        off = arena.auto_disable(state, result["arena"], now)   # morte automatica
        for e in arena.events(result["arena"], now):
            e["desligada"] = e.get("strategy") in off or \
                (state.get("disabled", {}).get(e.get("strategy")) or {}).get("reason") == "arena"
            events.append(e)
        late = [k for k in off if not any(e.get("strategy") == k for e in events
                                           if e["event"] == "ARENA")]
        if late:                 # mortas antes da morte automatica existir
            events.append({"t": now, "event": "ARENA_OFF", "id": f"arena-off-{now}",
                           "strategies": late, "real": False})
    except Exception as e:  # a arena nunca pode parar o scan
        result["arena"] = {"erro": str(e)[:120]}
    # recompensas do escritorio: conquistas reais desbloqueiam espacos
    try:
        result["rewards"], ev = rewards.update(state, result, now)
        events += ev
    except Exception as e:  # nunca pode parar o scan
        result["rewards"] = []
    result["halt"] = state.get("halt")
    result["paper_trend"], ev = paper_trend.update(
        state, eligible, daily, cfg, now, market_ok,
        state.get("halt") or block
        or ("desligada" if "TREND_DAILY" in disabled else None))
    events += ev
    # pre-aviso: uma vez por dia por ativo e estrategia em vigilancia
    seen = state.setdefault("watch_alerted", {})
    for k in [k for k, t in seen.items() if now - t > 86400]:
        del seen[k]
    for r in both:
        d = r["decision"]
        if d["decision"] == "WATCHLIST" and d.get("state") == "WAITING" \
                and d.get("plan") and d.get("mode") == "REAL":
            key = f"{r['asset']}-{d['strategy']}"
            if key not in seen:
                seen[key] = now
                events.append({"t": now, "event": "WATCH", "id": f"watch-{key}",
                               "asset": r["asset"], "pair": d["venue"]["pair"],
                               "side": d.get("side", "LONG"),
                               "strategy": d["strategy"], "trigger": d["trigger"],
                               "entry": d["plan"]["entry_zone"],
                               "stop": d["plan"]["stop"],
                               "tp1": d["plan"]["tp"][0]})
    led = ledger.apply(state, events)
    result["journal"] = ledger.view(led)
    result["active_signals"] = [s for s in state["signals"].values()
                                if s["status"] in ("ACTIVE", "TRIGGERED")]
    result["track_record"] = state.get("track", {})
    result["closed_signals"] = sorted(
        (s for s in state["signals"].values()
         if s["status"] in ("EXPIRED", "INVALIDATED", "CLOSED")),
        key=lambda s: -s["closed_at"])[:15]
    ok_all = len(live) == len(sources.ALL) and ven is not None
    dec = [r["decision"]["decision"] for r in eligible]
    result.update(
        status_global="OK" if ok_all else "DEGRADED",
        counts={"pairs_seen": len(uni),
                "eligible": sum(r["eligible"] for r in uni),
                "deep_checked": len(eligible),
                "data_valid": sum(r.get("data_status") == validate.VALID
                                  for r in eligible),
                "data_invalid": sum(r.get("data_status") == validate.INVALID
                                    for r in eligible),
                "long": sum(r["decision"]["decision"] == "LONG"
                            and r["decision"].get("mode") == "REAL"
                            for r in eligible),
                "short": sum((r.get("decision_short") or {}).get("decision")
                             == "SHORT" for r in eligible),
                "watch_short": sum((r.get("decision_short") or {}).get(
                    "decision") == "WATCHLIST" for r in eligible),
                "paper": sum(r["decision"]["decision"] == "LONG"
                             and r["decision"].get("mode") == "PAPER"
                             for r in eligible),
                "watchlist": dec.count("WATCHLIST"),
                "no_trade": dec.count("NO TRADE")},
        universe=eligible)
    return result, state, events
