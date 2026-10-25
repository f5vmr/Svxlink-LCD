
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
)


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

    return {
        "success": True,
        "action": action,
        "command": command,
        "transmitted": False,
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

        print(
            "SvxLink LCD control service ready "
            "(preview only)",
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
