"""(05/11, preparacao isolada; NAO LIGADO a nenhum circuito) Base comum para varias estrategias independentes.

So funcoes puras: nao fala com corretoras, nao envia ordens, nao le chaves. Cada circuito (Bybit: engine/executor;
OKX: tools/okx_exec) continua independente e, quando o Rui autorizar, passa a chamar estas funcoes ANTES de cada ordem.

Regras:
- Registo por corretora: cada estrategia tem estado (investigacao / papel / real / suspensa), interruptor real explicito
  (ausente = papel), fracao do capital, risco por operacao, maximo de posicoes, exposicao bruta e alavancagem maxima.
- Etiqueta: cada ordem leva o codigo da estrategia no id do cliente (clOrdId/orderLinkId), para saber de quem e cada posicao.
- Bloqueio por instrumento: uma estrategia por instrumento de cada vez (a OKX esta em net_mode: duas estrategias na mesma
  moeda anular-se-iam).
- Tamanho pelo risco: nocional = risco x capital / distancia do stop. A alavancagem EFETIVA e a minima que a margem
  disponivel exige, com teto de 10x (ou menos, por estrategia/contrato). Nunca se usa alavancagem so porque existe.
- Tetos globais por corretora: exposicao bruta total e risco aberto total.
- Stop obrigatorio: nenhuma ordem real sem stop; cada volta confere que cada posicao real tem stop na corretora.
- Monitorizacao: sinal de vida, posicoes sem dono, stops em falta, degradacao face ao backtest (alerta e proposta, nunca
  desliga sozinho)."""
import math
import re

ESTADOS = ("investigacao", "papel", "real", "suspensa")
ALAV_TETO = 10.0
CODIGO = re.compile(r"^[a-z0-9]{2,6}$")


# ---------- registo ----------
def valida_registo(reg):
    """Lista de erros do registo {"corretora", "tetos": {...}, "estrategias": {codigo: {...}}}; vazia = valido."""
    erros = []
    t = reg.get("tetos") or {}
    for k in ("bruta_max", "risco_aberto_max"):
        if not isinstance(t.get(k), (int, float)) or t[k] <= 0:
            erros.append(f"tetos.{k} em falta ou invalido")
    soma = 0.0
    for cod, e in (reg.get("estrategias") or {}).items():
        if not CODIGO.match(cod):
            erros.append(f"{cod}: codigo invalido (2-6 letras minusculas/digitos)")
        if e.get("estado") not in ESTADOS:
            erros.append(f"{cod}: estado invalido")
        if e.get("estado") == "real" and e.get("real") is not True:
            erros.append(f"{cod}: estado real sem interruptor real explicito")
        if not 0 < float(e.get("risco_pct") or 0) <= 3:
            erros.append(f"{cod}: risco_pct fora de ]0, 3]")
        if float(e.get("alav_max") or 1) > ALAV_TETO:
            erros.append(f"{cod}: alav_max acima de {ALAV_TETO:g}x")
        soma += float(e.get("fracao") or 0) if e.get("estado") == "real" else 0
    if soma > 1 + 1e-9:
        erros.append(f"fracoes das estrategias reais somam {soma:.2f} > 1")
    return erros


def e_real(reg, cod):
    e = (reg.get("estrategias") or {}).get(cod) or {}
    return e.get("estado") == "real" and e.get("real") is True


