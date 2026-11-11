"""Registo central e imutavel das hipoteses da investigacao (auditoria de
2026-11-11, so investigacao; nao mexe em engine/ nem na producao).

Porque existe: ate aqui o numero de hipoteses vivia em frases do diario
(engine/hipoteses.py le-o com expressoes regulares sobre o texto), as fichas
nao tinham campos obrigatorios, nada impedia uma hipotese de ser validada com
os mesmos dados com que foi desenhada, e uma linha apagada do diario
desaparecia sem rasto.

Ficheiro: backtest/registo/hipoteses.jsonl, uma linha JSON por acontecimento,
so acrescentar. Cada linha leva o hash SHA-256 da anterior ("prev") e o seu
("hash"), por isso apagar ou mudar uma linha antiga parte a cadeia
(verificar) e encurtar o ficheiro e detetado contra o git (verificar_prefixo).

Tipos de linha:
  retroativo   hipotese testada antes deste registo (semente, com origem)
  pre_registo  ficha completa ANTES de qualquer resultado (FICHA_CAMPOS)
  uso_dados    uma hipotese consumiu uma janela de dados (desenho/reserva)
  resultado    resultado da validacao declarada na ficha
  nota         correccao ou anotacao (nunca apaga nada)

Regras que o codigo faz cumprir:
  1. uma ficha so entra com todos os campos e uma familia conhecida;
  2. a validacao nao pode sobrepor-se aos dados de exploracao da propria ficha;
  3. validacao "prospetiva": so dados com data POSTERIOR ao pre-registo;
  4. validacao "reserva": cada hipotese usa uma reserva uma unica vez; se a
     janela ja foi vista por outra hipotese (exploracao, desenho ou reserva)
     o veredicto maximo e EXPLORATORIA, nunca CANDIDATA;
  5. um resultado so entra depois do pre-registo, com a metrica primaria e os
     criterios de rejeicao que la estao (nao se trocam depois de ver);
  6. nenhuma descoberta se diz confirmada com dados vistos (veredicto_maximo).

Uso:
  python -m tools.registo_hipoteses verificar [--contra REF]
  python -m tools.registo_hipoteses resumo
  python -m tools.registo_hipoteses pre-registar ficha.json
  python -m tools.registo_hipoteses resultado resultado.json
"""
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHEIRO = os.path.join(RAIZ, "backtest", "registo", "hipoteses.jsonl")
REL = "backtest/registo/hipoteses.jsonl"

FAMILIAS = {
    "A": "momento e continuacao",
    "B": "reversao a media",
    "C": "fraqueza estrutural e shorts",
    "D": "quebras e expansao de volatilidade",
    "E": "transicoes de regime e filtros de mercado",
    "F": "sazonalidade intradiaria e de calendario",
    "G": "microestrutura, liquidez e fluxo",
    "H": "combinacoes de varias temporalidades",
    "I": "fontes novas (derivados, OI, liquidacoes, modelos)",
    "X": "gestao/saidas/carteira (nao e ideia de entrada)",
}
TIPOS = ("retroativo", "pre_registo", "uso_dados", "resultado", "nota")
FICHA_CAMPOS = ("id", "familia", "justificacao", "fonte_dados", "universo", "direcao",
                "temporalidade", "entrada", "saida", "custos", "h0", "metrica_primaria",
                "criterios_rejeicao", "protocolo", "exploracao", "validacao", "grelha")
DIRECOES = ("LONG", "SHORT", "AMBOS")
VEREDICTOS = ("REJEITADA", "NAO VALIDADA", "AMOSTRA INSUFICIENTE", "EXPLORATORIA",
              "PARA PAPEL", "CANDIDATA")
POSITIVOS = ("EXPLORATORIA", "PARA PAPEL", "CANDIDATA")      # por ordem crescente
MAX_GRELHA = 6
CUSTO_MIN_LADO = 0.35          # % por lado: 0,25% comissao Bybit UE + 0,1% deslize


class RegistoErro(ValueError):
    pass


