// =====================================================================
// CCAuto - maximally active Cookie Clicker automation
//
// Paste the whole file into the browser console (F12 -> Console) while
// the game is loaded, or load it as a bookmarklet / Steam mod.
// Running it again replaces the old instance. Console commands:
//   CCAuto.stop()        stop everything
//   CCAuto.start()       start again
//   CCAuto.status()      print the current state
//   CCAuto.forecast(10)  next 10 Force the Hand of Fate outcomes
//   CCAuto.snapshot()    JSON for strategy_sim/run_strategies.py
//   CCAuto.popWrinklers()  pop all non-shiny wrinklers (before ascending)
//   CCAuto.cfg.X = ...   change a setting live
//
// Strategy defaults come from strategy_sim/ (see strategy_sim/results.md).
// Keep the game in its own visible window: background tabs are throttled
// to 1 timer per second (or per minute), which breaks clicking and combos.
// =====================================================================
(function () {
'use strict';
if (window.CCAuto && window.CCAuto.stop) window.CCAuto.stop();

var A = window.CCAuto = {};

// ---------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------
A.cfg = {
    // --- clicking & golden cookies ---
    CLICKS_PER_SECOND: 10,
    POP_GOLDEN: true,            // pop golden / wrath cookies and reindeer
    HOLD_GOLDEN: false,          // keep natural golden cookies on screen until they
                                 // almost fade (only useful with Dragon's Fortune)
    MUTE_GC_CHIME: true,         // golden cookie chime off: its sound can consume a random
                                 // number and break the spell forecast (Firefox)

    // --- Grimoire: forecast-based Force the Hand of Fate ---
    GRIMOIRE: 'forecast_double', // 'off' | 'forecast' | 'forecast_double'
    COMBO_THRESHOLD: 500,        // product of active CpS buffs needed before casting
                                 // (Frenzy = 7, Frenzy x Building special ~ 500)
    SKIP_BAD_SPELLS: true,       // at full magic, cast a cheap spell to move past a bad FtHoF
    // Good FtHoF outcomes worth casting during a combo
    GOOD_SPELLS: ['click frenzy', 'building special', 'cookie storm', 'blood frenzy'],

    // --- Godzamok (Pantheon): sell + rebuy cheap buildings during click buffs ---
    GODZAMOK: true,
    GODZ_MIN_CLICK_MULT: 100,    // only during Click frenzy / Dragonflight
    GODZ_ROUNDS: 30,             // sell/rebuy rounds per click buff (each adds +1%/building)
    GODZ_BATCH: 1000,            // buildings sold per round
    GODZ_MAX_BANK_FRACTION: 0.5, // never spend more than this share of the bank on it
    GODZ_KEEP: ['Wizard tower', 'Farm', 'Temple', 'Bank'], // never sold (minigames)

    // --- Stock market: loans during giant combos ---
    LOAN2_IN_COMBO: false,       // 'pawnshop loan' (x2 CpS 40 s, then x0.1 for 40 min, -40% bank)
    LOAN2_MIN_COMBO: 1e5,

    // --- Krumblor ---
    AUTO_TRAIN_DRAGON: true,
    DRAGON_AURAS: ['Radiant Appetite', 'Breath of Milk'], // simulated best with Godzamok
    DRAGON_ORBS_MAX_ATTEMPTS: 50,     // sell/rebuy attempts per second
    DRAGON_ORBS_MAX_COST_FRACTION: 0.01, // max cookies lost per attempt, share of the bank

    // --- Pantheon (needs free worship swaps, slotted once) ---
    PANTHEON: {diamond: 'ruin', ruby: 'mother', jade: 'labor'}, // Godzamok, Mokalsium, Muridal
    AUTO_PANTHEON: true,

    // --- Shop ---
    AUTO_BUY_BUILDINGS: true,
    AUTO_BUY_UPGRADES: true,
    LUCKY_RESERVE_SECONDS: 6000,      // bank kept for Lucky! (in s of unbuffed CpS)
    CHEAP_UPGRADE_SECONDS: 600,       // buy non-CpS upgrades costing less than this much CpS
    UPGRADE_BLACKLIST: ['Chocolate egg', 'Elder Pledge', 'Elder Covenant',
        'Revoke Elder Covenant', 'Golden switch [off]', 'Golden switch [on]',
        'Shimmering veil [off]', 'Shimmering veil [on]', 'Sugar frenzy',
        'Festive biscuit', 'Ghostly biscuit', 'Lovesick biscuit', "Fool's biscuit",
        'Bunny biscuit', 'Milk selector', 'Background selector', 'Golden cookie sound selector'],

    // --- Elder state ---
    ELDER_STAGE: 1,              // 1 = One mind only (1/3 wrath cookies, wrinklers spawn),
                                 // 3 = Elder Pact, 0 = Elder Covenant. Simulated best: 1

    // --- Wrinklers ---
    POP_WRINKLERS_FOR_DROPS: true, // pop during Halloween / Easter until all drops are found

    // --- Seasons ---
    AUTO_SEASONS: true,
    SEASON_ORDER: ['valentines', 'christmas', 'easter', 'halloween'],
    FINAL_SEASON: 'auto',        // 'auto' = Business day with Startrade, else Christmas

    // --- Garden ---
    AUTO_GARDEN: true,
    GARDEN_BONUS_PLANT: 'whiskerbloom', // after research: fill all 36 tiles with this
    GARDEN_MAX_SEED_BANK_FRACTION: 0.05,

    // --- Stock market ---
    AUTO_MARKET: true,
    MARKET_HIRE_BROKERS: true,
    // buy below / sell above, as a fraction of each good's resting value
    // (fitted by strategy_sim/market_sim.py for a level 10 bank, ~129 $/h per unit
    // of stock out of sample; 1 $ = 1 s of your highest raw CpS); index = good id
    MARKET_BUY_BELOW: [0.3, 0.2, 0.1, 0.1, 0.1, 0.2, 0.2, 0.4, 0.4, 0.5, 0.3, 0.4, 0.2, 0.4, 0.6, 0.4, 0.5, 0.4],
    MARKET_SELL_ABOVE: [3.0, 2.5, 2.0, 1.3, 1.5, 1.7, 1.3, 1.3, 1.3, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],

    // --- Sugar lumps ---
    AUTO_LUMPS: true,

    // --- UI ---
    SHOW_PANEL: true,
    LOG: true
};
var cfg = A.cfg;

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
var timers = [];
var stateText = {};
function log(msg) { if (cfg.LOG) console.log('[CCAuto] ' + msg); }
function note(key, msg) { stateText[key] = msg; }

function minigame(name) {
    var o = Game.Objects[name];
    return (o && o.minigameLoaded && o.minigame) ? o.minigame : null;
}

function cpsBuffMult() {
    var m = 1;
    for (var i in Game.buffs) {
        var b = Game.buffs[i];
        if (typeof b.multCpS !== 'undefined') m *= b.multCpS;
    }
    return m;
}
function clickBuffMult() {
    var m = 1;
    for (var i in Game.buffs) {
        var b = Game.buffs[i];
        if (typeof b.multClick !== 'undefined') m *= b.multClick;
    }
    return m;
}
function anyBuff() { for (var i in Game.buffs) return true; return false; }
function goldenOnScreen() { return Game.shimmerTypes['golden'].n; }
// A combo is running while any CpS or click buff boosts production
function comboRunning() { return cpsBuffMult() > 1.0001 || clickBuffMult() > 1.0001; }

function highestBuilding() {
    var best = null;
    for (var i in Game.Objects) if (Game.Objects[i].amount > 0) best = Game.Objects[i];
    return best;
}

// Building.buy() sells in sell mode, so force buy mode
function buyBuilding(b, n) {
    if (n <= 0) return 0;
    var mode = Game.buyMode, before = b.amount;
    Game.buyMode = 1;
    b.buy(n);
    Game.buyMode = mode;
    return b.amount - before;
}
function sellBuilding(b, n) {
    if (n <= 0) return 0;
    var before = b.amount;
    b.sell(n);
    return before - b.amount;
}
// Cookies lost by selling the top n of a building and buying them back
function sellRebuyLoss(b, n) {
    n = Math.min(n, b.amount);
    if (n <= 0) return 0;
    return b.getReverseSumPrice(n) / b.getSellMultiplier() * (1 - b.getSellMultiplier());
}

// Cookies the bank always keeps (Lucky! payout, combo money)
function bankReserve() {
    // the Lucky! reserve only matters once golden cookies are frequent
    var r = Game.Has('Get lucky') ? Game.unbuffedCps * cfg.LUCKY_RESERVE_SECONDS : 0;
    r = Math.max(r, godzRoundCost() * cfg.GODZ_ROUNDS * 2 + towerRebuyCost());
    return r;
}

function aura(name) { return Game.auraMult(name) > 0; }

// ---------------------------------------------------------------------
// 1. Clicker and shimmers
// ---------------------------------------------------------------------
// Time based, so timer jitter doesn't lower the average rate. The game ignores
// clicks less than 20 ms apart, so only one click per tick.
var clickClock = {t0: 0, done: 0};
function clickTick() {
    var now = Date.now();
    if (!clickClock.t0 || now - clickClock.t0 > 60000) { clickClock.t0 = now; clickClock.done = 0; }
    var due = Math.floor((now - clickClock.t0) / 1000 * cfg.CLICKS_PER_SECOND);
    if (clickClock.done < due) { Game.ClickCookie(); clickClock.done++; }
}

var orbAttempts = 0;
function shimmerTick() {
    if (!cfg.POP_GOLDEN) return;
    for (var i = Game.shimmers.length - 1; i >= 0; i--) {
        var s = Game.shimmers[i];
        // natural / Dragon Orbs cookies have forceObj 0, spell cookies carry an object
        if (s.type == 'golden' && cfg.HOLD_GOLDEN && s.force == '' &&
            s.life > Game.fps * 1.5 && s.forceObj === 0) continue;
        s.pop();
    }
}

// Dragon Orbs: with no buff and no golden cookie on screen, selling the most
// powerful building has a 10% chance to spawn a golden cookie.
function orbsTick() {
    if (!aura('Dragon Orbs')) return;
    // Godzamok grants Devastation on every sale before the game checks the
    // "no buffs" condition, so with him slotted a wish can never happen.
    if (Game.hasGod && Game.hasGod('ruin')) { note('orbs', 'blocked by Godzamok'); return; }
    var best = highestBuilding();
    if (!best) return;
    for (var k = 0; k < cfg.DRAGON_ORBS_MAX_ATTEMPTS; k++) {
        if (anyBuff() || goldenOnScreen() > 0) return;
        var loss = sellRebuyLoss(best, 1);
        if (loss > Game.cookies * cfg.DRAGON_ORBS_MAX_COST_FRACTION) { note('orbs', 'too expensive'); return; }
        if (Game.cookies + best.getPrice() * best.getSellMultiplier() < best.getPrice()) return;
        sellBuilding(best, 1);
        buyBuilding(best, 1);
        orbAttempts++;
        if (goldenOnScreen() > 0) { note('orbs', 'wish granted after ' + orbAttempts + ' tries'); orbAttempts = 0; }
    }
}

// ---------------------------------------------------------------------
// 2. Grimoire: deterministic spell forecast
// The game seeds the RNG with Game.seed + '/' + spellsCastTotal before every
// cast. We replay the same random calls as M.spells['hand of fate'].
// ---------------------------------------------------------------------
function seasonPicRandom() {
    return Game.season == 'valentines' || Game.season == 'fools' ||
        Game.season == 'easter' || Game.season == 'halloween';
}

// Outcome of FtHoF at offset k from now with n golden cookies on screen
function fthofOutcome(k, n) {
    var M = minigame('Wizard tower');
    if (!M) return null;
    var spell = M.spells['hand of fate'];
    var fail = 0.15;
    if (Game.hasBuff('Magic adept')) fail *= 0.1;
    if (Game.hasBuff('Magic inept')) fail *= 5;
    fail *= 1 + 0.1 * Game.auraMult('Supreme Intellect');
    fail += 0.15 * (typeof n === 'number' ? n : Game.shimmerTypes['golden'].n);
    Math.seedrandom(Game.seed + '/' + (M.spellsCastTotal + k));
    var out;
    var win = Math.random() < 1 - fail;
    if (seasonPicRandom()) Math.random();
    Math.random(); Math.random();      // shimmer x, y
    if (win) {
        var ch = ['frenzy', 'multiply cookies'];
        if (!Game.hasBuff('Dragonflight')) ch.push('click frenzy');
        if (Math.random() < 0.1) ch.push('cookie storm', 'cookie storm', 'blab');
        if (Game.BuildingsOwned >= 10 && Math.random() < 0.25) ch.push('building special');
        if (Math.random() < 0.15) ch = ['cookie storm drop'];
        if (Math.random() < 0.0001) ch.push('free sugar lump');
        out = choose(ch);
    } else {
        var ch2 = ['clot', 'ruin cookies'];
        if (Math.random() < 0.1) ch2.push('cursed finger', 'blood frenzy');
        if (Math.random() < 0.003) ch2.push('free sugar lump');
        if (Math.random() < 0.1) ch2 = ['blab'];
        out = choose(ch2);
    }
    Math.seedrandom();
    return {out: out, win: win};
}
// does a non-FtHoF spell at offset k backfire? (same first random number)
function spellFails(k, spellKey) {
    var M = minigame('Wizard tower');
    Math.seedrandom(Game.seed + '/' + (M.spellsCastTotal + k));
    var u = Math.random();
    Math.seedrandom();
    return u >= 1 - M.getFailChance(M.spells[spellKey]);
}

A.forecast = function (n) {
    n = n || 10;
    var res = [];
    for (var k = 0; k < n; k++) {
        var f = fthofOutcome(k);
        res.push((k + 1) + ': ' + (f ? (f.win ? '' : '[backfire] ') + f.out : '-'));
    }
    console.log(res.join('\n'));
    return res;
};

function isGood(o) {
    if (!o) return false;
    if (cfg.GOOD_SPELLS.indexOf(o.out) != -1) return true;
    return o.out == 'frenzy' && !Game.hasBuff('Frenzy');
}

function towers() { return Game.Objects['Wizard tower']; }
function magicMaxFor(n, lvl) {
    n = Math.max(n, 1); lvl = Math.max(lvl, 1);
    return Math.floor(4 + Math.pow(n, 0.6) + Math.log((n + (lvl - 1) * 10) / 15 + 1) * 15);
}
function fthofCostAt(M, magicM) {
    var s = M.spells['hand of fate'];
    return Math.floor((s.costMin + magicM * s.costPercent) * (1 - 0.1 * Game.auraMult('Supreme Intellect')));
}
function towerRebuyCost() {
    var t = towers();
    if (!t || !t.amount) return 0;
    return sellRebuyLoss(t, Math.max(0, t.amount - 10));
}

function popNewestGolden() {
    for (var i = Game.shimmers.length - 1; i >= 0; i--) {
        var s = Game.shimmers[i];
        if (s.type == 'golden' && !s.popped && s.force != 'cookie storm drop') { s.pop(); return; }
    }
}

function castFthof(M) {
    var ok = M.castSpell(M.spells['hand of fate']);
    if (ok) popNewestGolden();
    return ok;
}

function grimoireTick() {
    if (cfg.GRIMOIRE == 'off') return;
    var M = minigame('Wizard tower');
    if (!M) return;
    var cost = M.getSpellCost(M.spells['hand of fate']);
    var nxt = fthofOutcome(0);
    note('spell', 'next: ' + (nxt.win ? '' : 'backfire ') + nxt.out + ' | magic ' + Math.floor(M.magic) + '/' + M.magicM);
    var P = cpsBuffMult();
    if (P >= cfg.COMBO_THRESHOLD && isGood(nxt) && M.magic >= cost) {
        log('Combo x' + Beautify(P) + ': casting FtHoF -> ' + nxt.out);
        castFthof(M);
        if (cfg.GRIMOIRE == 'forecast_double') doubleCast(M);
        return;
    }
    // Move past a bad outcome while magic is full anyway
    if (cfg.SKIP_BAD_SPELLS && !isGood(nxt) && M.magic >= M.magicM - 1 && !comboRunning()) {
        // A backfiring spell: Resurrect Abomination only pops a wrinkler.
        // A successful one: Haggler's Charm (cheap, 1 min harmless buff).
        var key = spellFails(0, "haggler's charm") ? 'resurrect abomination' : "haggler's charm";
        var sp = M.spells[key];
        if (M.magic >= M.getSpellCost(sp)) {
            var before = M.spellsCastTotal;
            M.castSpell(sp);
            if (M.spellsCastTotal > before) log('Skipped ' + nxt.out + ' with ' + key);
        }
    }
}

// Second FtHoF right away: sell Wizard towers until the lower max magic makes
// the remaining magic enough, cast, buy the towers back.
function doubleCast(M) {
    var nxt = fthofOutcome(0);
    if (!isGood(nxt)) return;
    var t = towers();
    var start = t.amount, keep = start;
    while (keep > 1 && fthofCostAt(M, magicMaxFor(keep, t.level)) > M.magic) {
        keep = keep > 50 ? Math.floor(keep * 0.9) : keep - 1;
    }
    if (fthofCostAt(M, magicMaxFor(keep, t.level)) > M.magic) return;
    var sold = start - keep;
    var loss = sellRebuyLoss(t, sold);
    if (loss > Game.cookies * 0.5) { log('Double cast skipped: towers too expensive'); return; }
    if (sold > 0) sellBuilding(t, sold);
    M.computeMagicM();
    log('Double cast (sold ' + sold + ' towers) -> ' + nxt.out);
    castFthof(M);
    if (sold > 0) buyBuilding(t, sold);
    M.computeMagicM();
}

// ---------------------------------------------------------------------
// 3. Godzamok sell/rebuy stacking during click buffs
// Every sale adds +1% click power per building sold to the running Devastation
// buff (without resetting its timer), so several sell+rebuy rounds stack.
// ---------------------------------------------------------------------
function godzBatch() {
    // cheapest buildings first, skipping minigame buildings
    var list = [];
    for (var i in Game.Objects) {
        var b = Game.Objects[i];
        if (b.amount <= 0 || cfg.GODZ_KEEP.indexOf(b.name) != -1) continue;
        list.push(b);
    }
    list.sort(function (a, b) { return a.getPrice() - b.getPrice(); });
    var batch = [], n = 0;
    for (var j = 0; j < list.length && n < cfg.GODZ_BATCH; j++) {
        var k = Math.min(list[j].amount, cfg.GODZ_BATCH - n);
        batch.push([list[j], k]);
        n += k;
    }
    return batch;
}
function godzRoundCost() {
    if (!cfg.GODZAMOK || !Game.hasGod || !Game.hasGod('ruin')) return 0;
    var c = 0, batch = godzBatch();
    for (var i = 0; i < batch.length; i++) c += sellRebuyLoss(batch[i][0], batch[i][1]);
    return c;
}
function godzamokTick() {
    if (!cfg.GODZAMOK || !Game.hasGod || !Game.hasGod('ruin')) return;
    if (Game.hasBuff('Devastation')) return;
    if (clickBuffMult() < cfg.GODZ_MIN_CLICK_MULT) return;
    var batch = godzBatch();
    var cost = godzRoundCost();
    var budget = Game.cookies * cfg.GODZ_MAX_BANK_FRACTION;
    var rounds = cost > 0 ? Math.min(cfg.GODZ_ROUNDS, Math.floor(budget / cost)) : cfg.GODZ_ROUNDS;
    for (var r = 0; r < rounds; r++) {
        for (var i = 0; i < batch.length; i++) sellBuilding(batch[i][0], batch[i][1]);
        for (var j = 0; j < batch.length; j++) buyBuilding(batch[j][0], batch[j][1]);
    }
    var d = Game.hasBuff('Devastation');
    if (d) log('Godzamok: ' + rounds + ' rounds, clicks x' + Beautify(d.multClick, 1));
}

function loanTick() {
    if (!cfg.LOAN2_IN_COMBO) return;
    var M = minigame('Bank');
    if (!M || !M.takeLoan || M.officeLevel < 3) return;   // 2nd loan slot: Finance headquarters
    if (Game.hasBuff('Loan 2') || Game.hasBuff('Loan 2 (interest)')) return;
    if (cpsBuffMult() * clickBuffMult() < cfg.LOAN2_MIN_COMBO) return;
    if (M.takeLoan(2)) log('Took the pawnshop loan during a combo');
}

// ---------------------------------------------------------------------
// 4. Krumblor
// ---------------------------------------------------------------------
function dragonSacrifice(level) {
    var last = Game.dragonLevels.length - 1;
    if (level >= 5 && level < last - 2) return [[Game.ObjectsById[level - 5], 100]];
    var per = (level == last - 2) ? 50 : (level == last - 1) ? 200 : 0;
    var list = [];
    if (per > 0) for (var i in Game.Objects) list.push([Game.Objects[i], per]);
    return list;
}
function dragonTick() {
    if (comboRunning() || goldenOnScreen()) return;
    if (cfg.AUTO_TRAIN_DRAGON && Game.dragonLevel < Game.dragonLevels.length - 1) {
        var lvl = Game.dragonLevel, step = Game.dragonLevels[lvl];
        if (step.cost()) {
            var sac = dragonSacrifice(lvl);
            step.buy();
            Game.dragonLevel = lvl + 1;
            if (Game.dragonLevel >= Game.dragonLevels.length - 1) Game.Win('Here be dragon');
            Game.recalculateGains = 1; Game.upgradesToRebuild = 1;
            for (var i = 0; i < sac.length; i++) buyBuilding(sac[i][0], sac[i][1]);
            log('Dragon trained to level ' + Game.dragonLevel);
        }
    }
    // Auras: set once, re-set only if something changed them
    var slots = Game.dragonLevel >= Game.dragonLevels.length - 1 ? 2 : 1;
    var want = [];
    for (var j = 0; j < cfg.DRAGON_AURAS.length && want.length < slots; j++) {
        var a = Game.dragonAurasBN[cfg.DRAGON_AURAS[j]];
        if (a && Game.dragonLevel >= a.id + 4) want.push(a.id);
    }
    var cur = [Game.dragonAura, Game.dragonAura2];
    for (var w = 0; w < want.length; w++) {
        if (cur.slice(0, slots).indexOf(want[w]) != -1) continue;
        for (var s = 0; s < slots; s++) {
            if (want.indexOf(cur[s]) == -1) {
                var hb = highestBuilding();
                if (s == 0) Game.dragonAura = want[w]; else Game.dragonAura2 = want[w];
                if (hb) { hb.sacrifice(1); buyBuilding(hb, 1); }
                cur[s] = want[w];
                Game.recalculateGains = 1;
                log('Dragon aura ' + (s + 1) + ' -> ' + Game.dragonAuras[want[w]].name);
                break;
            }
        }
    }
}

// ---------------------------------------------------------------------
// 5. Pantheon (slot once while swaps are available)
// ---------------------------------------------------------------------
function pantheonTick() {
    if (!cfg.AUTO_PANTHEON) return;
    var M = minigame('Temple');
    if (!M) return;
    var want = [cfg.PANTHEON.diamond, cfg.PANTHEON.ruby, cfg.PANTHEON.jade];
    for (var slot = 0; slot < 3; slot++) {
        var g = want[slot] && M.gods[want[slot]];
        if (!g || g.slot == slot) continue;
        if (M.swaps < 1) { note('pantheon', 'waiting for a worship swap'); return; }
        M.useSwap(1);
        M.lastSwapT = 0;
        M.slotGod(g, slot);
        if (M.draw) M.toRedraw = 1;
        log('Pantheon: ' + g.name + ' -> slot ' + (slot + 1));
        return; // one per tick
    }
}

// ---------------------------------------------------------------------
// 6. Shop: buildings and upgrades by payback period (real ΔCpS)
// ---------------------------------------------------------------------
function upgradeSkipped(u) {
    if (u.bought || u.pool == 'toggle' || u.pool == 'debug' || u.pool == 'prestige') return true;
    if (u.priceLumps) return true;
    if (u.choicesFunction) return true;
    if (cfg.UPGRADE_BLACKLIST.indexOf(u.name) != -1) return true;
    // Grandmapocalypse research only if we want it
    if (u.name == 'One mind' && cfg.ELDER_STAGE < 1) return true;
    if (u.name == 'Communal brainsweep' && cfg.ELDER_STAGE < 2) return true;
    if (u.name == 'Elder Pact' && cfg.ELDER_STAGE < 3) return true;
    if (u.clickFunction && ['One mind', 'Communal brainsweep', 'Elder Pact'].indexOf(u.name) == -1) return true;
    return false;
}

// value of production: CpS + clicks
function production() { return Game.cookiesPs + cfg.CLICKS_PER_SECOND * Game.computedMouseCps; }

function deltaBuilding(b) {
    var base = production();
    b.amount++; Game.CalculateGains();
    var d = production() - base;
    b.amount--; Game.CalculateGains();
    return d;
}
function deltaUpgrade(u) {
    var base = production();
    u.bought = 1; Game.CalculateGains();
    var d = production() - base;
    u.bought = 0; Game.CalculateGains();
    return d;
}

var PRIORITY_UPGRADES = Game.goldenCookieUpgrades.concat(['A festive hat', 'Elder spice',
    'Sacrilegious corruption', 'Wrinklerspawn', 'Dragon fang', 'Dragon teddy bear',
    'Green yeast digestives', 'Golden goose egg']);

function shopTick() {
    if (comboRunning() || Game.OnAscend) return;
    Game.CalculateGains();
    var cps = Math.max(Game.cookiesPs, 1e-9);
    for (var guard = 0; guard < 100; guard++) {
        var budget = Game.cookies - bankReserve();
        var best = null, bestPP = Infinity, kind = '';
        if (cfg.AUTO_BUY_UPGRADES) {
            for (var i = 0; i < Game.UpgradesInStore.length; i++) {
                var u = Game.UpgradesInStore[i];
                if (upgradeSkipped(u) || (u.canBuy && !u.canBuy())) continue;
                var price = u.getPrice();
                if (PRIORITY_UPGRADES.indexOf(u.name) != -1 ||
                    price < cps * cfg.CHEAP_UPGRADE_SECONDS) {
                    if (price <= budget) { best = u; bestPP = -1; kind = 'u'; break; }
                    continue;
                }
                var d = deltaUpgrade(u);
                if (d <= 0) continue;
                var pp = Math.max(0, price - budget) / cps + price / d;
                if (pp < bestPP) { bestPP = pp; best = u; kind = 'u'; }
            }
        }
        if (cfg.AUTO_BUY_BUILDINGS && bestPP >= 0) {
            for (var n in Game.Objects) {
                var b = Game.Objects[n];
                if (b.locked) continue;
                var bp = b.getPrice();
                var bd = deltaBuilding(b);
                if (bd <= 0) continue;
                var bpp = Math.max(0, bp - budget) / cps + bp / bd;
                if (bpp < bestPP) { bestPP = bpp; best = b; kind = 'b'; }
            }
        }
        if (!best) return;
        var cost = kind == 'u' ? best.getPrice() : best.getPrice();
        if (cost > budget) { note('shop', 'saving for ' + best.name + ' (' + Beautify(cost) + ')'); return; }
        if (kind == 'u') { best.buy(true); if (!best.bought) return; }
        else if (!buyBuilding(best, 1)) return;
        Game.CalculateGains();
        cps = Math.max(Game.cookiesPs, 1e-9);
        note('shop', 'bought ' + best.name);
    }
}

// Elder state: Pact (wrinklers) or Covenant
function elderTick() {
    if (cfg.ELDER_STAGE > 0 && Game.Has('Elder Covenant')) {
        var r = Game.Upgrades['Revoke Elder Covenant'];
        if (r.unlocked && !r.bought && Game.cookies > r.getPrice() * 2) { r.buy(true); log('Revoked the Elder Covenant'); }
    }
    if (cfg.ELDER_STAGE == 0 && !Game.Has('Elder Covenant')) {
        var c = Game.Upgrades['Elder Covenant'];
        if (c.unlocked && !c.bought && Game.cookies > c.getPrice() * 2) { c.buy(true); log('Signed the Elder Covenant'); }
    }
}

// ---------------------------------------------------------------------
// 7. Wrinklers: only popped for season drops (Halloween / Easter)
// ---------------------------------------------------------------------
function seasonNeedsWrinklerPops() {
    if (!cfg.POP_WRINKLERS_FOR_DROPS) return false;
    if (Game.season == 'halloween') return !allUnlocked(Game.halloweenDrops);
    if (Game.season == 'easter') return !allUnlocked(Game.easterEggs);
    return false;
}
function wrinklerTick() {
    if (!seasonNeedsWrinklerPops()) return;
    for (var i in Game.wrinklers) {
        var w = Game.wrinklers[i];
        // a pop is a drop roll: pop as soon as it ate something
        if (w.phase == 2 && w.type != 1 && w.sucked > Game.cookiesPs) w.hp = 0;
    }
}
A.popWrinklers = function () {
    for (var i in Game.wrinklers) {
        var w = Game.wrinklers[i];
        if (w.phase > 0 && w.type != 1) w.hp = 0;
    }
};

// ---------------------------------------------------------------------
// 8. Seasons
// ---------------------------------------------------------------------
function allUnlocked(list) {
    for (var i = 0; i < list.length; i++) if (!Game.HasUnlocked(list[i])) return false;
    return true;
}
function allBought(list) {
    for (var i = 0; i < list.length; i++) if (!Game.Has(list[i])) return false;
    return true;
}
function seasonDone(s) {
    if (s == 'valentines') return allBought(Game.heartDrops);
    if (s == 'christmas') return Game.santaLevel >= 14 && allUnlocked(Game.santaDrops) && allUnlocked(Game.reindeerDrops);
    if (s == 'easter') return allUnlocked(Game.easterEggs);
    if (s == 'halloween') return allUnlocked(Game.halloweenDrops);
    return true;
}
function finalSeason() {
    if (cfg.FINAL_SEASON != 'auto') return cfg.FINAL_SEASON;
    return Game.Has('Startrade') ? 'fools' : 'christmas';
}
function santaTick() {
    if (Game.season != 'christmas' || !Game.Has('A festive hat') || Game.santaLevel >= 14) return;
    var moni = Math.pow(Game.santaLevel + 1, Game.santaLevel + 1);
    if (Game.cookies - bankReserve() <= moni) return;
    Game.Spend(moni);
    Game.santaLevel = (Game.santaLevel + 1) % 15;
    if (Game.santaLevel == 14) Game.Unlock("Santa's dominion");
    var drops = [];
    for (var i in Game.santaDrops) if (!Game.HasUnlocked(Game.santaDrops[i])) drops.push(Game.santaDrops[i]);
    var drop = choose(drops);
    if (drop) Game.Unlock(drop);
    if (Game.santaLevel >= 6) Game.Win('Coming to town');
    if (Game.santaLevel >= 14) Game.Win('All hail Santa');
    log('Santa level ' + Game.santaLevel);
}
function seasonTick() {
    santaTick();
    if (!cfg.AUTO_SEASONS || !Game.Has('Season switcher') || comboRunning()) return;
    var target = null;
    for (var i = 0; i < cfg.SEASON_ORDER.length; i++) {
        if (!seasonDone(cfg.SEASON_ORDER[i])) { target = cfg.SEASON_ORDER[i]; break; }
    }
    if (!target) target = finalSeason();
    note('season', target + (Game.season == target ? '' : ' (switching)'));
    if (Game.season == target) return;
    var trig = Game.Upgrades[Game.seasons[target].trigger];
    if (!trig || !trig.unlocked) return;
    if (Game.cookies - bankReserve() < trig.getPrice()) return;
    trig.buy(true);
    log('Season -> ' + target);
}

// ---------------------------------------------------------------------
// 9. Garden: research every seed, then the bonus layout
// ---------------------------------------------------------------------
// layouts: 'line' = parents in rows 1 and 4 (A on even, B on odd columns),
// 'ring' = 4 empty centres surrounded by 8 parents, 'rows' = A in rows 0/3,
// B in rows 2/5, 'empty' = bare plot for weeds, 'meddle' = harvest old meddleweed
var RECIPES = [
    ['meddleweed', 'empty'],
    ['brownMold', 'meddle'], ['crumbspore', 'meddle'],
    ['thumbcorn', 'line', 'bakerWheat', 'bakerWheat'],
    ['bakeberry', 'line', 'bakerWheat', 'bakerWheat'],
    ['cronerice', 'line', 'bakerWheat', 'thumbcorn'],
    ['gildmillet', 'line', 'cronerice', 'thumbcorn'],
    ['clover', 'line', 'bakerWheat', 'gildmillet'],
    ['goldenClover', 'line', 'bakerWheat', 'gildmillet'],
    ['shimmerlily', 'line', 'clover', 'gildmillet'],
    ['elderwort', 'line', 'shimmerlily', 'cronerice'],
    ['whiteMildew', 'line', 'brownMold', 'brownMold'],
    ['chocoroot', 'line', 'bakerWheat', 'brownMold'],
    ['whiteChocoroot', 'line', 'chocoroot', 'whiteMildew'],
    ['queenbeet', 'line', 'chocoroot', 'bakeberry'],
    ['duketater', 'line', 'queenbeet', 'queenbeet'],
    ['queenbeetLump', 'ring', 'queenbeet', 'queenbeet'],
    ['greenRot', 'line', 'whiteMildew', 'clover'],
    ['keenmoss', 'line', 'greenRot', 'brownMold'],
    ['drowsyfern', 'line', 'chocoroot', 'keenmoss'],
    ['wardlichen', 'line', 'cronerice', 'whiteMildew'],
    ['glovemorel', 'line', 'crumbspore', 'thumbcorn'],
    ['cheapcap', 'line', 'crumbspore', 'shimmerlily'],
    ['doughshroom', 'line', 'crumbspore', 'crumbspore'],
    ['foolBolete', 'line', 'doughshroom', 'greenRot'],
    ['wrinklegill', 'line', 'crumbspore', 'brownMold'],
    ['whiskerbloom', 'line', 'shimmerlily', 'whiteChocoroot'],
    ['chimerose', 'line', 'shimmerlily', 'whiskerbloom'],
    ['nursetulip', 'line', 'whiskerbloom', 'whiskerbloom'],
    ['tidygrass', 'line', 'bakerWheat', 'whiteChocoroot'],
    ['everdaisy', 'rows', 'tidygrass', 'elderwort'],
    ['ichorpuff', 'line', 'elderwort', 'crumbspore'],
    ['shriekbulb', 'line', 'duketater', 'duketater']
];

// returns 6x6 array of plant keys (null = target / empty tile)
function layoutFor(type, a, b) {
    var L = [];
    for (var y = 0; y < 6; y++) { L.push([]); for (var x = 0; x < 6; x++) L[y].push(null); }
    if (type == 'line') {
        for (var x2 = 0; x2 < 6; x2++) { L[1][x2] = x2 % 2 == 0 ? a : b; L[4][x2] = x2 % 2 == 0 ? a : b; }
    } else if (type == 'ring') {
        for (var y3 = 0; y3 < 6; y3++) for (var x3 = 0; x3 < 6; x3++) L[y3][x3] = a;
        L[1][1] = L[1][4] = L[4][1] = L[4][4] = null;
    } else if (type == 'rows') {
        for (var x4 = 0; x4 < 6; x4++) { L[0][x4] = a; L[3][x4] = a; L[2][x4] = b; L[5][x4] = b; }
    } else if (type == 'fill') {
        for (var y5 = 0; y5 < 6; y5++) for (var x5 = 0; x5 < 6; x5++) L[y5][x5] = a;
    }
    return L;
}

function setSoil(G, key) {
    var s = G.soils[key];
    if (!s || G.freeze || G.soil == s.id || G.nextSoil > Date.now() || G.parent.amount < s.req) return;
    G.nextSoil = Date.now() + (Game.Has('Turbo-charged soil') ? 1 : 1000 * 60 * 10);
    G.toCompute = true; G.soil = s.id; G.computeStepT();
    for (var i in G.soils) {
        var it = G.soils[i], el = l('gardenSoil-' + it.id);
        if (el) { if (it.id == G.soil) el.classList.add('on'); else el.classList.remove('on'); }
    }
}

function cheapToPlant(G, plant) {
    if (cpsBuffMult() > 1.0001) return false;              // seed price follows current CpS
    return G.getCost(plant) <= Game.cookies * cfg.GARDEN_MAX_SEED_BANK_FRACTION && G.canPlant(plant);
}
function plantAt(G, x, y, key) {
    var p = G.plants[key];
    if (!p || !p.unlocked || !cheapToPlant(G, p)) return false;
    G.useTool(p.id, x, y);
    return true;
}

function gardenTick() {
    if (!cfg.AUTO_GARDEN) return;
    var G = minigame('Farm');
    if (!G || G.freeze) return;
    if (G.plantsUnlockedN < G.plantsN) gardenResearch(G);
    else gardenBonus(G);
}

function currentRecipe(G) {
    for (var i = 0; i < RECIPES.length; i++) {
        var r = RECIPES[i], target = G.plants[r[0]];
        if (!target || target.unlocked) continue;
        if (r[1] == 'meddle') { if (G.plants.meddleweed.unlocked) return r; continue; }
        if (r[1] == 'empty') return r;
        if (G.plants[r[2]].unlocked && G.plants[r[3]].unlocked) return r;
    }
    return null;
}

function gardenResearch(G) {
    var r = currentRecipe(G);
    if (!r) return;
    note('garden', 'researching ' + G.plants[r[0]].name);
    var L = (r[1] == 'empty' || r[1] == 'meddle') ? layoutFor('none') : layoutFor(r[1], r[2], r[3]);
    var allParentsMature = true, anyParent = false;
    for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) {
        if (!G.isTileUnlocked(x, y)) continue;
        var tile = G.plot[y][x], want = L[y][x];
        var plant = tile[0] > 0 ? G.plantsById[tile[0] - 1] : null;
        if (plant && !plant.unlocked) {
            // a new seed: let it mature, then harvest to unlock it
            if (tile[1] >= plant.mature) { G.harvest(x, y); log('Garden: unlocked ' + plant.name); }
            continue;
        }
        if (r[1] == 'meddle' && plant && plant.key == 'meddleweed') {
            // harvesting old meddleweed may leave brown mold / crumbspore behind
            if (tile[1] + Math.ceil(plant.ageTick + plant.ageTickR) >= 100) G.harvest(x, y);
            continue;
        }
        if (r[1] == 'empty' && plant && plant.key == 'meddleweed') continue;
        if (want) {
            anyParent = true;
            if (plant && plant.key == want) { if (tile[1] < plant.mature) allParentsMature = false; continue; }
            if (plant) G.harvest(x, y);
            allParentsMature = false;
            plantAt(G, x, y, want);
        } else if (plant) {
            // target tile holding a known plant: clear it
            G.harvest(x, y);
        }
    }
    if (r[1] == 'empty' || r[1] == 'meddle') setSoil(G, 'fertilizer');
    else setSoil(G, anyParent && allParentsMature && G.parent.amount >= 300 ? 'woodchips' : 'fertilizer');
}

function gardenBonus(G) {
    var key = cfg.GARDEN_BONUS_PLANT, p = G.plants[key];
    if (!p || !p.unlocked) return;
    var harvestPlant = ['bakeberry', 'queenbeet', 'duketater', 'chocoroot', 'whiteChocoroot'].indexOf(key) != -1;
    setSoil(G, harvestPlant ? 'fertilizer' : 'clay');
    note('garden', 'bonus: ' + p.name);
    for (var y = 0; y < 6; y++) for (var x = 0; x < 6; x++) {
        if (!G.isTileUnlocked(x, y)) continue;
        var tile = G.plot[y][x];
        var plant = tile[0] > 0 ? G.plantsById[tile[0] - 1] : null;
        if (!plant) { plantAt(G, x, y, key); continue; }
        if (plant.key != key) { G.harvest(x, y); continue; }
        if (harvestPlant && tile[1] >= plant.mature) {
            // harvest during combos, or when the bank cap binds anyway, or before it dies
            var dying = tile[1] + Math.ceil(plant.ageTick + plant.ageTickR) >= 100;
            if (cpsBuffMult() >= 50 || dying) G.harvest(x, y);
        }
    }
}

// ---------------------------------------------------------------------
// 10. Stock market
// ---------------------------------------------------------------------
function marketTick() {
    if (!cfg.AUTO_MARKET) return;
    var M = minigame('Bank');
    if (!M) return;
    if (cfg.MARKET_HIRE_BROKERS && M.brokers < M.getMaxBrokers() &&
        M.getBrokerPrice() < (Game.cookies - bankReserve()) * 0.1) {
        Game.Spend(M.getBrokerPrice()); M.brokers++;
    }
    for (var i = 0; i < M.goodsById.length; i++) {
        var g = M.goodsById[i];
        if (!g.active) continue;
        var rest = M.getRestingVal(i);
        var lo = Math.max(1, rest * (cfg.MARKET_BUY_BELOW[i] || 0.3)), hi = rest * (cfg.MARKET_SELL_ABOVE[i] || 1.0);
        if (g.val >= hi && g.stock > 0) { M.sellGood(i, g.stock); continue; }
        if (g.val <= lo) {
            var room = M.getGoodMaxStock(g) - g.stock;
            if (room <= 0) continue;
            var unit = Game.cookiesPsRawHighest * g.val * (1 + 0.01 * (20 * Math.pow(0.95, M.brokers)));
            var n = Math.min(room, Math.floor(Math.max(0, Game.cookies - bankReserve()) / unit));
            if (n > 0) M.buyGood(i, n);
        }
    }
}

// ---------------------------------------------------------------------
// 11. Sugar lumps
// ---------------------------------------------------------------------
function lumpTick() {
    if (!cfg.AUTO_LUMPS || !Game.canLumps()) return;
    var age = Date.now() - Game.lumpT;
    if (age < Game.lumpRipeAge) return;
    var t = Game.lumpCurrentType;
    if (t == 0 || t == 1 || t == 4) { Game.clickLump(); return; }
    var late = age > Game.lumpOverripeAge - 60000;
    if (t == 2) {
        // golden: doubles the bank, capped at 24 h of *current* CpS -> best during a combo
        if (late || Game.cookiesPs * 86400 >= Game.cookies) Game.clickLump();
        return;
    }
    if (late) Game.clickLump();     // meaty: wait as long as possible
}

// ---------------------------------------------------------------------
// Status panel and snapshot
// ---------------------------------------------------------------------
var panel = null;
function panelTick() {
    if (!cfg.SHOW_PANEL) { if (panel) { panel.remove(); panel = null; } return; }
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'ccautoPanel';
        panel.style.cssText = 'position:fixed;left:4px;bottom:4px;z-index:100000000;background:rgba(0,0,0,0.75);' +
            'color:#fff;font:11px monospace;padding:4px 6px;border-radius:4px;pointer-events:none;max-width:360px;';
        document.body.appendChild(panel);
    }
    var wr = 0;
    for (var i in Game.wrinklers) if (Game.wrinklers[i].phase == 2) wr += Game.wrinklers[i].sucked;
    var lines = [
        'CCAuto  bank ' + Beautify(Game.cookies) + '  reserve ' + Beautify(bankReserve()),
        'wrinklers hold ' + Beautify(wr) + '  buffs x' + Beautify(cpsBuffMult(), 1) + ' cps, x' + Beautify(clickBuffMult(), 1) + ' click'
    ];
    for (var k in stateText) lines.push(k + ': ' + stateText[k]);
    panel.innerHTML = lines.join('<br>');
}

