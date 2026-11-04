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
