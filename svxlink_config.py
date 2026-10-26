
#!/usr/bin/env python3

"""
SvxLink-LCD V0.5

Read SvxLink configuration and discover DTMF control
destinations without modifying the configuration or
transmitting commands.
"""

import configparser
import os
import pwd
import stat
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



def validate_runtime_pty(pty_path):
    """
    Verify a configured SvxLink DTMF control PTY.

    Checks:
      - The configured path is a symbolic link.
      - Its resolved target is under /dev/pts.
      - The target is a character device.
      - The target is owned by svxlink.
      - The current process has write permission.

    Does not open the PTY or transmit DTMF.
    """

    path = Path(pty_path)

    if not path.is_symlink():
        raise ValueError(
            f"DTMF control path is not a symlink: {path}"
        )

    target = path.resolve(strict=True)

    if target.parent != Path("/dev/pts"):
        raise ValueError(
            f"Unexpected DTMF PTY target: {target}"
        )

    device = target.stat()

    if not stat.S_ISCHR(device.st_mode):
        raise ValueError(
            f"DTMF target is not a character device: {target}"
        )

    svxlink_uid = pwd.getpwnam("svxlink").pw_uid

    if device.st_uid != svxlink_uid:
        raise ValueError(
            f"DTMF PTY is not owned by svxlink: {target}"
        )

    if not os.access(target, os.W_OK):
        raise PermissionError(
            f"DTMF PTY is not writable: {target}"
        )

    return str(target)

def lookup_federation_talkgroup(talkgroup, directory_path=None):
    """
    Look up a talkgroup in the bundled federation directory.

    Returns the matching dictionary, or None if the TG
    is not present.
    """
    import json
    from pathlib import Path

    if directory_path is None:
        directory_path = (
            Path(__file__).resolve().parent
            / "config"
            / "federation_talkgroups.json"
        )

    if isinstance(talkgroup, bool):
        raise ValueError("Invalid talkgroup number")

    try:
        tg_number = int(talkgroup)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid talkgroup number") from exc

    if tg_number <= 0:
        raise ValueError("Invalid talkgroup number")

    with Path(directory_path).open(encoding="utf-8") as handle:
        directory = json.load(handle)

    for entry in directory["talkgroups"]:
        if entry["tg"] == tg_number:
            return entry.copy()

    return None

def get_monitored_talkgroups(config_path=SVXLINK_CONFIG):
    """
    Read MONITOR_TGS from the configured ReflectorLogic.

    Resolve each talkgroup against the federation directory.
    Unknown talkgroups remain available by number.
    """
    import configparser

    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
    )

    parser.read(config_path)

    if not parser.has_section("ReflectorLogic"):
        return []

    raw_value = parser.get(
        "ReflectorLogic",
        "MONITOR_TGS",
        fallback="",
    )

    monitored = []
    seen = set()

    for item in raw_value.split(","):
        value = item.strip()

        if not value:
            continue

        if not value.isascii() or not value.isdecimal():
            raise ValueError(
                f"Invalid monitored talkgroup: {value}"
            )

        number = int(value)

        if number <= 0:
            raise ValueError(
                f"Invalid monitored talkgroup: {value}"
            )

        if number in seen:
            continue

        seen.add(number)

        directory_entry = lookup_federation_talkgroup(number)

        monitored.append({
            "tg": number,
            "name": (
                directory_entry["name"]
                if directory_entry
                else f"TG {number}"
            ),
            "source": "monitored",
            "in_directory": directory_entry is not None,
        })

    return monitored

def get_configured_macros(
    config_path=SVXLINK_CONFIG,
    logic_name=None,
):
    """
    Discover macros belonging to the active SvxLink radio logic.

    Preserve macro IDs as strings, including leading zeros.
    This function never executes a macro.
    """
    import configparser

    destinations = discover_dtmf_logics(config_path)

    # Ensure the requested logic exists and reject
    # ambiguous multi-logic installations.
    select_dtmf_logic(destinations, logic_name)

    if logic_name is not None:
        active_logic = logic_name
    else:
        active_logic = next(iter(destinations))

    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
    )
    parser.optionxform = str

    with open(config_path, encoding="utf-8") as handle:
        parser.read_file(handle)

    if not parser.has_section(active_logic):
        raise ValueError(
            f"Missing active logic section: {active_logic}"
        )

    macro_section = parser.get(
        active_logic,
        "MACROS",
        fallback="",
    ).strip()

    if not macro_section:
        return {
            "logic": active_logic,
            "prefix": "",
            "macros": [],
        }

    if not parser.has_section(macro_section):
        raise ValueError(
            f"Missing macro section: {macro_section}"
        )

    prefix = parser.get(
        active_logic,
        "MACRO_PREFIX",
        fallback="D",
    ).strip()

    if not prefix:
        raise ValueError("Empty macro prefix")

    macros = []

    for macro_id, definition in parser.items(macro_section):

        macro_id = macro_id.strip()
        definition = definition.strip()

        if not macro_id.isascii() or not macro_id.isdecimal():
            raise ValueError(
                f"Invalid macro ID: {macro_id}"
            )

        if not definition:
            raise ValueError(
                f"Empty macro definition: {macro_id}"
            )

        macros.append({
            "id": macro_id,
            "command": f"{prefix}{macro_id}#",
            "definition": definition,
        })

    return {
        "logic": active_logic,
        "prefix": prefix,
        "macros": macros,
    }