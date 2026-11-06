"""(06/11, P1, preparacao isolada; NAO LIGADO a nenhum workflow) TF-SHORT em MODO SOMBRA com o executor de short.

Liga: paper TF-SHORT (tools/okx_tfshort, conta executavel) -> regras da A1 (engine/multiestrategia: bloqueio por
instrumento, tamanho, tetos) -> executor de short (tools/okx_short) -> CorretoraSombra (simulacao em memoria, SEM rede)
-> registo unico (engine/registo, origem "sombra"). Nada sai para a OKX: o executor so aceita escritas na corretora
sombra (objeto-senha) e, para tudo o resto, continua bloqueado pelo interruptor absoluto SHORT_REAL_PERMITIDO = False.

Fail-closed (nenhuma ENTRADA nova; as posicoes abertas continuam geridas):
  - estado em falta (precisa de inicializacao explicita), ilegivel, adulterado ou de versao desconhecida;
  - falha de comunicacao ou recusa durante a volta;
  - precos desatualizados (o executor recusa o plano).
Parametros dos X-Perps por validar antes de qualquer uso real: ver VALIDAR."""
import hashlib
import json
import os

import okx_short as S
from engine import multiestrategia as M
from engine import registo as G

VERSAO = 1
CUSTO_LADO = 0.0005 + 0.0010 + 0.0002          # taxa + deslize + spread (igual ao paper TF-SHORT)
VALIDAR = {
    "ctVal / ctValCcy": "X-Perps 'USD_UM': confirmar se o contrato vale ctVal moedas ou ctVal USD (muda o tamanho)",
    "minSz / lotSz / tickSz": "por instrumento; a lista publica muda (ler sempre antes de planear)",
    "alavancagem maxima": "por escalao de posicao; set-leverage em margem isolada para FUTURES XPERP",
    "order-algo oco/conditional": "confirmar que existem para FUTURES XPERP na OKX EEA com reduceOnly em net_mode",
    "attachAlgoOrds": "alternativa a proteger depois do preenchimento (por confirmar no XPERP)",
    "clOrdId": "ate 32 alfanumericos; unicidade por conta (confirmar janela de unicidade)",
    "financiamento": "intervalo e calculo do X-Perp (o ensaio viu taxas repetidas: possivel taxa base fixa)",
    "limites de preco": "banda de preco por ordem (ordens a mercado podem ser recusadas em movimentos fortes)",
    "posSide": "net_mode: sem posSide; confirmar que um SELL sem posicao abre short e nao e recusado",
}