# ---------- datas ----------

def agora_iso():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _data(s):
    """'AAAA-MM-DD' ou ISO completo -> datetime UTC."""
    if isinstance(s, (int, float)):
        return _dt.datetime.fromtimestamp(s, _dt.timezone.utc)
    s = str(s)
    if len(s) == 10:
        s += "T00:00:00Z"
    return _dt.datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt.timezone.utc)


def _janela(j):
    if not j or "inicio" not in j:
        raise RegistoErro("janela sem inicio")
    a = _data(j["inicio"])
    b = _data(j["fim"]) if j.get("fim") else _dt.datetime.max.replace(tzinfo=_dt.timezone.utc)
    if b <= a:
        raise RegistoErro(f"janela invertida: {j}")
    return a, b


def sobrepoe(j1, j2):
    a1, b1 = _janela(j1)
    a2, b2 = _janela(j2)
    return a1 < b2 and a2 < b1


# ---------- cadeia ----------

def _canon(rec):
    return json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":"))


def _hash(rec):
    return hashlib.sha256(_canon(rec).encode("utf-8")).hexdigest()


def ler(caminho=FICHEIRO):
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def verificar(linhas):
    """Lista de problemas da cadeia (vazia = integra)."""
    prob, prev = [], None
    for i, r in enumerate(linhas):
        if r.get("seq") != i:
            prob.append(f"linha {i}: seq {r.get('seq')} fora de ordem")
        if r.get("prev") != prev:
            prob.append(f"linha {i}: prev nao bate com a linha anterior (apagada ou alterada?)")
        if r.get("hash") != _hash(r):
            prob.append(f"linha {i}: hash nao bate (conteudo alterado)")
        if r.get("tipo") not in TIPOS:
            prob.append(f"linha {i}: tipo desconhecido {r.get('tipo')}")
        prev = r.get("hash")
    return prob


def verificar_prefixo(antigas, novas):
    """O registo novo tem de comecar exatamente pelo antigo (so acrescentar)."""
    if len(novas) < len(antigas):
        return [f"registo encurtou de {len(antigas)} para {len(novas)} linhas"]
    return [f"linha {i} mudou" for i, (a, b) in enumerate(zip(antigas, novas))
            if a.get("hash") != b.get("hash")]


def linhas_git(ref, rel=REL):
    try:
        txt = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=RAIZ, capture_output=True,
                             text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    return [json.loads(l) for l in txt.splitlines() if l.strip()]


def acrescentar(linhas, tipo, id_, dados, quando=None):
    """Nova linha encadeada (nao grava; ver gravar)."""
    if tipo not in TIPOS:
        raise RegistoErro(f"tipo desconhecido: {tipo}")
    rec = {"seq": len(linhas), "tipo": tipo, "id": id_, "quando": quando or agora_iso(),
           "dados": dados, "prev": linhas[-1]["hash"] if linhas else None}
    rec["hash"] = _hash(rec)
    linhas.append(rec)
    return rec


def gravar(linhas, caminho=FICHEIRO):
    """Grava acrescentando so as linhas novas; recusa se o ficheiro no disco
    nao for prefixo das linhas em memoria."""
    no_disco = ler(caminho)
    p = verificar_prefixo(no_disco, linhas) + verificar(linhas)
    if p:
        raise RegistoErro("; ".join(p))
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:
        for r in linhas[len(no_disco):]:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


# ---------- fichas ----------

