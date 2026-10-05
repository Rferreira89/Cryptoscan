"""Parametros do sistema. Podem ser alterados em config.json na raiz."""
import json
import os

DEFAULTS = {
    "venue": "Bybit EU",        # unica corretora onde se opera
    "quote": "USDC",            # a Bybit UE nao lista USDT (MiCA)
    "direction": "LONG_ONLY",   # nao usado: os shorts dependem de "shorts"
    "risk_pct": 1.0,            # risco por operacao, % do capital
    "max_position_pct": 25.0,   # teto por posicao, % do capital
    "fee_pct": 0.1,             # comissao spot por lado (taxa base Bybit)
    "min_rr": 2.0,
    # 1.o objetivo tem de ser um nivel real do mercado (decisao de
    # 2026-10-04: no historico, alvos so projetados deram -0.36R por
    # operacao contra -0.20R com nivel real; ambos negativos).
    "require_real_tp1": True,
    # 1.o objetivo a mais de 2.5R e recusado (decisao de 2026-10-05): no
    # historico, 16% de acerto e -0.34R (502 operacoes) contra 41% e -0.14R
    # quando fica entre 1R e 1.5R. Todos os grupos sao negativos. Ligado em
    # config.json (2.5); None aqui = sem limite.
    "max_rr_tp1": None,
    # Estrategias desligadas a mao. RANGE (compras e shorts): decisao do
    # utilizador em 2026-10-05; no historico, 12% e 17% de acerto, -0.80R e
    # -0.74R por operacao (83 operacoes, 71 no stop).
    "disabled_strategies": ["RANGE", "RANGE_SHORT"],
    "min_score": 65,
    # Modo concentrado (decisao do utilizador, 2026-10-02): com 50 USDC,
    # no maximo 2 operacoes de cada vez, posicoes ate 25 USDC e risco ate
    # max_risk_usdc por operacao (2.5 USDC = 5% em config.json desde
    # 2026-10-03; o valor por omissao abaixo e 2 USDC). Conta sinais ativos, operacoes abertas e
    # posicoes da tendencia diaria.
    "max_open_positions": 2,
    "signal_expiry_hours": 12,  # 3 velas de 4H
    "max_venue_spread_pct": 0.30,
    "min_venue_volume_usd": 25_000,   # ordens pequenas: o spread pesa mais
    "alerts": True,             # Telegram em cada compra e venda
    # Decisao do utilizador (2026-10-02): operar com dinheiro real mesmo sem
    # estrategias validadas. Os sinais saem como operacoes reais, cada um
    # com o registo do backtest. False = nao validadas ficam em PAPEL.
    "real_money_unvalidated": True,
    "paper_unvalidated": True,
    # Risco base das estrategias nao validadas (nunca mais do que risk_pct).
    # Com alavancagem 2x o risco efetivo por operacao chega a 2%.
    "unvalidated_risk_pct": 1.0,
    # Decisao do utilizador (2026-10-02): alavancagem nas estrategias de
    # swing (margem spot da Bybit UE). A posicao e o risco por operacao sao
    # multiplicados por este valor, ate ao maximo que mantem a liquidacao
    # estimada a mais do dobro da distancia do stop. 1 = sem alavancagem.
    "swing_leverage": 6.0,
    # Capital de trading em USDC (2026-10-02: 50). Atualiza-se pelo Telegram
    # com /capital <valor>. Serve para dar valores em USDC e para adaptar
    # as operacoes a ordem minima da Bybit UE.
    "capital_usdc": 50.0,
    "min_order_usdc": 5.0,
    # Decisao do utilizador (2026-10-02): todas as operacoes com posicao
    # fixa de 25 USDC. O risco passa a depender da distancia do stop; uma
    # operacao cujo risco excederia max_risk_usdc fica com posicao menor. None = dimensao
    # pelo risco (risk_pct).
    "fixed_position_usdc": 25.0,
    "max_risk_usdc": 2.0,
    # Decisao do utilizador (2026-10-02): sinais de short (venda a
    # descoberto em margem spot). So com o BTC ABAIXO da media de 200 dias,
    # o espelho exato da regra das compras.
    "shorts": True,
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
    if not 1 <= cfg["swing_leverage"] <= 6:
        raise ValueError("swing_leverage tem de estar entre 1 e 6")
    return cfg
