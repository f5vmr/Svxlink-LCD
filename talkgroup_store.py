"""Persistent favourites storage for SvxLink-LCD."""

import json
import os
import tempfile
from pathlib import Path

from dtmf_control import build_talkgroup_command


DEFAULT_STORE = Path(
    "/var/lib/svxlink-lcd/talkgroups.json"
)


def validate_favourites(favourites):
    """Validate and normalise a favourites list."""

    if not isinstance(favourites, list):
        raise ValueError("Favourites must be a list")

    result = []
    seen = set()

    for item in favourites:
        if not isinstance(item, dict):
            raise ValueError("Invalid favourite entry")

        name = item.get("name")
        number = item.get("number")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Invalid favourite name")

        build_talkgroup_command(number)

        number = int(number)

        if number in seen:
            continue

        seen.add(number)

        result.append({
            "name": name.strip(),
            "number": number,
        })

    return result


def load_favourites(store_path=DEFAULT_STORE):
    """Read the persistent favourites database."""

    with Path(store_path).open(
        "r", encoding="utf-8"
    ) as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Invalid favourites database")

    return validate_favourites(data["favorites"])


def save_favourites(favourites, store_path=DEFAULT_STORE):
    """Atomically save favourites without partial writes."""

    store_path = Path(store_path)
    validated = validate_favourites(favourites)

    if not store_path.parent.is_dir():
        raise FileNotFoundError(
            f"Favourites directory missing: {store_path.parent}"
        )

    fd, temporary_name = tempfile.mkstemp(
        prefix=".talkgroups-",
        suffix=".json",
        dir=str(store_path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {"favorites": validated},
                handle,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        # The setgid storage directory ensures new files
        # inherit the svxlink group automatically.
        os.chmod(temporary_name, 0o640)

        os.replace(temporary_name, store_path)

    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def initialise_favourites(
    initial_favourites,
    store_path=DEFAULT_STORE,
):
    """Create a favourites database only if none exists."""

    store_path = Path(store_path)

    if store_path.exists():
        return load_favourites(store_path)

    save_favourites(initial_favourites, store_path)

    return load_favourites(store_path)


def add_favourite(
    number,
    name=None,
    store_path=DEFAULT_STORE,
):
    """Add a talkgroup without duplicating an existing favourite."""

    build_talkgroup_command(number)
    number = int(number)

    favourites = load_favourites(store_path)

    if any(
        item["number"] == number
        for item in favourites
    ):
        return False

    if name is None:
        name = f"TG {number}"

    favourites.append({
        "name": name,
        "number": number,
    })

    save_favourites(favourites, store_path)

    return True
