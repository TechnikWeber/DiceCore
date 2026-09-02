# Playing

Two front doors, one service.

| | |
|---|---|
| **`/`** | The **game screen**. Put it on the television at the table. |
| **`/setup`** | Everything else — camera, detection, fair play, panel, training. |

The game screen is at the root and the setup page is not, on purpose: the page you look at
all evening should not be one tab away behind six you never touch. Opening the game screen
is also what makes DiceCore start watching the tray — it holds the websocket that drives
continuous reading, so there is no "start" button to forget.

![The game screen during a Kniffel turn: the combination in large letters, the five dice drawn as pips, the throw counter with two chips left, and the scorecard down the right-hand side](screenshots/play.jpg)

## What it shows

- **The headline**, as the mode read it: `18`, `Full house`, `3 successes`.
- **The dice**, drawn — a six-sider as pips, everything else as its number. Tap one to hold
  it in a game where holding is part of the rules.
- **The throw counter**: filled dots for throws used, hollow for throws left, amber for
  chips. `throw 2 of 3` in words next to it.
- **The scorecard**, for the games that have one. The current player's open categories show
  what they would score right now; tap one to book it.
- **The last turns**, down the side.

## Turns

Most games are one throw and done. Kniffel and Farkle are not: a turn there is three throws,
keeping what you like in between, and the turn ends when you book something.

**Holds are observed, not enforced.** DiceCore notices which dice did not move between two
throws and shows those as kept — that is the only signal a camera has. If it guesses wrong,
tap the die. Nothing depends on the guess being right: what gets scored is simply what is on
the tray, so a mis-detected hold costs you nothing but a wrong label for a moment.

A throw only counts when the dice actually changed. Looking at the same settled dice again —
which the camera does several times a second — is not a throw, and does not burn one.

### Chips

A chip buys one more throw when the ordinary ones are gone. Set how many each player gets
under **Detection → Game mode** (up to three; zero by default, since it is a house rule
rather than part of Kniffel).

**Chips are per game, not per turn.** Three chips means three for the whole evening, so
spending one is a decision — refilling them every turn would take the decision away and
leave only the button. A new game hands them back.

A chip **cannot be spent while ordinary throws remain**. Spending one by fumbling a button
is exactly the kind of mistake a game should not allow. In a game with no throw limit at
all, like Farkle, a chip buys nothing and says so.

## The two buttons

The browser is not always where your hands are. Two optional GPIO buttons do the same two
things:

| Button | Default pin (BCM) | Physical | Does |
|---|---|---|---|
| Chip | *(off)* | — | Spend a chip — one more throw |
| End turn | *(off)* | — | Finish the turn and hand the tower on |

Wire each between the pin and ground and leave **Buttons use the internal pull-up** on;
that is the whole circuit. Set the pins under **Setup → Screen & lamps**, and `-1` for a
button you do not want. They call exactly the same endpoints the browser buttons do, so a
table can use either, both, or neither.

## The panel during a turn

The little screen over the tower carries the turn as well: `2/3` in the corner, a dot for
each chip, and a caption that changes with what you may do next —

| | |
|---|---|
| **THROW AGAIN** | throws left |
| **CHIP OR BOOK** | throws gone, chips in hand |
| **TURN OVER** | nothing left to do but book |

The green lamp means the same thing it always did: it is your turn to throw.

## The boards

Two games have a board of their own, and they are deliberately opposite shapes — which is
what shows the turn machine is a machine rather than a Kniffel-shaped hole.

### Kniffel, and Kniffel Extreme

Three throws, dice kept in between, then a category. Every open box shows what it would
score right now; tapping one books it and hands the tower on. Crossing a box out for nothing
is a real move and has to be confirmed.

**Kniffel Extreme** is the same shape with six dice and a longer sheet: five and six of a
kind, two pairs and three pairs, a big full house of three and three, and a straight running
all the way from one to six. The upper bonus asks for 84 rather than 63 — with six dice you
expect one of every face in a throw, so three of one is no longer the effort the standard
bonus rewards — and pays 50.

> The extended sheet is a **defined house sheet, not a transcription of a boxed product**.
> If the version on your table says otherwise, the numbers are a table in
> `src/dicecore/play/kniffel.py` and changing them is a one-line job.

| | Kniffel | Kniffel Extreme |
|---|---|---|
| Dice | 5 | 6 |
| Boxes | 13 | 18 |
| Bonus | 35 at 63 | 50 at 84 |
| Best box | Kniffel, 50 | Six of a kind, 100 |

### Farkle

The opposite of a fixed number of throws: you throw as often as you dare. Set aside the
dice that score — they leave the tray, so the next throw genuinely has fewer dice in it,
which the camera sees directly — then either bank what the turn has earned or throw again.

A throw with nothing scoring in it is a **Farkle** and the whole turn is lost. Set aside all
six and the dice are *hot*: the whole hand comes back and you keep going.

Every die you set aside has to score. A selection with a dead die in it is refused rather
than scored, because carrying one along would quietly cost you a throw's worth of dice.

House rules, as implemented: single 1 is 100 and single 5 is 50; three of a kind is 100×
the face except three ones at 1000; four, five and six of a kind double, quadruple and
octuple that; a straight or three pairs is 1500; you need 500 in one turn to get on the
board; first to 10 000 wins. The target and the entry threshold are settings.

## Several players

Set the names under **Setup → Players and turns**, one per line. The tower passes round by
itself: booking a category ends the turn and the next name comes up. Changing the players
starts a new game, because handing player three's card to a different player three would be
worse than losing the scores.

One name is a solo game, which is the right shape for practising, for a fairness test, or
for a machine that just shows numbers.

## Your own screen instead

Everything the play screen does is `/api/v1/game` plus five POSTs, all part of the versioned
API — because a play screen is exactly the sort of thing someone will want to write their
own version of, on a tablet, on a TV, in a language this project does not use.

```bash
curl http://dicecore.local:8099/api/v1/game            # turn, cards, options, log
curl -X POST .../api/v1/game/chip                      # one more throw
curl -X POST .../api/v1/game/hold  -d '{"index": 2}'   # correct a hold
curl -X POST .../api/v1/game/book  -d '{"category": "full_house"}'
curl -X POST .../api/v1/game/next                      # end the turn
curl -X POST .../api/v1/game/reset -d '{"players": ["A", "B"]}'
```

The websocket at `/api/v1/events` carries the same game state alongside every roll, so a
screen never has to poll.

## Reading without playing

None of this is compulsory. A consumer that only wants numbers keeps using `/api/v1/roll`
and ignores the game entirely — and can even ask for a different mode with `?mode=`, which
changes nothing about the game running at the table. The D&D bot and the scoreboard at the
table can be looking at the same tray, disagreeing about what it means, and both be right.