# ---------- corretora sombra (simulacao, sem rede) ----------
class CorretoraSombra:
    """Responde como a API v5 nos caminhos que o executor usa. Ordens a mercado enchem ao preco atual com deslize;
    algos (stop/objetivo) disparam com a maxima/minima da vela passada a mover()."""
    senha = S._SOMBRA

    def __init__(self, foto=None):
        f = foto or {}
        self.precos = dict(f.get("precos") or {})
        self.ordens = dict(f.get("ordens") or {})
        self.algos = dict(f.get("algos") or {})
        self.pos = dict(f.get("pos") or {})
        self.n = int(f.get("n") or 0)
        self.falhar = set()                      # caminhos que falham nesta volta (testes de comunicacao)

    def foto(self):
        return {"precos": self.precos, "ordens": self.ordens, "algos": self.algos, "pos": self.pos, "n": self.n}

    def _encher(self, inst, lado, sz, px):
        q = sz if lado == "sell" else -sz        # pos > 0 = short (em contratos)
        self.pos[inst] = round(self.pos.get(inst, 0.0) + q, 10)
        return px

    def mover(self, velas):
        """velas: {inst: {"h":, "l":, "c":}}. Dispara stops/objetivos das posicoes short."""
        for aid, a in list(self.algos.items()):
            v = velas.get(a["instId"])
            if not v or self.pos.get(a["instId"], 0) <= 0:
                continue
            sl, tp = float(a["slTriggerPx"]), float(a.get("tpTriggerPx") or 0)
            if v["h"] >= sl:
                px = sl * (1 + 0.001)
            elif tp and v["l"] <= tp:
                px = tp
            else:
                continue
            self._encher(a["instId"], "buy", float(a["sz"]), px)
            a.update(estado="disparado", px=px)
            self.ordens[f"algo{aid}"] = {"instId": a["instId"], "state": "filled", "accFillSz": a["sz"], "px": px, "lado": "buy"}
            del self.algos[aid]
            self.algos_disparados = getattr(self, "algos_disparados", []) + [(aid, px)]
        for inst, v in velas.items():
            self.precos[inst] = v["c"]

    def __call__(self, metodo, path, corpo=None):
        chave = path.split("?")[0]
        if chave in self.falhar:
            raise TimeoutError("sombra: falha de comunicacao simulada")
        if metodo == "POST" and chave == "/api/v5/account/set-leverage":
            return {"code": "0", "data": [{}]}
        if metodo == "POST" and chave == "/api/v5/trade/order":
            inst, sz = corpo["instId"], float(corpo["sz"])
            px0 = self.precos.get(inst)
            if not px0:
                return {"code": "51001", "msg": "sem preco na sombra", "data": []}
            px = px0 * (1 - 0.001) if corpo["side"] == "sell" else px0 * (1 + 0.001)
            if corpo.get("reduceOnly") == "true":
                sz = min(sz, abs(self.pos.get(inst, 0)))
            self.n += 1
            self._encher(inst, corpo["side"], sz, px)
            self.ordens[corpo["clOrdId"]] = {"instId": inst, "state": "filled", "accFillSz": str(sz), "px": px, "lado": corpo["side"]}
            return {"code": "0", "data": [{"ordId": str(self.n)}]}
        if metodo == "POST" and chave == "/api/v5/trade/order-algo":
            self.n += 1
            self.algos[str(self.n)] = dict(corpo, estado="ativo")
            return {"code": "0", "data": [{"algoId": str(self.n)}]}
        if metodo == "POST" and chave == "/api/v5/trade/cancel-algos":
            for a in corpo:
                self.algos.pop(a["algoId"], None)
            return {"code": "0", "data": []}
        if metodo == "POST" and chave == "/api/v5/trade/cancel-order":
            return {"code": "0", "data": []}
        if metodo == "GET" and chave == "/api/v5/trade/order":
            o = self.ordens.get(path.split("clOrdId=")[1])
            if not o:
                return {"code": "51603", "msg": "Order does not exist", "data": []}
            return {"code": "0", "data": [{"state": o["state"], "accFillSz": o["accFillSz"], "avgPx": str(o["px"])}]}
        return {"code": "51000", "msg": "caminho nao suportado na sombra", "data": []}


