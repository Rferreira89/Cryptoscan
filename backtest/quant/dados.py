"""Operacoes do CryptoScan por AMBIENTE, para o modulo quant. Ambientes nunca se misturam:
  OKX_REAL   — okx.json real.hist (fechadas com entrada, stop e saida; R = (saida - entrada) / (entrada - stop))
  BYBIT_REAL — journal do scanner: modo REAL, executado, fechado, com result_r
  PAPEL      — H40 papel (okx.json fechadas), H45 papel (papel_panico), fases lateral, H46 recuo papel, TF-SHORT papel,
               arena (estado completo: so o que NAO foi executado em real)
  SOMBRA     — TF-SHORT sombra
  BACKTEST   — so entra o que tiver operacoes com hora (hoje a arena publica so agregados: fica assinalado)
Cada operacao: {ambiente, estrategia, ativo, t_entrada, t_saida, R, nota}. So R: nunca dinheiro."""
import json
import os


def _ler(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def okx_real(O):
    out = []
    for h in ((O or {}).get("real") or {}).get("hist") or []:
        if h.get("estado") != "fechada" or not (h.get("entrada") and h.get("stop") and h.get("saida")) or h["entrada"] == h["stop"]:
            continue
        out.append({"ambiente": "OKX_REAL", "estrategia": "H46" if h.get("estrategia") == "recuo" else "H40", "ativo": h.get("asset"),
                    "t_entrada": h.get("t_fill") or h.get("criado"), "t_saida": h.get("fechado"),
                    "R": (h["saida"] - h["entrada"]) / (h["entrada"] - h["stop"]), "nota": h.get("motivo")})
    return out


def bybit_real(S):
    return [{"ambiente": "BYBIT_REAL", "estrategia": r.get("strategy"), "ativo": r.get("asset"), "t_entrada": r.get("opened_at") or r.get("issued_at"),
             "t_saida": r.get("closed_at"), "R": r["result_r"], "nota": r.get("exit_reason")}
            for r in (((S or {}).get("journal") or {}).get("rows") or [])
            if r.get("mode") == "REAL" and r.get("status") == "CLOSED" and r.get("executed") is True and r.get("result_r") is not None]


def papel(O, St, T):
    out = []
    for c in (O or {}).get("fechadas") or []:                       # H40 papel: hora do sinal (o fill limite e posterior)
        out.append({"ambiente": "PAPEL", "estrategia": "H40", "ativo": c.get("asset"), "t_entrada": c.get("t_sig"), "t_saida": c.get("t_fim"), "R": c.get("r"), "nota": "entrada = hora do sinal"})
    for c in ((O or {}).get("recuo") or {}).get("fechadas") or []:
        out.append({"ambiente": "PAPEL", "estrategia": "H46", "ativo": c.get("asset"), "t_entrada": c.get("t_fill") or c.get("t_sig"), "t_saida": c.get("t_fim"), "R": c.get("r")})
    for c in ((St or {}).get("papel_panico") or {}).get("fechadas") or []:
        out.append({"ambiente": "PAPEL", "estrategia": "H45", "ativo": c.get("asset"), "t_entrada": c.get("t_fill") or c.get("t_sig"), "t_saida": c.get("t_fim"), "R": c.get("r")})
    for c in (((St or {}).get("papel_fases") or {}).get("lateral") or {}).get("fechadas") or []:
        out.append({"ambiente": "PAPEL", "estrategia": "FASES_LATERAL", "ativo": c.get("asset"), "t_entrada": c.get("t"), "t_saida": c.get("t_fim"), "R": c.get("r")})
    for c in (((T or {}).get("sinais") or {}).get("fechadas")) or []:
        out.append({"ambiente": "PAPEL", "estrategia": "TF-SHORT", "ativo": c.get("asset"), "t_entrada": c.get("t"), "t_saida": c.get("t_fim"), "R": c.get("r")})
    return [o for o in out if o["R"] is not None]


def sombra(Sb):
    return [{"ambiente": "SOMBRA", "estrategia": "TF-SHORT", "ativo": c.get("asset"), "t_entrada": c.get("t_fill") or c.get("t"), "t_saida": c.get("t_fim"), "R": c.get("r")}
            for c in (((Sb or {}).get("estado") or {}).get("fechadas")) or [] if c.get("r") is not None]


def arena_papel(estado_completo):
    """Operacoes da arena a partir do estado COMPLETO (cofre). Linhas do registo executadas em real ficam de fora
    (sao BYBIT_REAL) para nao misturar dinheiro real com papel. Devolve (operacoes, excluidas_reais)."""
    if not estado_completo:
        return [], 0
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    from engine import arena as AR
    reais = {r["id"] for r in estado_completo.get("ledger", []) if r.get("executed") is True}
    out, excl = [], 0
    for k, uid, op in AR.trades(estado_completo):
        if uid in reais:
            excl += 1; continue
        if op.get("r") is None:
            continue
        out.append({"ambiente": "PAPEL", "estrategia": "ARENA:" + k, "ativo": op.get("asset"),
                    "t_entrada": op.get("opened_at") or op.get("entry_t"), "t_saida": op.get("closed_at") or op.get("exit_t"), "R": op["r"]})
    return out, excl


def btc_de_derivados(Dv):
    """Precos horarios do BTC publicados em data/derivados.json: [(t, preco)]."""
    if not Dv or "BTC" not in (Dv.get("moedas") or {}):
        return []
    c = Dv["campos"]; it, ip = c.index("t"), c.index("preco")
    return [(x[it], x[ip]) for x in Dv["moedas"]["BTC"] if x[ip]]


def carregar(pasta, estado_completo=None):
    """Le as copias publicas da pasta (okx.json, state.json, scan.json, okx_tfshort.json, okx_tfshort_sombra.json,
    derivados.json) e, se houver, o estado completo. Devolve {operacoes, btc, notas}."""
    j = lambda n: _ler(os.path.join(pasta, n))
    O, St, S, T, Sb, Dv = j("okx.json"), j("state.json"), j("scan.json"), j("okx_tfshort.json"), j("okx_tfshort_sombra.json"), j("derivados.json")
    ops = okx_real(O) + bybit_real(S) + papel(O, St, T) + sombra(Sb)
    notas = []
    ar, excl = arena_papel(estado_completo)
    ops += ar
    if estado_completo is None:
        notas.append("arena: estado completo nao fornecido (operacoes da arena so no cofre)")
    elif excl:
        notas.append(f"arena: {excl} operacoes executadas em real ficaram fora da arena (contam como BYBIT_REAL)")
    notas.append("BACKTEST: a arena de re-simulacao (forma.json) publica so agregados sem hora; DSR/PBO nao se calculam sobre agregados")
    return {"operacoes": ops, "btc": btc_de_derivados(Dv), "notas": notas, "forma": j("forma.json")}
