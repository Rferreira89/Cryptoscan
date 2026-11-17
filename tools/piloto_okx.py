"""(17/11, ordens do Rui) PILOTO REAL OKX - executor isolado, com promocao automatica de estrategias qualificadas.

De onde vem cada decisao:
  - QUE estrategias podem operar: o registo central (ramo autonomo, hunter/estrategias_registo.json, escrito pelo motor
    de qualificacao do Hunter). So APPROVED_REAL / ACTIVE_REAL, e este executor VOLTA a conferir os numeros de cada uma
    contra os criterios da ordem (criterios_reais): uma entrada mal escrita no registo nao chega a uma ordem.
  - QUANDO entrar: o sinal do paper trading prospetivo (hunter/papel_estado.json, as mesmas regras e dados), espelhado
    para real se ainda for fresco e o preco nao tiver fugido (correspondencia papel <-> real; sinais perdidos ficam
    registados com a causa).
  - QUANTO: limites proprios (piloto_okx_config.json), nunca alterados pelo programa: capital ate 20 USDC, nocional ate
    20 USDC, risco planeado <= 0,25 USDC por operacao INCLUINDO custos, alavancagem 5x-10x (5x de referencia, mais so
    se a margem o exigir), 1 posicao, margem isolada; perda do dia 1 USDC (sem entradas ate ao dia seguinte), perda
    acumulada 3 USDC (suspensao para revisao), 5 USDC (piloto encerrado). Bloqueios persistentes.
  - Perdas: o maximo entre o estado guardado e o que a OKX mostra das posicoes do piloto (positions-history), para que
    perder o estado nunca apague perdas.
Isolamento: so mexe em ordens/posicoes com clOrdId/algoClOrdId "pil" (tools/piloto_id.py); nao abre em instrumentos
com posicao ou ordens de outro executor; so arranca com okx_exec.PILOTO_ISOLADO. Nunca: configuracoes globais da conta,
transferencias, levantamentos, martingale, grid, reforcos, piramidagem, aumento de tamanho apos perdas.
Uma ordem enviada nao e uma ordem executada; uma posicao so esta protegida com o stop confirmado na OKX. Um stop nao
garante a perda maxima (gaps, deslizamento, falhas): por isso a reserva de custos no dimensionamento.
Repositorio publico: piloto_publico.json nao tem valores monetarios; o estado completo vai cifrado (DATA_KEY).

Uso: python3 tools/piloto_okx.py <pasta> [--simular | --verificar]
  <pasta> tem piloto_estado.json (decifrado), estrategias_registo.json e papel_estado.json (copias do ramo autonomo)."""
import hashlib
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import protecao as PROT  # noqa: E402
from engine import quick_opportunities_derivatives as DERIV  # noqa: E402
import piloto_id as PID  # noqa: E402

CFG_FICHEIRO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "piloto_okx_config.json")
PREFIXO = PID.PREFIXO
COMISSAO = 0.0005               # por lado (taker, conservador)
PRAZO_ENTRADA_S = 900           # ordem limite de entrada: o que nao executar ate a volta seguinte e cancelado
TF_S = {"30m": 1800, "1H": 3600, "4H": 14400}
FUNDING_RESERVA_8H = 0.0001     # sem taxa de funding lida: 0,01% por 8 h contra a posicao
REGISTO_MAX_IDADE_S = 6 * 3600   # estados mudam devagar; os sinais (papel) tem de ser frescos
PAPEL_MAX_IDADE_S = 3600
V2_REJEITADA = "e495d11739f6"   # (17/11, ordem do Rui) rejeitada para real, definitivamente
REJEITADAS = {V2_REJEITADA, "f8f018b82179"}   # (17/11, 2.a ordem) nunca reativadas

# Criterios da ordem de 17/11 (secao 3): o registo diz que cumpre; este executor confere de novo.
CRITERIOS = {"oos_n_min": 100, "oos_acontecimentos_min": 30, "oos_dias_min": 30, "pf_min": 1.20, "alfa": 0.05,
             "quota_moeda_max": 0.40, "quota_acontecimento_max": 0.25, "quota_dia_max": 0.25,
             "papel_fechadas_min": 30, "papel_acontecimentos_min": 30, "papel_dias_min": 14}
ROBUSTEZ = ("custos_mais_25pct", "deslize_acima_da_media", "sem_melhores_operacoes", "sem_moedas_de_maior_contributo",
            "primeira_metade", "segunda_metade")


def cfg():
    with open(CFG_FICHEIRO, encoding="utf-8") as f:
        return json.load(f)


