import json
import os
import sys
import time

from . import scanner

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"


def main():
    res = scanner.run()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "scan.json"), "w") as f:
        json.dump(res, f, separators=(",", ":"))
    print("STATUS", res["status_global"])
    for name, s in res["sources"].items():
        print(f"  {name:8s}", "OK %d pares" % s["pairs"] if s["ok"]
              else "ERRO " + s["error"])
    if res["universe"]:
        print("COUNTS", res["counts"])
        for r in res["universe"][:45]:
            if not r["eligible"]:
                continue
            tfs = " ".join(f"{tf}:{v['status']}({v['n']},{v['source']})"
                           for tf, v in r.get("timeframes", {}).items())
            print(f"  {r['asset']:8s} liq {r['liquidity_score']:3d} "
                  f"vol ${r['volume_24h']/1e6:8.1f}M spr {r['spread_bps']:5.2f} "
                  f"src {len(r['sources'])} {r.get('data_status','-')} "
                  f"{','.join(r.get('flags', []))} {tfs}")
            for tf, v in r.get("timeframes", {}).items():
                if v["issues"]:
                    print(f"      {tf}: {'; '.join(v['issues'])}")
            an = r.get("analysis")
            for tf in ("1d", "4h"):
                a = an and an.get(tf)
                if a and a["ok"]:
                    ev = a["event"]
                    print(f"      {tf} ema:{a['ema_trend']} estr:{a['structure']} "
                          f"adx {a['adx']} rsi {a['rsi']} atr {a['atr_pct']}% "
                          f"ev:{ev['type']+' '+ev['direction']+' ha '+str(ev['bars_ago']) if ev else '-'} "
                          f"{','.join(a['patterns'])}")
                elif a:
                    print(f"      {tf} {a['reason']}")
            if an and an.get("mtf_conflict"):
                print(f"      CONFLITO: {an['mtf_conflict']}")
    # falha o job se nenhuma fonte respondeu: nunca publicar dados vazios
    sys.exit(0 if res["universe"] else 1)


if __name__ == "__main__":
    main()
