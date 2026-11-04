"""Golden cookie / combo simulator for late-game Cookie Clicker.

All formulas are taken from the live game source (orteil.dashnet.org/cookieclicker,
main.js + minigameGrimoire/Garden/Pantheon). Every cookie amount is expressed in
"seconds of base CpS": base CpS = 1 is the production without Radiant Appetite,
garden, pantheon, buffs and Dragon's Fortune. The result of a run is the average
production multiplier over the simulated time (total cookies gained / seconds).

The simulation steps in 1 s increments while something is going on (buffs,
golden cookies on screen) and jumps ahead when nothing can happen.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

FPS = 30

# Kitten upgrades (milk factors), incl. Fortune #103
KITTENS = [0.1, 0.125, 0.15, 0.175, 0.2, 0.2, 0.2, 0.2, 0.2, 0.175, 0.15, 0.125,
           0.115, 0.11, 0.105, 0.1, 0.05]

# Garden plants: cost (minutes of CpS), ageTick, ageTickR, mature, immortal
PLANTS = {
    'bakerWheat':   dict(cost=1,   at=7,   atr=2,   mature=35),
    'goldenClover': dict(cost=125, at=4,   atr=12,  mature=50),
    'shimmerlily':  dict(cost=60,  at=5,   atr=6,   mature=70),
    'elderwort':    dict(cost=180, at=0.3, atr=0.5, mature=90, immortal=True),
    'whiskerbloom': dict(cost=20,  at=2,   atr=2,   mature=60),
    'bakeberry':    dict(cost=45,  at=1,   atr=1,   mature=50, harvest=(0.03, 30 * 60)),
    'queenbeet':    dict(cost=90,  at=1,   atr=0.4, mature=80, harvest=(0.04, 60 * 60)),
    'duketater':    dict(cost=480, at=0.4, atr=0.1, mature=95, harvest=(0.08, 2 * 60 * 60)),
}
SOIL = {'clay': (15 * 60, 1.25), 'fertilizer': (3 * 60, 0.75)}

AURAS = ['RA', 'Fortune', 'Flight', 'Orbs', 'ES', 'RB', 'Guts', 'BoM', 'Epoch', 'AM', 'Reaper',
         'Arcane', 'SI']
# dragon aura ids (for Reality Bending: only auras the dragon knows count; we assume
# a fully trained dragon, so all of them)

PANTHEON = {
    # name: {god: slot}  slot 1 = diamond, 2 = ruby, 3 = jade
    'none': {},
    'Godz-Moka-Muri': {'ruin': 1, 'mother': 2, 'labor': 3},
    'Moka-Godz-Muri': {'mother': 1, 'ruin': 2, 'labor': 3},
    'Godz-Vomi-Moka': {'ruin': 1, 'decadence': 2, 'mother': 3},
    'Moka-Vomi-Jere': {'mother': 1, 'decadence': 2, 'industry': 3},
}

GOOD_FTHOF = {'click frenzy', 'building special', 'cookie storm', 'blood frenzy'}


@dataclass
class Params:
    days: float = 2.0
    bank0_s: float = 86400.0            # starting bank, seconds of base CpS
    clicks_per_s: float = 10.0
    click_frac: float = 0.44            # cookies per click / cookiesPs (no click buffs)
    milk: float = 24.0                  # achievements / 25
    building_amounts: tuple = (1000, 900, 800, 780, 760, 740, 720, 700, 680, 660, 640, 620,
                               600, 580, 560, 540, 520, 500, 480, 460)
    wizard_towers: int = 600
    wizard_level: int = 10
    tower_price_s: float = 0.01         # price of 1 wizard tower in s of base CpS
    top_building_price_s: float = 10.0  # price of 1 most powerful building (Dragon Orbs)
    godz_batch: int = 1000              # buildings sold per Godzamok round
    godz_batch_price_s: float = 1.0     # buy-back price of one such batch
    godz_max_rounds: int = 30
    wrinklers_max: int = 12             # 10 + Elder spice
    gc_eff_dur: float = 2 * 1.1 * 1.01 ** 4      # Get lucky, Lasting fortune, digits, GYD
    gc_life: float = 13 * 2 * 2 * 1.05 * 1.01 ** 3  # Lucky day, Serendipity, Decisive fate, digits
    gc_time_mod: float = 0.25 * 0.95 * 0.95 * 0.99  # Lucky day, Serendipity, goose egg, h. luck, GYD
    gc_gain_mult: float = 1.03 * 1.01   # Dragon fang, GYD
    loans: bool = True                  # loan 2 (pawnshop) available
    seed: int = 1


@dataclass
class Strategy:
    auras: tuple = ('RA', 'Flight')
    elder: int = 3                      # 0 = Elder Covenant, 1..3 grandmapocalypse stage
    garden: str = 'none'
    grimoire: str = 'forecast_double'   # none / blind / forecast / forecast_double
    combo_thr: float = 7.0              # CpS buff product needed to fire a combo
    hold_gc: bool = False               # keep golden cookies on screen (Dragon's Fortune)
    pantheon: str = 'none'
    loan2: bool = False
    godz: bool = True                   # use Godzamok rounds if he is slotted
    orbs_max_cost_s: float = 1e18       # max cookies per Orbs attempt

    def label(self):
        return (f"{'+'.join(self.auras)} | elder{self.elder} | {self.garden} | {self.grimoire}"
                f"@{self.combo_thr:g} | hold={int(self.hold_gc)} | {self.pantheon}"
                f" | loan2={int(self.loan2)}")


class Sim:
    def __init__(self, p: Params, s: Strategy):
        self.p, self.s = p, s
        self.rng = random.Random(p.seed * 7919 + 17)      # golden cookies
        self.grng = random.Random(p.seed * 15485863 + 5)  # garden
        self.wrng = random.Random(p.seed * 32452843 + 9)  # wrinklers, orbs, timers
        self.spell_seed = p.seed * 104729 + 3
        self.t = 0.0
        self.T = p.days * 86400
        self.bank = p.bank0_s
        self.costs = 0.0
        self.stats = {}

        a = set(s.auras)
        rb = 0.1 if 'RB' in a else 0.0
        self.aura = {k: (1.0 if k in a else 0.0) + (rb if k != 'RB' else 0.0) for k in AURAS}
        gods = PANTHEON[s.pantheon]
        self.god = gods

        def god(name, v1, v2, v3, default):
            lvl = gods.get(name)
            return {1: v1, 2: v2, 3: v3}.get(lvl, default)

        # ---- static multipliers ----
        milk_mult = 1.05 * (1 + self.aura['BoM'] * 0.05) * god('mother', 1.1, 1.05, 1.03, 1.0)
        eff = dict(cps=1.0, milk=1.0, gcFreq=1.0, gcGain=1.0, gcEffDur=1.0, gcDur=1.0,
                   wrathFreq=1.0, wrathGain=1.0)
        self.garden = None
        if s.garden != 'none':
            self.garden = Garden(self, s.garden)
        self.eff = eff
        self.milk_mult = milk_mult
        self.base_static = (1 + self.aura['RA']) * (0.95 if s.elder == 0 else 1.0)
        self.base_static *= god('labor', 0.97, 0.98, 0.99, 1.0)
        self.base_static *= god('industry', 1.1, 1.06, 1.03, 1.0)
        self.base_static *= god('decadence', 0.93, 0.95, 0.98, 1.0)
        self.click_static = god('labor', 1.15, 1.1, 1.05, 1.0)
        self.time_god = god('industry', 1.1, 1.06, 1.03, 1.0) * god('mother', 1.15, 1.1, 1.05, 1.0)
        self.dur_god = god('decadence', 1.07, 1.05, 1.02, 1.0)
        self.godz_lvl = gods.get('ruin', 0) if s.godz else 0
        self.sell_mult = 0.25 * (1 + self.aura['ES'])

        # ---- shimmers ----
        self.gcs = []          # dicts: wrath, life, force, lead
        self.spawned = False
        self.last_choice = ''
        self.next_spawn = self.t + self._sample_spawn(False)

        # ---- buffs: name -> [time, multCpS, multClick] ----
        self.buffs = {}
        self.cursed_arg = 0.0

        # ---- grimoire ----
        self.magicM_full = self.magic_max(p.wizard_towers)
        self.magic = self.magicM_full
        self.cast_index = 0
        self._spell_cache = {}

        # ---- wrinklers ----
        n = p.wrinklers_max + round(self.aura['Guts'] * 2)
        self.wr_n = min(14, n) if s.elder > 0 else 0
        self.wr_rate = 0.05 * (1 + self.aura['Guts'] * 0.2)
        self.wr_payout = 1.1 * 1.05 * 1.05 * (1 + self.aura['Guts'] * 0.2)
        self.wr_eating = self.wr_n      # start with all wrinklers attached
        self.wr_sucked = 0.0

        self.gained_storm = 0.0

    # ------------------------------------------------------------------ helpers
    def kitten_factor(self):
        m = self.milk_mult * self.eff['milk']
        f = 1.0
        for k in KITTENS:
            f *= (1 + self.p.milk * k * m) / (1 + self.p.milk * k * 1.05)
        return f

    def magic_max(self, towers):
        towers = max(towers, 1)
        lvl = max(self.p.wizard_level, 1)
        return math.floor(4 + towers ** 0.6 + math.log((towers + (lvl - 1) * 10) / 15 + 1) * 15)

    def spell_cost(self, cost_min, pct, magicM):
        return math.floor((cost_min + magicM * pct) * (1 - 0.1 * self.aura['SI']))

    def _sample_spawn(self, wrath):
        m = self.p.gc_time_mod * (1 - self.aura['Arcane'] * 0.05) * self.time_god
        if wrath:
            m /= self.eff.get('wrathFreq', 1.0) if hasattr(self, 'eff') else 1.0
        else:
            m /= self.eff.get('gcFreq', 1.0) if hasattr(self, 'eff') else 1.0
        tmin, tmax = 5 * 60 * m, 15 * 60 * m
        e = self.wrng.expovariate(1.0)
        x = (6 * e / (FPS * (tmax - tmin))) ** (1 / 6)
        return tmin + min(x, 1.0) * (tmax - tmin)

    def cps_mult_buffs(self):
        m = 1.0
        for b in self.buffs.values():
            m *= b[1]
        return m

    def click_mult_buffs(self):
        m = 1.0
        for b in self.buffs.values():
            m *= b[2]
        return m

    def cookies_ps(self):
        n = len(self.gcs)
        df = (1 + self.aura['Fortune'] * 1.23) ** n
        gm = self.eff['cps'] * self.kitten_factor_cached
        return self.base_static * gm * self.cps_mult_buffs() * df

    def gain(self, x, key):
        self.bank += x
        self.stats[key] = self.stats.get(key, 0.0) + x

    def spend(self, x, key):
        self.bank -= x
        self.costs += x
        self.stats['cost:' + key] = self.stats.get('cost:' + key, 0.0) + x

    def add_buff(self, name, time, cps=1.0, click=1.0):
        if name in self.buffs:
            self.buffs[name][0] += time
        else:
            self.buffs[name] = [time, cps, click]

    # ------------------------------------------------------------- golden cookies
    def spawn_gc(self, lead, force=None, wrath=None):
        if wrath is None:
            e = self.s.elder
            wrath = (e == 3) or (e == 2 and self.rng.random() < 2 / 3) or \
                    (e == 1 and self.rng.random() < 1 / 3)
        n = len(self.gcs) + 1
        life = self.p.gc_life * self.eff['gcDur'] * 0.95 ** (n - 1)
        self.gcs.append(dict(wrath=wrath, life=life, force=force, lead=lead))
        self.stats['gc_spawned'] = self.stats.get('gc_spawned', 0) + 1

    def gc_die(self, gc):
        self.gcs.remove(gc)
        if gc['lead']:
            self.spawned = False
            self.next_spawn = self.t + self._sample_spawn(gc['wrath'])

    def pop_gc(self, gc):
        r = self.rng.random
        wrath = gc['wrath']
        if gc['force']:
            choice = gc['force']
        else:
            lst = ['clot', 'multiply cookies', 'ruin cookies'] if wrath else ['frenzy', 'multiply cookies']
            if wrath and r() < 0.3:
                lst += ['blood frenzy', 'chain cookie', 'cookie storm']
            elif r() < 0.03:
                lst += ['chain cookie', 'cookie storm']
            if r() < 0.1 and (r() < 0.05 or 'Dragonflight' not in self.buffs):
                lst.append('click frenzy')
            if wrath and r() < 0.1:
                lst.append('cursed finger')
            if r() < 0.25:
                lst.append('building special')
            if (not wrath and r() < 0.15) or r() < 0.05:
                if r() < self.aura['Reaper']:
                    lst.append('dragon harvest')
                if r() < self.aura['Flight']:
                    lst.append('dragonflight')
            if self.last_choice and r() < 0.8 and self.last_choice in lst:
                lst = [c for c in lst if c != self.last_choice]
            if r() < 0.0001:
                lst.append('blab')
            choice = self.rng.choice(lst) if lst else 'frenzy'
        self.last_choice = choice
        self.gc_die(gc)
        self.apply_effect(choice, wrath)

    def apply_effect(self, choice, wrath):
        p = self.p
        edm = p.gc_eff_dur * (1 + self.aura['Epoch'] * 0.05) * self.dur_god * self.eff['gcEffDur']
        mult = p.gc_gain_mult
        if wrath:
            mult *= self.eff['wrathGain']
        else:
            mult *= (1 + self.aura['AM'] * 0.1) * self.eff['gcGain']
        cps = self.cookies_ps()
        self.stats['eff:' + choice] = self.stats.get('eff:' + choice, 0) + 1
        if choice == 'frenzy':
            self.add_buff('Frenzy', math.ceil(77 * edm), 7)
        elif choice == 'blood frenzy':
            self.add_buff('Elder frenzy', math.ceil(6 * edm), 666)
        elif choice == 'clot':
            self.add_buff('Clot', math.ceil(66 * edm), 0.5)
        elif choice == 'dragon harvest':
            self.add_buff('Dragon Harvest', math.ceil(60 * edm), 15)
        elif choice == 'click frenzy':
            self.add_buff('Click frenzy', math.ceil(13 * edm), 1, 777)
        elif choice == 'dragonflight':
            self.add_buff('Dragonflight', math.ceil(10 * edm), 1, 1111)
            if self.rng.random() < 0.8:
                self.buffs.pop('Click frenzy', None)
        elif choice == 'building special':
            i = self.rng.randrange(len(p.building_amounts))
            pw = p.building_amounts[i] / 10 + 1
            if wrath and self.rng.random() < 0.3:
                self.add_buff(f'debuff{i}', math.ceil(30 * edm), 1 / pw)
            else:
                self.add_buff(f'bs{i}', math.ceil(30 * edm), pw)
        elif choice == 'multiply cookies':
            self.gain(mult * min(self.bank * 0.15, cps * 900) + 13, 'lucky')
        elif choice == 'ruin cookies':
            x = min(self.bank, min(self.bank * 0.05, cps * 600) + 13)
            self.spend(x, 'ruin')
        elif choice == 'cursed finger':
            d = math.ceil(10 * edm)
            self.add_buff('Cursed finger', d, 0.0)
            self.cursed_arg = cps * d
        elif choice == 'cookie storm':
            self.add_buff('Cookie storm', math.ceil(7 * edm), 1, 1)
        elif choice == 'cookie storm drop':
            self.gain(mult * cps * 60 * self.rng.randint(1, 7), 'storm')
        elif choice == 'chain cookie':
            cap = min(cps * 6 * 3600, self.bank * 0.5) * mult
            self.gain(1.11 * cap, 'chain')

    # --------------------------------------------------------------- grimoire
    def _spell_rolls(self, idx):
        if idx not in self._spell_cache:
            r = random.Random(f'{self.spell_seed}/{idx}')
            self._spell_cache[idx] = [r.random() for _ in range(8)]
        return self._spell_cache[idx]

    def fthof_outcome(self, idx, n_on_screen):
        """Outcome of Force the Hand of Fate cast at spell index idx (game logic)."""
        u, a, b, c, d, e, f, g = self._spell_rolls(idx)
        fail = 0.15 * (1 + 0.1 * self.aura['SI']) + 0.15 * n_on_screen
        if u < 1 - fail:
            ch = ['frenzy', 'multiply cookies']
            if 'Dragonflight' not in self.buffs:
                ch.append('click frenzy')
            if a < 0.1:
                ch += ['cookie storm', 'cookie storm', 'blab']
            if b < 0.25:
                ch.append('building special')
            if c < 0.15:
                ch = ['cookie storm drop']
            if d < 0.0001:
                ch.append('free sugar lump')
            return ch[int(e * len(ch))], False
        ch = ['clot', 'ruin cookies']
        if a < 0.1:
            ch += ['cursed finger', 'blood frenzy']
        if b < 0.003:
            ch.append('free sugar lump')
        if c < 0.1:
            ch = ['blab']
        return ch[int(d * len(ch))], True

    def spell_fails(self, idx):
        u = self._spell_rolls(idx)[0]
        return u >= 1 - 0.15 * (1 + 0.1 * self.aura['SI'])

    def cast_fthof(self):
        out, wrath = self.fthof_outcome(self.cast_index, len(self.gcs))
        self.cast_index += 1
        self.stats['fthof'] = self.stats.get('fthof', 0) + 1
        self.spawn_gc(False, force=out, wrath=wrath)
        return self.gcs[-1]

    def grimoire_step(self):
        s = self.s
        if s.grimoire == 'none':
            return
        M = self.magicM_full
        cost = self.spell_cost(10, 0.6, M)
        if s.grimoire == 'blind':
            if self.magic >= cost:
                self.magic -= cost
                gc = self.cast_fthof()
                self.pop_gc(gc)
            return
        # forecast based
        n = len(self.gcs)
        P = self.cps_mult_buffs()
        nxt, _ = self.fthof_outcome(self.cast_index, n)
        good = nxt in GOOD_FTHOF or (nxt == 'frenzy' and 'Frenzy' not in self.buffs)
        if P >= s.combo_thr and good and self.magic >= cost:
            self.magic -= cost
            self.pop_gc(self.cast_fthof())
            if s.grimoire == 'forecast_double':
                nxt2, _ = self.fthof_outcome(self.cast_index, len(self.gcs))
                good2 = nxt2 in GOOD_FTHOF or (nxt2 == 'frenzy' and 'Frenzy' not in self.buffs)
                if good2:
                    T = self.p.wizard_towers
                    keep = T
                    while keep > 1 and self.spell_cost(10, 0.6, self.magic_max(keep)) > self.magic:
                        keep = max(1, int(keep * 0.9) if keep > 50 else keep - 1)
                    c2 = self.spell_cost(10, 0.6, self.magic_max(keep))
                    if c2 <= self.magic:
                        sold = T - keep
                        self.spend(sold * self.p.tower_price_s * (1 - self.sell_mult), 'towers')
                        self.magic -= c2
                        self.pop_gc(self.cast_fthof())
            return
        # nothing to fire: advance past bad outcomes while magic is (nearly) full
        if not good and self.magic >= M - 1:
            if self.spell_fails(self.cast_index):
                c = self.spell_cost(20, 0.1, M)        # Resurrect Abomination: pops a wrinkler
                if self.magic >= c:
                    self.magic -= c
                    self.cast_index += 1
                    if self.wr_eating > 0:
                        self.pop_wrinklers(1)
            else:
                c = self.spell_cost(10, 0.1, M)        # Haggler's Charm: 60 s harmless buff
                if self.magic >= c:
                    self.magic -= c
                    self.cast_index += 1
                    self.add_buff("Haggler's luck", 60)
            self.stats['skips'] = self.stats.get('skips', 0) + 1

    def regen_magic(self, dt):
        M = self.magicM_full
        if self.magic >= M:
            return
        mx = max(M, 100)
        if self.magic < 4e-6 * mx:
            self.magic += 0.002 * 0.002 * FPS * dt
            return
        sq = math.sqrt(self.magic) + 0.03 * dt / math.sqrt(mx)
        self.magic = min(M, sq * sq)

    def time_to_full_magic(self):
        M = self.magicM_full
        if self.magic >= M:
            return math.inf
        mx = max(M, 100)
        return max(1.0, (math.sqrt(M) - math.sqrt(max(self.magic, 1e-9))) * math.sqrt(mx) / 0.03)

    # --------------------------------------------------------------- wrinklers
    def pop_wrinklers(self, k):
        k = min(k, self.wr_eating)
        if k <= 0:
            return
        share = self.wr_sucked * k / self.wr_eating
        self.wr_sucked -= share
        self.gain(share * self.wr_payout, 'wrinklers')
        self.wr_eating -= k
        self.stats['wr_popped'] = self.stats.get('wr_popped', 0) + k

    def respawn_wrinklers(self, dt):
        missing = self.wr_n - self.wr_eating
        if missing <= 0:
            return
        rate = 0.00001 * self.s.elder * FPS          # per second per slot
        pr = 1 - math.exp(-rate * dt)
        for _ in range(missing):
            if self.wrng.random() < pr:
                self.wr_eating += 1

    # --------------------------------------------------------------- abilities
    def try_orbs(self):
        if self.aura['Orbs'] <= 0 or self.buffs or self.gcs:
            return
        # Godzamok (any slot) grants Devastation on every sale *before* the game
        # checks Dragon Orbs' "no buffs" condition, so the wish can never happen.
        if 'ruin' in self.god:
            return
        cost = self.p.top_building_price_s * (1 - self.sell_mult)
        if cost > self.s.orbs_max_cost_s:
            return
        pr = self.aura['Orbs'] * 0.1
        tries = 1
        while self.wrng.random() >= pr and tries < 1000:
            tries += 1
        self.spend(tries * cost, 'orbs')
        self.stats['orb_gc'] = self.stats.get('orb_gc', 0) + 1
        self.spawn_gc(False)

    def try_godzamok(self):
        if not self.godz_lvl or 'Devastation' in self.buffs:
            return
        if self.click_mult_buffs() < 100:
            return
        per = {1: 0.01, 2: 0.005, 3: 0.0025}[self.godz_lvl]
        cost = self.p.godz_batch_price_s * (1 - self.sell_mult)
        rounds = self.p.godz_max_rounds
        if cost > 0:
            rounds = int(min(rounds, max(0, self.bank * 0.5) / cost))
        if rounds <= 0:
            return
        self.spend(rounds * cost, 'godzamok')
        self.add_buff('Devastation', 10, 1, 1 + per * self.p.godz_batch * rounds)

    def try_loan2(self):
        if not (self.s.loan2 and self.p.loans) or 'Loan 2' in self.buffs or 'Loan 2 (interest)' in self.buffs:
            return
        if self.cps_mult_buffs() * self.click_mult_buffs() < 1e5:
            return
        self.spend(self.bank * 0.4, 'loan2')
        self.add_buff('Loan 2', 40, 2.0)
        self.loan2_pending = True

    # --------------------------------------------------------------- main loop
    def idle(self):
        return not self.buffs and not self.gcs

    def run(self):
        p, s = self.p, self.s
        self.kitten_factor_cached = self.kitten_factor()
        if self.garden:
            self.garden.apply()
            self.kitten_factor_cached = self.kitten_factor()
        self.next_spawn = self.t + self._sample_spawn(s.elder == 3)
        self.loan2_pending = False
        while self.t < self.T:
            # natural spawn
            if not self.spawned and self.t >= self.next_spawn:
                self.spawn_gc(True)
                self.spawned = True
            self.try_orbs()
            # pop golden cookies
            for gc in list(self.gcs):
                if s.hold_gc and gc['force'] is None and gc['life'] > 1.5:
                    continue
                self.pop_gc(gc)
            self.try_orbs()
            for gc in list(self.gcs):
                if not (s.hold_gc and gc['force'] is None and gc['life'] > 1.5):
                    self.pop_gc(gc)
            self.grimoire_step()
            self.try_godzamok()
            self.try_loan2()
            if self.garden:
                self.garden.act()

            # step length
            if self.idle() and (self.aura['Orbs'] <= 0 or 'ruin' in self.god):
                dt = max(1.0, min(self.next_spawn - self.t if not self.spawned else math.inf,
                                  self.time_to_full_magic(),
                                  self.garden.next_tick - self.t if self.garden else math.inf,
                                  self.T - self.t, 600.0))
            else:
                dt = 1.0
            self.integrate(dt)
        # end: pop every wrinkler
        self.pop_wrinklers(self.wr_eating)
        total = self.bank - p.bank0_s + self.costs_offset()
        return total / self.T

    def costs_offset(self):
        return 0.0  # costs already left the bank

    def integrate(self, dt):
        p = self.p
        cps = self.cookies_ps()
        suck = min(1.0, self.wr_eating * self.wr_rate)
        clickm = self.click_mult_buffs() * self.click_static
        if 'Cursed finger' in self.buffs:
            clicks = p.clicks_per_s * self.cursed_arg * dt
        else:
            clicks = p.clicks_per_s * p.click_frac * cps * clickm * dt
        self.gain(cps * (1 - suck) * dt, 'cps')
        self.gain(clicks, 'clicks')
        self.wr_sucked += cps * suck * dt
        if 'Cookie storm' in self.buffs:
            self.gain(15 * dt * p.gc_gain_mult * cps * 60 * 4, 'storm')
        self.t += dt
        # buffs
        for name in list(self.buffs):
            b = self.buffs[name]
            b[0] -= dt
            if b[0] <= 0:
                del self.buffs[name]
                if name == 'Loan 2':
                    self.add_buff('Loan 2 (interest)', 40 * 60, 0.1)
        # golden cookies on screen
        for gc in list(self.gcs):
            gc['life'] -= dt
            if gc['life'] <= 0:
                if self.s.hold_gc:
                    self.pop_gc(gc)
                else:
                    self.gc_die(gc)
        self.regen_magic(dt)
        if self.wr_n:
            self.respawn_wrinklers(dt)
        if self.garden:
            self.garden.advance()


class Garden:
    """36 tiles of a single plant. Passive layouts on clay, harvest layouts on fertilizer."""

    def __init__(self, sim: Sim, plant: str):
        self.sim, self.plant = sim, plant
        self.info = PLANTS[plant]
        self.harvest = self.info.get('harvest')
        self.soil = 'fertilizer' if self.harvest else 'clay'
        self.tick_s, self.eff_mult = SOIL[self.soil]
        # start: a fully grown passive layout, harvest layouts start freshly planted
        if self.harvest:
            self.ages = [0] * 36
        else:
            self.ages = [self.info['mature'] + sim.grng.randint(0, 20) for _ in range(36)]
            if self.info.get('immortal'):
                self.ages = [self.info['mature'] + 1] * 36
        self.next_tick = sim.t + self.tick_s

    def stage_mult(self, age):
        m = self.info['mature']
        if age < 0:
            return 0
        if age >= m:
            return 1
        if age >= m * 0.666:
            return 0.5
        if age >= m * 0.333:
            return 0.25
        return 0.1

    def apply(self):
        sim = self.sim
        e = dict(cps=1.0, milk=1.0, gcFreq=1.0, gcGain=1.0, gcEffDur=1.0, gcDur=1.0,
                 wrathFreq=1.0, wrathGain=1.0)
        for age in self.ages:
            m = self.eff_mult * self.stage_mult(age)
            if m == 0:
                continue
            pl = self.plant
            if pl == 'bakerWheat' or pl == 'bakeberry':
                e['cps'] += 0.01 * m
            elif pl == 'goldenClover':
                e['gcFreq'] += 0.03 * m
            elif pl == 'shimmerlily':
                e['gcGain'] += 0.01 * m
                e['gcFreq'] += 0.01 * m
            elif pl == 'elderwort':
                e['wrathGain'] += 0.01 * m
                e['wrathFreq'] += 0.01 * m
            elif pl == 'whiskerbloom':
                e['milk'] += 0.002 * m
            elif pl == 'queenbeet':
                e['gcEffDur'] += 0.003 * m
                e['cps'] *= 1 - 0.02 * m
        sim.eff = e
        sim.kitten_factor_cached = sim.kitten_factor()

    def plant_tile(self, i):
        sim = self.sim
        cost = max(0.0, sim.cookies_ps() * self.info['cost'] * 60)
        sim.spend(cost, 'seeds')
        self.ages[i] = 0

    def act(self):
        sim = self.sim
        P = sim.cps_mult_buffs()
        changed = False
        for i, age in enumerate(self.ages):
            if age < 0:
                # replant only while production is not boosted (seed price follows CpS)
                if P <= 1.0:
                    self.plant_tile(i)
                    changed = True
            elif self.harvest and age >= self.info['mature']:
                pct, secs = self.harvest
                cps = sim.cookies_ps()
                bank_capped = pct * sim.bank <= secs * cps
                dying = age + math.ceil(self.info['at'] + self.info['atr']) >= 100 and \
                    sim.t + 1 >= self.next_tick
                if bank_capped or P >= 50 or dying:
                    sim.gain(min(pct * sim.bank, secs * cps), 'harvest')
                    self.ages[i] = -1
                    changed = True
        if changed:
            self.apply()

    def advance(self):
        sim = self.sim
        if sim.t < self.next_tick:
            return
        self.next_tick += self.tick_s
        rnd = sim.grng.random
        for i, age in enumerate(self.ages):
            if age < 0:
                continue
            x = self.info['at'] + self.info['atr'] * rnd()
            step = math.floor(x) + (1 if rnd() < x - math.floor(x) else 0)
            age += step
            if self.info.get('immortal'):
                age = min(self.info['mature'] + 1, age)
            elif age >= 100:
                age = -1
            self.ages[i] = age
        self.apply()


def run(p: Params, s: Strategy):
    sim = Sim(p, s)
    v = sim.run()
    return v, sim.stats
