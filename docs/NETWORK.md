**English** · [Deutsch](NETWORK.de.md)

# Getting the box on the network

A dice tower sits on a shelf with no keyboard and no screen. When it cannot reach the WiFi —
a new house, a changed password, somebody else's table — there has to be a way in that is not
an SSH session, because there is no session to have.

The answer is the one YonderRC arrived at: **the box serves its own network.** A phone joins
it, a captive portal pops the setup page open without anybody typing an address, and from
there you tell it which network to join.

## What it does by itself

```
no network for 45 seconds  →  opens "DiceCore-setup"  →  phone joins  →  page opens
```

- **45 seconds, not immediately.** A router rebooting takes a network away for twenty
  seconds, and a box that runs off with its own radio every time that happens is worse than
  one that waits. The grace period is a setting.
- **The network it serves is open by default.** Somebody who cannot reach the box also
  cannot be told a password. Set one if the shelf is somewhere public.
- **The portal needs port 80**, so it needs root. Without it the network still appears and
  the setup page still works — it just has to be typed in (`http://10.42.0.1:8099/setup`).
- **DNS is only hijacked when the box has no uplink of its own.** With one, the hotspot
  shares real internet, and pointing every name at the box would break it for everyone
  connected while triggering a portal they do not need.

## Joining a network

**Setup → Network.** Scan, pick, type the password, join.

One thing to expect: **the box has one radio**, so joining a network closes the one it is
serving — including the connection you are reading the page over, if you came in through it.
That is not a failure. Rejoin your own WiFi and the box will be on it too. The page says so
before it starts rather than appearing to hang.

If the password is wrong, **the box reopens its own network** rather than sitting there
unreachable. That is the whole reason the hotspot is brought back on failure.

## The WiFi country, and why nothing works without it

**A Raspberry Pi refuses to transmit until it knows which country's rules apply.** Until it
does, the radio is soft-blocked and NetworkManager reports:

```
Error: Device is not available.
```

which is a sentence nobody guesses the meaning of. It is the single most common reason a
fresh Pi's hotspot never appears. Set it once on the Network page, or:

```bash
sudo raspi-config nonint do_wifi_country DE
```

The page reads the radio state and says which of the possible problems it actually is —
blocked by a hardware switch, blocked with no country set, or simply nothing in range.

## Ethernet

Nothing to configure: a cable is a cable, NetworkManager brings it up, and the box is
reachable at whatever address it gets. The Network page shows it, and an Ethernet connection
counts as an uplink — so a box on a cable will never open its own network, and if you ask it
to, it shares the wired connection rather than hijacking DNS.

## Running as root

The service runs as root, and that is a deliberate trade rather than an oversight. Two
things need it, and both are the difference between a box you can recover and one you
cannot:

- managing WiFi through NetworkManager **when the network is already gone**, and
- binding port 80 for the captive portal.

There is no authentication on the setup page. On a home network that is a reasonable place
to land; on a shared one it is worth knowing before you plug it in.

## What it cannot do

- **Choose between two known networks.** It joins what it is told and stays there.
- **Hidden networks** are not in a scan; type the name in by hand.
- **Enterprise WiFi** (WPA2-Enterprise, eduroam and friends) is not handled at all.
- **A second radio.** With one, serving and joining are exclusive, which is the constraint
  the whole design works around.
