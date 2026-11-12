# CCAuto: notes for further development

Cookie Clicker (web v2.058) automation. The product is `cookie_auto.js`, a single
browser-console script. Everything else exists to choose its settings, test it or publish it.

## Files

| path | what |
|---|---|
| `cookie_auto.js` | the script. `A.cfg` at the top holds every setting; modules are numbered sections (1 clicker/shimmers, 2 Grimoire forecast, 3 Godzamok, 4 Krumblor, 5 Pantheon, 6 shop + elder state, 7 wrinklers, 8 seasons, 9 garden, 10 stock market, 11 sugar lumps, status panel). `CCAuto._t` exposes internals for tests. |
| `strategy_sim/gc_sim.py`, `run_strategies.py` | Python simulator ported from the game source, plus a coordinate-descent search over strategy dimensions. `uv run strategy_sim/run_strategies.py [snapshot.json]` |
| `strategy_sim/market_sim.py` | port of the stock price model; fits the per-good buy/sell thresholds (`MARKET_BUY_BELOW/SELL_ABOVE`) |
| `strategy_sim/results.html` | charts of the (stopped) search run; embedded on the site |
| `tests/browser_test.py` | **main test**: Playwright + headless Firefox loads the *live* game from orteil.dashnet.org, builds a late-game save with cheats, checks forecast vs real casts, double cast, Godzamok, Orbs, season budget, shop/garden/market ticks, then runs the full loop (`WAIT=` seconds). Prints JSON; look at `ok` fields, `warnings`, `page_errors`. `uv run tests/browser_test.py` |
| `tests/browser_smoke.py` | quicker load-and-run check |
| `site/index.html` + `.github/workflows/pages.yml` | GitHub Pages site (bookmarklet via `Game.LoadMod`, copy button, charts). The workflow copies `site/`, `cookie_auto.js`, `results.html` on every push to `main`. |
| `PLAN.md` | the original revision plan and the user's decisions on it (historical) |
| `auto_script.txt` | the old script (SteeleRobert fork). Superseded, kept for reference only. |
| `main.py` | uv placeholder, unused |

There is no Node.js on this machine. JS is checked only through the Playwright tests (uv dev dependency).
The game source can be fetched from `https://orteil.dashnet.org/cookieclicker/main.js` (and `minigameGarden.js` etc.); check mechanics there, not from memory.

Repo: `git@github.com:Mythiotis/cookieclicker-auto.git` (public, hyphen!). Site: https://mythiotis.github.io/cookieclicker-auto/. The README is visitor-facing: no maintainer/publishing instructions in it.

## History (six sessions, Oct 31 to Nov 12 2026)

1. **Origin.** Forked https://github.com/SteeleRobert/CookieClicker-Automation into `auto_script.txt`, adapted for a level-11 farm (a 6×6 plot from level 9, nothing changes above) and the Shimmering veil (`PROTECT_VEIL`: idle play while the veil is up). Explained that the meddleweed phase is intended: Brown Mold and Crumbspore only come from harvesting meddleweed.
2. **Questions on the old script.** The Elder Covenant flip-flop around Frenzies is a leftover combo trick that only costs money with the veil up. FtHoF wasn't cast on a plain Frenzy because of the veil guard and ×1000 thresholds.
3. **Krumblor.** Added dragon training + aura choice. Dragon Orbs was judged *not* OP: it only works with no buff running, so it can't stack combos.
4. **Old script fixes.** Veil vs clicking compared by value (`BREAK_VEIL_FOR_CLICKING`), added a building/upgrade buyer, fixed an infinite `while` tower-rebuy loop that froze the tab.
5. **The rewrite (main session).** The user asked for a plan first (`PLAN.md`), then corrected it:
   - building prices are negligible late game when staying 20 to 50 under the last building, so sell/rebuy costs don't matter
   - the stock market must run at full capacity
   - "calculate" means *write a Python simulator and search*, not estimate
   - sell Wizard towers for double casts, never spend sugar lumps on it

   That produced `strategy_sim/` and the new `cookie_auto.js`. The search was stopped early on request (the 2nd cost scenario was identical to the 1st). Result, about 3.3e8× base CpS: auras Radiant Appetite + Breath of Milk, elder stage 1 (One mind), Whiskerbloom on clay after research, forecast + double cast at a ×500 CpS-buff threshold, Pantheon Godzamok/Mokalsium/Muridal, pop golden cookies immediately, no pawnshop loan. Godzamok sell/rebuy stacking is the biggest factor (about 200×). Dragon Orbs and Godzamok are mutually exclusive (a sale grants Devastation before the Orbs "no buff" check). Market fit gives about 129 $/h per unit held; there are **18** goods (You has one). Then published to GitHub Pages as Mythiotis, with the stock chart labelled by stock names, a visitor README and a draggable/foldable status panel (default spot over the building pictures, away from Krumblor).
