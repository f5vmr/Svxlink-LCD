
#!/usr/bin/env python3

"""
SvxLink-LCD V0.4
Restricted DTMF control-service handler.

Initial implementation:
    - Receives one JSON request
    - Validates the requested operation
    - Constructs the SvxLink DTMF command
    - Returns a JSON preview
    - DOES NOT TRANSMIT DTMF

The systemd socket service will be added separately.
"""

import json
import sys
import socket

from dtmf_control import (
    build_module_command,
    build_talkgroup_command,
    load_lcd_config,
    write_validated_dtmf,
)

from svxlink_config import (
    discover_dtmf_logics,
    select_dtmf_logic,
    validate_dtmf_destination,
    validate_runtime_pty,
)

# Safety default: no DTMF transmission.
ENABLE_DTMF_TRANSMISSION = True

def discover_control_destination(logic_name=None, config_path=None):
    """
    Discover and validate an active SvxLink DTMF destination.

    Single radio logic: selected automatically.
    Multiple radio logics: explicit selection required.

    No PTY is opened and no DTMF is transmitted.
    """

    if config_path is None:
        destinations = discover_dtmf_logics()
    else:
        destinations = discover_dtmf_logics(config_path)

    destination = select_dtmf_logic(
        destinations,
        logic_name=logic_name,
    )

    if logic_name is None:
        logic_name = next(
            name
            for name, entry in destinations.items()
            if entry is destination
        )

    pty = validate_dtmf_destination(
        logic_name,
        destination,
    )

    return {
        "logic": logic_name,
        "type": destination["type"],
        "pty": pty,
    }


def process_request(request, config):
    """
    Validate a control request and return a DTMF preview.

    Only named operations are permitted.
    Arbitrary DTMF strings are not accepted.
    """

    if not isinstance(request, dict):
        raise ValueError("Request must be a JSON object")

    if set(request) != {"action", "value"}:
        raise ValueError("Invalid request fields")

    action = request["action"]
    value = request["value"]

    if action == "talkgroup":

        favourites = config["talkgroups"]["favorites"]

        matching = [
            entry
            for entry in favourites
            if str(entry["number"]) == str(value)
        ]

        if not matching:
            raise ValueError(
                "Talkgroup is not in the configured favourites"
            )

        command = build_talkgroup_command(
            matching[0]["number"]
        )

    elif action == "module":

        modules = config["modules"]

        matching = [
            entry
            for entry in modules
            if entry["name"] == value
        ]

        if not matching:
            raise ValueError(
                "Module is not configured"
            )

        command = build_module_command(
            matching[0]["dtmf_id"]
        )

    else:
        raise ValueError(
            "Unsupported control action"
        )

    # Resolve the destination from the actual SvxLink
    # configuration, not from a caller-supplied PTY.
    #
    # A single radio logic is selected automatically.
    # Multiple radio logics are rejected until an
    # explicit port-selection mechanism is provided.

    destination = discover_control_destination()

    # Validate the actual SvxLink PTY before accepting
    # this command preview. No DTMF is transmitted.
    resolved_pty = validate_runtime_pty(
        destination["pty"]
    )

    transmitted = False

    control = config.get("control", {})

    configured_type = control.get("node_type")
    actual_type = destination["type"]

    if (
        ENABLE_DTMF_TRANSMISSION
        and control.get("transmission_enabled") is True
        and configured_type != actual_type
    ):
        raise ValueError(
            f"LCD node type '{configured_type}' does not match "
            f"SvxLink logic type '{actual_type}'"
        )

    live_enabled = (
        ENABLE_DTMF_TRANSMISSION
        and control.get("transmission_enabled") is True
        and configured_type == actual_type
        and len(discover_dtmf_logics()) == 1
    )

    if live_enabled:
        write_validated_dtmf(
            command,
            destination["pty"],
        )
        transmitted = True

    return {
        "success": True,
        "action": action,
        "command": command,
        "logic": destination["logic"],
        "pty": destination["pty"],
        "resolved_pty": resolved_pty,
        "transmitted": transmitted,
    }


def main():
    """
    Process repeated requests through a systemd-activated
    Unix socket.

    Preview only: no DTMF transmission.
    """

    import os

    listen_fds = int(os.environ.get("LISTEN_FDS", "0"))
    listen_pid = int(os.environ.get("LISTEN_PID", "0"))

    if listen_fds != 1 or listen_pid != os.getpid():
        raise RuntimeError(
            "Expected one systemd-activated socket"
        )

    with socket.socket(fileno=3) as server:

        try:
            config = load_lcd_config()
            control = config.get("control", {})

            live_enabled = (
                ENABLE_DTMF_TRANSMISSION
                and control.get("transmission_enabled") is True
            )

            if live_enabled:
                destination = discover_control_destination()

                live_enabled = (
                    control.get("node_type") == destination["type"]
                    and len(discover_dtmf_logics()) == 1
                )

            mode = (
                "live transmission enabled"
                if live_enabled
                else "preview only"
            )

        except (ValueError, OSError, KeyError) as exc:
            mode = f"control unavailable: {exc}"

        print(
            f"SvxLink LCD control service ready ({mode})",
            flush=True,
        )

        while True:

            connection, _ = server.accept()

            with connection:

                try:
                    connection.settimeout(3.0)

                    with connection.makefile(
                        "r",
                        encoding="utf-8",
                    ) as reader:
                        request = json.loads(
                            reader.readline(4096)
                        )

                    config = load_lcd_config()

                    result = process_request(
                        request,
                        config,
                    )

                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    OSError,
                ) as error:

                    result = {
                        "success": False,
                        "error": str(error),
                        "transmitted": False,
                    }

                try:
                    connection.sendall(
                        (
                            json.dumps(result) + "\n"
                        ).encode("utf-8")
                    )
                except OSError:
                    pass


if __name__ == "__main__":
    main()
