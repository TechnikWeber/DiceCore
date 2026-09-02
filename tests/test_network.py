"""
Getting the box onto a network, and opening its own when there is none.

Everything decided on strings is a pure function so it can be pinned down without a Pi; the
shell calls are a thin layer that is not exercised here. Ported from YonderRC, including the
parts that were only learned by getting them wrong on real hardware — a hotspot built with
`nmcli device wifi hotspot` cannot be open, and "device is not available" means no WiFi
country has ever been set.
"""

import time

from dicecore.system.network import (
    HOTSPOT_ADDRESS,
    HOTSPOT_CON_NAME,
    HotspotProfile,
    RadioState,
    captive_portal_conf,
    explain_failure,
    hotspot_commands,
    is_country_code,
    join_commands,
    parse_active,
    parse_device_state,
    parse_mode,
    parse_networks,
    parse_rfkill,
    parse_wifi_country,
    should_hijack_dns,
    wifi_country_args,
)
from dicecore.system.portal import (
    CaptivePortal,
    Watcher,
    portal_target,
    should_open_hotspot,
)

# --- reading what the system says -------------------------------------------------


def test_a_blocked_radio_is_read_out_of_rfkill():
    assert parse_rfkill("\tSoft blocked: yes\n\tHard blocked: no") == (True, False)
    assert parse_rfkill("\tSoft blocked: no\n\tHard blocked: yes") == (False, True)
    assert parse_rfkill("") == (False, False)


def test_an_unset_country_reads_as_unset_not_as_the_code_zero_zero():
    assert parse_wifi_country("country DE: DFS-ETSI") == "DE"
    assert parse_wifi_country("country 00: DFS-UNSET") is None
    assert parse_wifi_country("GB") == "GB"
    assert parse_wifi_country("") is None


def test_a_radio_is_only_usable_when_it_is_unblocked_and_knows_its_country():
    assert RadioState(False, False, "DE").usable
    assert not RadioState(True, False, "DE").usable
    assert not RadioState(False, False, None).usable


def test_the_interface_state_is_picked_out_of_the_device_list():
    listing = "eth0:connected\nwlan0:unavailable\nlo:unmanaged"
    assert parse_device_state(listing) == "unavailable"
    assert parse_device_state(listing, "eth0") == "connected"
    assert parse_device_state(listing, "wlan9") == "missing"


def test_serving_and_joining_look_alike_until_you_ask_the_interface():
    assert parse_mode("\ttype AP\n\tssid DiceCore-setup") == "ap"
    assert parse_mode("\ttype managed") == "client"
    assert parse_mode("") == "unknown"


def test_a_mesh_showing_one_name_four_times_is_offered_once():
    # Four identical rows help nobody choose; the strongest is the one worth keeping.
    listing = "Home:41:WPA2\nHome:88:WPA2\nHome:12:WPA2\nOther:60:WPA2\n:30:"
    networks = parse_networks(listing)
    assert [n["ssid"] for n in networks] == ["Home", "Other"]
    assert networks[0]["signal"] == 88


def test_an_open_network_is_labelled_rather_than_left_blank():
    assert parse_networks("Cafe:70:")[0]["security"] == "open"


def test_the_box_knows_when_it_is_serving_rather_than_joined():
    active = parse_active(f"{HOTSPOT_CON_NAME}:wlan0:802-11-wireless:activated\n"
                          "Wired:eth0:802-3-ethernet:activated")
    assert active["hotspot"] and active["ethernet"] and active["wifi"]


# --- the commands -----------------------------------------------------------------


def test_the_hotspot_is_built_by_hand_so_it_can_be_open():
    # `nmcli device wifi hotspot` cannot produce an open network and picks its own address,
    # and an open one is the point: somebody who cannot reach the box cannot be told a
    # password either.
    commands = hotspot_commands(HotspotProfile("Tower", ""))
    joined = [" ".join(c) for c in commands]
    assert any("connection delete" in c for c in joined)      # no stale profile survives
    assert any("802-11-wireless.mode ap" in c for c in joined)
    assert any(f"ipv4.addresses {HOTSPOT_ADDRESS}/24" in c for c in joined)
    assert not any("wifi-sec" in c for c in joined)
    assert joined[-1].endswith(HOTSPOT_CON_NAME)


def test_a_password_of_eight_characters_or_more_secures_it():
    assert not HotspotProfile("x", "short").secured
    assert HotspotProfile("x", "longenough").secured
    assert any("wifi-sec.psk" in " ".join(c)
               for c in hotspot_commands(HotspotProfile("x", "longenough")))


def test_an_ssid_with_a_semicolon_in_it_is_just_text():
    # argv lists, never a shell string.
    commands = hotspot_commands(HotspotProfile("weird; rm -rf /", ""))
    assert "weird; rm -rf /" in commands[1]


def test_an_empty_name_still_produces_a_network():
    assert "DiceCore-setup" in hotspot_commands(HotspotProfile("   ", ""))[1]


def test_joining_takes_the_hotspot_down_first_because_there_is_one_radio():
    commands = join_commands("Home", "secret")
    assert commands[0][:2] == ["connection", "down"]
    assert "password" in commands[1] and "secret" in commands[1]
    assert "password" not in join_commands("Cafe", "")[1]


