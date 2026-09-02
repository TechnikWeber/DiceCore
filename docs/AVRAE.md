**English** · [Deutsch](AVRAE.de.md)

# Avrae, Discord, and anything else

DiceCore reads physical dice. What a table usually wants next is for that number to appear
where the game already lives. This is the outbound half of the API: instead of somebody
asking DiceCore for a roll, DiceCore hands each finished roll over.

Everything here is **off by default**, and two of the three carry a credential.
**Setup → API → Send rolls out.**

## What Avrae can and cannot do

**Avrae rolls its own dice, and cannot be made to use yours.** There is no way to make
`!check athletics` consult the d20 on your table — not through this project and not through
any other, because Avrae's dice are Avrae's. Anyone who tells you otherwise is guessing.

What *is* possible, and is what this does:

1. DiceCore writes each roll into an Avrae **user variable**, over Avrae's own API.
2. A one-line **alias** in Discord reads that variable back out.

You still type something in Discord. The *number* comes off your table.

### Two shapes of alias, and the difference matters

**`!phys` — show what I threw.** Avrae prints your roll. Simple, and certain to work.

**`!pr` — make Avrae roll my number.** This is the one most people are after. It hands Avrae
a die that *can only* land on what you threw — `1d20mi17ma17` is a d20 clamped to 17 — so the
result goes through Avrae's own roller and comes out in Avrae's own format, bonuses and all.
`!pr +5` after a throw of 17 gives you Avrae rolling 17+5.

What it still is not: `!check athletics` does not consult your table. If you want the
physical die in a check, you build the alias that does it, and this is the shape to build it
from.

**What was verified and what was not.** The API this writes to is verified against Avrae's
own source. The aliases are not — I have no Avrae account to try them on, and the clamping
trick relies on dice syntax that may have moved. Try them in a quiet channel first.

Verified against Avrae's own source (`avrae/avrae-service`, `blueprints/customizations.py`
and `avrae/avrae`, `aliasing/evaluators.py`):

```
POST https://api.avrae.io/customizations/uvars/<name>
Authorization: <token from avrae.io/dashboard>
Content-Type: application/json

{"value": "…"}
```

and, in an alias, `get_uvar(name)` / `uvar_exists(name)`.

## Setting it up

1. **Get a token.** Sign in at [avrae.io/dashboard](https://avrae.io/dashboard) and copy the
   API token. It is a credential for that Avrae account — it can read and write its aliases
   and variables — and DiceCore keeps it in its config file in plain text. Worth knowing
   before putting one on a machine other people can reach.
2. **Paste it** into *Setup → API → Avrae*, switch on **Send finished rolls** and **Write
   rolls to an Avrae variable**, and save.
3. **Press "Send a test roll".** It waits for Avrae's answer rather than firing and
   forgetting, so a wrong token says so immediately.
4. **Paste the alias into Discord once.** The page shows it with a copy button, already
   carrying the variable name you chose:

```
!alias phys echo <drac2>
if not uvar_exists("dicecore"):
    return "No physical roll yet — throw the dice."
r = load_json(get_uvar("dicecore"))
faces = ", ".join([str(d["kind"]) + " " + str(d["value"]) for d in r["dice"]])
out = "**" + str(r["total"]) + "**  (" + faces + ")"
if not r["usable"]:
    out = out + "  ⚠️ voided — the dice changed after they were read"
return out
</drac2>
```

Now throw the dice and type `!phys`.

The alias is written without f-strings or anything clever on purpose: the point is that it
works first time on somebody else's Avrae, not that it is elegant.

### What is in the variable

```json
{"total": 21, "notation": "1d6+1d20 → 4, 17",
 "dice": [{"kind": "d20", "value": 17}, {"kind": "d6", "value": 4}],
 "verdict": "clean", "usable": true, "at": 1788362021.9,
 "headline": "21", "mode": "rpg"}
```

Small and flat, because a variable has a size limit and a Draconic alias wants the fields it
will use rather than the boxes the dice were found in. Read `usable` if you care: it is false
only when the fair-play watch saw the dice change after they were read.

### Using it in your own aliases

The value is yours once `load_json` has it, and the clamping trick above generalises:
`1d20mi{v}ma{v}` is the physical die expressed in Avrae's own dice language, so anywhere a
command takes a dice expression, it takes your throw. Which flag your table's command uses
depends on the command.

## Discord, without Avrae

Simpler and completely reliable: a webhook message in a channel, so everyone sees the
physical roll as it lands.

*Channel settings → Integrations → Webhooks → New webhook → Copy URL*, paste it into
*Setup → API → Discord*, done. Messages look like:

> 🎲 **21** — 4, 17

with a note appended when the fair-play watch has something to say about the roll.

One thing to know: Discord treats webhook messages as bot messages, and **bots do not
trigger other bots**. A webhook post cannot make Avrae do anything — which is exactly why
the uvar route above exists.

## Anywhere else

*Setup → API → Anywhere else* POSTs the same JSON the API returns for a roll to a URL of
yours, as it happens. That is the seam for a bot of your own, a scoreboard, a spreadsheet, or
the bridge to whichever service is not in this list.

## How it behaves

- **On a thread, always.** A webhook on a bad connection takes seconds, and nothing outside
  DiceCore may slow down the reading of a die.
- **Sent once the verdict is in**, not the moment the number exists — so a roll the fair-play
  watch voids never reaches anybody's game. Turn off *Skip rolls the fair-play watch voided*
  if you would rather see everything.
- **A failed delivery is recorded and forgotten.** No retries: a dice roll is interesting for
  about ten seconds, and a queue of stale ones is worse than none. The last few attempts are
  listed under the settings.
- **Credentials are never handed back out.** The page can say whether a token is set; it
  cannot show you the token.
