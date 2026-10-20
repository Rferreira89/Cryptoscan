"""Evolucao real da carteira (pedido do Rui, 20/10: "um grafico real e as
percentagens de quanto vamos ganhando").

Uma amostra por hora do valor total da conta Bybit. O ganho acumulado G so
muda com o mercado, nunca com depositos: entre duas amostras, a parte da
variacao do valor que o mercado nao explica (o nucleo vale qty x variacao do
preco; as operacoes ativas sao pequenas) e maior do que LIMIAR e tratada como
deposito ou transferencia e nao conta como ganho.

O ponto de partida de G e o resultado real das operacoes ja fechadas
(executadas, com dinheiro real), para o grafico nao comecar do zero. A
percentagem e G sobre o dinheiro posto na conta (valor - G)."""

PASSO = 3600                    # uma amostra por hora
MAX_PTS = 24 * 120              # 120 dias de amostras horarias
LIMIAR_USDC, LIMIAR_PCT = 3.0, 0.015


def _r(x, d=2):
    return round(float(x), d)


def trades_fechados(led):
    """[(t_fecho, pnl_usdc, id)] das operacoes reais executadas e fechadas.
    pnl = R x risco em USDC, com o R real da Bybit quando existe."""
    out = []
    for x in led or []:
        if x.get("mode") != "REAL" or x.get("executed") is not True or x.get("status") != "CLOSED":
            continue
        r = next((x.get(k) for k in ("real_r", "user_result_r", "result_r") if x.get(k) is not None), None)
        risk = x.get("risk_usdc")
        if r is None or not risk:
            continue
        t = x.get("user_closed_at") or x.get("closed_at") or x.get("issued_at") or 0
        out.append((int(t), float(r) * float(risk), x.get("id")))
    return sorted(out)


def _nucleo(nuc):
    """({ativo: qty}, {ativo: preco}) das posicoes do nucleo."""
    pos, plano = (nuc or {}).get("pos") or {}, (nuc or {}).get("plano") or {}
    q = {a: float(p.get("qty") or 0) for a, p in pos.items() if p.get("qty")}
    px = {a: float((plano.get(a) or {}).get("preco") or 0) for a in plano if (plano.get(a) or {}).get("preco")}
    return q, px


def atualizar(state, equity, now, led=None, nuc=None):
    """Junta uma amostra (no maximo uma por PASSO) e devolve o estado."""
    ev = state.setdefault("evolucao", {})
    if not equity or equity <= 0:
        return ev
    eq, now = float(equity), int(now)
    q, px = _nucleo(nuc)
    nres = sum(float(((nuc or {}).get("plano") or {}).get(a, {}).get("resultado_usdc") or 0) for a in q)
    if "g" not in ev:
        tr = trades_fechados(led)
        g, hist = 0.0, []
        for t, p, i in tr:
            g += p
            hist.append([t, _r(g)])
        g += nres
        ev.update(g=_r(g, 4), desde=now, hist=hist, pts=[[now, _r(eq), _r(g)]], fluxos=[],
                  ult={"t": now, "eq": eq, "q": q, "px": px})
        return ev
    u = ev.get("ult") or {}
    if now - (u.get("t") or 0) < PASSO:
        return ev
    mercado = sum(qq * (px.get(a, 0) - (u.get("px") or {}).get(a, px.get(a, 0)))
                  for a, qq in (u.get("q") or {}).items() if a in px)
    dv = eq - float(u.get("eq") or eq)
    resto = dv - mercado
    fluxo = resto if abs(resto) > max(LIMIAR_USDC, LIMIAR_PCT * float(u.get("eq") or eq)) else 0.0
    if fluxo:
        ev.setdefault("fluxos", []).append([now, _r(fluxo)])
        ev["fluxos"] = ev["fluxos"][-50:]
    ev["g"] = _r(float(ev["g"]) + dv - fluxo, 4)
    ev.setdefault("pts", []).append([now, _r(eq), _r(ev["g"])])
    ev["pts"] = ev["pts"][-MAX_PTS:]
    ev["ult"] = {"t": now, "eq": eq, "q": q, "px": px}
    return ev


def _pct(g, eq):
    base = eq - g
    return round(g / base * 100, 2) if base > 0 else None


def resumo(ev, equity=None, now=None, n=180):
    """Para o painel: serie (no maximo n pontos), ganho e percentagens."""
    pts = list((ev or {}).get("pts") or [])
    if not pts:
        return None
    eq = float(equity or pts[-1][1])
    g = float(ev.get("g") or 0)
    now = int(now or pts[-1][0])

    def ha(seg):                       # ganho ha seg segundos (ou o mais antigo)
        alvo = now - seg
        cand = [p for p in pts if p[0] <= alvo]
        if cand:
            return cand[-1]
        h = [p for p in (ev.get("hist") or []) if p[0] <= alvo]
        return [alvo, None, h[-1][1]] if h else None

    per = {}
    for k, s in (("dia", 86400), ("semana", 7 * 86400), ("mes", 30 * 86400)):
        p = ha(s)
        if p is not None:
            base = (p[1] - p[2]) if p[1] else (eq - g)     # dinheiro posto na conta nessa altura
            per[k] = round((g - p[2]) / base * 100, 2) if base > 0 else None
    serie = [[t, gg] for t, gg in (ev.get("hist") or [])] + [[p[0], p[2]] for p in pts]
    if len(serie) > n:
        passo = len(serie) / n
        serie = [serie[int(i * passo)] for i in range(n - 1)] + [serie[-1]]
    return {"g_usdc": _r(g), "pct": _pct(g, eq), "investido": _r(eq - g), "periodos": per,
            "serie": serie, "capital": [[p[0], p[1]] for p in pts[-n:]], "desde": ev.get("desde"),
            "fluxos": (ev.get("fluxos") or [])[-10:], "inicio": (ev.get("hist") or [[ev.get("desde")]])[0][0]}