A.status = function () { console.log(panel ? panel.innerText : JSON.stringify(stateText)); };

A.snapshot = function () {
    var M = minigame('Wizard tower');
    var ra = 1 + Game.auraMult('Radiant Appetite');
    var base = Game.unbuffedCps / ra;
    var amounts = [];
    for (var i in Game.Objects) if (Game.Objects[i].amount >= 10) amounts.push(Game.Objects[i].amount);
    var top = highestBuilding(), t = towers();
    var batchPrice = 0, batch = godzBatch();
    for (var j = 0; j < batch.length; j++) batchPrice += batch[j][0].getReverseSumPrice(batch[j][1]) / batch[j][0].getSellMultiplier();
    var snap = {
        bank0_s: Game.cookies / base,
        click_frac: Game.computedMouseCps / clickBuffMult() / Math.max(Game.cookiesPs, 1e-9),
        milk: Game.AchievementsOwned / 25,
        building_amounts: amounts,
        wizard_towers: t.amount, wizard_level: t.level,
        tower_price_s: t.getPrice() / base,
        top_building_price_s: top ? top.getPrice() / base : 0,
        godz_batch: cfg.GODZ_BATCH,
        godz_batch_price_s: batchPrice / base,
        wrinklers_max: Game.getWrinklersMax() - Math.round(Game.auraMult('Dragon Guts') * 2)
    };
    var s = JSON.stringify(snap);
    console.log(s);
    return snap;
};

