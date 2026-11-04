"""Search for the most profitable combination of strategies.

    uv run strategy_sim/run_strategies.py                 # default late-game numbers
    uv run strategy_sim/run_strategies.py snapshot.json   # numbers from your save

snapshot.json is the output of CCAuto.snapshot() (or the console snippet in
PLAN.md); keys that are missing keep their defaults.

Search: coordinate descent over every strategy dimension (auras, elder state,
garden, Grimoire use, combo threshold, holding golden cookies, pantheon, loans),
using the same random seeds for every candidate (common random numbers), in
three cost scenarios for selling buildings. Writes results.md next to this file.
"""
from __future__ import annotations

import itertools
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, replace
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gc_sim import PANTHEON, Params, Strategy, run  # noqa: E402
import market_sim  # noqa: E402

REPS = int(os.environ.get('REPS', 48))
DAYS = float(os.environ.get('DAYS', 2))

AURA_POOL = ['RA', 'Fortune', 'Flight', 'Orbs', 'RB', 'Guts', 'ES', 'Epoch', 'Reaper', 'AM',
             'BoM', 'Arcane']
DIMS = {
    'auras': [tuple(c) for c in itertools.combinations(AURA_POOL, 2)],
    'elder': [0, 1, 3],
    'garden': ['none', 'bakerWheat', 'goldenClover', 'shimmerlily', 'elderwort', 'whiskerbloom',
               'bakeberry', 'queenbeet', 'duketater'],
    'grimoire': ['none', 'blind', 'forecast', 'forecast_double'],
    'combo_thr': [1.0, 7.0, 50.0, 500.0],
    'hold_gc': [False, True],
    'pantheon': list(PANTHEON),
    'loan2': [False, True],
}

# price of selling/rebuying buildings, in seconds of base CpS
SCENARIOS = {
    'cheap buildings': dict(tower_price_s=0.01, top_building_price_s=10, godz_batch_price_s=1),
    'medium': dict(tower_price_s=10, top_building_price_s=1000, godz_batch_price_s=1000),
    'expensive': dict(tower_price_s=1000, top_building_price_s=1e5, godz_batch_price_s=1e5),
}


def _one(args):
    p, s = args
    return run(p, s)[0]


def evaluate(pool, base: Params, strats):
    jobs = []
    for s in strats:
        for r in range(REPS):
            jobs.append((replace(base, seed=r + 1, days=DAYS), s))
    vals = pool.map(_one, jobs, chunksize=4)
    out = []
    for k, s in enumerate(strats):
        v = vals[k * REPS:(k + 1) * REPS]
        mean = statistics.fmean(v)
        se = statistics.stdev(v) / len(v) ** 0.5 if len(v) > 1 else 0
        out.append((mean, se, statistics.median(v), s))
    return out


def coordinate_descent(pool, base, start: Strategy, log):
    best = start
    best_val = evaluate(pool, base, [best])[0]
    detail = {}
    for sweep in range(2):
        improved = False
        for dim, options in DIMS.items():
            cands = [replace(best, **{dim: o}) for o in options]
            res = evaluate(pool, base, cands)
            res.sort(key=lambda x: -x[0])
            detail[dim] = res
            if res[0][0] > best_val[0] * 1.0001 and getattr(res[0][3], dim) != getattr(best, dim):
                improved = True
            best_val = res[0]
            best = res[0][3]
            log(f'  sweep {sweep + 1} {dim:10s} -> {getattr(best, dim)!s:28s} {best_val[0]:.4g}')
        if not improved:
            break
    return best_val, detail


def fmt(x):
    return f'{x:.3g}'


def main():
    base = Params()
    if len(sys.argv) > 1:
        snap = json.load(open(sys.argv[1]))
        for k, v in snap.items():
            if hasattr(base, k):
                setattr(base, k, tuple(v) if isinstance(v, list) else v)
    lines = []

    def log(s):
        print(s, flush=True)
        lines.append(s)

    t0 = time.time()
    report = ['# Strategy simulation results', '',
              f'{REPS} runs x {DAYS:g} days per candidate, same seeds for all candidates. '
              'Values = average production in multiples of base CpS '
              '(base = no Radiant Appetite, no buffs, no garden/pantheon).', '']
    with Pool() as pool:
        for name, sc in SCENARIOS.items():
            p = replace(base, **sc)
            log(f'== scenario: {name} {sc}')
            # two starting points: Dragon Orbs (no Godzamok) and Godzamok (no Orbs);
            # the two exclude each other, so a single descent could get stuck
            runs = []
            for start in (Strategy(auras=('RA', 'Orbs'), pantheon='none'),
                          Strategy(auras=('RA', 'Flight'), pantheon='Godz-Moka-Muri')):
                log(f'  start: {start.label()}')
                runs.append(coordinate_descent(pool, p, start, log))
            runs.sort(key=lambda r: -r[0][0])
            for (v2, se2, med2, b2), _ in runs:
                report.append(f'- descent result: `{b2.label()}` mean {fmt(v2)} ± {fmt(se2)}, median {fmt(med2)}')
            report.append('')
            (val, se, med, best), detail = runs[0]
            report += [f'## Scenario: {name}', '',
                       f'Building prices (s of base CpS): {sc}', '',
                       f'**Best: `{best.label()}`**  ', f'mean {fmt(val)} ± {fmt(se)}, median {fmt(med)}', '']
            for dim, res in detail.items():
                report.append(f'<details><summary>{dim}</summary>\n')
                report.append('| option | mean | ± | median |')
                report.append('|---|---|---|---|')
                for mean, se2, med2, s in res[:12]:
                    report.append(f'| {getattr(s, dim)!s} | {fmt(mean)} | {fmt(se2)} | {fmt(med2)} |')
                report.append('\n</details>\n')
    # stock market
    log('== stock market thresholds')
    report += ['## Stock market', '',
               'Thresholds fitted on 60 000 ticks (~42 days), checked on an independent run.', '']
    for db in (0.0, 1.0):
        fit = market_sim.optimise(bank_level=10, dragon_boost=db, seed=1)
        test = market_sim.simulate_paths(60000, 10, db, seed=2)
        oh = 1 + 0.01 * (20 * 0.95 ** 100)
        report.append(f'### {"with" if db else "without"} Supreme Intellect (bank level 10)\n')
        report.append('| good | resting | buy below | sell above | $/h per unit (fit) | $/h per unit (test) |')
        report.append('|---|---|---|---|---|---|')
        tot_fit = tot_test = 0
        for g in fit:
            pt = market_sim.evaluate(test[g['id']], g['buy_below'], g['sell_above'], oh) / 60000 * 60
            tot_fit += g['profit_per_unit_per_hour']
            tot_test += pt
            report.append(f"| {g['id']} | {g['resting']} | {g['buy_below_frac']:.1f}x | "
                          f"{g['sell_above_frac']:.1f}x | {g['profit_per_unit_per_hour']:.3f} | {pt:.3f} |")
        report.append(f'\nSum over goods: {tot_fit:.2f} $/h per unit of stock (fit), {tot_test:.2f} (test).\n')
    report.append(f'\n_Runtime {time.time() - t0:.0f} s_\n')
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results.md')
    open(out, 'w').write('\n'.join(report))
    log(f'written {out}')


if __name__ == '__main__':
    main()
