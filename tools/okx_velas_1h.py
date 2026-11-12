"""(12/11, autorizado pelo Rui 07:29) Recolha historica de velas de 1h da OKX para a investigacao intradiaria.

So pedidos GET PUBLICOS (sem chaves). Para cada X-Perp vivo da OKX EEA guarda:
  - as velas de 1h do proprio contrato (o que existir: os X-Perps sao recentes);
  - as velas de 1h do mesmo ativo em USDT a vista na OKX (historico mais longo, mesmo preco de referencia),
    marcadas como "substituto" para a investigacao saber o que e o contrato e o que nao e.
Formato: <pasta>/<BASE>.csv.gz (substituto a vista) e <pasta>/xperp/<BASE>.csv.gz, linhas t,o,h,l,c,v (t em s).
Incremental: se o ficheiro ja existe, so pede o que falta. Nao escreve nada fora da pasta dada.
Uso: python3 -m tools.okx_velas_1h <pasta> [--dias 365] [--max 400]"""
import gzip
import json
import os
import socket
import sys
import time
import urllib.request

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


def velas(host, inst, desde, ja):
    """Velas de 1h fechadas de inst desde 'desde' (s), pedindo para tras a partir de agora ate encontrar o que ja ha."""
    linhas, after, pedidos = {}, None, 0
    while pedidos < 120:
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


def correr(pasta, dias=365, maximo=400):
    desde = int(time.time()) // H * H - dias * 86400
    inst = instrumentos()
    feitos, vazios = 0, []
    for b, iid in sorted(inst.items())[:maximo]:
        for nome, host, i in ((os.path.join(pasta, "xperp", b + ".csv.gz"), BASE, iid),
                              (os.path.join(pasta, b + ".csv.gz"), GLOBAL, f"{b}-USDT")):
            ja = ler(nome)
            novo = velas(host, i, max([desde] + [t + H for t in ja]), ja)
            if novo or ja:
                ja.update(novo)
                gravar(nome, ja)
            elif nome.endswith(b + ".csv.gz") and "xperp" not in nome:
                vazios.append(b)
        feitos += 1
    meta = {"t": int(time.time()), "xperps": len(inst), "recolhidos": feitos, "sem_substituto_a_vista": vazios,
            "dias": dias, "nota": "a vista USDT da OKX como substituto do X-Perp (mesmo ativo); xperp/ = o proprio contrato"}
    with open(os.path.join(pasta, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta


if __name__ == "__main__":
    a = sys.argv
    dias = int(a[a.index("--dias") + 1]) if "--dias" in a else 365
    mx = int(a[a.index("--max") + 1]) if "--max" in a else 400
    print(json.dumps(correr(a[1], dias, mx)))