// ---------------------------------------------------------------------
// Start / stop
// ---------------------------------------------------------------------
function safe(fn, name) {
    return function () {
        try { fn(); } catch (e) { console.warn('[CCAuto] ' + name + ': ' + e); }
    };
}

A.start = function () {
    A.stop();
    var P = cfg.PANTHEON || {};
    if (cfg.DRAGON_AURAS.indexOf('Dragon Orbs') != -1 && cfg.AUTO_PANTHEON &&
        (P.diamond == 'ruin' || P.ruby == 'ruin' || P.jade == 'ruin'))
        console.warn('[CCAuto] Dragon Orbs never work while Godzamok is slotted - pick one of them');
    if (cfg.MUTE_GC_CHIME) Game.chimeType = 0;
    timers.push(setInterval(safe(clickTick, 'click'), 25));
    timers.push(setInterval(safe(function () {
        orbsTick(); shimmerTick(); grimoireTick(); godzamokTick(); loanTick(); shimmerTick();
    }, 'combo'), 100));
    timers.push(setInterval(safe(function () {
        wrinklerTick(); lumpTick(); dragonTick(); pantheonTick(); elderTick(); seasonTick();
    }, 'misc'), 1000));
    timers.push(setInterval(safe(shopTick, 'shop'), 2000));
    timers.push(setInterval(safe(gardenTick, 'garden'), 5000));
    timers.push(setInterval(safe(marketTick, 'market'), 10000));
    timers.push(setInterval(safe(panelTick, 'panel'), 500));
    log('started');
};
A.stop = function () {
    while (timers.length) clearInterval(timers.pop());
    if (panel) { panel.remove(); panel = null; }
};

// internals, for tests
A._t = {fthofOutcome: fthofOutcome, doubleCast: doubleCast, godzamokTick: godzamokTick,
    orbsTick: orbsTick, gardenTick: gardenTick, marketTick: marketTick, seasonTick: seasonTick,
    shopTick: shopTick, pantheonTick: pantheonTick, dragonTick: dragonTick, grimoireTick: grimoireTick,
    wrinklerTick: wrinklerTick, lumpTick: lumpTick, elderTick: elderTick, bankReserve: bankReserve,
    godzRoundCost: godzRoundCost, state: stateText};

A.start();
})();
