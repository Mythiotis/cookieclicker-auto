"""Stock market simulator: exact port of minigameMarket.js M.tick().

Prices are not affected by the player's trades, so price paths are generated once
and every buy/sell threshold pair is evaluated on the same paths.
Profit is measured in "$", and 1 $ = 1 second of your highest raw CpS
(Game.cookiesPsRawHighest), which is what the game pays out.
"""
from __future__ import annotations

import random

N_GOODS = 18


def resting(i, bank_level):
    return 10 + 10 * i + (bank_level - 1)


def simulate_paths(ticks, bank_level=10, dragon_boost=0.0, seed=1):
    rng = random.Random(seed)
    r = rng.random
    goods = []
    for i in range(N_GOODS):
        goods.append(dict(mode=rng.choice([0, 1, 1, 2, 2, 3, 4, 5]), dur=int(10 + r() * 690),
                          val=resting(i, bank_level), d=r() * 0.2 - 0.1))
    paths = [[0.0] * ticks for _ in range(N_GOODS)]
    cap = 100 + (bank_level - 1) * 3
    db = dragon_boost
    for t in range(ticks):
        globD = 0.0
        globP = r()
        if r() < 0.1 + 0.1 * db:
            globD = (r() - 0.5) * 2
        for i, me in enumerate(goods):
            me['d'] *= 0.97 + 0.01 * db
            mode = me['mode']
            if mode == 0:
                me['d'] *= 0.95; me['d'] += 0.05 * (r() - 0.5)
            elif mode == 1:
                me['d'] *= 0.99; me['d'] += 0.05 * (r() - 0.1)
            elif mode == 2:
                me['d'] *= 0.99; me['d'] -= 0.05 * (r() - 0.1)
            elif mode == 3:
                me['d'] += 0.15 * (r() - 0.1); me['val'] += r() * 5
            elif mode == 4:
                me['d'] -= 0.15 * (r() - 0.1); me['val'] -= r() * 5
            elif mode == 5:
                me['d'] += 0.3 * (r() - 0.5)
            me['val'] += (resting(i, bank_level) - me['val']) * 0.01
            if globD != 0 and r() < globP:
                me['val'] -= (1 + me['d'] * r() ** 3 * 7) * globD
                me['val'] -= globD * (1 + r() ** 3 * 7)
                me['d'] += globD * (1 + r() * 4)
                me['dur'] = 0
            me['val'] += ((r() - 0.5) * 2) ** 11 * 3
            me['d'] += 0.1 * (r() - 0.5)
            if r() < 0.15:
                me['val'] += (r() - 0.5) * 3
            if r() < 0.03:
                me['val'] += (r() - 0.5) * (10 + 10 * db)
            if r() < 0.1:
                me['d'] += (r() - 0.5) * (0.3 + 0.2 * db)
            if mode == 5:
                if r() < 0.5:
                    me['val'] += (r() - 0.5) * 10
                if r() < 0.2:
                    me['d'] = (r() - 0.5) * (2 + 6 * db)
            if mode == 3 and r() < 0.3:
                me['d'] += (r() - 0.5) * 0.1; me['val'] += (r() - 0.7) * 10
            if mode == 3 and r() < 0.03:
                me['mode'] = 4
            if me['mode'] == 4 and r() < 0.3:
                me['d'] += (r() - 0.5) * 0.1; me['val'] += (r() - 0.3) * 10
            if me['val'] > cap and me['d'] > 0:
                me['d'] *= 0.9
            me['val'] += me['d']
            if me['val'] < 5:
                me['val'] += (5 - me['val']) * 0.5
            if me['val'] < 5 and me['d'] < 0:
                me['d'] *= 0.95
            me['val'] = max(me['val'], 1)
            paths[i][t] = me['val']
            me['dur'] -= 1
            if me['dur'] <= 0:
                me['dur'] = int(10 + r() * (690 - 200 * db))
                if r() < db and r() < 0.5:
                    me['mode'] = 5
                elif r() < 0.7 and me['mode'] in (3, 4):
                    me['mode'] = 5
                else:
                    me['mode'] = rng.choice([0, 1, 1, 2, 2, 3, 4, 5])
    return paths


def evaluate(path, buy_below, sell_above, overhead):
    """Profit per unit of stock (in $) of 'buy everything below X, sell all above Y'."""
    holding = False
    paid = 0.0
    profit = 0.0
    for v in path:
        if not holding:
            if v <= buy_below:
                holding = True
                paid = v * overhead
        elif v >= sell_above:
            profit += v - paid
            holding = False
    if holding:
        profit += path[-1] - paid          # mark to market
    return profit


def optimise(bank_level=10, brokers=100, ticks=60000, seed=1, dragon_boost=0.0):
    overhead = 1 + 0.01 * (20 * 0.95 ** brokers)
    paths = simulate_paths(ticks, bank_level, dragon_boost, seed)
    result = []
    for i in range(N_GOODS):
        R = resting(i, bank_level)
        best = None
        for a in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            for b in [1.0, 1.1, 1.2, 1.3, 1.5, 1.7, 2.0, 2.5, 3.0]:
                lo = max(1.0, R * a)
                hi = R * b
                pr = evaluate(paths[i], lo, hi, overhead)
                if best is None or pr > best[0]:
                    best = (pr, a, b, lo, hi)
        pr, a, b, lo, hi = best
        # per hour, per unit of stock (1 tick = 1 minute)
        result.append(dict(id=i, resting=R, buy_below_frac=a, sell_above_frac=b,
                           buy_below=lo, sell_above=hi, profit_per_unit_per_hour=pr / ticks * 60))
    return result


if __name__ == '__main__':
    import json
    import sys
    lvl = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(json.dumps(optimise(bank_level=lvl), indent=1))
