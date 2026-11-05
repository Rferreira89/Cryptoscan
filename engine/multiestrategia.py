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
