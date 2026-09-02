**English** · [Deutsch](ONLINE.de.md)

# Playing against another DiceCore

Everyone has their own DiceCore. One of them holds the game; the others sit at it. Each
player throws on **their own** tray — their own camera, or their own simulator — and what
lands there appears on every screen at once.

There is nothing to install and nothing to sign up for. It is one button on the game screen.

```
   Alice's DiceCore                     Bob's DiceCore
   ┌──────────────────┐                 ┌──────────────────┐
   │  the game lives  │◄── websocket ───│  a mirror of it  │
   │  here            │───────────────► │                  │
   └──────────────────┘                 └──────────────────┘
     her camera or sim                    his camera or sim
```

## Doing it

**One of you hosts.** On the game screen, `Play online` → `Open a table`. The screen shows
an address; read it out.

**Everybody else joins.** `Play online`, type that address into the box, `Join`. The seat
list fills up on every screen as people arrive.

**The host picks the game and starts it.** The seats *are* the players, in the order they
sat down, so there is no player list to fill in — the wizard shows the names it already has.

**Then play.** Whoever's turn it is throws on their own DiceCore; everyone else watches the
dice land, live. Booking, holding, chips and banking all work the same as at one table, and
the screen simply says `watching` when it is not your turn.

To leave, `Leave the table` in the corner. The game carries on without you, and your seat is
kept — rejoining with the same name puts you back in your own scorecard column rather than
at the end of the table.

## What counts as "the same network"

Anything where one machine can open a TCP connection to another:

| | |
|---|---|
| **The same WiFi or LAN** | The usual case. Use the address the host screen shows. |
| **Tailscale** | Works as-is. The host screen shows its `100.x.y.z` address too — use that one. |
| **Hamachi, ZeroTier, a VPN** | Same idea: whatever address that network gives the host. |
| **Over the open internet** | Not without thinking about it. See *Who can join* below. |

The host screen lists every address it can find itself at. Read out the one on the network
you share — the `100.x` one for Tailscale, the `192.168.x` one for a home network.

## Sim dice: playing with no dice at all

DiceCore does not need a camera to play. The switch at the top of the lobby says *Real* or
*Simulated*; tap **Simulated** and a `Throw` button appears where the tray would be. That is
the whole difference — and it is the default, so a box out of the box already plays.

The simulator is not a random number generator with a scoreboard attached. It **draws the
dice and reads the picture back through the real engine** — the same segmentation, the same
pip counting, the same game modes, the same boards, the same panel. What you see on the
screen was genuinely *read*, and a bug anywhere in that chain shows up on a laptop instead of
only on a tower.

Which means the combinations all work, and none of them is a special case:

- Everyone round one screen, one real tower. The original.
- Everyone round one screen, no tower at all — sim dice, tap `Throw`.
- Four people in four rooms, each with a tower.
- Four people in four rooms, **none** with a tower.
- Two with towers and two without, in the same game. Nobody can tell from the scorecard.

Each instance decides for itself. The host does not impose a source on anybody, because
whose dice you throw is your business.

## How it works, and what that costs

**One instance owns the game.** The host's `GameSession` is the only copy that exists;
everyone else has a mirror of it and asks it for things. Nobody merges anything and nobody
resolves a conflict, because there is never more than one answer to "whose turn is it".
That lopsidedness is the design, not a shortcut:

- **A guest closing the tab loses nothing.** The game is not in their browser.
- **A guest losing WiFi loses nothing.** They reconnect — it retries with a backoff — and
  their seat is still theirs.
- **The host going away ends the evening.** The scorecard was there. This is the trade.

The rule the whole thing rests on is that **only the player whose turn it is may act**.
It is enforced at the host, not at the button: a guest whose screen is out of date does not
get to book a box because their copy said it was their turn. They get `It is not your turn.`
back, and their screen catches up. `src/dicecore/table/protocol.py` has it in one function
and `tests/test_table.py` pins it down.

Rolls travel as **numbers, not pictures**. A guest reads their own tray with their own
engine and sends up `[{"kind": "d6", "value": 4}, …]`. That keeps a turn under a kilobyte,
and it means a Pi Zero with no OpenCV can still sit at a table as long as something reads
its frames.

## Who can join

**Anybody who can reach the port.** There is no password, and that is deliberate — the same
decision as the rest of DiceCore, which is built for a table in a room rather than for the
open internet. On a home network or a Tailnet that is exactly right: the people who can
reach it are the people in the house.

Do not port-forward it to the internet. What somebody could do is join your table and take a
turn, which is annoying rather than dangerous — but the live camera view, if you have turned
it on, is a camera.

The seat list on the host screen shows exactly who is connected, and closing the table
disconnects everybody.

## When it does not work

**"did not answer"** — the address is wrong, the other DiceCore is not running, or a
firewall is in the way. The port is the one in the address; on a Pi it is 8099.

**"That DiceCore speaks table protocol 2, this one speaks 1."** — one of you is on an older
version. `git pull && systemctl restart dicecore` on the older one.

**"The table is full (8 seats)."** — eight is the limit. It is a dice game.

**A seat says "lost the connection"** — that instance dropped off. It reconnects on its own;
the game waits if it is their turn.

**Everything looks frozen** — check the corner of the header. `waiting for Bob` means it is
working and Bob has not thrown yet.
