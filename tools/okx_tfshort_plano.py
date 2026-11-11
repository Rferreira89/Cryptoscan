"""(11/11, PREPARACAO; NAO LIGADO) Planos de ordem da TF-SHORT U2 para a OKX X-Perps, a partir das decisoes que o
papel ja toma (tools/okx_tfshort.py: s <= 1 entra, s >= 3 sai, stop entrada + 3 ATR20, peso por volatilidade,
<= 5 posicoes, exposicao bruta <= 0,5x, minimo do contrato sem subir o risco).

So constroi os corpos dos pedidos e diz se cabem; nao chama a OKX, nao tem chave, nao envia nada. Ligar isto ao
executor (tools/okx_exec.py) e uma decisao do Rui (interruptor proprio "tfshort_real", desligado por omissao).
Repositorio publico: o resultado guarda precos e contratos, nunca valores da conta."""
import math

from tools import okx_tfshort as T

CFG = {"tfshort_real": False, "tfshort_risco_max_pct": 1.5, "tfshort_max_pos": T.MAX_POS,
       "tfshort_bruta_max": T.BRUTA_MAX, "alavancagem": 3}


def _passo(x, p):
    return math.floor(x / p + 1e-9) * p if p else x


def _fmt(x, p):
    casas = max(0, -int(math.floor(math.log10(p)))) if p and p < 1 else 0
    return f"{x:.{casas}f}"


def plano_entrada(moeda, sinal, info, eq, abertas, cfg=None):
    """sinal: {"entrada": preco, "atr": ATR20 em preco, "w": peso}; info do X-Perp: inst, ctVal, minSz, lotSz, tick, lever;
    eq: capital da conta; abertas: {moeda: {"nocional": ...}}. Devolve (corpo, resumo) ou (None, motivo)."""
    c = dict(CFG, **(cfg or {}))
    if not c["tfshort_real"]:
        return None, "tfshort_real desligado (so papel)"
    if moeda in abertas:
        return None, "ja ha posicao nesta moeda"
    if len(abertas) >= c["tfshort_max_pos"]:
        return None, f"maximo de {c['tfshort_max_pos']} posicoes"
    px, atr, w = sinal["entrada"], sinal["atr"], sinal["w"]
    if not (px > 0 and atr > 0 and 0 < w <= 1 and eq > 0):
        return None, "dados invalidos"
    lote = info.get("lotSz") or info["minSz"]
    n = _passo(eq * w / (info["ctVal"] * px), lote)
    if n < info["minSz"] or n <= 0:
        return None, f"abaixo do minimo do contrato (capital minimo ~{info['minSz'] * info['ctVal'] * px / w:.0f})"
    noc = n * info["ctVal"] * px
    bruta = sum(v.get("nocional", 0) for v in abertas.values()) + noc
    if bruta > c["tfshort_bruta_max"] * eq + 1e-9:
        return None, f"exposicao bruta passaria {c['tfshort_bruta_max']}x"
    stop = px + T.STOP_ATR * atr
    perda = noc * ((stop / px - 1) + 2 * T.CUSTO)
    if perda > eq * c["tfshort_risco_max_pct"] / 100 + 1e-12:
        return None, f"risco no stop {100 * perda / eq:.2f}% acima de {c['tfshort_risco_max_pct']}%"
    dist = stop / px - 1
    alav = max(1, min(int(c["alavancagem"]), int(info.get("lever") or 1), int(1 / (1.5 * dist))))
    tick = info.get("tick") or 1e-8
    corpo = {"instId": info["inst"], "tdMode": "isolated", "side": "sell", "ordType": "market", "sz": _fmt(n, lote),
             "clOrdId": f"tf{moeda[:8]}{int(sinal.get('t', 0)) % 100000000}"[:32],
             "attachAlgoOrds": [{"slTriggerPx": _fmt(math.ceil(stop / tick) * tick, tick), "slOrdPx": "-1"}]}
    return corpo, {"contratos": n, "alav": alav, "stop": stop, "risco_pct_no_stop": round(100 * perda / eq, 3),
                   "exposicao_bruta_x": round(bruta / eq, 3)}


def plano_saida(moeda, info, contratos):
    """Fecho pela regra (s >= 3): compra a mercado so para reduzir (nunca abre long)."""
    lote = info.get("lotSz") or info["minSz"]
    return {"instId": info["inst"], "tdMode": "isolated", "side": "buy", "ordType": "market",
            "sz": _fmt(contratos, lote), "reduceOnly": True, "clOrdId": f"tx{moeda[:8]}"[:32]}
