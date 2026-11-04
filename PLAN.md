# Cookie Clicker auto script: revision plan

Status: **implemented** in `cookie_auto.js`. Decisions D1/D3/D5 were settled by simulation
(`strategy_sim/`, chart in `strategy_sim/results.html`): auras Radiant Appetite + Breath of Milk,
Pantheon Godzamok/Mokalsium/Muridal (Godzamok makes Dragon Orbs impossible), elder stage 1,
garden Whiskerbloom on clay, forecast + double cast at a CpS-buff product of 500, no holding of
golden cookies, no loans, stock market at full capacity with fitted thresholds, no lumps spent.
The text below is the original plan, kept for reference.

---

## 1. Why the current script keeps the bank low

Reading `auto_script.txt`, these are the cookie leaks, most expensive first:

| # | Where | What goes wrong |
|---|-------|-----------------|
| 1 | Garden (`get_all_plants`, l. 1548) | Seeds cost *minutes of current CpS* each. The breeding loop rips out the whole plot (`clean_all_plants`) every time a layout check fails and replants it, plants during buffs (up to 5x CpS, so 5x seed price), and once every seed is unlocked it calls `farm.convert()` whenever lumps ≤ 100. Convert resets the seeds, so research starts over: an endless loop of expensive seeds (Queenbeet, Duketater, etc. cost 1 h+ of CpS each). |
| 2 | Grimoire (`sell_cast`, `autoCastSpells`, `lump_cast`) | Sells Wizard towers every second whenever a threshold is met and buys them back at full price, losing 50–75 % of their value each time. It casts Force the Hand of Fate blind, so about 15 % of casts backfire (Clot, Ruin = direct cookie loss). |
| 3 | Dragon auras (`apply_dragon_auras`) | Every aura change sacrifices your **most expensive building** and buys it back. The wanted aura set flips between idle and active whenever `clicking_beats_veil()` changes, which depends on current CpS. Each flip costs a top-tier building. |
| 4 | Dragon training | Levels 23/24 sacrifice 50 and 200 of *every* building. The script buys them all back right away, which empties the bank for a long time. |
| 5 | Elder Covenant toggle (`change_elders`) | Buys/revokes the Covenant around every Frenzy. That costs cookies, costs 5 % CpS while active and stops wrinklers spawning, which is the biggest CpS multiplier in the late game. |
| 6 | Stock market | Fills every good up to max stock from the bank, using thresholds tuned for a level 10 bank. Ties up a lot of cookies. |
| 7 | Veil logic (`PROTECT_VEIL = true`) | With the veil up, the script does not click and does not pop golden cookies, so it plays idle, which is not what you want. |
| 8 | Browser throttling | Background tabs run `setInterval` at most once per second, and Chrome's "intensive throttling" drops that to once per minute after 5 min hidden. 10 clicks/s and spell timing then don't happen. |

Smaller issues: upgrades are bought cheapest-first with no value check; the building payback ignores synergies, grandma and kitten effects; there are seven unsynchronised `setInterval`s that all spend from the same bank; there is no way to stop the script without reloading.

---

## 2. Target architecture

A full rewrite into **one file `cookie_auto.js`** (paste into the console, or load as a bookmarklet/Steam mod), built around a single coordinator instead of independent timers:

```
CCAuto
 ├─ config          all tunables in one object, editable live (CCAuto.cfg.x = ...)
 ├─ scheduler       one fast loop (100 ms: clicks, shimmers) + one logic loop (1 s)
 ├─ bank            central budget: decides the reserve, all purchases go through it
 ├─ modules         clicker, shimmers, grimoire, dragon, shop, seasons, garden, wrinklers, lumps
 ├─ log/status      small on-screen panel: current mode, reserve, next purchase, next spells
 └─ CCAuto.stop() / start() / status() / forecast()
```

Rules every module follows:
- Spending goes through `bank.canSpend(amount, priority)`. The bank keeps the **Lucky reserve** (see 3.2) and blocks normal purchases during a combo.
- No module sells buildings unless the expected gain is computed and larger than the loss.
- Game internals I'm not sure about (spell RNG, seed unlock condition, season prices, wrath chances) get checked against the current game source (`main.js`, `minigameGrimoire.js`, `minigameGarden.js`) before I write that part.