# ---------- estado persistente ----------
def _soma(conteudo):
    return hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def guardar(caminho, estado):
    """Escrita atomica (ficheiro temporario + rename) com versao e soma de controlo."""
    corpo = {"versao": VERSAO, "estado": estado, "soma": _soma(estado)}
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        json.dump(corpo, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def carregar(caminho, iniciar=False):
    """(estado, ok, motivo). ok=False -> nenhuma entrada nova nesta volta (fail-closed)."""
    if not os.path.exists(caminho):
        if iniciar:
            return {"ops": {}, "fechadas": [], "registo": [], "alertas": []}, True, "estado inicializado (autorizado)"
        return {"ops": {}, "fechadas": [], "registo": [], "alertas": []}, False, "estado inexistente: precisa de inicializacao autorizada"
    try:
        corpo = json.load(open(caminho))
    except Exception:
        return {"ops": {}, "fechadas": [], "registo": [], "alertas": []}, False, "estado ilegivel"
    if corpo.get("versao") != VERSAO:
        return corpo.get("estado") or {}, False, f"versao do estado desconhecida ({corpo.get('versao')})"
    est = corpo.get("estado") or {}
    if corpo.get("soma") != _soma(est):
        return est, False, "estado adulterado (soma de controlo nao confere)"
    return est, True, "ok"


# ---------- alertas ----------
def alerta(tipo, op=None, texto=""):
    m = (op or {}).get("moeda") or (op or {}).get("inst") or ""
    base = {"entrada": f"🟣 Sombra TF-SHORT — short em {m} a {(op or {}).get('px_fill', (op or {}).get('px'))}, stop {(op or {}).get('stop')}",
            "stop": f"🛑 Sombra TF-SHORT — {m}: stop atingido",
            "saida": f"✅ Sombra TF-SHORT — {m}: saída pela regra",
            "erro": f"⚠️ Sombra TF-SHORT — erro: {texto}",
            "reconciliacao": f"🔄 Sombra TF-SHORT — reconciliação: {texto}",
            "bloqueio": f"🔒 Sombra TF-SHORT — sem entradas novas: {texto}"}[tipo]
    return base if not texto or tipo in ("erro", "reconciliacao", "bloqueio") else f"{base} ({texto})"


# ---------- uma volta ----------
def registo_tfs(cfg_okx):
    """Registo da A1 (derivado do okx_config) com o TF-SHORT em 'papel' (sombra), teto de 0,5x e 5 posicoes."""
    r = M.registo_okx(cfg_okx)
    r["estrategias"]["tfs"] = {"estado": "papel", "fracao": 1.0, "risco_pct": 3.0, "max_pos": 5, "bruta_max": 0.5, "alav_max": 2}
    return r


def volta(tfs, estado, ok_estado, motivo_estado, cli, velas, infos, cfg_okx, capital, agora, cfg_exec=None, enviar=None):
    """Uma volta da sombra. tfs: estado do paper TF-SHORT; velas: {moeda: {"h","l","c","t"}} do X-Perp (vela fechada);
    infos: {moeda: {"inst", ctVal, minSz, lotSz}}. Devolve a lista de alertas desta volta."""
    cfg_exec = cfg_exec or {}
    al = []
    pode_entrar, porque = ok_estado, motivo_estado
    if not ok_estado:
        al.append(alerta("bloqueio", texto=motivo_estado))
    inst = {m: i["inst"] for m, i in infos.items()}
    # 1) o mercado anda: stops/objetivos na corretora sombra
    if isinstance(cli, CorretoraSombra):
        cli.mover({inst[m]: v for m, v in velas.items() if m in inst})
    # 2) acompanhar o que esta aberto; detetar fechos
    aberto_tfs = set(((tfs.get("conta") or {}).get("abertas") or {}).keys())
    for cl, op in list(estado["ops"].items()):
        antes = op["estado"]
        try:
            S.acompanhar(cli, cfg_exec, op, agora)
        except S.Recusa as e:
            al.append(alerta("erro", op, str(e))); pode_entrar = False; porque = "recusa durante a volta"
        if op.get("aviso"):
            al.append(alerta("erro", op, op.pop("aviso"))); pode_entrar = False; porque = "falha de comunicacao"
        if antes == "incerto" and op["estado"] != "incerto":
            al.append(alerta("reconciliacao", op, f"{op['moeda']} -> {op['estado']}"))
        if op["estado"] in ("aberta", "parcial") and op.get("px_fill") is None and isinstance(cli, CorretoraSombra):
            op["px_fill"] = cli.ordens.get(cl, {}).get("px")
            al.append(alerta("entrada", op))
        disparo = isinstance(cli, CorretoraSombra) and op["estado"] == "aberta" and cli.pos.get(op["inst"], 0) <= 1e-12 \
            and op.get("px_fill") is not None
        if disparo:                                              # o stop/objetivo fechou a posicao na corretora
            px_out = [o for k, o in cli.ordens.items() if k.startswith("algo") and o["instId"] == op["inst"]][-1]["px"]
            _fechar_registo(estado, op, px_out, "stop" if px_out >= op["stop"] else "objetivo", agora)
            al.append(alerta("stop" if px_out >= op["stop"] else "saida", op))
        elif op["estado"] == "aberta" and op["moeda"] not in aberto_tfs:   # a regra do TF-SHORT saiu
            try:
                S.fechar(cli, cfg_exec, op)
                px_out = cli.ordens.get(op["cl_id"][:28] + "f", {}).get("px") if isinstance(cli, CorretoraSombra) else None
                _fechar_registo(estado, op, px_out, "regra", agora)
                al.append(alerta("saida", op))
            except (S.SemComunicacao, S.Recusa, S.EnvioBloqueado) as e:
                al.append(alerta("erro", op, str(e))); pode_entrar = False; porque = "falha ao fechar"
    # 3) entradas novas: as posicoes da conta executavel do TF-SHORT que a sombra ainda nao tem
    if not pode_entrar:
        if ok_estado:
            al.append(alerta("bloqueio", texto=porque))
        estado["alertas"] = (estado.get("alertas") or []) + al
        return al
    reg = registo_tfs(cfg_okx)
    donos = {o["inst"]: o["cod"] for o in estado["ops"].values() if o["estado"] in ("pendente", "parcial", "aberta", "incerto")}
    abertas = [{"cod": o["cod"], "nocional": o["nocional"], "risco_usd": o["risco_usd"]} for o in estado["ops"].values()
               if o["estado"] in ("pendente", "parcial", "aberta", "incerto")]
    for moeda, p in sorted(((tfs.get("conta") or {}).get("abertas") or {}).items()):
        sid = f"{moeda}-{p['t']}"
        if any(o["sinal"] == sid for o in estado["ops"].values()) or moeda not in infos or moeda not in velas:
            continue
        v = velas[moeda]
        risco = 100 * p["w"] * (p["stop"] / p["entrada"] - 1)          # o mesmo risco do paper (peso x distancia do stop)
        sinal = {"id": sid, "moeda": moeda, "inst": infos[moeda]["inst"], "px": v["c"], "t_px": v["t"], "stop": p["stop"],
                 "objetivo": None, "t_sinal": p["t"], "cod": "tfs"}
        reg["estrategias"]["tfs"]["risco_pct"] = max(0.01, min(3.0, risco))
        plano = S.planear(sinal, capital, capital, infos[moeda], reg, abertas, donos, agora)
        if not plano["ok"]:
            estado.setdefault("ignoradas", []).append({"sinal": sid, "motivo": plano["motivo"], "t": agora})
            continue
        op = S.abrir(cli, cfg_exec, plano, estado, agora, mercado=True)
        if op["estado"] == "incerto":
            al.append(alerta("erro", op, op.get("motivo", ""))); break      # nao abre mais nada nesta volta
        if op["estado"] in ("bloqueada", "recusada"):
            al.append(alerta("erro", op, op.get("motivo", "")))
            continue
        S.acompanhar(cli, cfg_exec, op, agora)
        if isinstance(cli, CorretoraSombra):
            op["px_fill"] = cli.ordens.get(op["cl_id"], {}).get("px")
        al.append(alerta("entrada", op))
        donos[op["inst"]] = "tfs"; abertas.append({"cod": "tfs", "nocional": op["nocional"], "risco_usd": op["risco_usd"]})
    estado["alertas"] = (estado.get("alertas") or []) + al
    if enviar:
        for a in al:
            enviar(a)
    return al


def _fechar_registo(estado, op, px_out, motivo, agora):
    """Fecha a op e escreve-a no registo unico como SOMBRA (nunca real), com custos estimados."""
    e = op.get("px_fill") or op["px"]
    risco = op["stop"] - op["px"]
    R = None
    if px_out and risco > 0:
        R = round(((e - px_out) / e - 2 * CUSTO_LADO) * e / risco, 4)
    op.update(estado="fechada", saida=px_out, motivo_saida=motivo, t_saida=agora, R=R)
    estado["fechadas"].append(op["cl_id"])
    reg = G.op("TF-SHORT sombra (P1)", "sombra", "okx", op["moeda"], "okx_sombra", op["cl_id"], op, R=R, lado="SHORT",
               t_entrada=op.get("criado"), t_saida=agora, motivo=motivo,
               custos={"comissao": round(2 * 0.0005 * op["nocional"], 6), "deslize": round(2 * 0.0010 * op["nocional"], 6),
                       "spread": round(2 * 0.0002 * op["nocional"], 6)})
    estado["registo"].append(reg)