6. **Spending freeze fix (this file written here).** The user saw seasons not switching and found from the status panel that *kept back* (54.7 novemdecillion) was about 44× their bank (1.25 novemdecillion), so free-to-spend was 0 and the shop, market and seasons all stopped. Cause: the reserve held 30 × 2 full Godzamok rounds of 1000 buildings, and late game, with buildings bought up to near bank level, one round costs about a bank. Fixed by capping the combo reserve, fitting Godzamok rounds to the budget, adding the season claim, and switching to wood chips at 2/3 mature parents (the user approved that).

## Design rules that matter

- **One shared budget.** `bankReserve()` = the larger of the Lucky! reserve (6000 s unbuffed CpS once *Get lucky* is owned) and the combo money (Godzamok rounds + Wizard tower rebuy). The combo money is capped at `COMBO_RESERVE_MAX_FRACTION` (0.5) of the bank's high-water mark since start/ascension (`bankPeak()`). The cap must use the high-water mark: a cap on the *current* bank lets the shop drain the bank step by step. Late game the bank is ~1e7 s of CpS because combos dominate income, so CpS-based reserves are tiny and the cap is what binds. `spendReserve()` = that plus `seasonClaim()`. The shop and the market spend only above `spendReserve()`. **Any new consumer that buys something occasional must claim its price the same way.** The shop and market spend every free cookie within seconds (shop 2 s tick, market 10 s), so an unclaimed purchase never gets enough together.
- Season switch price = 1e9 + 60 s × unbuffed CpS × 1.5^`Game.seasonUses` (×2/1.5/1.25 with Selebrak). `seasonUses` only resets on ascension, and seasons expire after 24 h, so every renewal is 1.5× dearer. Caps: `SEASON_MAX_PRICE_SECONDS` (collecting drops, 24 h) and `FINAL_SEASON_MAX_PRICE_SECONDS` (renewing, 1 h). Above the cap there is no claim, so the shop isn't blocked forever.
- Godzamok: each round sells the cheapest buildings whose sell+rebuy loss fits `GODZ_MAX_BANK_FRACTION × bank / GODZ_ROUNDS` (`godzBatch(maxLoss)`, binary search per building). Never a fixed batch: a fixed batch costing more than the budget meant 0 rounds.
- Grimoire forecast replays `Math.seedrandom(Game.seed+'/'+spellsCastTotal)`. Anything that draws random numbers in between breaks it (hence `MUTE_GC_CHIME`).
- Nothing is planted, harvested for value or switched while a CpS buff runs, because seed prices follow current CpS.
- Background tabs throttle timers; the game must stay in a visible window.

## Open points / ideas

- **Garden research layout:** parents sit in rows 1 and 4, all other tiles are targets. Each parent is replanted on its own when it dies, and planting is skipped during CpS buffs or when a seed costs > 5% of the bank, so parent ages drift apart. That is intended: mutations only count *mature* neighbours (`neighsM` in `minigameGarden.js`), and per-tile replanting maximises the time each parent is mature. Wood chips go on at ≥ 2/3 mature parents and off below 1/3 (hysteresis, because soil changes have a 10 min cooldown).
- Whether buying buildings close to the bank level is right at all late game: the shop's payback uses base production, but income is dominated by combos. That's worth a simulator run.
- Run the third cost scenario of the strategy search, or a search fitted to the user's own `CCAuto.snapshot()`.
- `auto_script.txt` could be deleted once the user agrees.

## Working with this user

- Wants a plan first for big changes, and decides on it before implementation.
- Wants claims backed by computation (simulator / game source), not estimates.
- Verify in the real game through the Playwright tests before reporting something as working.
- Commits are authored as the repo owner; push to `origin main` only when asked.