def _dia(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


# ------------------------------------------------------------------ estrategias -----------------------------------
def criterios_reais(e):
    """(ok, falhas) para uma entrada do registo. Tudo tem de estar presente e dentro dos limites; o que faltar falha."""
    C = CRITERIOS
    f = []
    if e.get("id") in REJEITADAS:
        return False, ["rejeitada definitivamente (ordens de 17/11)"]
    if e.get("estado") not in ("APPROVED_REAL", "ACTIVE_REAL"):
        f.append(f"estado {e.get('estado')}")
    o = e.get("oos") or {}
    num = lambda d, k: d.get(k) if isinstance(d.get(k), (int, float)) and not isinstance(d.get(k), bool) else None
    chk = [("oos_n", num(o, "n"), lambda x: x >= C["oos_n_min"]),
           ("oos_acontecimentos", num(o, "acontecimentos"), lambda x: x >= C["oos_acontecimentos_min"]),
           ("oos_dias", num(o, "dias"), lambda x: x >= C["oos_dias_min"]),
           ("oos_r_medio", num(o, "r_medio"), lambda x: x > 0),
           ("profit_factor", num(o, "profit_factor"), lambda x: x >= C["pf_min"]),
           ("p_holm", num(o, "p_holm"), lambda x: x < C["alfa"])]
    ic = o.get("ic95_acontecimento")
    chk.append(("ic95_inferior", ic[0] if isinstance(ic, list) and len(ic) == 2 and isinstance(ic[0], (int, float)) else None,
                lambda x: x > 0))
    rb = o.get("robustez") or {}
    for k in ROBUSTEZ:
        chk.append((f"robustez:{k}", num(rb, k), lambda x: x > 0))
    cc = o.get("concentracao") or {}
    for k, lim in (("moeda", C["quota_moeda_max"]), ("acontecimento", C["quota_acontecimento_max"]),
                   ("dia", C["quota_dia_max"])):
        chk.append((f"concentracao:{k}", num(cc, k), lambda x, lim=lim: x <= lim))
    p = e.get("papel") or {}
    chk += [("papel_fechadas", num(p, "fechadas"), lambda x: x >= C["papel_fechadas_min"]),
            ("papel_acontecimentos", num(p, "acontecimentos"), lambda x: x >= C["papel_acontecimentos_min"]),
            ("papel_dias", num(p, "dias"), lambda x: x >= C["papel_dias_min"]),
            ("papel_r_medio", num(p, "r_medio"), lambda x: x > 0),
            ("papel_falhas_criticas", num(p, "falhas_criticas"), lambda x: x == 0)]
    for nome, v, teste in chk:
        if v is None:
            f.append(f"{nome}: em falta")
        elif not teste(v):
            f.append(f"{nome}: {v}")
    return not f, f


def criterios_experimentais(e, ops_reais=()):
    """(17/11, 2.a ordem do Rui) EXPERIMENTAL_REAL: so a auditoria tecnica (sem estatistica) + degradacao real da
    PROPRIA estrategia (5+ operacoes com media < -0,5R, ou -4R acumulados): suspensa sozinha, as outras continuam."""
    f = []
    if e.get("id") in REJEITADAS:
        return False, ["rejeitada definitivamente (ordens de 17/11)"]
    if e.get("estado") != "EXPERIMENTAL_REAL":
        f.append(f"estado {e.get('estado')}")
    a = e.get("auditoria_tecnica") or {}
    if a.get("ok") is not True:
        f.append("auditoria tecnica: " + ", ".join(a.get("falhas") or ["em falta"]))
    sd = (e.get("definicao") or {}).get("saida") or {}
    if not (isinstance(sd.get("k"), (int, float)) and sd["k"] > 0 and sd.get("hold")):
        f.append("stop/duracao indefinidos")
    rr = [o["r"] for o in ops_reais if o.get("estrategia") == e.get("id") and o.get("r") is not None]
    if len(rr) >= 5 and sum(rr) / len(rr) < -0.5:
        f.append(f"degradada em real ({len(rr)} op., media {sum(rr) / len(rr):+.2f}R): suspensa individualmente")
    if rr and sum(rr) <= -4:
        f.append(f"degradada em real ({sum(rr):+.1f}R acumulados): suspensa individualmente")
    return not f, f


def prioridade(e, ops_reais=()):
    """Prioridade dinamica: aprovadas primeiro; depois expectativa (fora da amostra, ou backtest para as
    experimentais) ajustada pelo resultado real recente da propria estrategia (3+ operacoes)."""
    base = float((e.get("oos") or {}).get("r_medio") or 0) + 1.0 if e.get("estado") in ("APPROVED_REAL", "ACTIVE_REAL") \
        else float((e.get("backtest") or {}).get("r_medio") or 0)
    rr = [o["r"] for o in ops_reais if o.get("estrategia") == e.get("id") and o.get("r") is not None][-10:]
    return base + (0.5 * sum(rr) / len(rr) if len(rr) >= 3 else 0.0)


def estrategias_aprovadas(registo, c, ops_reais=()):
    """Elegiveis para real, cada uma pelo seu estado: APPROVED/ACTIVE_REAL (criterios estatisticos conferidos) ou
    EXPERIMENTAL_REAL (auditoria tecnica). Uma estrategia recusada nunca impede as outras."""
    out, recusadas = {}, {}
    for e in (registo or {}).get("estrategias", {}).values():
        if e.get("estado") in ("APPROVED_REAL", "ACTIVE_REAL"):
            ok, falhas = criterios_reais(e)
        elif e.get("estado") == "EXPERIMENTAL_REAL":
            ok, falhas = criterios_experimentais(e, ops_reais)
        else:
            continue
        if ok and (e.get("lado") in c["lados"] or e.get("origem") == "copy"):
            out[e["id"]] = e
        else:
            recusadas[e["id"]] = falhas or [f"lado {e.get('lado')} nao autorizado"]
    return out, recusadas


# ------------------------------------------------------------------ dimensionamento -------------------------------
def _passo(x, passo):
    return math.floor(x / passo + 1e-9) * passo if passo else x


def dimensionar(pl, inst, c, spread_pct, saldo=None, funding_8h=None, horas=24.0):
    """Contratos para arriscar <= risco_max_op USDC INCLUINDO custos (comissao ida e volta, spread, reserva de
    deslizamento, funding estimado na duracao maxima); nocional <= nocional_max; alavancagem entre alav_min e alav_max
    (alav_min de referencia; sobe so se a margem nao couber no capital livre) e nunca acima da do instrumento.
    Rejeita (devolve o motivo) em vez de aumentar para o minimo."""
    e, st, lado = pl["entrada"], pl["stop"], pl["lado"]
    if not e or not st or (lado == "LONG" and not st < e) or (lado == "SHORT" and not st > e):
        return None, "stop invalido"
    ctv = float(inst["ctVal"]) * float(inst.get("ctMult") or 1)
    nocional_1 = ctv * (e if (inst.get("ctValCcy") or "").upper() not in ("USD", "USDC") else 1.0)
    fr = FUNDING_RESERVA_8H if funding_8h is None else (funding_8h if lado == "LONG" else -funding_8h)
    custo_pct = 2 * COMISSAO + spread_pct / 100 + c["reserva_deslize_pct"] / 100 + max(0.0, fr) * math.ceil(horas / 8)
    risco_1 = nocional_1 * abs(e - st) / e + nocional_1 * custo_pct
    n = _passo(min(c["risco_max_op"] / risco_1, c["nocional_max"] / nocional_1), float(inst["lotSz"]))
    minimo = float(inst["minSz"])
    if n < minimo:
        return None, (f"tamanho minimo ({minimo:g} contratos) passaria o risco ou o nocional autorizados")
    nocional = n * nocional_1
    livre = min(c["capital_max"], saldo if saldo is not None else c["capital_max"])
    alav = max(int(c["alav_min"]), math.ceil(nocional / max(1e-9, livre * 0.9)))
    teto_inst = float(inst.get("lever") or 0) or c["alav_max"]
    if alav > c["alav_max"]:
        return None, f"precisaria de {alav}x (maximo autorizado {c['alav_max']}x)"
    if alav > teto_inst:
        return None, f"o instrumento so permite {teto_inst:g}x (minimo autorizado {c['alav_min']}x)"
    return {"contratos": n, "nocional": round(nocional, 4), "risco_total": round(n * risco_1, 4), "alav": alav,
            "margem": round(nocional / alav, 4), "custos_estimados": round(n * nocional_1 * custo_pct, 4),
            "custo_r": round(custo_pct * e / abs(e - st), 4)}, None


# ------------------------------------------------------------------ estado e limites ------------------------------
def estado_inicial():
    return {"ops": [], "aberta": None, "bloqueio": None, "suspenso": None, "perda_realizada": 0.0, "dias": {},
            "vistos": [], "portas": {}, "eventos": [], "sinais_perdidos": [], "bloqueio_dia": {}}


def evento(st, now, txt, **kw):
    st["eventos"].append({"t": int(now), "txt": txt, **kw})
    st["eventos"] = st["eventos"][-500:]


def perdas(st, upl, now, okx=None):
    """Perda acumulada e do dia = realizada + nao realizada (so a parte negativa). A realizada e a pior entre o estado e
    a OKX (okx = {"total": x, "dias": {...}} das posicoes fechadas do piloto)."""
    dia = _dia(now)
    nao = min(0.0, upl or 0.0)
    real_total = min(st["perda_realizada"], (okx or {}).get("total", 0.0))
    real_dia = min(st["dias"].get(dia, 0.0), ((okx or {}).get("dias") or {}).get(dia, 0.0))
    return {"acumulada": round(max(0.0, -(real_total + nao)), 4), "dia": round(max(0.0, -(real_dia + nao)), 4)}


def aplicar_limites(st, c, upl, now, okx=None):
    """Bloqueios persistentes: so se levantam editando o estado (decisao do Rui), nunca numa nova execucao."""
    p = perdas(st, upl, now, okx)
    acoes = []
    if p["acumulada"] >= c["perda_max"]:
        if not st["bloqueio"]:
            st["bloqueio"] = {"t": int(now), "motivo": "perda acumulada maxima atingida: piloto encerrado"}
        acoes += ["cancelar_entradas", "fechar_posicao"]
    elif p["acumulada"] >= c["suspender_em"] and not st["suspenso"]:
        st["suspenso"] = {"t": int(now), "motivo": "perda acumulada de suspensao atingida: revisao obrigatoria"}
        acoes += ["cancelar_entradas"]
    dia = _dia(now)
    if p["dia"] >= c["perda_diaria_max"] and not st["bloqueio_dia"].get(dia):
        st["bloqueio_dia"][dia] = "perda diaria maxima atingida: sem entradas ate ao dia seguinte (UTC)"
        acoes += ["cancelar_entradas"]
    st["bloqueio_dia"] = {k: v for k, v in st["bloqueio_dia"].items() if k >= _dia(now - 7 * 86400)}
    return p, sorted(set(acoes))


def perdas_okx(api, st):
    """PnL realizado (realizedPnl = pnl + comissoes + funding) das posicoes fechadas do piloto, pela OKX: as do estado
    (posId) e as que as execucoes "pil" (fills-history, 3 meses) mostram, mesmo que o estado se tenha perdido."""
    ph = api.priv("GET", "/api/v5/account/positions-history?instType=FUTURES&limit=100")
    fh = api.priv("GET", "/api/v5/trade/fills-history?instType=FUTURES&limit=100")
    if (ph or {}).get("code") != "0" or (fh or {}).get("code") != "0":
        return None
    nossos = {o.get("posId") for o in st["ops"] if o.get("posId")}
    pil = [x for x in fh.get("data") or [] if str(x.get("clOrdId") or "").startswith(PREFIXO)]
    tot, dias = 0.0, {}
    for x in ph.get("data") or []:
        c0, u0 = int(x.get("cTime") or 0), int(x.get("uTime") or 0)
        dele = x.get("posId") in nossos or any(f.get("instId") == x.get("instId") and c0 - 1000 <= int(f.get("ts") or 0) <= u0 + 1000
                                               for f in pil)
        if dele:
            v = float(x.get("realizedPnl") or x.get("pnl") or 0)
            tot += v
            d = _dia(u0 // 1000)
            dias[d] = dias.get(d, 0.0) + v
    return {"total": round(tot, 6), "dias": {k: round(v, 6) for k, v in dias.items()}}


# ------------------------------------------------------------------ portas ----------------------------------------
def portas(api, st, c, now, registo, papel, isolado, cifra_ok, aprovadas, falhas_api):
    out = {}
    out["config_ativa"] = (bool(c.get("ativo")), "ativo no piloto_okx_config.json")
    conf = api.priv("GET", "/api/v5/account/config")
    ok, porque = DERIV.validate_okx_account_config(conf)
    out["conta_usdc"] = (ok, porque)
    row = ((conf or {}).get("data") or [{}])[0] if (conf or {}).get("code") == "0" else {}
    perm = str(row.get("perm") or "")
    out["sem_levantamentos"] = (bool(perm) and "withdraw" not in perm, f"permissoes da API: {perm or 'desconhecidas'}")
    out["modo_conta"] = (str(row.get("posMode")) == "net_mode" and str(row.get("acctLv")) in ("2", "3", "4"),
                         f"posMode={row.get('posMode')} acctLv={row.get('acctLv')} (precisa net_mode e conta com margem)")
    bal = api.priv("GET", "/api/v5/account/balance?ccy=USDC")
    try:
        disp = float(((bal.get("data") or [{}])[0].get("details") or [{}])[0].get("availBal") or 0)
    except (TypeError, ValueError, IndexError, AttributeError):
        disp = 0.0
    st["_saldo_usdc"] = disp
    margem_min = c["nocional_max"] / c["alav_max"]
    out["saldo_usdc"] = (disp >= margem_min, "saldo USDC disponivel chega para a margem de uma operacao"
                         if disp >= margem_min else "saldo USDC disponivel nao chega para a margem de uma operacao")
    out["isolamento"] = (bool(isolado), "okx_exec declara PILOTO_ISOLADO (nao adota nem abre por cima do piloto)"
                         if isolado else "o executor OKX existente nao esta isolado do piloto")
    out["estado_cifrado"] = (bool(cifra_ok), "estado guardado cifrado (DATA_KEY)" if cifra_ok else "sem DATA_KEY: o estado nao pode ser guardado")
    out["bloqueio"] = (not st["bloqueio"] and not st["suspenso"], (st["bloqueio"] or st["suspenso"] or {}).get("motivo", "sem bloqueio"))
    dia = _dia(now)
    out["perda_do_dia"] = (not st["bloqueio_dia"].get(dia), st["bloqueio_dia"].get(dia) or "dentro do limite diario")
    out["api_fiavel"] = (not falhas_api, "sem falhas da API nesta volta" if not falhas_api else f"{len(falhas_api)} pedidos falharam: {falhas_api[:3]}")
    t_reg, t_pap, t_cp = (registo or {}).get("t") or 0, (papel or {}).get("t") or 0, (papel or {}).get("t_copy") or 0
    fontes = [n for n, ok in (("papel", now - t_reg <= REGISTO_MAX_IDADE_S and now - t_pap <= PAPEL_MAX_IDADE_S),
                              ("copy", now - t_cp <= COPY_MAX_IDADE_S)) if ok]
    out["dados_frescos"] = (bool(fontes), f"fontes de sinais frescas: {', '.join(fontes) or 'nenhuma'} (registo ha {(now - t_reg) // 60} min, "
                                          f"papel ha {(now - t_pap) // 60} min, copy ha {(now - t_cp) // 60 if t_cp else '-'} min)")
    out["contas_confirmadas"] = (not any(o.get("pnl_por_confirmar") for o in st["ops"]), "resultado de todas as posicoes fechadas confirmado na OKX")
    nexp = sum(1 for e in aprovadas.values() if e.get("estado") == "EXPERIMENTAL_REAL")
    out["estrategias_elegiveis"] = (bool(aprovadas), f"{len(aprovadas) - nexp} aprovadas e {nexp} experimentais" if aprovadas else
                                    "nenhuma estrategia elegivel (aprovada ou experimental)")
    return {k: {"ok": bool(v[0]), "detalhe": v[1]} for k, v in out.items()}


# ------------------------------------------------------------------ OKX -------------------------------------------
class Contador:
    """Envolve a API e regista os pedidos falhados nesta volta (porta api_fiavel)."""
    def __init__(self, api):
        self.api, self.falhas = api, []

    def priv(self, metodo, path, corpo=None):
        r = self.api.priv(metodo, path, corpo)
        if (r or {}).get("code") != "0" and metodo == "GET":
            self.falhas.append(path.split("?")[0].rsplit("/", 1)[-1])
        return r

    def pub(self, path, params=None):
        return self.api.pub(path, params)


def instrumentos(api):
    """X-Perps de cripto vivos e negociaveis pela conta, com a especificacao atual."""
    r = api.priv("GET", "/api/v5/account/instruments?instType=FUTURES")
    conta = {x["instId"] for x in (r.get("data") or [])} if (r or {}).get("code") == "0" else set()
    out = {}
    for i in api.pub("/api/v5/public/instruments", {"instType": "FUTURES"}) or []:
        iid = i.get("instId", "")
        if (DERIV.is_um_xperp(iid) and iid in conta and i.get("state") == "live" and i.get("ctType") == "linear"
                and str(i.get("ruleType")).lower() != "pre_market"):    # (17/11) cripto, acoes e outros X-Perps
            out[iid] = {"inst": iid, "ctVal": i["ctVal"], "ctMult": i.get("ctMult") or 1, "ctValCcy": i.get("ctValCcy"),
                        "lotSz": i["lotSz"], "minSz": i["minSz"], "tickSz": i["tickSz"], "lever": i.get("lever")}
    return out


def ocupado_por_outro(api, inst):
    """O instrumento tem posicao ou ordens que NAO sao do piloto? (modo net juntaria as posicoes). None = sem resposta."""
    pos = api.priv("GET", f"/api/v5/account/positions?instId={inst}")
    pend = api.priv("GET", f"/api/v5/trade/orders-pending?instId={inst}")
    a1 = api.priv("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional")
    a2 = api.priv("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco")
    if any((x or {}).get("code") != "0" for x in (pos, pend, a1, a2)):
        return None
    if any(float(x.get("pos") or 0) for x in pos.get("data") or []):
        return True
    if any(not str(x.get("clOrdId") or "").startswith(PREFIXO) for x in pend.get("data") or []):
        return True
    return any(not str(x.get("algoClOrdId") or "").startswith(PREFIXO) for x in (a1.get("data") or []) + (a2.get("data") or []))


def _cl(id_op):
    return PREFIXO + hashlib.sha256(id_op.encode()).hexdigest()[:24]


# ------------------------------------------------------------------ ciclo -----------------------------------------
COPY_MAX_IDADE_S = 900


def juntar_copy(registo, papel, copy, now):
    """(17/11, CopyTrading) Os sinais do CopyTrading (ramo autonomo, copy/sinais.json) entram como mais uma fonte:
    estrategias "copy:<fonte>:<trader>" (EXPERIMENTAL_REAL, uma por trader, suspensa sozinha se degradar) e sinais
    abertos/fechados. Partilham TODOS os limites do piloto (mesmo orcamento, 1 posicao). Uma fonte velha deixa de
    contribuir sinais novos sem fechar as portas da outra."""
    reg = {"t": (registo or {}).get("t"), "estrategias": dict((registo or {}).get("estrategias") or {})}
    pap = {"t": (papel or {}).get("t"), "abertas": list((papel or {}).get("abertas") or []) if now - int((papel or {}).get("t") or 0) <= PAPEL_MAX_IDADE_S else [],
           "fechadas": list((papel or {}).get("fechadas") or [])}
    if copy:
        reg["estrategias"].update(copy.get("estrategias") or {})
        if now - int(copy.get("t") or 0) <= COPY_MAX_IDADE_S:
            pap["abertas"] += copy.get("abertas") or []
        pap["fechadas"] += copy.get("fechadas") or []
        pap["t_copy"] = copy.get("t")
    return reg, pap


def ciclo(api, pasta, now=None, simular=False, registo=None, papel=None, isolado=None, cifra_ok=None, enviar=lambda m: None,
          copy=None):
    now = int(now or time.time())
    c = cfg()
    p = os.path.join(pasta, "piloto_estado.json")
    st = estado_inicial()
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            st.update(json.load(f))
    if st.get("aberta"):                                     # a aberta e a mesma operacao da lista (um so objeto)
        ids = [o.get("id") for o in st["ops"]]
        if st["aberta"].get("id") in ids:
            st["ops"][ids.index(st["aberta"]["id"])] = st["aberta"]
        else:
            st["ops"].append(st["aberta"])
    if isolado is None:
        isolado = _okx_exec_isolado()
    if cifra_ok is None:
        cifra_ok = bool(os.environ.get("DATA_KEY"))
    api = Contador(api)
    msgs = []
    papel = papel or {}
    registo, papel = juntar_copy(registo, papel, copy, now)
    aprovadas, recusadas = estrategias_aprovadas(registo, c, st["ops"])
    # 1. reconciliar com a OKX (so o que e do piloto)
    rec = reconciliar(api, st, now, msgs, simular)
    orfas(api, st, now, msgs, simular)
    okx = perdas_okx(api, st)
    pp, acoes = aplicar_limites(st, c, rec.get("upl", 0.0), now, okx)
    if acoes:
        executar_acoes(api, st, acoes, now, msgs, simular)
    # 2. gerir a posicao: saida por tempo e espelho do fecho do papel
    gerir(api, st, now, msgs, simular, papel)
    # 3. portas e entrada nova (so sem posicao)
    st["portas"] = portas(api, st, c, now, registo, papel, isolado, cifra_ok, aprovadas, api.falhas)
    fechadas = [k for k, v in st["portas"].items() if not v["ok"]]
    if st["aberta"] is None and len([o for o in st["ops"] if o.get("estado") in ("pendente", "aberta")]) < c["posicoes_max"]:
        cand = procurar(api, st, c, now, papel, aprovadas)
        st["ultimo_sinal"] = {k: v for k, v in (cand or {}).items() if k != "inst_spec"} if cand else None
        if cand and cand.get("plano"):
            if fechadas:
                evento(st, now, "sinal valido NAO executado: portas fechadas", portas=fechadas, sinal=cand["id"])
                perdido(st, now, cand["id"], "portas fechadas: " + ", ".join(fechadas))
                msgs.append(f"🔒 Piloto OKX: sinal {cand['base']} {cand['lado']} ({cand['estrategia']}) não executado — "
                            f"portas fechadas: {', '.join(fechadas)}.")
            else:
                entrar(api, st, c, cand, now, msgs, simular)
    st["perdas"] = pp
    st["recusadas_pelo_executor"] = recusadas
    relatorio_diario(st, now, msgs, aprovadas)
    st["t"] = now
    st["simulacao"] = bool(simular)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    with open(os.path.join(pasta, "piloto_publico.json"), "w", encoding="utf-8") as f:
        json.dump(publico(st, c, aprovadas, now), f, ensure_ascii=False, indent=1)
    for m in msgs:
        enviar(m)
    return st, msgs


def _okx_exec_isolado():
    try:
        import okx_exec
        return bool(getattr(okx_exec, "PILOTO_ISOLADO", False))
    except Exception:
        return False


def perdido(st, now, sid, motivo):
    st["sinais_perdidos"].append({"t": int(now), "sinal": sid, "motivo": motivo})
    st["sinais_perdidos"] = st["sinais_perdidos"][-300:]


def procurar(api, st, c, now, papel, aprovadas):
    """Sinais do papel das estrategias aprovadas, ainda frescos; escolhe o melhor (expectativa fora da amostra menos o
    custo extra estimado; empate: liquidez). Um sinal nunca e tratado duas vezes."""
    if not aprovadas:
        return None
    novos = [o for o in papel.get("abertas") or [] if o.get("estrategia") in aprovadas and o.get("id_op") not in st["vistos"]
             and o.get("inst")]
    if not novos:
        return None
    xp = instrumentos(api)
    tick = {t["instId"]: t for t in api.pub("/api/v5/market/tickers", {"instType": "FUTURES"}) or []}
    cands = []
    for o in novos:
        sid, e = o["id_op"], aprovadas[o["estrategia"]]
        st["vistos"].append(sid)
        tf_s = TF_S.get(o.get("tf"), 3600)
        copia = o.get("origem") == "copy"
        atraso = now - (int(o["t_ref"]) if copia else int(o["t_sinal"]) + tf_s)
        amax = c["atraso_max_s"].get("copy" if copia else o.get("tf"), 600 if copia else 900)
        if atraso > amax:
            perdido(st, now, sid, (f"copia tardia: {atraso // 60} min depois da entrada do trader" if copia else
                                   f"chegou {atraso // 60} min depois do fecho da vela") + f" (maximo {amax // 60})")
            continue
        if e.get("regimes") and o.get("regime") not in e["regimes"]:
            perdido(st, now, sid, f"regime {o.get('regime')} fora dos aprovados {e['regimes']}")
            continue
        if o.get("lado") not in c["lados"] or (o.get("lado") != e.get("lado") and e.get("origem") != "copy"):
            perdido(st, now, sid, "lado nao autorizado ou diferente da estrategia aprovada")
            continue
        inst = xp.get(o["inst"])
        if not inst:
            perdido(st, now, sid, "contrato nao negociavel por esta conta")
            continue
        t = tick.get(o["inst"]) or {}
        bid, ask = float(t.get("bidPx") or 0), float(t.get("askPx") or 0)
        spread = 100 * (ask - bid) / ((ask + bid) / 2) if bid > 0 and ask > 0 else None
        if spread is None or spread > c["spread_max_pct"]:
            perdido(st, now, sid, f"spread {None if spread is None else round(spread, 3)}% acima de {c['spread_max_pct']}% (liquidez)")
            continue
        lado, d = o["lado"], (1 if o["lado"] == "LONG" else -1)
        px = ask if lado == "LONG" else bid
        risco = float(o["saida"]["k"]) * float(o["atr_ref"])
        ref = float(o.get("entrada") or (o.get("decisao") or {}).get("fecho") or 0)
        if not risco or not ref:
            perdido(st, now, sid, "sinal sem ATR ou preco de referencia")
            continue
        if abs(px - ref) > c["desvio_max_r"] * risco:
            perdido(st, now, sid, f"preco fugiu {abs(px - ref) / risco:.2f}R da referencia do papel (maximo {c['desvio_max_r']}R)")
            continue
        stop = float(o["stop_inicial"]) if o.get("stop_inicial") else px - d * risco
        alvo = (float(o["objetivo"]) if o.get("objetivo") else px + d * float(o["saida"]["tp"]) * risco) if o["saida"].get("tp") else None
        if (px - stop) * d <= 0 or (alvo is not None and (alvo - px) * d <= 0):
            perdido(st, now, sid, "preco atual ja fora do plano (stop ou objetivo)")
            continue
        horas = float(o["saida"].get("hold") or 6) * tf_s / 3600
        fund = api.pub("/api/v5/public/funding-rate", {"instId": o["inst"]}) or []
        f8 = float(fund[0]["fundingRate"]) if fund and fund[0].get("fundingRate") not in (None, "") else None
        pl = {"entrada": px, "stop": stop, "alvo": alvo, "lado": lado}
        dim, porque = dimensionar(pl, inst, c, spread, saldo=st.get("_saldo_usdc"), funding_8h=f8, horas=horas)
        if not dim:
            perdido(st, now, sid, porque)
            continue
        oc = ocupado_por_outro(api, o["inst"])
        if oc is not False:
            perdido(st, now, sid, "instrumento com posicao/ordens de outro executor" if oc else "OKX sem resposta sobre o instrumento")
            continue
        score = prioridade(e, st["ops"]) - dim["custo_r"]
        cands.append({"id": sid, "estrategia": o["estrategia"], "versao": e.get("versao") or o["estrategia"], "base": o.get("b"),
                      "inst": o["inst"], "lado": lado, "tf": o.get("tf"), "regime": o.get("regime"), "t_sinal": int(o["t_sinal"]),
                      "plano": pl, "dim": dim, "spread_pct": round(spread, 4), "tick": inst["tickSz"], "hold_s": int(horas * 3600),
                      "score": round(score, 4), "vol": float(t.get("volCcy24h") or 0)})
    st["vistos"] = st["vistos"][-20000:]
    if not cands:
        return None
    cands.sort(key=lambda x: (-x["score"], -x["vol"]))
    for x in cands[1:]:
        perdido(st, now, x["id"], f"outra oportunidade melhor na mesma volta ({cands[0]['id']}); 1 posicao de cada vez")
    return cands[0]


def entrar(api, st, c, cand, now, msgs, simular):
    d, pl = cand["dim"], cand["plano"]
    cl = _cl(cand["id"])
    tk = float(cand["tick"])
    px = lambda x: f"{_passo(x, tk):.10f}".rstrip("0").rstrip(".")
    venda = cand["lado"] == "SHORT"
    op = {"id": cand["id"], "clOrdId": cl, "estrategia": cand["estrategia"], "versao": cand["versao"], "inst": cand["inst"],
          "base": cand["base"], "lado": cand["lado"], "tf": cand["tf"], "regime": cand["regime"], "t_sinal": cand["t_sinal"],
          "t_ordem": int(now), "preco_previsto": pl["entrada"], "stop": float(px(pl["stop"])),
          "alvo": float(px(pl["alvo"])) if pl["alvo"] else None, "contratos": d["contratos"], "alav": d["alav"],
          "risco_planeado": d["risco_total"], "nocional": d["nocional"], "custos_estimados": d["custos_estimados"],
          "spread_pct": cand["spread_pct"], "estado": "pendente", "prazo": int(now) + PRAZO_ENTRADA_S, "hold_s": cand["hold_s"],
          "sair_em": None}
    if simular:
        op["estado"] = "simulada (sem ordem)"
        st["ops"].append(op)
        evento(st, now, "SIMULACAO: ordem nao enviada", op=op["id"])
        msgs.append(f"🧪 Piloto OKX (simulação): entraria em {cand['base']} {cand['lado']} ({cand['estrategia']}), "
                    f"{d['contratos']:g} contratos, {d['alav']}x.")
        return
    q = api.priv("GET", f"/api/v5/trade/order?instId={cand['inst']}&clOrdId={cl}")
    if (q or {}).get("code") == "0" and (q.get("data") or [{}])[0].get("ordId"):
        evento(st, now, "ordem com este clOrdId ja existe na OKX: nao repito", op=op["id"])
        perdido(st, now, cand["id"], "ordem ja existente na OKX (protecao contra duplicados)")
        return
    lv = api.priv("POST", "/api/v5/account/set-leverage", {"instId": cand["inst"], "lever": str(d["alav"]), "mgnMode": "isolated"})
    if (lv or {}).get("code") != "0":
        evento(st, now, "alavancagem recusada: sem ordem", resposta=str(lv)[:200])
        msgs.append(f"⚠️ Piloto OKX: a OKX recusou {d['alav']}x em {cand['base']}; nenhuma ordem enviada.")
        return
    algo = {"attachAlgoClOrdId": cl[:28] + "slt", "slTriggerPx": px(pl["stop"]), "slOrdPx": "-1"}
    if pl["alvo"]:
        algo.update(tpTriggerPx=px(pl["alvo"]), tpOrdPx="-1")
    r = api.priv("POST", "/api/v5/trade/order", {
        "instId": cand["inst"], "tdMode": "isolated", "side": "sell" if venda else "buy", "ordType": "limit",
        "px": px(pl["entrada"]), "sz": f"{d['contratos']:g}", "clOrdId": cl, "attachAlgoOrds": [algo]})
    dd = ((r or {}).get("data") or [{}])[0]
    if (r or {}).get("code") != "0" or dd.get("sCode") not in (None, "0"):
        evento(st, now, "ordem recusada pela OKX", resposta=str(r)[:300])
        msgs.append(f"⚠️ Piloto OKX: ordem em {cand['base']} recusada pela OKX ({dd.get('sMsg') or (r or {}).get('msg')}).")
        return
    op["ordId"] = dd.get("ordId")
    st["aberta"] = op
    st["ops"].append(op)
    evento(st, now, "ordem ENVIADA (ainda nao executada)", op=op["id"], ordId=op["ordId"])
    msgs.append(f"📌 Piloto OKX: ordem limite {cand['lado']} {cand['base']} ({cand['estrategia']}) enviada "
                f"({d['contratos']:g} contratos, {d['alav']}x isolada, stop{' e objetivo' if pl['alvo'] else ''} anexados). "
                f"Enviada não é executada: confirmo na volta seguinte.")


def _algos(api, inst):
    a1 = api.priv("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=conditional")
    a2 = api.priv("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType=oco")
    return [x for x in ((a1 or {}).get("data") or []) + ((a2 or {}).get("data") or []) if x.get("instId", inst) == inst]


def reconciliar(api, st, now, msgs, simular=False):
    """Estado da OKX para a operacao do piloto: ordem (executada, parcial, cancelada), posicao, stop, fecho."""
    op = st.get("aberta")
    if not op or "simulada" in op.get("estado", ""):
        if op:
            st["aberta"] = None
        return {}
    o = api.priv("GET", f"/api/v5/trade/order?instId={op['inst']}&ordId={op.get('ordId')}")
    od = ((o or {}).get("data") or [{}])[0] if (o or {}).get("code") == "0" else {}
    pos = api.priv("GET", f"/api/v5/account/positions?instId={op['inst']}")
    if (pos or {}).get("code") != "0":
        return {"upl": 0.0}                                  # sem resposta: nada se decide nesta volta
    pd = next((x for x in pos.get("data") or [] if float(x.get("pos") or 0) != 0), None)
    upl = float(pd.get("upl") or 0) if pd else 0.0
    acc = float(od.get("accFillSz") or 0)
    if op["estado"] == "pendente":
        if acc > 0:
            op.update(estado="aberta", contratos_exec=acc, preco_efetivo=float(od.get("avgPx") or 0),
                      t_execucao=int(int(od.get("fillTime") or 0) / 1000), posId=(pd or {}).get("posId"))
            if not op["t_execucao"] or op["t_execucao"] < op["t_ordem"] - 60 or op["t_execucao"] > now + 60:
                op["t_execucao"] = int(now)                  # hora de execucao implausivel: conta a partir de agora
            d = 1 if op["lado"] == "LONG" else -1
            op["slippage_pct"] = round(100 * d * (op["preco_efetivo"] / op["preco_previsto"] - 1), 4)
            op["sair_em"] = op["t_execucao"] + int(op.get("hold_s") or 6 * 14400)
            parcial = od.get("state") == "partially_filled" or acc < op["contratos"]
            evento(st, now, "EXECUTADA" + (" parcialmente" if parcial else ""), op=op["id"], contratos=acc)
            msgs.append(f"✅ Piloto OKX: {op['lado']} executado em {op['base']} a {op['preco_efetivo']:.6g} "
                        f"({acc:g}/{op['contratos']:g} contratos).")
            if parcial:
                if od.get("state") == "partially_filled":
                    api.priv("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
                    evento(st, now, "resto da ordem parcial cancelado")
                op["risco_planeado"] = round(op["risco_planeado"] * acc / op["contratos"], 4)
        elif now >= op["prazo"] or od.get("state") in ("canceled", "mmp_canceled"):
            if od.get("state") not in ("canceled", "mmp_canceled"):
                cx = api.priv("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op["ordId"]})
                q = api.priv("GET", f"/api/v5/trade/order?instId={op['inst']}&ordId={op.get('ordId')}")
                qd = ((q or {}).get("data") or [{}])[0]
                if float(qd.get("accFillSz") or 0) > 0:          # executou entre a leitura e o cancelamento
                    return reconciliar(api, st, now, msgs, simular)
                if qd.get("state") not in ("canceled", "mmp_canceled") and (cx or {}).get("code") != "0":
                    evento(st, now, "cancelamento por confirmar: tento na volta seguinte", op=op["id"])
                    return {"upl": upl}
            op["estado"] = "nao executada (cancelada)"
            st["aberta"] = None
            evento(st, now, "entrada nao executada no prazo: cancelada", op=op["id"])
            msgs.append(f"⏹️ Piloto OKX: entrada em {op['base']} não executada no prazo; cancelada.")
            return {"upl": 0.0}
    if op["estado"] in ("aberta", "a fechar"):
        if pd is None:                                       # fechou (stop, objetivo, tempo, espelho ou manual)
            fechar_contas(api, st, op, now, msgs)
            return {"upl": 0.0}
        op["posId"] = op.get("posId") or pd.get("posId")
        ok, mot = PROT.stop_cobre(_algos(api, op["inst"]), abs(float(pd["pos"])), op["lado"], op.get("preco_efetivo"))
        op["stop_confirmado"] = bool(ok)
        if not ok:
            evento(st, now, "POSICAO SEM STOP CONFIRMADO", motivos=mot)
            r = api.priv("POST", "/api/v5/trade/order-algo", {
                "instId": op["inst"], "tdMode": "isolated", "side": "buy" if op["lado"] == "SHORT" else "sell",
                "ordType": "conditional", "sz": f"{abs(float(pd['pos'])):g}", "reduceOnly": True,
                "algoClOrdId": op["clOrdId"][:28] + "rep", "slTriggerPx": str(op["stop"]), "slOrdPx": "-1"})
            if (r or {}).get("code") == "0":
                msgs.append(f"⚠️ Piloto OKX: {op['base']} estava sem stop confirmado; stop reposto (confirmo na volta seguinte).")
            else:
                api.priv("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated"})
                st["bloqueio"] = {"t": int(now), "motivo": "stop nao colocado: posicao fechada por seguranca"}
                op["estado"] = "a fechar"
                evento(st, now, "stop falhou: fecho de seguranca e piloto bloqueado")
                msgs.append(f"🛑 Piloto OKX: não consegui proteger {op['base']}; pedi o fecho da posição e bloqueei o piloto.")
    return {"upl": upl}


def orfas(api, st, now, msgs, simular):
    """Ordens e posicoes do piloto na OKX que o estado nao segue (estado perdido, falha a meio): cancela/fecha e suspende."""
    seguida = (st.get("aberta") or {}).get("ordId")
    pend = api.priv("GET", "/api/v5/trade/orders-pending?instType=FUTURES")
    for x in (pend or {}).get("data") or [] if (pend or {}).get("code") == "0" else []:
        if str(x.get("clOrdId") or "").startswith(PREFIXO) and x.get("ordId") != seguida:
            evento(st, now, "ORDEM ORFA DO PILOTO", inst=x.get("instId"))
            if not simular:
                api.priv("POST", "/api/v5/trade/cancel-order", {"instId": x["instId"], "ordId": x["ordId"]})
            st["suspenso"] = st["suspenso"] or {"t": int(now), "motivo": "ordem orfa do piloto encontrada e cancelada: revisao"}
            msgs.append(f"🛑 Piloto OKX: ordem órfã do piloto em {str(x.get('instId')).split('-')[0]} — cancelei e suspendi novas entradas.")
    pos = api.priv("GET", "/api/v5/account/positions?instType=FUTURES")
    if (pos or {}).get("code") != "0":
        return
    seguidas = {(st.get("aberta") or {}).get("inst")}
    for x in pos.get("data") or []:
        if not float(x.get("pos") or 0) or x.get("instId") in seguidas:
            continue
        dono = PID.do_piloto(api.priv, x["instId"], int(x.get("cTime") or 0) - 1000 if x.get("cTime") else None)
        if dono is True:
            evento(st, now, "POSICAO ORFA DO PILOTO", inst=x["instId"])
            if not simular:
                api.priv("POST", "/api/v5/trade/close-position", {"instId": x["instId"], "mgnMode": "isolated"})
            st["suspenso"] = st["suspenso"] or {"t": int(now), "motivo": "posicao orfa do piloto encontrada e fechada: revisao"}
            msgs.append(f"🛑 Piloto OKX: posição órfã do piloto em {x['instId'].split('-')[0]} — pedi o fecho e suspendi novas entradas.")


def fechar_contas(api, st, op, now, msgs):
    h = api.priv("GET", f"/api/v5/account/positions-history?instType=FUTURES&instId={op['inst']}&limit=20")
    linha = next((x for x in (h or {}).get("data") or [] if op.get("posId") and x.get("posId") == op["posId"]
                  and int(x.get("uTime") or 0) // 1000 >= op.get("t_execucao", 0)), None)
    if linha is None:
        op["tentativas_contas"] = op.get("tentativas_contas", 0) + 1
        op["estado"] = "a fechar"
        if op["tentativas_contas"] >= 4:                     # 1 h sem confirmacao: conta a perda planeada e suspende
            liquido = -op["risco_planeado"]
            op.update(pnl_por_confirmar=True)
            _registar_fecho(st, op, now, liquido, None, "por confirmar na OKX")
            msgs.append(f"⚠️ Piloto OKX: {op['base']} fechada mas sem resultado confirmado na OKX; conto a perda planeada e não entro até confirmar.")
        return
    liquido = float(linha.get("realizedPnl") or linha.get("pnl") or 0)
    px_saida = float(linha.get("closeAvgPx") or 0) or None
    d = 1 if op["lado"] == "LONG" else -1
    motivo = ("objetivo" if op.get("alvo") and px_saida and (px_saida - op["alvo"]) * d >= -abs(op["alvo"]) * 0.001 else
              "stop" if px_saida and (op["stop"] - px_saida) * d >= -abs(op["stop"]) * 0.001 else op.get("motivo_saida") or "tempo/espelho/outro")
    op.pop("pnl_por_confirmar", None)
    _registar_fecho(st, op, now, liquido, px_saida, motivo)
    msgs.append(f"🏁 Piloto OKX: {op['base']} {op['lado']} fechada ({motivo}), {op['r']:+.2f}R.")


def _registar_fecho(st, op, now, liquido, px_saida, motivo):
    op.update(estado="fechada", t_fecho=int(now), preco_saida=px_saida, pnl_liquido=round(liquido, 6), motivo_saida=motivo,
              r=round(liquido / op["risco_planeado"], 3) if op["risco_planeado"] else None,
              duracao_h=round((now - op.get("t_execucao", now)) / 3600, 1))
    st["perda_realizada"] = round(st["perda_realizada"] + liquido, 6)
    dia = _dia(now)
    st["dias"][dia] = round(st["dias"].get(dia, 0.0) + liquido, 6)
    if st.get("aberta") and st["aberta"].get("id") == op["id"]:
        st["aberta"] = None
    evento(st, now, "FECHADA", op=op["id"], r=op["r"], motivo=motivo)


def gerir(api, st, now, msgs, simular, papel):
    op = st.get("aberta")
    if not op or op.get("estado") != "aberta" or simular:
        return
    pap = next((x for x in (papel or {}).get("fechadas") or [] if x.get("id_op") == op["id"]), None)
    motivo = None
    if pap:
        motivo = f"espelho do papel ({pap.get('motivo')})"
        op["r_papel"] = pap.get("r")
    elif op.get("sair_em") and now >= op["sair_em"]:
        motivo = "tempo"
    if motivo:
        r = api.priv("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated"})
        op["motivo_saida"] = motivo
        op["estado"] = "a fechar" if (r or {}).get("code") == "0" else "aberta"
        evento(st, now, f"fecho pedido ({motivo}); confirmo na volta seguinte", op=op["id"], resposta=(r or {}).get("code"))
        msgs.append(f"⏱️ Piloto OKX: {op['base']} — pedi o fecho ({motivo}).")


def executar_acoes(api, st, acoes, now, msgs, simular):
    op = st.get("aberta")
    motivo = (st["bloqueio"] or st["suspenso"] or {}).get("motivo") or "perda diaria maxima atingida"
    if op and op.get("estado") == "pendente" and "cancelar_entradas" in acoes and not simular:
        api.priv("POST", "/api/v5/trade/cancel-order", {"instId": op["inst"], "ordId": op.get("ordId")})
        evento(st, now, "entrada pendente cancelada por limite (confirmo na volta seguinte)", op=op["id"])
        op["prazo"] = 0
    if op and op.get("estado") in ("aberta", "a fechar") and "fechar_posicao" in acoes and not simular:
        api.priv("POST", "/api/v5/trade/close-position", {"instId": op["inst"], "mgnMode": "isolated"})
        op["estado"], op["motivo_saida"] = "a fechar", "limite de perda"
    chave = (tuple(acoes), motivo)
    if st.get("_ultimo_limite") != list(chave[0]) + [motivo]:
        st["_ultimo_limite"] = list(chave[0]) + [motivo]
        evento(st, now, "LIMITE ATINGIDO", acoes=acoes, motivo=motivo)
        msgs.append(f"🛑 Piloto OKX: {motivo}. Ações: {', '.join(acoes)}.")


def relatorio_diario(st, now, msgs, aprovadas):
    """Uma vez por dia (primeira volta depois das 21:00 UTC): operacoes do dia, R, sinais perdidos, estado das portas."""
    dia = _dia(now)
    if now % 86400 < 21 * 3600 or st.get("relatorio_dia") == dia:
        return
    st["relatorio_dia"] = dia
    hoje = [o for o in st["ops"] if o.get("t_fecho") and _dia(o["t_fecho"]) == dia and o.get("r") is not None]
    perd = [x for x in st["sinais_perdidos"] if _dia(x["t"]) == dia]
    fech = [k for k, v in st["portas"].items() if not v["ok"]]
    msgs.append(f"📒 Piloto OKX — relatório {dia}: {len(hoje)} operações reais fechadas"
                + (f" ({sum(o['r'] for o in hoje):+.2f}R)" if hoje else "") + f"; {len(perd)} sinais perdidos; "
                + (f"{len(aprovadas)} estratégias aprovadas" if aprovadas else "nenhuma estratégia aprovada")
                + ("; portas fechadas: " + ", ".join(fech) if fech else "; todas as portas abertas")
                + (" ; BLOQUEADO" if st["bloqueio"] else " ; SUSPENSO" if st["suspenso"] else "") + ".")


def desempenho(st):
    """Metricas reais por estrategia (sem valores monetarios): sinais vistos, executaveis, operacoes, acerto,
    expectativa, PF, drawdown em R, deslize, duracao, por moeda/regime/timeframe, recente (ultimas 10)."""
    out = {}
    for o in st["ops"]:
        d = out.setdefault(o.get("estrategia"), {"ops": []})
        d["ops"].append(o)
    for sid in st.get("sinais_perdidos") or []:
        k = str(sid.get("sinal", "")).split("|")[0]
        out.setdefault(k, {"ops": []}).setdefault("perdidos", 0)
        out[k]["perdidos"] += 1
    res = {}
    for k, d in out.items():
        fe = [o for o in d["ops"] if o.get("r") is not None]
        rs = [o["r"] for o in fe]
        g, p = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
        eq = pk = dd = 0.0
        for x in rs:
            eq += x
            pk, dd = max(pk, eq), max(dd, pk - eq)
        grp = lambda c: {v: round(sum(o["r"] for o in fe if o.get(c) == v), 3) for v in {o.get(c) for o in fe}}
        med = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
        res[k] = {"sinais_perdidos": d.get("perdidos", 0), "ordens": len([o for o in d["ops"] if o.get("ordId")]),
                  "fechadas": len(fe), "acerto": med([1.0 if x > 0 else 0.0 for x in rs]), "r_medio": med(rs),
                  "profit_factor": round(g / p, 3) if p else None, "drawdown_r": round(dd, 3),
                  "deslize_medio_pct": med([o["slippage_pct"] for o in d["ops"] if o.get("slippage_pct") is not None]),
                  "duracao_media_h": med([o["duracao_h"] for o in fe if o.get("duracao_h") is not None]),
                  "por_moeda": grp("base"), "por_regime": grp("regime"), "por_tf": grp("tf"), "recente_r": med(rs[-10:])}
    return res


def publico(st, c, aprovadas, now):
    """Resumo SEM valores monetarios (repositorio publico): estados, precos, R, motivos."""
    campos = ("id", "estrategia", "versao", "base", "inst", "lado", "tf", "regime", "t_sinal", "t_ordem", "t_execucao", "t_fecho",
              "preco_previsto", "preco_efetivo", "slippage_pct", "stop", "alvo", "preco_saida", "alav", "estado", "stop_confirmado",
              "motivo_saida", "r", "r_papel", "duracao_h", "spread_pct")
    oper = all(v["ok"] for k, v in st["portas"].items() if k != "estrategias_elegiveis")
    return {"t": now, "aviso": "REAL (piloto OKX). Sem valores monetarios neste ficheiro.", "simulacao": st.get("simulacao"),
            "operacional": oper, "ativas": sorted(aprovadas) if oper else [],
            "estados": {k: v.get("estado") for k, v in aprovadas.items()},
            "recusadas": st.get("recusadas_pelo_executor"),
            "desempenho": desempenho(st),
            "limites": {k: c[k] for k in ("alav_min", "alav_max", "posicoes_max", "margem", "lados")},
            "portas": {k: {"ok": v["ok"], "detalhe": v["detalhe"] if k not in ("saldo_usdc",) else ("ok" if v["ok"] else "insuficiente")}
                       for k, v in st["portas"].items()},
            "bloqueado": bool(st["bloqueio"]), "suspenso": bool(st["suspenso"]),
            "motivo": (st["bloqueio"] or st["suspenso"] or {}).get("motivo"),
            "ops": [{k: o.get(k) for k in campos} for o in st["ops"][-200:]],
            "sinais_perdidos": st["sinais_perdidos"][-50:],
            "eventos": [{k: v for k, v in e.items() if k in ("t", "txt", "op", "motivo", "r", "portas", "sinal", "inst", "motivos")}
                        for e in st["eventos"][-50:]]}


# ------------------------------------------------------------------ verificacao da conta (so leitura) --------------
def verificar(api, c):
    """So pedidos GET. Devolve factos sem valores monetarios (o log do GitHub e publico)."""
    out = {}
    conf = api.priv("GET", "/api/v5/account/config")
    row = ((conf or {}).get("data") or [{}])[0] if (conf or {}).get("code") == "0" else {}
    out["consulta_conta"] = (conf or {}).get("code") == "0"
    out["settlement"] = str(row.get("settleCcy") or "desconhecido")
    out["settlement_usdc"] = DERIV.validate_okx_account_config(conf)[0]
    out["modo_posicao"] = row.get("posMode")
    out["nivel_conta"] = row.get("acctLv")
    perm = str(row.get("perm") or "")
    out["permissoes"] = perm or "desconhecidas"
    out["sem_levantamentos"] = bool(perm) and "withdraw" not in perm
    bal = api.priv("GET", "/api/v5/account/balance?ccy=USDC")
    try:
        disp = float(((bal.get("data") or [{}])[0].get("details") or [{}])[0].get("availBal") or 0)
    except (TypeError, ValueError, IndexError, AttributeError):
        disp = None
    margem = c["nocional_max"] / c["alav_min"]
    out["saldo_usdc_lido"] = disp is not None and (bal or {}).get("code") == "0"
    out["saldo_cobre_margem_a_5x"] = bool(disp is not None and disp >= margem)
    out["saldo_cobre_capital_maximo"] = bool(disp is not None and disp >= c["capital_max"])
    out["margem_necessaria_usdc_nocional_maximo"] = {"5x": round(c["nocional_max"] / 5, 2), "10x": round(c["nocional_max"] / 10, 2)}
    xp = instrumentos(api)
    out["instrumentos_negociaveis"] = len(xp)
    lev = [float(i.get("lever") or 0) for i in xp.values()]
    out["instrumentos_com_5x"] = sum(1 for x in lev if x >= 5)
    out["instrumentos_com_10x"] = sum(1 for x in lev if x >= 10)
    tick = {t["instId"]: t for t in api.pub("/api/v5/market/tickers", {"instType": "FUTURES"}) or []}
    cabe = 0
    for iid, i in xp.items():
        px = float((tick.get(iid) or {}).get("last") or 0)
        if px:
            n1 = float(i["ctVal"]) * float(i.get("ctMult") or 1) * (px if (i.get("ctValCcy") or "").upper() not in ("USD", "USDC") else 1)
            cabe += n1 * float(i["minSz"]) <= c["nocional_max"]
    out["instrumentos_com_minimo_dentro_do_nocional"] = cabe
    lv = api.priv("GET", "/api/v5/account/leverage-info?instId=" + (next(iter(xp), "BTC-USD_UM_XPERP")) + "&mgnMode=isolated")
    out["leitura_alavancagem"] = (lv or {}).get("code") == "0"
    # como a OKX representa a origem (isolamento): os campos existem nas respostas?
    fl = api.priv("GET", "/api/v5/trade/fills-history?instType=FUTURES&limit=5")
    out["fills_trazem_clOrdId"] = ((fl or {}).get("code") == "0", all("clOrdId" in x for x in (fl or {}).get("data") or []),
                                  len((fl or {}).get("data") or []))
    al = api.priv("GET", "/api/v5/trade/orders-algo-history?ordType=oco&state=effective&limit=5")
    out["algos_trazem_algoClOrdId"] = ((al or {}).get("code") == "0", all("algoClOrdId" in x for x in (al or {}).get("data") or []),
                                      len((al or {}).get("data") or []))
    out["isolamento_okx_exec"] = _okx_exec_isolado()
    out["ok"] = all([out["consulta_conta"], out["settlement_usdc"], out["sem_levantamentos"], out["modo_posicao"] == "net_mode",
                     out["saldo_usdc_lido"], out["saldo_cobre_margem_a_5x"], out["instrumentos_com_5x"] > 0,
                     out["isolamento_okx_exec"]])
    return out


# ------------------------------------------------------------------ main ------------------------------------------
class ApiReal:
    def __init__(self):
        import okx_exec as E
        import okx_agente as A
        self._priv, self._pub = E.privado, A.get

    def priv(self, metodo, path, corpo=None):
        return self._priv(metodo, path, corpo)

    def pub(self, path, params=None):
        import urllib.parse
        return self._pub(path + ("?" + urllib.parse.urlencode(params) if params else ""))


def _ler(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    pasta = sys.argv[1]
    if "--verificar" in sys.argv:
        r = verificar(ApiReal(), cfg())
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0)
    simular = "--simular" in sys.argv
    try:
        from engine import alerts
        enviar = alerts.send
    except Exception:
        enviar = lambda m: None
    st, msgs = ciclo(ApiReal(), pasta, simular=simular, registo=_ler(os.path.join(pasta, "estrategias_registo.json")),
                     papel=_ler(os.path.join(pasta, "papel_estado.json")), enviar=enviar,
                     copy=_ler(os.path.join(pasta, "copy_sinais.json")))
    print(json.dumps({"portas": {k: v["ok"] for k, v in st["portas"].items()}, "aberta": bool(st["aberta"]),
                      "bloqueado": bool(st["bloqueio"]), "suspenso": bool(st["suspenso"]), "ops": len(st["ops"]),
                      "simulacao": st["simulacao"], "sinais_perdidos_volta": sum(1 for s in st["sinais_perdidos"] if s["t"] == st["t"])},
                     ensure_ascii=False))
