"""Caminho para a liberdade (23/10, pedido do Rui: "encurtar o caminho").

So informa. Separa o resultado do mercado do dinheiro depositado, calcula o capital que paga
cada etapa de rendimento mensal e quantos anos faltam com o deposito mensal configurado.
Uma vez por semana (domingo a noite) manda o resumo para o Telegram.
Os cenarios sao contas com retorno constante, nao previsoes."""
import time

ETAPAS = (500, 1000, 2000)
RETORNOS = (0.15, 0.30)


def capital_para(rend, cfg):
    return rend / (1 - cfg.get("imposto_pct", 28) / 100) * 12 / (cfg.get("levantamento_pct", 5) / 100)


def anos(cap, dep, r, alvo, maxm=1200):
    c, m, rm = float(cap), 0, (1 + r) ** (1 / 12) - 1
    while c < alvo and m < maxm:
        c = c * (1 + rm) + dep
        m += 1
    return round(m / 12, 1) if c >= alvo else None


def resumo(equity, evol, cfg):
    cfg = cfg or {}
    dep = float(cfg.get("deposito_mensal") or 0)
    ev = evol or {}
    out = {"capital": round(float(equity or 0), 2), "depositado": ev.get("investido"), "mercado": ev.get("g_usdc"),
           "deposito_mensal": dep, "etapas": []}
    for rend in ETAPAS:
        alvo = round(capital_para(rend, cfg))
        out["etapas"].append({"rendimento": rend, "capital": alvo,
                              "anos": {f"{int(r * 100)}%": anos(equity or 0, dep, r, alvo) for r in RETORNOS}})
    return out


def semanal(state, res, now):
    """Mensagem de domingo (a partir das 19h UTC), uma vez por semana. Devolve o texto ou None."""
    g = time.gmtime(now)
    semana = int(now // (7 * 86400))
    if g.tm_wday != 6 or g.tm_hour < 19 or state.get("liberdade_semana") == semana:
        return None
    L = res.get("liberdade") or {}
    if not L.get("capital"):
        return None
    state["liberdade_semana"] = semana
    per = ((res.get("evolucao") or {}).get("periodos") or {})
    sem = per.get("semana")
    linhas = [f"🕊️ <b>Caminho para a liberdade</b> — semana",
              f"Capital {L['capital']:.2f} USDC · depositado {L.get('depositado') or 0:.0f} · mercado {L.get('mercado') or 0:+.2f} USDC"
              + (f" ({sem:+.2f}% na semana)" if sem is not None else "")]
    for e in L.get("etapas") or []:
        a15, a30 = e["anos"].get("15%"), e["anos"].get("30%")
        t = lambda a: "não chega" if a is None else f"{a:.1f} anos".replace(".", ",")
        linhas.append(f"• {e['rendimento']} €/mês ({e['capital']:,.0f}): {t(a15)} a 15% · {t(a30)} a 30%".replace(",", " ", 1))
    linhas.append(f"Com {L['deposito_mensal']:.0f} €/mês de depósito. Cada 100 € a mais por mês encurta o caminho; o painel deixa mudar os números.")
    return "\n".join(linhas)
