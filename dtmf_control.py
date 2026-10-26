#!/usr/bin/env python3

"""
SvxLink-LCD V0.4
Independent SvxLink DTMF control helper.

No commands are transmitted by this module's
validation or path-resolution functions.
"""

from pathlib import Path
import json
import os
import pwd
import stat
import re


CONTROL_DIRECTORY = Path("/dev/shm")

DTMF_PATTERN = re.compile(r"[0-9A-D*#]+")

DEFAULT_MODULE_IDS = {
    "ModuleHelp": 0,
    "ModuleParrot": 1,
    "EchoLink": 2,
    "ModuleMetar": 5,
}


def validate_dtmf(command):
    """Validate a complete DTMF command."""

    if not isinstance(command, str):
        raise ValueError("DTMF command must be a string")

    command = command.strip().upper()

    if not command or not DTMF_PATTERN.fullmatch(command):
        raise ValueError("Invalid DTMF command")

    return command


def resolve_control_path(node_type, port=None):
    """
    Resolve the SvxLink DTMF control PTY.

    node_type:
        simplex
        repeater
        multiport

    Multi-port operation requires an explicit port.
    """

    node_type = str(node_type).strip().lower()

    if node_type == "multiport":

        if port is None:
            raise ValueError(
                "Multi-port control requires a port"
            )

        port = str(port).strip()

        if not re.fullmatch(r"[1-9][0-9]*", port):
            raise ValueError("Invalid port number")

        return CONTROL_DIRECTORY / (
            f"port{port}_dtmf_ctrl"
        )

    if port is not None:
        raise ValueError(
            "Port must not be specified for "
            "single-port control"
        )

    if node_type == "repeater":
        return CONTROL_DIRECTORY / "repeater_dtmf_ctrl"

    if node_type == "simplex":
        return CONTROL_DIRECTORY / "simplex_dtmf_ctrl"

    raise ValueError(f"Unsupported node type: {node_type}")


def build_talkgroup_command(talkgroup):
    """Construct a SvxReflector talkgroup command."""

    talkgroup = str(talkgroup).strip()

    if not re.fullmatch(r"[0-9]+", talkgroup):
        raise ValueError("Invalid talkgroup number")

    return f"91{talkgroup}#"


def build_module_command(module_id):
    """Construct a module activation command."""

    module_id = str(module_id).strip()

    if not re.fullmatch(r"[0-9]+", module_id):
        raise ValueError("Invalid module number")

    return f"{module_id}#"


def get_module_command(module_name, module_ids=None):
    """Resolve a module name to its configured DTMF command."""

    if module_ids is None:
        module_ids = DEFAULT_MODULE_IDS

    if module_name not in module_ids:
        raise ValueError(
            f"No module ID configured for {module_name}"
        )

    return build_module_command(module_ids[module_name])


def validate_selected_port(port, enabled_ports):
    """
    Require an explicitly enabled port for multi-port control.
    """

    port = str(port).strip()

    if not re.fullmatch(r"[1-9][0-9]*", port):
        raise ValueError("Invalid selected port")

    allowed = {str(item) for item in enabled_ports}

    if port not in allowed:
        raise ValueError(
            f"Port {port} is not enabled"
        )

    return port


