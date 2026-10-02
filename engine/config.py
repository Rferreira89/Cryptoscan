"""Parametros do sistema. Podem ser alterados em config.json na raiz."""
import json
import os

DEFAULTS = {
    "venue": "Bybit EU",        # unica corretora onde se opera
    "quote": "USDC",            # a Bybit UE nao lista USDT (MiCA)
    "direction": "LONG_ONLY",   # spot, sem alavancagem: nao ha shorts
    "risk_pct": 1.0,            # risco por operacao, % do capital
    "max_position_pct": 25.0,   # teto por posicao, % do capital
    "fee_pct": 0.1,             # comissao spot por lado (taxa base Bybit)
    "min_rr": 2.0,
    "min_score": 65,
    "max_open_positions": 4,    # sinais ativos + operacoes abertas
    "signal_expiry_hours": 12,  # 3 velas de 4H
    "max_venue_spread_pct": 0.30,
    "min_venue_volume_usd": 25_000,   # ordens pequenas: o spread pesa mais
    "alerts": True,             # Telegram em cada compra e venda
    # Decisao do utilizador (2026-10-02): operar com dinheiro real mesmo sem
    # estrategias validadas. Os sinais saem como operacoes reais, cada um
    # com o registo do backtest. False = nao validadas ficam em PAPEL.
    "real_money_unvalidated": True,
    "paper_unvalidated": True,
    # Estrategias nao validadas arriscam metade (nunca mais do que risk_pct)
    "unvalidated_risk_pct": 0.5,
    # Sem compras novas com o BTC abaixo da media de 200 dias
    "require_btc_above_sma200": True,
    # Travao de perdas (em R, soma das operacoes fechadas)
    "max_daily_loss_r": 3.0,
    "max_weekly_loss_r": 6.0,
    "cooldown_after_losses": 3,     # perdas seguidas -> pausa de 24h
}


def load(path="config.json"):
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            user = json.load(f)
        unknown = set(user) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"config.json: chaves desconhecidas {sorted(unknown)}")
        cfg.update(user)
    if not 0 < cfg["risk_pct"] <= 2:
        raise ValueError("risk_pct tem de estar entre 0 e 2")
    return cfg
