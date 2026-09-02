**English** · [Deutsch](TRAINING.de.md)

# Teaching DiceCore your dice

The classic engine counts pips and needs nothing. Numerals — a d20 showing 14, a d10 showing
7 — need a model, and a model needs to see *your* dice under *your* light. That is a
five-minute job, not a project, and it happens entirely in the browser.

## Why a model at all

A d20 seen from above is a hexagon with a triangular face on top and five more faces angled
away from the camera, each with its own number on it. Reading it means finding the one face
that is head-on and reading only that. Add that dice differ in colour, translucency, ink and
finish — and that a 6 and a 9 are the same glyph — and hand-written rules stop being worth
writing. A classifier that has seen a few hundred of *your* dice is both easier and better.

## Sets, models, and which is which

Two words that are easy to mix up, and everything else follows from the difference.

**A set** is one lot of dice photographed under one light. It is the unit you *collect*
into: frames on disk with a label per die. Name it after both the dice and the setup —
"black d20s, desk lamp" — because a model trained across two different setups learns the
average of them and is worse at each.

**A model** is what the engine loads and reads with. It is trained from **one or more sets
at once**, and it knows exactly the faces that were in them and nothing else. Train from a
set of d6s and it reads d6s; add a set of d20s and the same model reads both.

That is what makes a set worth carrying between machines: your friend owns the d20s, so he
collects a few hundred throws on his own tower, sends you the file, and you train one model
from his set and yours together. **Export this set (.zip)** and the file input beside it do
exactly that — a plain zip of the frames and the labels, so you can also just unzip it and
look at your own data.

Only one model is loaded at a time. Under **Models** you pick which; the engine uses that
one, and it can recognise whatever went into it.

## The loop

**Training → New set**, then:

1. **Name the set after the setup, not just the dice** — "black d20s, desk lamp". A model
   trained across two different lights learns the average of both and is worse at each.
2. **Roll and store.** DiceCore captures, finds the dice and pre-fills its guesses. A die it
   could not read shows as `?`.
3. **Fix what is wrong, then Confirm.** Only confirmed dice are trained on — training on
   unconfirmed guesses teaches the model its own mistakes.
4. Repeat. Tick **keep rolling** to capture every few seconds and just keep throwing.

Watch the face counts under the set. "412 samples" means nothing if 400 of them are a d20
showing 1; the thin faces are listed so the next handful of rolls can be aimed at them.

## Three examples, start to finish

**Ordinary six-siders.** You may not need training at all — the classic reader counts pips
without any. Train only if your dice are unusual: dark, translucent, oddly inked. New set
*"white d6, kitchen lamp"*, then roll and confirm about sixty dice. Every throw of three
gives you three, so that is twenty throws.

**Kniffel.** The same, and five dice a throw means twelve throws gets you sixty. Tick *keep
rolling*, throw, glance, correct, repeat. The engine usually has the pips right already, so
most throws are one glance and nothing to type.

**A roleplaying set.** This is where training earns its keep: the classic reader cannot read
numerals at all, so a d20 is unreadable until a model exists. Set which dice may appear under
*Detection*, then roll the d20 on its own until each of its twenty faces has come up about
ten times — two hundred confirmed dice, an evening. Do the d8, d12 and the rest in the same
set or in sets of their own; they can all go into one model either way.

The awkward part of a d20 is that faces come up at random, so the last few need patience.
The per-face counts under the set show which are thin; aim the next throws at those, or pick
the die up and place it — a placed die is not a fair roll but it is a perfectly good
photograph, and the model only ever sees the picture.

## How much is enough

| | Confirmed dice | What to expect |
|---|---|---|
| Minimum to train at all | 60 | It will run; it will not be good |
| Usable | ~10 per face | A d20 needs ~200, a d6 ~60 |
| Comfortable | ~25 per face | A d20 needs ~500 |

A hundred throws of four dice is four hundred samples. That is one evening, and it is
roughly the point where a d20 model starts being boring in the good way.

The single most useful thing you can vary while collecting: **where in the tray the dice
land, and how they are rotated**. Vary nothing else. Light, camera and tray should stay
exactly as they will be in use.

## Training

**Train** on the Training tab. Progress, loss and accuracy stream into the page; you can
close the browser and come back. It needs PyTorch, so it runs on a PC — the tab says so if
this machine cannot, and offers a **button that installs it** (about 2 GB; DiceCore has to
be restarted afterwards to pick it up). Options:

- Copy `~/.local/share/dicecore/datasets/<set>` to a PC, run DiceCore there, train, copy the
  model directory back.
- Or run the whole of DiceCore on the PC with `engine.mode=remote` pointing the Pi at it,
  and never move anything.

From a terminal it is `dicecore train <set-id> --epochs 30`.

The result is a directory holding `model.onnx` and `model.json`. Press **Use** next to it, or
set `engine.mode=model`.

## What is actually trained

Two stages. Finding the dice is done by the classic segmentation — it is free, it needs no
labels, and it is not the hard part. The model only *reads* one cropped die:

- 64 × 64 grayscale crop, square around the die's centre, so a tilted die is never stretched.
- Three small conv blocks and a global average pool, ~200k parameters. It has to run on a Pi.
- Output: one class per `kind:value` seen in the set, e.g. `d20:14`.

Augmentation is where the accuracy comes from: **full 360° rotation**, plus shift, scale and
brightness. Dice land in every orientation, so the model must be rotation-invariant — and it
can be even for 6 vs 9, because dice settle that with an underline that rotates along with
the numeral. Without rotation augmentation the model learns the orientation of your tower.

Validation is split per class, not at random: with a small set, a random split can leave a
rare face out of validation entirely, and then the accuracy number is only about the common
faces.

## When it is wrong

Keep collecting into the same set — corrections are worth more than fresh guesses, because
they are exactly the samples the model is missing. Then retrain. Watch **engine agreement**
on the set: it is the honest measure of how the current engine does on dice it has not been
told the answer to yet.