def load_lcd_config(config_path=None):
    """
    Load and validate the local LCD configuration.

    This function does not transmit DTMF or modify
    the SvxLink configuration.
    """

    if config_path is None:
        system_config = Path(
            "/etc/svxlink-lcd/lcd_config.json"
        )

        repository_config = (
            Path(__file__).resolve().parent
            / "config"
            / "lcd_config.json"
        )

        config_path = (
            system_config
            if system_config.exists()
            else repository_config
        )

    with Path(config_path).open(
        "r", encoding="utf-8"
    ) as handle:
        config = json.load(handle)

    if not isinstance(config, dict):
        raise ValueError("Invalid LCD configuration")

    control = config.get("control")
    talkgroups = config.get("talkgroups")
    modules = config.get("modules")

    if not isinstance(control, dict):
        raise ValueError("Missing control configuration")

    node_type = control.get("node_type")

    if node_type not in ("simplex", "repeater", "multiport"):
        raise ValueError("Invalid node type")

    transmission_enabled = control.get(
        "transmission_enabled", False
    )

    if type(transmission_enabled) is not bool:
        raise ValueError(
            "transmission_enabled must be a JSON boolean"
        )

    if not isinstance(talkgroups, dict):
        raise ValueError("Invalid talkgroup configuration")

    if talkgroups.get("prefix") != "91":
        raise ValueError("Unsupported talkgroup prefix")

    favourites = talkgroups.get("favorites")

    if not isinstance(favourites, list):
        raise ValueError("Invalid talkgroup favourites")

    for favourite in favourites:
        if not isinstance(favourite, dict):
            raise ValueError("Invalid talkgroup entry")

        build_talkgroup_command(favourite.get("number"))

        if not isinstance(favourite.get("name"), str):
            raise ValueError("Invalid talkgroup name")

    if not isinstance(modules, list):
        raise ValueError("Invalid module list")

    for module in modules:
        if not isinstance(module, dict):
            raise ValueError("Invalid module entry")

        if not isinstance(module.get("name"), str):
            raise ValueError("Invalid module name")

        build_module_command(module.get("dtmf_id"))

    if node_type == "multiport":
        validate_selected_port(
            control.get("selected_port"),
            control.get("enabled_ports", []),
        )
    elif control.get("selected_port") is not None:
        raise ValueError(
            "Single-port configuration must not select a port"
        )

    return config


def send_dtmf(
    command,
    node_type,
    port=None,
    enabled_ports=None,
):
    """
    Send a validated DTMF command to SvxLink.

    Multi-port transmission requires both an explicitly
    selected port and the current list of enabled ports.

    Call only after operator confirmation.
    """

    command = validate_dtmf(command)
    node_type = str(node_type).strip().lower()

    if node_type == "multiport":
        if enabled_ports is None:
            raise ValueError(
                "Enabled ports are required for multi-port control"
            )

        port = validate_selected_port(
            port,
            enabled_ports,
        )

    control_path = resolve_control_path(
        node_type,
        port=port,
    )

    if not control_path.exists():
        raise FileNotFoundError(
            f"DTMF control PTY not found: {control_path}"
        )

    with control_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(command)

    return command


def write_validated_dtmf(command, configured_pty):
    """
    Write DTMF to a validated SvxLink control PTY.

    The opened file descriptor is checked before writing.

    WARNING:
    Calling this function transmits real DTMF.
    """

    command = validate_dtmf(command)

    from svxlink_config import validate_runtime_pty

    # Resolve and validate the current PTY.
    target = validate_runtime_pty(configured_pty)

    # Open the actual device, not the symbolic link.
    fd = os.open(
        target,
        os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK,
    )

    try:
        device = os.fstat(fd)

        svxlink_uid = pwd.getpwnam("svxlink").pw_uid

        if not stat.S_ISCHR(device.st_mode):
            raise ValueError(
                "Opened DTMF target is not a character device"
            )

        if device.st_uid != svxlink_uid:
            raise PermissionError(
                "Opened DTMF target has an unexpected owner"
            )

        # Verify that the configured link still resolves
        # to the same device after opening.
        current_target = validate_runtime_pty(
            configured_pty
        )

        current_device = os.stat(current_target)

        if (
            device.st_dev != current_device.st_dev
            or device.st_ino != current_device.st_ino
            or device.st_rdev != current_device.st_rdev
        ):
            raise RuntimeError(
                "SvxLink DTMF PTY changed during validation"
            )

        payload = command.encode("ascii")

        written = os.write(fd, payload)

        if written != len(payload):
            raise OSError(
                "Incomplete DTMF command write"
            )

    finally:
        os.close(fd)

    return command
