# Game modes

DiceCore reads dice. A **mode** reads the *result*. Those are two different jobs, and keeping
them apart is what stops this being a project about one game: the camera does not care
whether five sixes are thirty points or a Kniffel, and the scoring does not care how the
sixes were recognised.

A mode decides three things:

1. **Which dice may appear.** Narrowing this is the cheapest accuracy win available, and it
   lets DiceCore say *"this is two dice and there are three on the tray"* instead of quietly
   scoring the leftover one from the last throw.
2. **How the faces become an answer.** A sum, a count of successes, a combination, a
   comparison against a target.
3. **What goes on the screen in big letters.** `18`, `3 successes`, `Full house`, `Mäxchen!`

Modes live in [`src/dicecore/modes/catalogue.py`](../src/dicecore/modes/catalogue.py) as a
table and in [`scoring.py`](../src/dicecore/modes/scoring.py) as pure functions. Adding a
game is an entry plus a function — no change to the reader, the API or the web UI, which
builds its settings form from the mode's own parameters.

## The list

| Mode | Dice | What it does |
|---|---|---|
| **Normal** | 1–6 × d6 | Pips, added up. Almost every board game there is. |
| **Normal, extended** | 1–6 × d6, d10 | Six- and ten-siders together. A d10's zero counts as ten. |
| **Tabletop roleplaying** | the polyhedral set | Every die reported and added; a d100 and a d10 read together as 1–100; a natural 20 or a natural 1 called out. |
| **Dice pool** | any | Count how many dice reached the target. |
| **Best or worst of several** | 2–4 | Only the highest die counts — or the lowest. |
| **Exploding dice** | 1–3 | A die showing its maximum is thrown again and added. |
| **Roll under a target** | 1–3 | Success when the roll comes in at or under a target. |
| **Kniffel / Yahtzee** | 5 × d6 | The combination, not the sum. Three throws and a scorecard. |
| **Kniffel Extreme** | 6 × d6 | A longer sheet: five and six of a kind, two and three pairs, a 1–6 straight. |
| **Farkle / Zehntausend** | 1–6 × d6 | Throw as often as you dare; set aside, bank, or lose the lot. |
| **Backgammon** | 2 × d6 | `5-3`, or `double 4 — four moves`. |
| **Mäxchen** | 2 × d6 | Two dice as a two-digit number. 21 is the Mäxchen. |
| **One die, big** | 1 | A single number, as large as the screen allows. |
| **Fairness test** | 1 | Is this die loaded? |
| **Build your own** | any | Pick the rule and the numbers yourself. |

Switch modes with the picker at the top of **Roll**; adjust a mode's numbers under
**Detection → Game mode**.

## The ones worth explaining

### Dice pool — one mode, a great many games

Roll a handful, count how many reached a target. That is not one game, it is a family:

| Game | Dice | Threshold | Tens count twice |
|---|---|---|---|
| Warhammer 40,000 ("hits on 4+") | d6 | 4 | no |
| Shadowrun | d6 | 5 | no |
| World of Darkness / Vampire | d10 | 8 | **yes** |
| Blades in the Dark | d6 | 4 | no |

Two settings cover all of them, which is exactly why this is one mode and not four.

### Exploding dice

A die showing its maximum is thrown again and the results add up. DiceCore keeps the running
total between throws and the display says `16…` — with the ellipsis — while the roll is
still open, so nobody walks away from half a result. The moment a die lands short, the
total is final and the next throw starts from nothing.

### Roll under a target

Success when the roll is *at or under* the number. Call of Cthulhu rolls percentile: a d100
(the tens) and a d10 (the units) read together as 1–100, where a double zero is 100 — the
one place in dice where two zeroes are the best possible result. GURPS uses three
six-siders instead; turn `percentile` off and it works the same way.

### Fairness test

Throw the same die a few hundred times and DiceCore counts. A chi-square goodness-of-fit
test against a flat distribution says one of three things:

- **not enough** — a d6 needs about 30 throws before the test means anything, a d20 about 100
- **nothing unusual** — the distribution gives no reason to think the die is loaded
- **unusual / very unusual** — this pattern turns up in fewer than one fair die in twenty
  (or one in a hundred)

Read that third answer carefully. One fair die in twenty lands in "unusual" — that is what a
5 % threshold *means*, not a scandal. And there is deliberately no "fair" verdict, because
this test cannot show that: it can only fail to show the opposite.

**Start again** under *Detection → Game mode* clears the tally, which you want whenever you
pick up a different die.

### Build your own

Any game that is not in the list: choose the rule (`sum`, `pool`, `best`, `under`) and the
numbers. If you find yourself using it constantly, that game deserves a proper entry in the
catalogue — send the numbers along and it becomes one.

## Ten-sided dice

A d10 is the one die whose printing is not standard. Modern ones show **0–9** and let the
game decide what the zero is worth; older sets are printed **1–10**, where the ten is a
two-digit glyph on a single face.

That is a property of *your dice*, not of the game, so it is set once under **Detection →
Game mode** and it decides the labels a model is trained on — changing it later means
relabelling.

**What the zero is worth is a different question, and it belongs to the game.** Ten in
nearly every one, which is the general answer under the same panel; but some house rules
count it as nothing, so that a 0-1-2-3-4-5 run is a straight. Every mode can override the
general answer with its own, and *as set generally* is the third choice — so a table can
have one game where a zero is ten and another where it is nothing, without either of them
being wrong.

## From your own code

```python
import requests

roll = requests.get("http://dicecore.local:8099/api/v1/roll?mode=pool").json()
print(roll["reading"]["headline"])          # "3 successes"
print(roll["reading"]["extras"]["successes"])
```

`?mode=` reads one roll as another game **without changing the configured one**, so a bot
counting successes and a screen showing a total can share one tray. `GET /api/v1/modes`
lists them all with their parameters, which is what a consumer's own mode picker should be
built from.

Every reading carries the same shape:

```json
{"mode": "yahtzee", "headline": "Full House", "detail": "3, 3, 3, 5, 5 · 25 points",
 "value": 25, "celebrate": false, "lament": false,
 "extras": {"combination": "full house", "points": 25, "values": [3, 3, 3, 5, 5]}}
```

`headline` is for a screen, `value` for arithmetic, `extras` for anything that needs the
detail. A consumer that ignores all of it still gets `total`, `dice` and `notation`.

## What a mode is not

It is not a rules engine. DiceCore does not know your modifier, your armour class, whose
turn it is or what you rolled *for*. It reads what is on the tray and names it. Everything
after that belongs in the game — which is the whole reason the API exists.