def validar_ficha(f, quando):
    falta = [c for c in FICHA_CAMPOS if f.get(c) in (None, "", [], {})]
    if falta:
        raise RegistoErro("ficha incompleta, faltam: " + ", ".join(falta))
    if f["familia"] not in FAMILIAS:
        raise RegistoErro(f"familia desconhecida: {f['familia']}")
    if f["direcao"] not in DIRECOES:
        raise RegistoErro(f"direcao invalida: {f['direcao']}")
    if not isinstance(f["grelha"], list) or not 1 <= len(f["grelha"]) <= MAX_GRELHA:
        raise RegistoErro(f"grelha tem de ter 1 a {MAX_GRELHA} configuracoes")
    c = f["custos"]
    if not isinstance(c, dict) or float(c.get("por_lado_pct", 0)) < CUSTO_MIN_LADO:
        raise RegistoErro(f"custos por lado abaixo de {CUSTO_MIN_LADO}% (comissao real + deslize)")
    if not isinstance(f["criterios_rejeicao"], list):
        raise RegistoErro("criterios_rejeicao tem de ser uma lista")
    v, e = f["validacao"], f["exploracao"]
    if v.get("tipo") not in ("prospetiva", "reserva"):
        raise RegistoErro("validacao.tipo tem de ser 'prospetiva' ou 'reserva'")
    _janela(e)
    _janela(v)
    if sobrepoe(e, v):
        raise RegistoErro("a validacao sobrepoe-se aos dados de exploracao da propria ficha")
    if v["tipo"] == "prospetiva" and _data(v["inicio"]) < _data(quando):
        raise RegistoErro("validacao prospetiva tem de comecar depois do pre-registo")


def pre_registar(linhas, ficha, quando=None):
    quando = quando or agora_iso()
    if any(r["id"] == ficha.get("id") and r["tipo"] in ("pre_registo", "retroativo") for r in linhas):
        raise RegistoErro(f"id repetido: {ficha.get('id')}")
    validar_ficha(ficha, quando)
    return acrescentar(linhas, "pre_registo", ficha["id"], ficha, quando)


def _ficha(linhas, id_):
    for r in linhas:
        if r["id"] == id_ and r["tipo"] == "pre_registo":
            return r
    return None


def janelas_vistas(linhas, ate_seq=None, excluir_id=None):
    """Janelas de dados ja vistas por OUTRAS hipoteses (exploracao, desenho,
    reserva usada, janelas declaradas dos retroativos)."""
    out = []
    for r in linhas[:ate_seq]:
        if r["id"] == excluir_id:
            continue
        d = r["dados"]
        if r["tipo"] == "pre_registo":
            out.append((r["id"], "exploracao", d["exploracao"]))
        elif r["tipo"] == "uso_dados":
            out.append((r["id"], d["papel"], d["janela"]))
        elif r["tipo"] == "retroativo" and d.get("janela"):
            out.append((r["id"], "retroativo", d["janela"]))
    return out


def contaminacao(linhas, janela, excluir_id=None):
    """Quem ja viu dados desta janela (lista de (id, papel))."""
    return [(i, p) for i, p, j in janelas_vistas(linhas, excluir_id=excluir_id) if sobrepoe(j, janela)]


def usar_dados(linhas, id_, papel, janela, quando=None):
    """Regista o consumo de uma janela. A reserva so uma vez por hipotese."""
    if papel not in ("desenho", "reserva", "prospetiva"):
        raise RegistoErro(f"papel invalido: {papel}")
    f = _ficha(linhas, id_)
    if not f:
        raise RegistoErro(f"{id_}: sem pre-registo; registe a ficha antes de usar dados")
    if papel == "reserva":
        for r in linhas:
            if r["id"] == id_ and r["tipo"] == "uso_dados" and r["dados"]["papel"] == "reserva":
                raise RegistoErro(f"{id_}: a reserva ja foi usada uma vez; nao se reavalia")
    if papel != "desenho" and sobrepoe(f["dados"]["exploracao"], janela):
        raise RegistoErro(f"{id_}: a janela de {papel} sobrepoe-se a exploracao da ficha")
    if papel == "prospetiva" and _data(janela["inicio"]) < _data(f["quando"]):
        raise RegistoErro(f"{id_}: dados prospetivos anteriores ao pre-registo")
    vistos = contaminacao(linhas, janela, excluir_id=id_) if papel == "reserva" else []
    return acrescentar(linhas, "uso_dados", id_, {"papel": papel, "janela": janela,
                                                    "ja_vista_por": len(vistos)}, quando)


