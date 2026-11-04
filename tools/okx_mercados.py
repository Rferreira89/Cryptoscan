"""(04/11) Lista publica dos contratos da OKX Europa (sem chave): que ativos ha e o valor minimo de cada ordem.
Serve para saber o que cabe numa conta pequena. Corre no servidor europeu (IPv4)."""
import json, socket, urllib.request
_gai = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, socket.AF_INET, *a, **k)
B = "https://eea.okx.com"


def get(path):
    req = urllib.request.Request(B + path, headers={"User-Agent": "cryptoscan/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read()).get("data") or []


tick = {t["instId"]: float(t.get("last") or 0) for tt in ("SWAP", "FUTURES") for t in get(f"/api/v5/market/tickers?instType={tt}")}
linhas = []
for tt in ("SWAP", "FUTURES"):
    for i in get(f"/api/v5/public/instruments?instType={tt}"):
        if i.get("state") != "live":
            continue
        px = tick.get(i["instId"], 0)
        ct, mn = float(i.get("ctVal") or 0), float(i.get("minSz") or 0)
        nom = ct * mn * px if i.get("ctType") == "linear" else ct * mn
        linhas.append((i["instId"], tt, i.get("settleCcy"), round(nom, 2), i.get("lever"), i.get("expTime")))
print("contratos ativos:", len(linhas))
for l in sorted(linhas, key=lambda x: x[0]):
    print("  ", l[0], l[1], "liquida em", l[2], "| ordem minima ~", l[3], "USD | alav max", l[4])
