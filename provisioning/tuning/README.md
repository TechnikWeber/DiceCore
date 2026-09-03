# Tuning files

libcamera tuning files that DiceCore ships because the stock ones are unusable for our case.
`install.sh` copies everything here to `/var/lib/dicecore/tuning/`.

## imx519-af.json (not yet included)

Raspberry Pi's own `imx519.json` contains no `rpi.af` algorithm, so libcamera answers every
focus request with *no AF algorithm available* and the Arducam 16MP's lens never moves. It
does not look like broken autofocus — it looks like a soft lens.

**Until one is installed, DiceCore does not set a tuning file at all.** Pointing
`LIBCAMERA_RPI_TUNING_FILE` at a file that is not there is not a soft failure: libcamera
cannot load the IPA, drops the sensor, and `rpicam-still` answers *no cameras available* —
so a working camera looks like an unplugged ribbon cable. Selecting the module therefore
leaves the tuning file empty and says so, and you get a working camera with a fixed lens
rather than no camera at all.

The fix is Raspberry Pi's `imx519.json` with an `rpi.af` block added, which Arducam ships in
their own package. Until this repo carries a redistributable copy:

```bash
# On the Pi, after installing Arducam's libcamera packages:
sudo cp /usr/share/libcamera/ipa/rpi/vc4/imx519.json /var/lib/dicecore/tuning/imx519-af.json
# then check that it contains an "rpi.af" section:
grep -q 'rpi.af' /var/lib/dicecore/tuning/imx519-af.json && echo "autofocus present"
```

Then press **Apply module** again (it picks the file up now that it exists) or set
**Camera → Tuning file** to that path by hand, and pick a focus mode. Over a dice tray,
prefer `manual` at a fixed dioptre — `continuous` hunts every time a die moves.