def veredicto_maximo(linhas, id_):
    """O melhor veredicto que esta hipotese ainda pode receber."""
    f = _ficha(linhas, id_)
    if not f:
        return "EXPLORATORIA"
    usos = [r for r in linhas if r["id"] == id_ and r["tipo"] == "uso_dados"
            and r["dados"]["papel"] in ("reserva", "prospetiva")]
    if not usos:
        return "EXPLORATORIA"
    if any(r["dados"]["papel"] == "reserva" and r["dados"].get("ja_vista_por") for r in usos):
        return "PARA PAPEL"          # reserva ja vista por outras: no maximo vai para papel
    return "CANDIDATA"


def registar_resultado(linhas, id_, resultado, quando=None):
    """resultado: {metricas: {...}, veredicto, n_operacoes, n_acontecimentos, notas}."""
    f = _ficha(linhas, id_)
    if not f:
        raise RegistoErro(f"{id_}: resultado sem pre-registo")
    quando = quando or agora_iso()
    if _data(quando) <= _data(f["quando"]):
        raise RegistoErro(f"{id_}: resultado nao pode ser anterior ao pre-registo")
    mp = f["dados"]["metrica_primaria"]
    nome = mp["nome"] if isinstance(mp, dict) else mp
    if nome not in (resultado.get("metricas") or {}):
        raise RegistoErro(f"{id_}: falta a metrica primaria declarada ({nome})")
    v = resultado.get("veredicto")
    if v not in VEREDICTOS:
        raise RegistoErro(f"veredicto invalido: {v}")
    teto = veredicto_maximo(linhas, id_)
    if v in POSITIVOS and POSITIVOS.index(v) > POSITIVOS.index(teto):
        raise RegistoErro(f"{id_}: veredicto {v} acima do maximo permitido ({teto})")
    return acrescentar(linhas, "resultado", id_, dict(resultado, teto=teto), quando)


# ---------- resumo e contagem ----------

def resumo(linhas, janela=None):
    hip = {}
    for r in linhas:
        if r["tipo"] in ("retroativo", "pre_registo"):
            hip[r["id"]] = r
    fam = {}
    for i, r in hip.items():
        fam[r["dados"].get("familia", "?")] = fam.get(r["dados"].get("familia", "?"), 0) + 1
    configs = sum(int(r["dados"].get("configuracoes") or len(r["dados"].get("grelha") or []) or 1)
                  for r in hip.values())
    out = {"linhas": len(linhas), "hipoteses": len(hip), "configuracoes": configs,
           "por_familia": dict(sorted(fam.items())),
           "por_origem": {}, "pre_registadas": sum(1 for r in hip.values() if r["tipo"] == "pre_registo"),
           "integra": not verificar(linhas)}
    for r in hip.values():
        o = r["dados"].get("origem", "pre_registo")
        out["por_origem"][o] = out["por_origem"].get(o, 0) + 1
    if janela:
        out["viram_a_janela"] = len({i for i, _ in contaminacao(linhas, janela)})
    return out


# ---------- semente retroativa ----------

_REGRAS = [   # (expressao, familia) — a primeira que bate decide
    (r"KRONOS|\bML\b|H5-ML|FUNDING|FINANCIAMENTO|\bOI\b|OPEN INTEREST|H5[2-9]|LSR|LIQUIDA", "I"),
    (r"^SHORT|SHORT_| SHORT|SHORT |H36|H40-GATO|H44|H47|H48|ESPELHO", "C"),
    (r"HORAS|HORA |SAZONAL|SEMANA|FIM DE SEMANA", "F"),
    (r"1H|DAY TRADE|DIP_TREND|MULTITEMP|H24-1H", "H"),
    (r"FLUXO|ABSORC|COMPRADORES|SWEEP|LIQUIDITY|VOLUME|LIMITE|SPREAD", "G"),
    (r"BREAKOUT|BRK|SQUEEZE|COMPRESS|QUEBRA|TURTLE|TARTARUGA|RETESTE|ROMP|DON20|DON55", "D"),
    (r"NUCLEO|SMA200|REGIME|FASE|MACRO|VOL-TARGET|CONTA-TENDENCIA|TENDENCIA-MACRO|H39", "E"),
    (r"MOMENTUM|ROTACAO|TOP10|DUAL|FORCA|TENDENCIA|TREND|IMPULSO|ETH-BTC|FORTES", "A"),
    (r"BOUNCE|SOBREVENDA|OVERSOLD|DIP|RECUO|PULLBACK|CAPITUL|PANICO|REVERS|FIBO|RSI2|QUEDA|"
     r"RESILIENTE|ATRASO|INTERVALO|RACIO|AMPLITUDE|MR25|MR30", "B"),
    (r"SCORE|SAIDA|TP1|RAMIRO|CUSTO|RISCO|LIMITE-LUTADORES|UMA-CONTA|ENGOLFO|GATILHO", "X"),
]


