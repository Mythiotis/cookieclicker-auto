# 🍪 CCAuto: Cookie Clicker on autopilot

A fully active late-game script for [Cookie Clicker](https://orteil.dashnet.org/cookieclicker/).
It clicks, predicts every spell before casting it, stacks combos, gardens, trades stocks and
switches seasons. Its strategy was picked by a simulator built from the game's own source code.

**Website, one-click install and simulation charts: https://mythiotis.github.io/cookieclicker-auto/**

## Install

Tested on the web version 2.058.

1. Open Cookie Clicker and wait for your save to load.
2. Either drag the **🍪 CCAuto** bookmarklet from the [website](https://mythiotis.github.io/cookieclicker-auto/)
   to your bookmarks bar and click it on the game page, or copy [`cookie_auto.js`](cookie_auto.js)
   into the browser console (F12 → Console).
3. A small **CCAuto** window appears. Drag it by its title bar wherever it's out of the way,
   and fold it with **–**. It remembers where you put it.

Keep the game in its own visible window: browsers slow down timers in background tabs, which
breaks clicking and combo timing.

## What it does

| | |
|---|---|
| 👆 Clicking | 10 clicks per second; pops every golden cookie, wrath cookie and reindeer |
| 🔮 Grimoire | replays the game's random number generator to know what Force the Hand of Fate will give, casts only into combos, skips bad outcomes with cheap spells, double casts by selling Wizard towers |
| 💥 Godzamok | sells and rebuys cheap buildings in rounds during Click frenzy, stacking click power |
| 🏗️ Shop | buys buildings and upgrades by payback time, using the CpS each one would really add; keeps a reserve for Lucky! and combos |
| 🐉 Krumblor & Pantheon | trains the dragon, sets the auras once, slots the gods |
| 🌱 Garden | breeds all 34 seeds, then fills the plot with Whiskerbloom |
| 📈 Stock market | trades all 18 stocks with thresholds fitted on a port of the game's price model |
| 🎃 Seasons | collects every seasonal drop, then stays in the season with the best boost |
| 🐛 Wrinklers | left alone to multiply your cookies; popped only for season drops, never shiny ones |

### The status window

| line | meaning |
|---|---|
| Cookies in bank | what you have right now |
| Kept back (not spent) | the shop never spends this: enough for a full Lucky! payout and for selling/rebuying buildings in combos |
| Free to spend | bank minus the amount kept back |
| Wrinklers are holding | cookies eaten by wrinklers; you get them back with a bonus when they pop |
| Production / Click boost now | all active buffs multiplied together |
| Next spell, Shop, Season, Garden, … | what each part of the script is doing |

### Console commands

| command | |
|---|---|
| `CCAuto.stop()` / `CCAuto.start()` | pause / resume |
| `CCAuto.forecast(10)` | the next 10 Force the Hand of Fate results |
| `CCAuto.popWrinklers()` | pop all non-shiny wrinklers (do this before ascending) |
| `CCAuto.resetPanel()` | put the status window back in its default place |
| `CCAuto.snapshot()` | your save's numbers as JSON, for the simulator |
| `CCAuto.cfg.<SETTING> = …` | change any setting while it runs (all listed at the top of `cookie_auto.js`) |

## Good to know

- **Dragon Orbs and Godzamok don't mix.** Every sale grants Godzamok's buff before the game checks
  Orbs' "no buffs" rule, so the wish never happens. The default setup uses Godzamok.
- **Double casting needs about 600+ Wizard towers** at tower level 10; with fewer the script waits.
- **Elder stage 1** can't be reached once you own Communal brainsweep or Elder Pact.
  Set `CCAuto.cfg.ELDER_STAGE = 3` in that case.

## How the strategy was chosen

`strategy_sim/` holds a Python simulator built from the game's source: golden cookies, buffs,
spells, wrinklers, auras, pantheon, garden and stock market. A search tried every combination
and picked the one with the highest average production. You can see the results on the
[website](https://mythiotis.github.io/cookieclicker-auto/results.html).

To fit it to your own save (needs [uv](https://docs.astral.sh/uv/)):

```
# in the game console
copy(JSON.stringify(CCAuto.snapshot()))
# save the clipboard as snapshot.json, then
uv run strategy_sim/run_strategies.py snapshot.json
```

`tests/browser_test.py` loads the real game in a headless browser and checks the script
against it (spell forecast, double cast, Godzamok, Dragon Orbs, shop, seasons, garden, market).

---

Fan project. Cookie Clicker is made by Orteil & Opti (DashNet); this project isn't affiliated with them.