---

## 3. Modules in detail

### 3.1 Active play: clicking, golden cookies, Grimoire, Krumblor (your point 1)

**Clicker**: `Game.ClickCookie()` 10x per second, always on. The veil is not used: it's never re-bought and has no effect on decisions.

**Shimmers**: pops every golden cookie, wrath cookie and reindeer as it appears (fast loop, no 1 s delay). Exception: while the multi-GC combo is being *assembled*, forced golden cookies can be held on screen for a few seconds so their buffs stack. This needs Dragon's Fortune (see decision D1).

**Grimoire: forecast-based Force the Hand of Fate (FtHoF)**
The spell outcome is deterministic: the game seeds the RNG with `Game.seed + '/' + spellsCastTotal`. The script recomputes the next ~10 outcomes the same way FtHoF planners do and acts on that:
1. **Keep magic full** by default. Don't cast blind.
2. **Skip bad outcomes**: if the next FtHoF would backfire or give something weak (Blab, Cookie chain on a small bank, etc.), cast the cheapest spell (Haggler's Charm) to move the seed past it, but only when magic regen allows it without delaying a good cast.
3. **Combo trigger**: when a natural Frenzy (x7) is running, or Elder frenzy / Building special, and the forecast holds Click frenzy and/or Building special:
   - cast FtHoF, pop the golden cookie at once (or hold it, multi-GC mode);
   - **double cast** if the next outcome is also good: sell just enough Wizard towers that the remaining magic covers a second FtHoF at the reduced maximum, cast, then buy the towers back. This only happens if `expected combo gain > tower resale loss × safety factor`; the gain uses current CpS, buff multipliers and click value at 10/s;
   - optional: refill magic with one sugar lump (15 min cooldown) for a third cast on very large combos, only above a lump reserve (default: keep 100).
4. During click buffs the clicker keeps running at 10/s. Purchases are frozen until the combo ends.

**Krumblor**
- **Training**: levels needing 100 of one building happen when no buff is active and the rebuy fits into ≤ X % of the bank. The 50-of-all / 200-of-all levels only happen when buying back costs ≤ 25 % of the bank (configurable). Training is skipped while a combo is likely (magic nearly full and a good spell forecast).
- **Auras**: one fixed pair chosen for the combo strategy, set **once**. Never flipped back and forth. Re-applied only if something else changed them. Proposal in decision D1.

### 3.2 Buildings: optimized purchasing (your point 2)

- **True ΔCpS per building**, Cookie Monster style: temporarily add +1 of the building, recalculate gains, read the CpS difference, revert. This covers synergies, grandma upgrades, kittens, auras and so on. Cursors also count the click value at 10 clicks/s.
- **Score = payback period** = `max(0, price − spendable)/CpS + price/ΔCpS`. Buy the best one. If it's not affordable, save for it rather than buy something worse, unless something else pays off sooner even after the wait.
- **Lucky reserve**: keep `6000 s × unbuffed CpS` once that's less than ~X % of what you produce in Y hours (early on buildings beat the reserve), so Lucky / Frenzy+Lucky pay out in full. The reserve also covers the double-cast tower rebuy. Optional: `42000 s` (Frenzy-Lucky) as a setting.
- Bulk-buying 10/100 when the next 10 are all "best" (fewer calls, same result).
- No buying during combos, and no selling except for the explicit, gain-checked tower double cast.

### 3.3 Upgrades (your point 3)

- **CpS / click upgrades**: same ΔCpS simulation (toggle the upgrade on, recalculate, revert). Ranked together with buildings in one list by payback period.
- **Non-CpS but valuable** (Lucky day, Serendipity, Get lucky, golden-cookie and Grimoire upgrades, dragon upgrades, Santa/season items, heart biscuits, plant upgrades): a priority whitelist, bought as soon as they cost ≤ N minutes of CpS.
- **Everything else** (cosmetics, milk flavours etc.): bought when the price is below a small fraction of the bank.
- **Never auto-buy**: Elder Pledge, Elder Covenant, Revoke Covenant, Shimmering veil on/off, Golden switch, Sugar frenzy, season switchers (the seasons module handles these), the Chocolate egg (save it for before ascending), and anything paid in sugar lumps.
- **Grandmapocalypse chain** (One mind → Communal brainsweep → Elder Pact) is bought on purpose for the wrinkler strategy (see 3.6 / decision D3). The confirmation prompt is bypassed.

### 3.4 Seasons (your point 4)

Needs the *Season switcher* heavenly upgrade. Switching price is roughly `1 min of CpS × 1.5^(switches this ascension)` (to be checked), so it rises and the module switches as rarely as possible.

1. **Collection phase**, in this order (skipping seasons that are already complete):
   - **Valentine's Day**: buy the 6 heart biscuits (they unlock one after another), then switch.
   - **Christmas**: pop reindeer, level Santa to max (cheap), buy every Christmas cookie, Elf upgrades and so on.
   - **Halloween**: spooky cookies drop only from **popped wrinklers**. This is the one season where wrinklers are popped regularly (each pop is a drop roll).
   - **Easter**: eggs drop from golden cookies and wrinklers. Combos plus wrinkler pops. The Chocolate egg stays excluded.
   - A season counts as done when all its drop or purchase upgrades are owned. Then the module switches to the next one.
2. **Boost phase** (everything collected): stay in one season. Default **Christmas** (reindeer pops are free cookies that scale with buffs, plus no switching cost). Switching back and forth gives no lasting boost once the upgrades are owned.

### 3.5 Garden: research first, then bonus (your point 5)

**Research mode** (until all 34 seeds are unlocked), rewritten so it doesn't burn cookies:
- Mutation recipes checked against the game's real `getMuts()` table (several in the current table are approximate). Breed each missing plant with a fixed, efficient 6x6 layout for its recipe type (single parent, two parents, special: Juicy Queenbeet 8-ring, Everdaisy 3+3, Shriekbulb).
- **Plant only when cheap**: no CpS buff active (seed prices follow the current CpS). Plant extra eagerly during a Clot.
- **Never rip out the whole plot** just because one tile is off. Only fix the wrong tile. Weeds and unwanted plants are pulled only from mutation tiles.
- Soil: Fertilizer while parents grow, Wood chips once parents are mature (more mutations).
- A new mutation is protected until mature, then harvested to unlock the seed (unlock condition to be checked in the game source).
- **No automatic Convert** (sacrificing the garden). That's what caused the reset loop. Kept as an opt-in setting (decision D4).

**Bonus mode** (all seeds unlocked): a layout for the multi-GC strategy, chosen in decision D5. Planting and replanting only outside buffs.

### 3.6 Wrinklers: popped only when it pays (your point 6)

Background: with *n* wrinklers each one eats `n × 5 %` of CpS and returns it ×1.1 (more with upgrades and shiny). 10–12 wrinklers make about **6–8x** effective CpS. The best play is to keep the maximum number alive, but those cookies sit *inside* the wrinklers, not in the bank. Partly because of this the bank looks low even when you're doing well. The status panel will show `bank + wrinkler value` so you can see the real total.

Rules:
- Requires Grandmapocalypse (decision D3). No Pledge or Covenant.
- **Never pop shiny wrinklers.**
- **Pop the fattest non-shiny wrinkler only when**:
  1. *Purchase unlock*: the best purchase (by payback) isn't affordable, bank + that wrinkler is enough, and buying now beats waiting for the wrinkler to keep eating (rough check: its payout ≥ T minutes of CpS and the purchase payback is short);
  2. *Season drops*: Halloween or Easter still has missing items. Then the oldest wrinklers are popped so drop rolls keep coming;
  3. *Combo funding*: a forecast double-cast combo needs the tower rebuy money;
  4. (manual) `CCAuto.popAllWrinklers()` before ascending.
- Never pop during a CpS buff for "value": the payout is fixed by what was already eaten.

### 3.7 Sugar lumps (supporting)

Harvest normal lumps when ripe. Hold golden, meaty and caramelized lumps until shortly before they'd fall off, as now. Lump spending: only the Grimoire refill from 3.1, above a reserve. No auto-levelling unless you want it.

### 3.8 Removed / off by default

Shimmering veil logic, Elder Covenant toggling, Dragon Orbs fishing, Stock market (off; can be kept as an opt-in module, decision D6).

---

## 4. Decisions for you

| ID | Question | My recommendation |
|----|----------|-------------------|
| **D1** | What exactly do you mean by "multi-golden cookie strategy"? (a) **FtHoF forecast + double/triple casting** so several golden-cookie buffs (Frenzy × Building special × Click frenzy) stack; or (b) **Golden-cookie stacking**: hold several GCs on screen for Dragon's Fortune, then pop them all; or (c) both. | **(c)**, with auras **Radiant Appetite + Dragon's Fortune**. Alternative for pure click combos: Radiant Appetite + Dragonflight (but natural Dragonflight overwrites Click frenzy, which hurts FtHoF combos). |
| **D2** | Allow selling Wizard towers for double casts, and spending sugar lumps on magic refills? | Yes to towers (gain-checked). Lump refills only above a reserve of 100 lumps. |
| **D3** | Grandmapocalypse for wrinklers (natural GCs become mostly wrath cookies; FtHoF cookies stay golden), or Elder Pledge/Covenant (all GCs golden, no wrinklers)? | **Grandmapocalypse.** Wrinklers are worth far more. Combos come from FtHoF anyway. |
| **D4** | After garden research is finished: auto-Convert the garden for +10 lumps (restarts research, very expensive)? | **No** (opt-in setting only). |
| **D5** | Garden bonus layout: (a) 36 Golden clover on clay (more GCs); (b) Bakeberries harvested during combos (bank boost); (c) mixed clover/shimmerlily + nursetulip. | **(a)** for the multi-GC strategy. |
| **D6** | Keep the stock market module (off by default) or delete it? | Keep, off by default. |
| **D7** | How do you run it: browser tab (which browser) or the Steam version? And should `main.py` / `pyproject.toml` stay (e.g. a later Python helper) or be removed? | JS file only. Python files untouched unless you want them gone. |
| **D8** | Final season after collection. | Christmas. |

**Please also paste the output of this snippet** (console, in your game), so thresholds fit your save:

```js
(()=>{const M=Game.Objects['Wizard tower'].minigame,G=Game.Objects.Farm.minigame;
console.log(JSON.stringify({ver:Game.version,steam:!!window.steam,ascends:Game.resets,
prestige:Game.prestige,cps:Game.unbuffedCps,bank:Game.cookies,lumps:Game.lumps,
dragon:Game.dragonLevel,auras:[Game.dragonAura,Game.dragonAura2],
wiz:[Game.Objects['Wizard tower'].amount,Game.Objects['Wizard tower'].level,M&&M.magicM],
farmLvl:Game.Objects.Farm.level,seeds:G&&G.plantsUnlockedN,
seasonSwitcher:Game.Has('Season switcher'),season:Game.season,seasonUses:Game.seasonUses,
elderWrath:Game.elderWrath,wrinklers:Game.getWrinklersMax(),veil:Game.Has('Shimmering veil'),
pantheon:!!Game.Objects.Temple.minigame}));})();
```

---

## 5. Implementation order (each step testable on its own)

1. **Skeleton**: config, scheduler, bank, status panel, `stop()/start()`. Port the clicker and shimmer popper. *Check: clicks at 10/s, GCs popped, nothing else spends.*
2. **Shop**: ΔCpS-simulated buildings and upgrades, Lucky reserve, blacklist. *Check: bank recovers, CpS climbs steadily, reserve visible in panel.*
3. **Wrinklers + Grandmapocalypse** chain. *Check: wrinklers max, no pops except by rule.*
4. **Grimoire forecast** (read-only first: `CCAuto.forecast()` prints the next 10 outcomes, you compare with a real cast), then skip-casting, then combos and double casts.
5. **Krumblor** training and fixed auras.
6. **Seasons** collection, then boost phase.
7. **Garden** research rewrite, then bonus layout.
8. Tuning pass with your numbers from the status panel.

Running tip for all steps: keep the game in its **own visible window** (not a background tab, not minimized), or use the Steam version. Otherwise browser throttling makes all timing meaningless.