# correccoes manuais onde as palavras enganam o classificador (revistas a mao)
SOBREPOR = {
    "OFF-H17a-REVERSAO-SEMANAL-COMPRA": "B", "OFF-H17b-REVERSAO-SEMANAL-SHORT": "C",
    "OFF-H23-L05-PANICO-LIMITE": "B", "OFF-H23-L10-PANICO-LIMITE": "B", "OFF-H43": "B",
    "OFF-H46": "B", "AFI-H15": "B", "INV-2026-10-15-ATRASO_BTC": "B",
    "INV-2026-10-16-RESILIENTE": "A", "ARENA-BOUNCE_SQUEEZE": "B",
    "OFF-H24-1D-FAMILIAS": "X", "OFF-H10-ESTRATEGIAS-POR-FASE": "E",
}


def classificar_familia(texto):
    t = (texto or "").upper()
    t = t.replace("Ã", "A").replace("Ç", "C").replace("É", "E").replace("Í", "I").replace("Ó", "O") \
        .replace("Á", "A").replace("Ú", "U").replace("Ê", "E").replace("Õ", "O")
    for rx, f in _REGRAS:
        if re.search(rx, t):
            return f
    return "X"


def semear(raiz=RAIZ, arena_classificacao=None, quando=None):
    """Linhas 'retroativo' para tudo o que ja foi testado, a partir dos
    diarios, dos estudos offline, das hipoteses de dados novos e da arena.
    Devolve lista de dicts (id, dados) pela ordem cronologica aproximada."""
    bt = os.path.join(raiz, "backtest")
    out = []
    inv = open(os.path.join(bt, "investigacao.md"), encoding="utf-8").read()
    for m in re.finditer(r"^## (\d{4}-\d{2}-\d{2}) — (.+)$", inv, re.M):
        dia, tit = m.group(1), m.group(2)
        if re.search(r"Sem hipótese|Pré-registo|Autópsia|Experiências|caçador noturno", tit):
            continue
        nome = tit.split(":")[0].strip() if ":" in tit and tit.split(":")[0].isupper() else tit
        out.append(("INV-" + dia + "-" + re.sub(r"[^A-Z0-9]+", "_", nome.upper())[:28].strip("_"),
                    {"origem": "investigacao", "data": dia, "titulo": tit, "familia": classificar_familia(tit),
                     "janela": {"inicio": _menos_meses(dia, 24), "fim": dia},
                     "conta_reserva": not tit.startswith("Kronos")}))
    afi = open(os.path.join(bt, "afinacao.md"), encoding="utf-8").read()
    for m in re.finditer(r"^### (\d{4}-\d{2}-\d{2}) — (H\d+): (.+)$", afi, re.M):
        dia, h, tit = m.groups()
        out.append(("AFI-" + h, {"origem": "afinacao", "data": dia, "titulo": tit,
                                 "familia": classificar_familia(tit),
                                 "janela": {"inicio": "2021-01-01", "fim": dia},
                                 "conta_reserva": h != "H14"}))
    off = json.load(open(os.path.join(bt, "hipoteses_offline.json"), encoding="utf-8"))
    for e in off.get("estudos") or []:
        tit = (e.get("pergunta") or "") + " " + e["id"]
        out.append(("OFF-" + e["id"], {"origem": "offline", "data": e.get("data") or "2026-10-21",
                                       "titulo": (e.get("pergunta") or e["id"])[:160],
                                       "resultado": (e.get("resultado") or "")[:200],
                                       "familia": classificar_familia(tit),
                                       "janela": {"inicio": "2021-01-01", "fim": e.get("data") or "2026-10-21"},
                                       "conta_reserva": True}))
    nov = json.load(open(os.path.join(bt, "hipoteses_novas.json"), encoding="utf-8"))
    for e in nov:
        dia = e["registada_em"][:10]
        out.append(("NOV-" + e["id"], {"origem": "dados_novos", "data": dia, "titulo": e.get("nome", "")[:160],
                                       "familia": classificar_familia(e.get("nome", "") + " " + e.get("lado", "")),
                                       "janela": {"inicio": e["registada_em"]},
                                       "conta_reserva": False, "prospetiva": True}))
    for c in arena_classificacao or []:
        nome = c.get("id") or c.get("nome")
        m = c.get("morte") or {}
        dia = _dt.datetime.fromtimestamp(m["t"], _dt.timezone.utc).strftime("%Y-%m-%d") if m.get("t") else None
        out.append(("ARENA-" + nome, {"origem": "arena", "data": dia, "titulo": nome, "estado": c.get("estado"),
                                      "familia": classificar_familia(nome),
                                      "janela": {"inicio": _menos_meses(dia or "2026-11-11", 3),
                                                 "fim": dia or "2026-11-11"},
                                      "motivo": (m.get("motivo") or "")[:120],
                                      "conta_reserva": True}))
    for i, d in out:
        if i in SOBREPOR:
            d["familia"] = SOBREPOR[i]
        if i.startswith("ARENA-") and i.endswith("_R2"):
            d["deriva_de"] = i[:-3]
    out.sort(key=lambda x: (x[1].get("data") or "9999", x[0]))
    return out