# ---------- etiquetas ----------
def etiqueta(cod, seq, t):
    """Id do cliente para a ordem: <codigo>x<t36><seq36>, so alfanumerico, <= 32 caracteres (OKX e Bybit aceitam)."""
    if not CODIGO.match(cod):
        raise ValueError("codigo de estrategia invalido")
    b36 = lambda n: (lambda s: s or "0")("".join("0123456789abcdefghijklmnopqrstuvwxyz"[n // 36 ** k % 36] for k in range(8, -1, -1)).lstrip("0"))
    return f"{cod}x{b36(int(t))}{b36(int(seq))}"[:32]


def dono(cl_id):
    """Codigo da estrategia a partir do id do cliente, ou None (posicao sem dono = alerta)."""
    m = re.match(r"^([a-z0-9]{2,6})x[0-9a-z]+$", cl_id or "")
    return m.group(1) if m else None


# ---------- bloqueio por instrumento ----------
def pode_abrir(posicoes, inst, cod):
    """posicoes: {inst: codigo_dono}. Bloqueia se outra estrategia ja tem o instrumento (ou se o dono e desconhecido)."""
    atual = posicoes.get(inst)
    if atual is None:
        return True, ""
    if atual == cod:
        return False, "a estrategia ja tem posicao neste instrumento"
    return False, f"instrumento bloqueado pela estrategia {atual}"


# ---------- tamanho pelo risco ----------
def tamanho(capital, risco_pct, entrada, stop, info, alav_max_estr=ALAV_TETO, alav_max_contrato=ALAV_TETO, margem_livre=None):
    """Devolve dict com contratos, nocional, risco efetivo, alavancagem efetiva e se cabe.
    info: ctVal, minSz, lotSz. A alavancagem efetiva e a menor inteira que cabe na margem livre (por omissao o capital)."""
    dist = abs(entrada - stop) / entrada
    if dist <= 0 or capital <= 0:
        return {"cabe": False, "motivo": "stop ou capital invalido"}
    nominal = risco_pct / 100 * capital / dist
    teto = min(ALAV_TETO, float(alav_max_estr), float(alav_max_contrato))
    livre = capital if margem_livre is None else margem_livre
    nominal = min(nominal, teto * livre)                       # nunca acima do teto de alavancagem
    ct, lote, mn = info["ctVal"], info.get("lotSz") or info["minSz"], info["minSz"]
    n = math.floor(nominal / (ct * entrada) / lote + 1e-9) * lote
    nom = n * ct * entrada
    if n < mn or n <= 0:
        return {"cabe": False, "motivo": "abaixo do minimo do contrato", "nocional_alvo": round(nominal, 4), "minimo": round(mn * ct * entrada, 4)}
    alav = max(1, math.ceil(nom / livre - 1e-9))
    if alav > teto:
        return {"cabe": False, "motivo": "exigiria alavancagem acima do teto"}
    return {"cabe": True, "contratos": n, "nocional": round(nom, 4), "risco_usd": round(nom * dist, 4),
            "risco_pct_efetivo": round(100 * nom * dist / capital, 3), "alav": alav}


# ---------- tetos globais ----------
def cabe_nos_tetos(abertas, nova, capital, tetos, estrategia):
    """abertas: [{"cod","nocional","risco_usd"}]; nova: idem. Verifica tetos da estrategia e da corretora."""
    mesmas = [x for x in abertas if x["cod"] == nova["cod"]]
    if len(mesmas) >= int(estrategia.get("max_pos") or 1):
        return False, "maximo de posicoes da estrategia"
    cap_e = capital * float(estrategia.get("fracao") or 1)
    if sum(x["nocional"] for x in mesmas) + nova["nocional"] > float(estrategia.get("bruta_max") or 1) * cap_e + 1e-9:
        return False, "exposicao bruta da estrategia"
    if sum(x["nocional"] for x in abertas) + nova["nocional"] > tetos["bruta_max"] * capital + 1e-9:
        return False, "exposicao bruta total da corretora"
    if sum(x["risco_usd"] for x in abertas) + nova["risco_usd"] > tetos["risco_aberto_max"] / 100 * capital + 1e-9:
        return False, "risco aberto total da corretora"
    return True, ""


# ---------- stops obrigatorios ----------
def ordem_valida(ordem):
    """Uma ordem real tem de levar stop do lado certo e etiqueta de estrategia."""
    if not dono(ordem.get("cl_id")):
        return False, "sem etiqueta de estrategia"
    st, px, lado = ordem.get("stop"), ordem.get("px"), ordem.get("lado")
    if not st or not px:
        return False, "sem stop"
    if (lado == "long" and st >= px) or (lado == "short" and st <= px):
        return False, "stop do lado errado"
    return True, ""


def stops_em_falta(posicoes, protecoes):
    """posicoes: {inst: ...}; protecoes: {inst: [stops ativos]}. Instrumentos com posicao real sem stop na corretora."""
    return sorted(i for i in posicoes if not protecoes.get(i))


# ---------- monitorizacao ----------
def saude(agora, ultima_volta, posicoes_corretora, donos, max_atraso_s=3 * 3600):
    """Alertas operacionais: volta atrasada, posicoes sem dono, donos sem posicao (estado dessincronizado)."""
    al = []
    if not ultima_volta or agora - ultima_volta > max_atraso_s:
        al.append("volta atrasada: o circuito nao corre ha mais de %d h" % (max_atraso_s // 3600))
    for i in sorted(set(posicoes_corretora) - set(donos)):
        al.append(f"posicao sem dono na corretora: {i}")
    for i in sorted(set(donos) - set(posicoes_corretora)):
        al.append(f"estado diz que {donos[i]} tem {i}, mas a corretora nao tem a posicao")
    return al


def degradacao(rs, ref_r_min, ref_queda_max, n_min=20):
    """rs: R das operacoes reais/papel por ordem. Alerta (texto) se, com >= n_min, o R medio dos ultimos n_min fica abaixo
    do limite inferior do backtest, ou a queda acumulada em R passa 1,5x a maxima do backtest. None se esta tudo bem."""
    if len(rs) < n_min:
        return None
    ult = rs[-n_min:]
    m = sum(ult) / len(ult)
    eq, pk, q = 0.0, 0.0, 0.0
    for r in rs:
        eq += r; pk = max(pk, eq); q = max(q, pk - eq)
    if m < ref_r_min:
        return f"R medio das ultimas {n_min} = {m:+.2f} abaixo do limite do backtest ({ref_r_min:+.2f}): proposta de suspensao"
    if q > 1.5 * ref_queda_max:
        return f"queda de {q:.1f}R acima de 1,5x a maxima do backtest ({ref_queda_max:.1f}R): proposta de suspensao"
    return None


# ---------- (05/11) ordens antigas sem etiqueta ----------
def dono_legado(corretora, cl_id, estrategia_estado=None):
    """Dono das ordens criadas ANTES das etiquetas (o prefixo "cs" nao diz a estrategia).
    OKX: clOrdId "cs<MOEDA><t>": H46 se o estado do agente a marcou como "recuo", senao H40 (pânico).
    Bybit: orderLinkId "cs-nb..." = tendencia BTC (nucleo); "cs-P-"/"cs-PANICO" = H45; "cs-d..." = ordem de diagnostico;
    outro "cs-..." = estrategias do scanner. Desconhecido -> None (alerta de posicao sem dono, nunca adivinha)."""
    cl = cl_id or ""
    novo = dono(cl)
    if novo:
        return novo
    if corretora == "okx" and cl.startswith("cs") and len(cl) > 2:
        return "h46" if estrategia_estado == "recuo" else "h40"
    if corretora == "bybit" and cl.startswith("cs-"):
        r = cl[3:]
        if r.startswith("nb"):
            return "btc"
        if r.startswith("P-") or r.startswith("PANICO"):
            return "h45"
        if r.startswith("d"):
            return "diag"
        return "scan"
    return None


# ---------- (05/11) tendencia BTC: saida pela regra diaria em vez de stop ----------
def ordem_valida_estrategia(ordem, estrategia):
    """Como ordem_valida, mas aceita SEM stop uma estrategia registada com saida "regra_diaria" se for compra a vista
    sem emprestimo (alav 1): e o caso da tendencia BTC (sai no fecho diario abaixo da media; nao ha liquidacao porque
    nao ha divida). Com alavancagem > 1 o stop volta a ser obrigatorio."""
    if (estrategia or {}).get("saida") == "regra_diaria":
        if not dono(ordem.get("cl_id")) and not dono_legado("bybit", ordem.get("cl_id")):
            return False, "sem etiqueta de estrategia"
        if ordem.get("lado") != "long" or float(ordem.get("alav") or 1) > 1 or ordem.get("emprestimo"):
            return False, "saida pela regra diaria so a vista, long e sem emprestimo"
        return True, ""
    return ordem_valida(ordem)


# ---------- (05/11) Bybit: tamanho a vista ----------
def tamanho_avista(capital, preco, base_step, min_usdc, risco_pct=None, stop=None, fracao=None, alav_max_estr=1.0):
    """Bybit a vista/margem: quantidade em moeda base arredondada para baixo ao passo, com ordem minima em USDC.
    Pelo risco (risco_pct + stop) ou por fracao do capital (tendencia BTC). Alavancagem efetiva minima, teto da estrategia."""
    if capital <= 0 or preco <= 0:
        return {"cabe": False, "motivo": "capital ou preco invalido"}
    if fracao is not None:
        nominal = capital * float(fracao)
    else:
        dist = abs(preco - stop) / preco if stop else 0
        if dist <= 0:
            return {"cabe": False, "motivo": "stop invalido"}
        nominal = risco_pct / 100 * capital / dist
    teto = min(ALAV_TETO, float(alav_max_estr))
    nominal = min(nominal, teto * capital)
    q = math.floor(nominal / preco / base_step + 1e-9) * base_step
    nom = q * preco
    if nom < min_usdc or q <= 0:
        return {"cabe": False, "motivo": "abaixo da ordem minima", "nocional_alvo": round(nominal, 4)}
    alav = max(1, math.ceil(nom / capital - 1e-9))
    return {"cabe": True, "qty": q, "nocional": round(nom, 4), "alav": alav, "emprestimo": alav > 1}


# ---------- (05/11) registos derivados da configuracao atual (nao mudam o comportamento) ----------
def registo_okx(cfg):
    """Registo da OKX a partir do okx_config.json: os tetos sao EXATAMENTE os limites que o okx_exec ja aplica
    (max_posicoes, risco por operacao, alavancagem), para nao mudar a H46 nem a H40 por acidente."""
    n, alav = int(cfg.get("max_posicoes") or 1), float(cfg.get("alavancagem") or 1)
    rmax = max(float(cfg.get("risco_pct") or 1), float(cfg.get("recuo_risco_pct") or 1))
    return {"corretora": "okx",
            "tetos": {"bruta_max": alav, "risco_aberto_max": round(n * rmax, 4)},
            "estrategias": {
                "h46": {"estado": "real" if cfg.get("recuo_real") else "papel", "real": bool(cfg.get("recuo_real")),
                        "fracao": 1.0, "risco_pct": float(cfg.get("recuo_risco_pct") or 1), "max_pos": n, "bruta_max": alav, "alav_max": alav},
                "h40": {"estado": "real" if cfg.get("panico_real") else "papel", "real": bool(cfg.get("panico_real")),
                        "fracao": 1.0 if not cfg.get("recuo_real") else 0.0, "risco_pct": float(cfg.get("risco_pct") or 1),
                        "max_pos": n, "bruta_max": alav, "alav_max": alav}}}


def registo_bybit(cfg):
    """Registo da Bybit a partir do config.json: a tendencia BTC (nucleo) com saida pela regra diaria."""
    alav = float(cfg.get("nucleo_alavancagem") or 1)
    real = bool(cfg.get("nucleo_ligado"))
    return {"corretora": "bybit",
            "tetos": {"bruta_max": max(1.0, alav), "risco_aberto_max": 100.0},
            "estrategias": {"btc": {"estado": "real" if real else "papel", "real": real, "fracao": float(cfg.get("nucleo_fracao") or 1),
                                    "risco_pct": 3.0, "max_pos": len(cfg.get("nucleo_moedas") or ["BTC"]), "bruta_max": max(1.0, alav),
                                    "alav_max": alav, "saida": "regra_diaria", "dias": int(cfg.get("nucleo_dias") or 200)}}}
