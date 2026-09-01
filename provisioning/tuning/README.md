# Tuning files

libcamera tuning files that DiceCore ships because the stock ones are unusable for our case.
`install.sh` copies everything here to `/var/lib/dicecore/tuning/`.

## imx519-af.json (not yet included)

Raspberry Pi's own `imx519.json` contains no `rpi.af` algorithm, so libcamera answers every
focus request with *no AF algorithm available* and the Arducam 16MP's lens never moves. It
does not look like broken autofocus — it looks like a soft lens.

The fix is Raspberry Pi's `imx519.json` with an `rpi.af` block added, which Arducam ships in
their own package. Until this repo carries a redistributable copy:

```bash
# On the Pi, after installing Arducam's libcamera packages:
sudo cp /usr/share/libcamera/ipa/rpi/vc4/imx519.json /var/lib/dicecore/tuning/imx519-af.json
# then check that it contains an "rpi.af" section:
grep -q 'rpi.af' /var/lib/dicecore/tuning/imx519-af.json && echo "autofocus present"
```

Then set **Camera → Tuning file** to that path and pick a focus mode. Over a dice tray,
prefer `manual` at a fixed dioptre — `continuous` hunts every time a die moves.
