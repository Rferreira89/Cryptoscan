"""Historico de derivados (pedido do Rui, 20/10), para testar no futuro
estrategias de liquidacoes, funding e dinheiro aberto (H4) com dados reais:
as bolsas nao dao este historico para tras, por isso grava-se a partir de agora.

Uma amostra por hora das MAX_MOEDAS moedas com mais dinheiro aberto em futuros,
a partir do que o scan ja le (sem pedidos extra). Guarda DIAS dias.
Linha: [t, preco, oi_musd, funding_ppm, ls_x100, liq_long_kusd, liq_short_kusd,
oi_chg_24h_x100, basis_x1000]. Ficheiro derivados.json no ramo data.
So le e grava dados; nao mexe em dinheiro nem em risco."""

PASSO = 3600
MAX_MOEDAS = 20
DIAS = 180
CAMPOS = ["t", "preco", "oi_musd", "funding_ppm", "ls_x100", "liq_long_kusd", "liq_short_kusd",
          "oi_chg_24h_x100", "basis_x1000"]


def _i(x, k):
    try:
        return None if x is None else int(round(float(x) * k))
    except (TypeError, ValueError):
        return None


def linha(row, t):
    d = row.get("derivatives") or {}
    lq = d.get("liquidations") or {}
    completa = lq.get("complete") is not False
    px = row.get("price")
    return [int(t), float(f"{px:.6g}") if px else None, _i(d.get("oi_usd"), 1e-6),
            _i(d.get("funding_rate"), 1e6), _i(d.get("ls_ratio"), 100),
            _i(lq.get("long_usd"), 1e-3) if completa else None,
            _i(lq.get("short_usd"), 1e-3) if completa else None,
            _i(d.get("oi_chg_24h_pct"), 100), _i(d.get("basis_pct"), 1000)]


def atualizar(hist, rows, now):
    """Junta uma amostra horaria. Devolve o historico (novo ou o mesmo)."""
    hist = hist if isinstance(hist, dict) and hist.get("moedas") is not None else {"campos": CAMPOS, "moedas": {}, "t": 0}
    now = int(now)
    if hist.get("t") and now - int(hist["t"]) < PASSO:
        return hist
    com = [r for r in rows or [] if (r.get("derivatives") or {}).get("oi_usd")]
    com.sort(key=lambda r: -(r["derivatives"]["oi_usd"] or 0))
    if not com:
        return hist
    corte = now - DIAS * 86400
    for r in com[:MAX_MOEDAS]:
        s = hist["moedas"].setdefault(r["asset"], [])
        s.append(linha(r, now))
    for a in list(hist["moedas"]):
        hist["moedas"][a] = [x for x in hist["moedas"][a] if x[0] >= corte]
        if not hist["moedas"][a]:
            del hist["moedas"][a]
    hist["t"] = now
    hist["campos"] = CAMPOS
    return hist


def resumo(hist):
    m = (hist or {}).get("moedas") or {}
    ts = [x[0] for s in m.values() for x in s]
    return {"moedas": len(m), "amostras": len(ts), "desde": min(ts) if ts else None}
