"""Functional test of cookie_auto.js against the real game in headless Firefox.

    uv run tests/browser_test.py

Builds a late-game save with console cheats, then checks:
  - the FtHoF forecast matches real casts (no season and during Easter)
  - double cast, Godzamok stacking, Dragon Orbs, pantheon slotting
  - shop, seasons, garden research, stock market and the full loop run without errors
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = open(os.path.join(ROOT, 'cookie_auto.js')).read()

SETUP = r"""
(async () => {
  Game.cookies = 1e90; Game.cookiesEarned = 1e90;
  for (var i in Game.Objects) { var b = Game.Objects[i]; Game.buyMode = 1; b.buy(400); }
  Game.lumps = 5000;
  for (const n of ['Farm', 'Bank', 'Temple', 'Wizard tower']) {
    for (let k = 0; k < 10; k++) Game.Objects[n].levelUp(true);
  }
  for (const n of Game.goldenCookieUpgrades.concat(['Season switcher', 'Elder spice'])) {
    if (Game.Upgrades[n]) Game.Upgrades[n].earn();
  }
  Game.dragonLevel = Game.dragonLevels.length - 1;
  Game.CalculateGains();
  return 'ok';
})()
"""

def main():
    results = {}
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        logs, errors = [], []
        page.on('console', lambda m: logs.append(m.text) if 'CCAuto' in m.text else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('https://orteil.dashnet.org/cookieclicker/', timeout=120000)
        page.wait_for_function('window.Game && Game.ready', timeout=120000)
        page.evaluate(SETUP)
        page.wait_for_function("['Farm','Bank','Temple','Wizard tower'].every(n => Game.Objects[n].minigameLoaded)", timeout=120000)
        page.evaluate(SCRIPT)
        page.evaluate('CCAuto.stop()')

        # ---- 1. forecast vs real casts
        def forecast_check(season):
            return page.evaluate("""(season) => {
              Game.season = season;
              var M = Game.Objects['Wizard tower'].minigame, ok = 0, bad = [];
              for (var k = 0; k < 60; k++) {
                for (var i = Game.shimmers.length - 1; i >= 0; i--) Game.shimmers[i].die();
                Game.buffs = {}; Game.recalculateGains = 1;
                var f = CCAuto._t.fthofOutcome(0);
                M.magic = M.magicM;
                M.castSpell(M.spells['hand of fate']);
                var s = Game.shimmers[Game.shimmers.length - 1];
                if (s && s.force == f.out && (!s.wrath) == f.win) ok++;
                else bad.push([f.out, f.win, s && s.force, s && s.wrath]);
              }
              for (var i = Game.shimmers.length - 1; i >= 0; i--) Game.shimmers[i].die();
              Game.season = '';
              return {ok: ok, bad: bad.slice(0, 5)};
            }""", season)
        results['forecast_no_season'] = forecast_check('')
        results['forecast_easter'] = forecast_check('easter')
        results['forecast_christmas'] = forecast_check('christmas')

        # ---- 2. double cast
        results['double_cast'] = page.evaluate("""() => {
          var M = Game.Objects['Wizard tower'].minigame, t = Game.Objects['Wizard tower'];
          Game.buyMode = 1; t.buy(500); M.computeMagicM(); M.magic = M.magicM; var n0 = M.spellsCastTotal, towers0 = t.amount;
          M.castSpell(M.spells['hand of fate']);
          var left = M.magic;
          CCAuto.cfg.GOOD_SPELLS = ['click frenzy','building special','cookie storm','blood frenzy','frenzy','multiply cookies','cookie storm drop','clot','ruin cookies','cursed finger','blab','free sugar lump'];
          CCAuto._t.doubleCast(M);
          for (var i = Game.shimmers.length - 1; i >= 0; i--) Game.shimmers[i].die();
          return {casts: M.spellsCastTotal - n0, towers_before: towers0, towers_after: t.amount,
                  magic_after_first: left, magicM: M.magicM};
        }""")

        # ---- 3. pantheon + Godzamok
        results['godzamok'] = page.evaluate("""() => {
          var M = Game.Objects['Temple'].minigame; M.swaps = 3;
          CCAuto._t.pantheonTick(); CCAuto._t.pantheonTick(); CCAuto._t.pantheonTick();
          var slots = M.slot.slice();
          Game.buffs = {};
          Game.gainBuff('click frenzy', 30, 777);
          var amounts0 = Object.values(Game.Objects).map(b => b.amount).join(',');
          var bank0 = Game.cookies;
          CCAuto._t.godzamokTick();
          var d = Game.hasBuff('Devastation');
          var amounts1 = Object.values(Game.Objects).map(b => b.amount).join(',');
          Game.buffs = {}; Game.recalculateGains = 1;
          return {slots: slots, hasRuin: Game.hasGod('ruin'), devastation: d ? d.multClick : 0,
                  buildings_restored: amounts0 == amounts1, spent_fraction: (bank0 - Game.cookies) / bank0};
        }""")

        # ---- 4. Dragon Orbs (Godzamok must be unslotted, he blocks the wish)
        results['orbs'] = page.evaluate("""() => {
          var P = Game.Objects['Temple'].minigame; P.slotGod(P.gods['ruin'], -1);
          Game.buffs = {};
          for (var i = Game.shimmers.length - 1; i >= 0; i--) Game.shimmers[i].die();
          CCAuto.cfg.DRAGON_AURAS = ['Radiant Appetite', 'Dragon Orbs'];
          CCAuto._t.dragonTick();
          var auras = [Game.dragonAuras[Game.dragonAura].name, Game.dragonAuras[Game.dragonAura2].name];
          var tries = 0;
          while (Game.shimmerTypes.golden.n == 0 && tries < 20) { CCAuto._t.orbsTick(); tries++; }
          var n = Game.shimmerTypes.golden.n;
          for (var i = Game.shimmers.length - 1; i >= 0; i--) Game.shimmers[i].die();
          return {auras: auras, golden_spawned: n, ticks: tries};
        }""")

        # ---- 4b. season switch is not starved by the shop / stock market
        results['season_starvation'] = page.evaluate("""() => {
          var out = {};
          Game.buffs = {};
          Game.season = ''; Game.seasonUses = 3; Game.computeSeasonPrices();
          for (var k in Game.seasons) { var u = Game.Upgrades[Game.seasons[k].trigger]; u.bought = 0; Game.Unlock(u.name); }
          var p = CCAuto._t.seasonPlan();
          out.target = p.target; out.price = p.price;
          // bank = reserve + exactly the switch price; the market wants to buy everything
          Game.cookies = CCAuto._t.bankReserve() + p.price * 1.01;
          var B = Game.Objects.Bank.minigame;
          for (var i = 0; i < B.goodsById.length; i++) { B.goodsById[i].val = 1; B.goodsById[i].stock = 0; }
          CCAuto._t.marketTick();
          CCAuto._t.shopTick();
          out.claim_left = Game.cookies >= CCAuto._t.bankReserve() + p.price;
          CCAuto._t.seasonTick();
          out.season = Game.season;
          // exponential price: after 30 switches the final-season renewal is skipped
          Game.seasonUses = 30; Game.computeSeasonPrices();
          for (var k in Game.seasons) { var u = Game.Upgrades[Game.seasons[k].trigger]; u.bought = 0; Game.Unlock(u.name); }
          Game.season = '';
          out.claim_when_too_dear = CCAuto._t.seasonClaim();
          Game.seasonUses = 0; Game.computeSeasonPrices(); Game.season = '';
          for (var k in Game.seasons) { var u = Game.Upgrades[Game.seasons[k].trigger]; u.bought = 0; Game.Unlock(u.name); }
          Game.cookies = 1e90;
          return out;
        }""")
        r = results['season_starvation']
        r['ok'] = r['claim_left'] and r['season'] == r['target'] and r['claim_when_too_dear'] == 0

        # ---- 4c. reserve when combo money would exceed the bank (late game, screenshot case)
        results['reserve_cap'] = page.evaluate("""() => {
          var out = {}, T = CCAuto._t;
          Game.buffs = {};
          var lucky = CCAuto.cfg.LUCKY_RESERVE_SECONDS;
          CCAuto.cfg.LUCKY_RESERVE_SECONDS = 0;  // late game it is tiny next to the bank
          var t = Game.Objects['Wizard tower'];
          var need = t.getReverseSumPrice(t.amount - 10) / t.getSellMultiplier() * (1 - t.getSellMultiplier());
          Game.cookies = need / 40;              // combo money ~40 banks, as in the screenshot
          T.resetPeak();
          out.bank = Game.cookies; out.uncapped_need = need;
          out.reserve = T.bankReserve();
          out.reserve_le_half_bank = out.reserve <= Game.cookies * 0.5 * 1.0001;
          var b0 = 0; for (var i in Game.Objects) b0 += Game.Objects[i].amount;
          var u0 = Game.UpgradesOwned;
          T.shopTick();
          var b1 = 0; for (var i in Game.Objects) b1 += Game.Objects[i].amount;
          out.shop_bought = (b1 - b0) + (Game.UpgradesOwned - u0);
          out.bank_after_shop_ge_half_peak = Game.cookies >= T.bankPeak() * 0.5 * 0.999;
          var batch = T.godzBatch(Game.cookies * 0.5 / 30), n = 0;
          for (var j = 0; j < batch.length; j++) n += batch[j][1];
          out.godz_units_per_round = n;
          out.ok = out.reserve_le_half_bank && out.shop_bought > 0 && out.bank_after_shop_ge_half_peak && n > 0;
          CCAuto.cfg.LUCKY_RESERVE_SECONDS = lucky;
          Game.cookies = 1e90; T.resetPeak();
          return out;
        }""")

        # ---- 4d. garden research: wood chips once 2/3 of the parents are mature
        results['woodchips'] = page.evaluate("""() => {
          var G = Game.Objects.Farm.minigame, out = {};
          Game.buffs = {};
          for (var k in G.plants) G.plants[k].unlocked = 1;
          G.plants.whiteMildew.unlocked = 0; G.getUnlockedN();
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) G.plot[y][x] = [0, 0];
          G.soil = G.soils.fertilizer.id; G.nextSoil = 0;
          CCAuto._t.gardenTick();
          var tiles = [];
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) if (G.plot[y][x][0] > 0) tiles.push([x, y]);
          out.parents_planted = tiles.length;
          var mat = G.plants.brownMold.mature;
          // 7 of 12 mature: stays on fertilizer
          tiles.forEach((t, i) => G.plot[t[1]][t[0]][1] = i < 7 ? mat : 0);
          G.nextSoil = 0; CCAuto._t.gardenTick();
          out.soil_at_7 = G.soilsById[G.soil].key;
          // 8 of 12 mature: wood chips
          tiles.forEach((t, i) => G.plot[t[1]][t[0]][1] = i < 8 ? mat : 0);
          G.nextSoil = 0; CCAuto._t.gardenTick();
          out.soil_at_8 = G.soilsById[G.soil].key;
          // 5 of 12 still above 1/3: keeps wood chips
          tiles.forEach((t, i) => G.plot[t[1]][t[0]][1] = i < 5 ? mat : 0);
          G.nextSoil = 0; CCAuto._t.gardenTick();
          out.soil_at_5 = G.soilsById[G.soil].key;
          out.note = CCAuto._t.state.garden;
          out.ok = out.parents_planted == 12 && out.soil_at_7 == 'fertilizer' && out.soil_at_8 == 'woodchips' && out.soil_at_5 == 'woodchips';
          for (var k in G.plants) G.plants[k].unlocked = 0;
          G.plants.bakerWheat.unlocked = 1; G.getUnlockedN();
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) G.plot[y][x] = [0, 0];
          return out;
        }""")

        # ---- 4e. synchronised research planting
        results['garden_sync'] = page.evaluate("""() => {
          var G = Game.Objects.Farm.minigame, T = CCAuto._t, out = {};
          Game.buffs = {};
          function only(key) {
            for (var k in G.plants) G.plants[k].unlocked = 1;
            G.plants[key].unlocked = 0; G.getUnlockedN();
            for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) G.plot[y][x] = [0, 0];
            G.computeBoostPlot();
          }
          function grid() { return G.plot.map(r => r.map(t => t[0] > 0 ? G.plantsById[t[0] - 1].key : null)); }
          function count(key) { var n = 0; grid().forEach(r => r.forEach(k => { if (k == key) n++; })); return n; }

          // juicy queenbeet: 21 queenbeets in a 5x5 block, 4 centres empty
          only('queenbeetLump');
          T.gardenTick();
          var g = grid();
          out.qb_planted = count('queenbeet');
          out.qb_centres_empty = [[1,1],[1,3],[3,1],[3,3]].every(c => g[c[0]][c[1]] == null);
          out.qb_spare_empty = [0,1,2,3,4,5].every(i => g[5][i] == null && g[i][5] == null);
          // one dies mid-cohort: not replanted until the whole cohort is gone
          for (var y = 0; y < 5; y++) for (var x = 0; x < 5; x++) if (G.plot[y][x][0]) G.plot[y][x][1] = 60;
          G.plot[0][0] = [0, 0];
          T.gardenTick();
          out.qb_straggler_waits = G.plot[0][0][0] == 0;
          out.qb_note = T.state.garden;
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) G.plot[y][x] = [0, 0];
          T.gardenTick();
          out.qb_new_round = count('queenbeet');

          // elderwort = shimmerlily x cronerice: cronerice (long-lived) first,
          // shimmerlily only when it would mature together with the cronerice
          only('elderwort');
          T.gardenTick();
          out.ew_first = {cronerice: count('cronerice'), shimmerlily: count('shimmerlily')};
          var cr = G.plants.cronerice, sl = G.plants.shimmerlily;
          var slT = T.plantTicks(G, 0, 1, sl, 0).mature;
          var rate = (cr.ageTick + cr.ageTickR / 2);
          function setCron(age) { for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) { var t = G.plot[y][x]; if (t[0] == cr.id + 1) t[1] = age; } }
          setCron(Math.floor(cr.mature - rate * (slT + 3)));   // cronerice ~3 ticks too far away
          T.gardenTick();
          out.ew_too_early = count('shimmerlily');
          setCron(Math.ceil(cr.mature - rate * (slT - 0.5)));   // now they would mature together
          T.gardenTick();
          out.ew_synced = count('shimmerlily');
          // shimmerlily died, cronerice close to death: no replant
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) if (G.plot[y][x][0] == sl.id + 1) G.plot[y][x] = [0, 0];
          setCron(97);
          T.gardenTick();
          out.ew_no_late_replant = count('shimmerlily');
          // cronerice young again (mature, long life left): shimmerlily replanted
          setCron(cr.mature + 2);
          T.gardenTick();
          out.ew_replant = count('shimmerlily');

          out.ok = out.qb_planted == 21 && out.qb_centres_empty && out.qb_spare_empty && out.qb_straggler_waits &&
            out.qb_new_round == 21 && out.ew_first.cronerice == 6 && out.ew_first.shimmerlily == 0 &&
            out.ew_too_early == 0 && out.ew_synced == 6 && out.ew_no_late_replant == 0 && out.ew_replant == 6;
          for (var k in G.plants) G.plants[k].unlocked = 0;
          G.plants.bakerWheat.unlocked = 1; G.getUnlockedN();
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) G.plot[y][x] = [0, 0];
          return out;
        }""")

        # ---- 5. shop, seasons, garden, market, grimoire tick
        results['ticks'] = page.evaluate("""() => {
          var out = {};
          var up0 = Game.UpgradesOwned;
          Game.buffs = {};
          CCAuto._t.shopTick();
          out.upgrades_bought = Game.UpgradesOwned - up0;
          CCAuto._t.seasonTick();
          out.season = Game.season;
          CCAuto._t.gardenTick();
          out.garden = CCAuto._t.state.garden;
          var G = Game.Objects.Farm.minigame, planted = 0;
          for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) if (G.plot[y][x][0] > 0) planted++;
          out.garden_planted = planted;
          var B = Game.Objects.Bank.minigame;
          for (var i = 0; i < B.goodsById.length; i++) B.goodsById[i].val = 1;   // everything cheap
          CCAuto._t.marketTick();
          out.market_stock = B.goodsById.map(g => g.stock).reduce((a, b) => a + b, 0);
          out.brokers = B.brokers;
          CCAuto._t.grimoireTick();
          out.spell = CCAuto._t.state.spell;
          return out;
        }""")

        # ---- 6. full loop for a while
        page.evaluate('CCAuto.cfg.GOOD_SPELLS = ["click frenzy","building special","cookie storm","blood frenzy"]; CCAuto.start()')
        t0 = page.evaluate('Game.cookieClicks')
        time.sleep(float(os.environ.get('WAIT', 30)))
        results['loop'] = page.evaluate("""(t0) => ({clicks: Game.cookieClicks - t0,
            panel: document.getElementById('ccautoPanel') ? document.getElementById('ccautoPanel').innerText : null})""", t0)
        results['warnings'] = [l for l in logs if 'CCAuto]' in l and (':' in l and ('Error' in l or 'error' in l or 'undefined' in l))]
        results['page_errors'] = errors
        results['log_tail'] = logs[-15:]
        browser.close()
    print(json.dumps(results, indent=1))

if __name__ == '__main__':
    main()