def test_the_country_command_is_the_one_raspi_config_takes():
    assert wifi_country_args("de") == ["nonint", "do_wifi_country", "DE"]
    assert is_country_code("DE") and not is_country_code("DEU") and not is_country_code(7)


# --- the captive portal -----------------------------------------------------------


def test_every_name_resolves_to_the_box_so_a_phone_opens_the_page():
    assert captive_portal_conf() == f"address=/#/{HOTSPOT_ADDRESS}\n"


def test_dns_is_only_hijacked_when_there_is_nothing_to_share():
    # With an uplink the hotspot shares real internet, and pointing every name at the box
    # would break it for everyone on it while triggering a portal they do not need.
    assert should_hijack_dns(False)
    assert not should_hijack_dns(True)


def test_a_probe_is_sent_to_the_setup_page_on_the_right_port():
    assert portal_target("captive.apple.com:80", 8099) == "http://captive.apple.com:8099/setup"
    assert portal_target("connectivitycheck.gstatic.com", 9000).endswith(":9000/setup")


def test_the_portal_does_not_stop_anything_when_it_cannot_bind_port_80():
    # It needs root, and on a laptop something else usually has :80.
    portal = CaptivePortal(8099)
    started = portal.start()
    try:
        assert started or portal.problem
    finally:
        portal.stop()


# --- deciding to open one ---------------------------------------------------------


def test_a_router_rebooting_does_not_make_the_box_run_away_with_the_radio():
    # Twenty seconds without a network is a router restarting, not a house move.
    assert not should_open_hotspot(False, False, 190.0, 200.0, grace_s=45)
    assert should_open_hotspot(False, False, 140.0, 200.0, grace_s=45)


def test_a_box_that_is_online_or_already_serving_leaves_things_alone():
    assert not should_open_hotspot(True, False, 100.0, 200.0)
    assert not should_open_hotspot(False, True, 100.0, 200.0)
    assert not should_open_hotspot(False, False, None, 200.0)


class FakeNetwork:
    def __init__(self, **status):
        self.state = {"managed": True, "online": False, "hotspot": False, **status}
        self.started = []

    def status(self):
        return dict(self.state)

    def start_hotspot(self, profile=None):
        self.started.append(profile)
        self.state["hotspot"] = True
        return True, "Serving its own network."


def test_the_watcher_opens_the_network_after_the_grace_period():
    network = FakeNetwork()
    watcher = Watcher(network, CaptivePortal(8099), grace_s=30)
    now = time.time()
    assert watcher.tick(now) is None            # first look: start the clock
    assert watcher.tick(now + 10) is None       # not yet
    assert watcher.tick(now + 40) is not None   # now
    assert len(network.started) == 1
    watcher.stop()


def test_the_clock_resets_the_moment_a_network_comes_back():
    network = FakeNetwork()
    watcher = Watcher(network, CaptivePortal(8099), grace_s=30)
    now = time.time()
    watcher.tick(now)
    network.state["online"] = True
    watcher.tick(now + 10)
    assert watcher.offline_since is None
    network.state["online"] = False
    watcher.tick(now + 20)
    assert watcher.tick(now + 40) is None       # the clock started again at +20
    watcher.stop()


def test_an_unmanaged_machine_is_left_entirely_alone():
    network = FakeNetwork(managed=False)
    watcher = Watcher(network, CaptivePortal(8099), grace_s=0)
    assert watcher.tick() is None and not network.started
    watcher.stop()


# --- explaining a failure ---------------------------------------------------------


def test_the_most_common_pi_failure_is_named_rather_than_repeated():
    # "Device is not available" is nmcli's way of saying rfkill has the radio blocked
    # because no country was ever set — the single most common reason a fresh Pi's hotspot
    # never appears, and a sentence nobody guesses from the message.
    failure = explain_failure("Error: Device is not available.",
                              RadioState(soft_blocked=True, country=None))
    assert "country" in failure.cause.lower() and failure.fixable_here


def test_a_hardware_switch_is_not_something_the_page_can_fix():
    failure = explain_failure("", RadioState(hard_blocked=True, country="DE"))
    assert not failure.fixable_here and "switch" in failure.fix.lower()


def test_a_wrong_password_says_so():
    assert "password" in explain_failure("Error: Secrets were required").cause.lower()


def test_an_unknown_failure_still_hands_over_something_to_chase():
    failure = explain_failure("Error: something nobody has seen before")
    assert failure.cause and failure.fix


def test_a_desktop_never_seizes_its_own_wifi():
    # On this feature's own terms a development machine would start serving an access point
    # the first time a router rebooted for longer than the grace period. A dice reader must
    # not be able to do that to somebody's computer.
    from dicecore.system.portal import auto_hotspot_wanted

    assert auto_hotspot_wanted("pi", is_pi=True)
    assert not auto_hotspot_wanted("pi", is_pi=False)
    assert auto_hotspot_wanted("always", is_pi=False)
    assert not auto_hotspot_wanted("off", is_pi=True)