def _menos_meses(dia, n):
    d = _data(dia)
    y, mth = d.year, d.month - n
    while mth <= 0:
        mth += 12
        y -= 1
    return f"{y:04d}-{mth:02d}-{min(d.day, 28):02d}"


# ---------- CLI ----------

def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, linhas = argv[0], ler()
    if cmd == "verificar":
        p = verificar(linhas)
        if "--contra" in argv:
            ant = linhas_git(argv[argv.index("--contra") + 1])
            if ant is not None:
                p += verificar_prefixo(ant, linhas)
        print("REGISTO INTEGRO" if not p else "\n".join(p))
        return 0 if not p else 1
    if cmd == "semear":                 # so com o registo vazio (uma vez)
        if linhas:
            print("o registo ja tem linhas: a semente so se faz uma vez")
            return 1
        cl = []
        if len(argv) > 1:
            cl = (json.load(open(argv[1], encoding="utf-8")).get("arena") or {}).get("classificacao") or []
        q = agora_iso()
        for id_, d in semear(arena_classificacao=cl):
            acrescentar(linhas, "retroativo", id_, d, q)
        gravar(linhas)
        print(len(linhas), "linhas retroativas")
        return 0
    if cmd == "resumo":
        print(json.dumps(resumo(linhas), ensure_ascii=False, indent=1))
        return 0
    if cmd == "pre-registar":
        rec = pre_registar(linhas, json.load(open(argv[1], encoding="utf-8")))
        gravar(linhas)
        print("pre-registada", rec["id"], rec["hash"][:12])
        return 0
    if cmd == "resultado":
        d = json.load(open(argv[1], encoding="utf-8"))
        rec = registar_resultado(linhas, d.pop("id"), d)
        gravar(linhas)
        print("resultado", rec["id"], rec["dados"]["veredicto"], "teto", rec["dados"]["teto"])
        return 0
    print("comando desconhecido:", cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
