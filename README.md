# Cookie Clicker auto

Fully active late-game automation for Cookie Clicker (web 2.058 / Steam), plus the
simulator used to choose its strategy.

| file | what it is |
|---|---|
| `cookie_auto.js` | the script: paste into the browser console (F12) with the game open |
| `strategy_sim/gc_sim.py` | golden cookie / combo simulator (formulas taken from the game source) |
| `strategy_sim/market_sim.py` | stock market simulator (exact port of the price model) |
| `strategy_sim/run_strategies.py` | strategy search, writes `strategy_sim/results.md` |
| `tests/browser_test.py` | loads the real game headless, builds a late-game save, checks the script |
| `auto_script.txt` | the old script (kept for reference, superseded) |
| `site/` | GitHub Pages site (built by `.github/workflows/pages.yml`) |

## Using the script

1. Open the game in its **own visible window** (background tabs throttle timers).
2. Paste `cookie_auto.js` into the console. A small status panel appears bottom left.
3. Console commands: `CCAuto.stop()`, `CCAuto.start()`, `CCAuto.status()`,
   `CCAuto.forecast(10)`, `CCAuto.snapshot()`, `CCAuto.popWrinklers()`.
   Settings live in `CCAuto.cfg` and can be changed while it runs.

## Re-running the strategy search with your own numbers

```
# in the game console:
copy(JSON.stringify(CCAuto.snapshot()))
# paste into snapshot.json, then:
uv run strategy_sim/run_strategies.py snapshot.json
```

`REPS` and `DAYS` environment variables control runs per candidate and simulated days.

## Tests

```
uv run tests/browser_test.py
```

Needs network access (loads orteil.dashnet.org) and the Playwright Firefox build.

## Publishing the site

Push to GitHub, then in the repository settings choose **Pages -> Source: GitHub Actions**.
The workflow copies `site/`, `cookie_auto.js` and `strategy_sim/results.html` into the site
on every push to `main`. The site's bookmarklet loads the script from the same address.
