"""(12/11, autorizado pelo Rui 07:29) Recolha historica de velas de 1h da OKX para a investigacao intradiaria.

So pedidos GET PUBLICOS (sem chaves). Para cada X-Perp vivo da OKX EEA guarda:
  - as velas de 1h do proprio contrato (o que existir: os X-Perps sao recentes);
  - as velas de 1h do mesmo ativo em USDT a vista na OKX (historico mais longo, mesmo preco de referencia),
    marcadas como "substituto" para a investigacao saber o que e o contrato e o que nao e.
Formato: <pasta>/<BASE>.csv.gz (substituto a vista) e <pasta>/xperp/<BASE>.csv.gz, linhas t,o,h,l,c,v (t em s).
Incremental: se o ficheiro ja existe, so pede o que falta. Nao escreve nada fora da pasta dada.
(12/11 09:20) Em LOTES: --orcamento S segundos (omissao 0 = sem limite) para nao ocupar o servidor europeu, que tambem corre
a conta e o executor da Bybit (a recolha de 07:31 prendeu-o 100 min). Cada serie so e gravada quando o historico fica
completo; uma serie interrompida pelo orcamento e descartada e refeita no lote seguinte. Series ja gravadas so pedem as
velas novas. --fios N (omissao 3) pedidos em paralelo, abaixo do limite publico da OKX (20 pedidos / 2 s).
Uso: python3 -m tools.okx_velas_1h <pasta> [--dias 365] [--max 400] [--orcamento 420] [--fios 3]"""
import gzip
import json
import os
import socket
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_orig = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [x for x in _orig(*a, **k) if x[0] == socket.AF_INET] or _orig(*a, **k)

BASE = "https://eea.okx.com"
GLOBAL = "https://www.okx.com"
H = 3600


def get(url, tentativas=4):
    for k in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cryptoscan/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            if str(d.get("code")) == "0":
                return d.get("data") or []
            if str(d.get("code")) in ("50011", "50013"):       # limite de pedidos: espera e repete
                time.sleep(1.5 * (k + 1))
                continue
            return []
        except Exception:                                        # noqa: BLE001
            time.sleep(1.0 * (k + 1))
    return []


def instrumentos():
    out = {}
    for i in get(f"{BASE}/api/v5/public/instruments?instType=FUTURES"):
        iid = i.get("instId", "")
        if "XPERP" in iid and i.get("state") == "live":
            out[iid.split("-")[0]] = iid
    return out


def ler(p):
    if not os.path.exists(p):
        return {}
    out = {}
    for l in gzip.open(p, "rt").read().split():
        z = l.split(",")
        if len(z) >= 6:
            out[int(z[0])] = z[1:6]
    return out


def gravar(p, linhas):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with gzip.open(p, "wt") as f:
        for t in sorted(linhas):
            f.write(",".join([str(t)] + [str(x) for x in linhas[t]]) + "\n")


class Interrompido(Exception):
    pass


def velas(host, inst, desde, ja, fim=None):
    """Velas de 1h fechadas de inst desde 'desde' (s), pedindo para tras a partir de agora ate encontrar o que ja ha.
    fim (time.time) = limite do lote: passado, levanta Interrompido (a serie nao fica a meio)."""
    linhas, after, pedidos = {}, None, 0
    while pedidos < 120:
        if fim is not None and time.time() > fim:
            raise Interrompido(inst)
        url = f"{host}/api/v5/market/history-candles?instId={inst}&bar=1H&limit=100" + (f"&after={after}" if after else "")
        d = get(url)
        pedidos += 1
        if not d:
            break
        for r in d:
            t = int(r[0]) // 1000
            if len(r) > 8 and str(r[8]) != "1":
                continue                                          # vela por fechar
            linhas[t] = [r[1], r[2], r[3], r[4], r[5]]
        mais_antiga = min(int(r[0]) for r in d)
        if mais_antiga // 1000 <= desde or mais_antiga // 1000 in ja:
            break
        after = mais_antiga
        time.sleep(0.12)
    return {t: v for t, v in linhas.items() if t >= desde}


def correr(pasta, dias=365, maximo=400, orcamento=0, fios=3):
    t0 = time.time()
    fim = t0 + orcamento if orcamento else None
    desde = int(t0) // H * H - dias * 86400
    inst = instrumentos()
    trabalho = []
    for b, iid in sorted(inst.items())[:maximo]:
        trabalho.append((b, os.path.join(pasta, "xperp", b + ".csv.gz"), BASE, iid))
        trabalho.append((b, os.path.join(pasta, b + ".csv.gz"), GLOBAL, f"{b}-USDT"))
    trava = threading.Lock()
    res = {"feitas": 0, "atualizadas": 0, "por_fazer": 0, "vazias": []}

    def uma(job):
        b, nome, host, i = job
        ja = ler(nome)
        if not ja and os.path.exists(nome):
            return                                               # sem mercado a vista (marcado num lote anterior)
        if ja and max(ja) >= int(time.time()) // H * H - 2 * H:
            return                                               # ja atualizada (ultima vela fechada)
        if fim is not None and time.time() > fim:
            with trava:
                res["por_fazer"] += 1
            return
        try:
            novo = velas(host, i, max([desde] + [t + H for t in ja]), ja, fim)
        except Interrompido:
            with trava:
                res["por_fazer"] += 1
            return
        if novo or ja:
            ja.update(novo)
            gravar(nome, ja)
            with trava:
                res["atualizadas" if len(ja) > len(novo) else "feitas"] += 1
        elif host == GLOBAL:
            with trava:
                res["vazias"].append(b)
            gravar(nome, {})                                      # marca "sem a vista" para nao repetir
    with ThreadPoolExecutor(max_workers=max(1, fios)) as ex:
        list(ex.map(uma, trabalho))
    meta = {"t": int(time.time()), "xperps": len(inst), "series": len(trabalho), "novas": res["feitas"],
            "atualizadas": res["atualizadas"], "por_fazer": res["por_fazer"], "completo": res["por_fazer"] == 0,
            "sem_substituto_a_vista": sorted(res["vazias"]), "dias": dias, "duracao_s": int(time.time() - t0),
            "nota": "a vista USDT da OKX como substituto do X-Perp (mesmo ativo); xperp/ = o proprio contrato"}
    with open(os.path.join(pasta, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta


if __name__ == "__main__":
    a = sys.argv

    def arg(k, d):
        return int(a[a.index(k) + 1]) if k in a else d
    print(json.dumps(correr(a[1], arg("--dias", 365), arg("--max", 400), arg("--orcamento", 0), arg("--fios", 3))))
