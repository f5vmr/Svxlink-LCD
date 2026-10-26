
#!/usr/bin/env python3

"""
SvxLink-LCD V0.5

Read SvxLink configuration and discover DTMF control
destinations without modifying the configuration or
transmitting commands.
"""

import configparser
from pathlib import Path


SVXLINK_CONFIG = Path("/etc/svxlink/svxlink.conf")


def discover_dtmf_logics(config_path=SVXLINK_CONFIG):
    """
    Return active SvxLink logic sections with a
    configured DTMF_CTRL_PTY.

    No PTY is opened or written.
    """

    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
    )

    parser.optionxform = str

    with Path(config_path).open(
        "r", encoding="utf-8"
    ) as handle:
        parser.read_file(handle)

    if not parser.has_section("GLOBAL"):
        raise ValueError("Missing GLOBAL section")

    logics = [
        item.strip()
        for item in parser.get(
            "GLOBAL",
            "LOGICS",
            fallback="",
        ).split(",")
        if item.strip()
    ]

    destinations = {}

    for logic in logics:

        if not parser.has_section(logic):
            continue

        logic_type = parser.get(
            logic,
            "TYPE",
            fallback="",
        ).strip().lower()

        if logic_type not in ("simplex", "repeater"):
            continue

        pty = parser.get(
            logic,
            "DTMF_CTRL_PTY",
            fallback="",
        ).strip()

        if not pty:
            continue

        destinations[logic] = {
            "type": logic_type,
            "pty": pty,
        }

    return destinations


def validate_dtmf_destination(logic_name, destination):
    """
    Validate the configured DTMF control destination.

    This performs configuration validation only.
    It does not open the PTY or transmit DTMF.
    """

    if not isinstance(destination, dict):
        raise ValueError("Invalid DTMF destination")

    logic_type = destination.get("type")
    pty = destination.get("pty")

    if logic_type not in ("simplex", "repeater"):
        raise ValueError("Unsupported radio logic type")

    if not isinstance(pty, str):
        raise ValueError("Invalid DTMF PTY path")

    import re

    if re.fullmatch(r"Port[1-9][0-9]*Logic", logic_name):

        port = logic_name[4:-5]

        expected = f"/dev/shm/port{port}_dtmf_ctrl"

    elif logic_name == "SimplexLogic":

        expected = "/dev/shm/simplex_dtmf_ctrl"

    elif logic_name == "RepeaterLogic":

        expected = "/dev/shm/repeater_dtmf_ctrl"

    else:
        raise ValueError(
            f"Unsupported logic name: {logic_name}"
        )

    if pty != expected:
        raise ValueError(
            f"Unexpected DTMF PTY for {logic_name}: {pty}"
        )

    return pty


def select_dtmf_logic(destinations, logic_name=None):
    """
    Select an unambiguous DTMF destination.

    Multi-logic installations require an explicit
    logic name.
    """

    if logic_name is not None:

        if logic_name not in destinations:
            raise ValueError(
                f"Logic not available: {logic_name}"
            )

        return destinations[logic_name]

    if len(destinations) == 1:
        return next(iter(destinations.values()))

    if not destinations:
        raise ValueError(
            "No radio DTMF control logic available"
        )

    raise ValueError(
        "Multiple radio logics require explicit selection"
    )

