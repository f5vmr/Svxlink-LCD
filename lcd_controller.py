
#!/usr/bin/env python3

"""
SvxLink LCD Controller V0.4

Adafruit 16x2 RGB LCD Pi Plate.
Live monitoring through SvxLink-Dash V4.1.

Talkgroup and module control through the restricted
SvxLink-LCD control service.
DTMF transmission requires explicit confirmation.
"""

import json
import signal
import socket
import time
import urllib.request

import board
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd

from dtmf_control import (
    build_talkgroup_command,
    build_module_command,
    load_lcd_config,
)

from talkgroup_store import (load_favourites, add_favourite, remove_favourite,)
from svxlink_config import get_monitored_talkgroups
from svxlink_config import  lookup_federation_talkgroup
API_URL = "http://127.0.0.1:5000/api/status?port=1"

CONTROL_SOCKET = "/run/svxlink-lcd/control.sock"

POLL_INTERVAL = 1.0
BUTTON_INTERVAL = 0.05

LCD_COLUMNS = 16
LCD_ROWS = 2

MAIN_MENU = [
    ("TALKGROUPS", "talkgroups"),
    ("MODULES", "modules"),
    ("MACROS", "macros"),
    ("NODE STATUS", "node"),
    ("SYSTEM", "system"),
]

NODE_MENU = [
    ("RADIO", "radio"),
    ("REFLECTOR", "reflector"),
    ("SERVICE", "service"),
]

SYSTEM_MENU = [
    ("IP ADDRESS", "ip"),
    ("CPU TEMP", "temperature"),
    ("UPTIME", "uptime"),
]


class SvxLinkLCD:

    def __init__(self):

        self.config = load_lcd_config()

        self.i2c = board.I2C()

        self.lcd = character_lcd.Character_LCD_RGB_I2C(
            self.i2c,
            LCD_COLUMNS,
            LCD_ROWS,
        )

        self.lcd.color = [0, 100, 0]
        self.lcd.clear()

        self.previous_display = None
        self.status_data = {}
        self.api_available = False

        self.menu_stack = []
        self.detail = None
        self.confirmation = None
        self.save_favourite = None
        self.remove_favourite_state = None
        self.previous_buttons = {
            "UP": False,
            "DOWN": False,
            "LEFT": False,
            "RIGHT": False,
            "SELECT": False,
        }

        self.running = True

    # ----------------------------------------------
    # Display
    # ----------------------------------------------

    def format_line(self, value):
        return str(value)[:LCD_COLUMNS].ljust(LCD_COLUMNS)

    def display(self, line1, line2):

        content = (
            self.format_line(line1),
            self.format_line(line2),
        )

        if content == self.previous_display:
            return

        self.lcd.message = (
            content[0] + "\n" + content[1]
        )

        self.previous_display = content

    # ----------------------------------------------
    # Dashboard status
    # ----------------------------------------------

    def fetch_status(self):

        with urllib.request.urlopen(
            API_URL,
            timeout=2,
        ) as response:
            data = json.load(response)

        if not isinstance(data, dict):
            raise ValueError("Invalid API response")

        if not isinstance(data.get("status"), dict):
            raise ValueError("Missing status object")

        self.status_data = data
        self.api_available = True

    def get_status(self):
        return self.status_data.get("status", {})

    def get_system(self):
        return self.status_data.get("system_info", {})

    def get_radio(self):
        return self.get_status().get("radio_state") or {}

    def get_talkgroup(self):
        return str(
            self.get_status().get("active_talkgroup")
            or "Standby"
        )

    def get_activity(self):

        radio = self.get_radio()

        if radio.get("tx"):
            return "TX"

        if radio.get("rx"):
            return "RX"

        return "IDLE"

    def get_connection(self):

        reflector = self.get_status().get(
            "reflector", "Unknown"
        )

        if str(reflector).strip().lower() == "connected":
            return "ONLINE"

        return "OFFLINE"

    # ----------------------------------------------
    # Available modules
    # ----------------------------------------------

    def available_modules(self):
        """
        Offer only configured modules that are also
        reported by the dashboard as available.

        Unknown module data formats are not treated
        as proof that a module is available.
        """

        reported = self.get_status().get("modules") or []

        if isinstance(reported, dict):
            reported = list(reported.keys())

        if not isinstance(reported, list):
            return []

        names = set()

        for entry in reported:

            if isinstance(entry, str):
                names.add(entry.strip().casefold())

            elif isinstance(entry, dict):
                name = entry.get("name")

                if isinstance(name, str):
                    names.add(name.strip().casefold())

        return [
            module
            for module in self.config["modules"]
            if module["name"].strip().casefold() in names
        ]

    # ----------------------------------------------
    # Menu definitions
    # ----------------------------------------------

    def menu_items(self, menu_name):

        if menu_name == "main":
            return MAIN_MENU

        if menu_name == "node":
            return NODE_MENU

        if menu_name == "system":
            return SYSTEM_MENU

        if menu_name == "talkgroups":

            favourites = load_favourites()
            monitored = get_monitored_talkgroups()

            items = [
                (
                    f"{entry['name']} {entry['number']}",
                    f"tg:{entry['number']}",
                )
                for entry in favourites
            ]

            favourite_numbers = {
                entry["number"]
                for entry in favourites
            }

            for entry in monitored:
                if entry["tg"] not in favourite_numbers:
                    items.append((
                        f"{entry['name']} {entry['tg']}",
                        f"tg:{entry['tg']}",
                    ))

            items.append(
                ("MANAGE FAVS", "manage_favourites")
            )

            return items

        if menu_name == "manage_favourites":

            favourites = load_favourites()

            return [
                (
                    f"{entry['name']} {entry['number']}",
                    f"remove_tg:{entry['number']}",
                )
                for entry in favourites
            ]

        if menu_name == "modules":

            modules = self.available_modules()

            return [
                (
                    str(entry["name"]),
                    f"module:{index}",
                )
                for index, entry in enumerate(modules)
            ]

        if menu_name == "macros":
            return [
                ("NOT CONFIGURED", "no_macros"),
            ]

        return []

    def current_menu(self):

        if not self.menu_stack:
            return None

        return self.menu_stack[-1]

    # ----------------------------------------------
    # Render screens
    # ----------------------------------------------

    def render_home(self):

        callsign = (
            self.get_status().get("callsign") or "UNKNOWN"
        )

        self.display(
            f"{callsign} {self.get_connection()}",
            f"TG {self.get_talkgroup()} {self.get_activity()}",
        )

    def render_menu(self):

        menu_name, index = self.current_menu()
        items = self.menu_items(menu_name)

        if not items:
            self.display(
                menu_name.upper(),
                "NO ITEMS",
            )
            return

        index = min(index, len(items) - 1)
        self.menu_stack[-1] = (menu_name, index)

        label, _ = items[index]

        titles = {
            "main": "MAIN MENU",
            "talkgroups": "TALKGROUPS",
            "manage_favourites": "MANAGE FAVS",
            "modules": "MODULES",
            "macros": "MACROS",
            "node": "NODE STATUS",
            "system": "SYSTEM",
        }

        self.display(
            titles.get(menu_name, menu_name.upper()),
            f"> {label}",
        )


    def render_remove_favourite(self):

        state = self.remove_favourite_state
        number = state["number"]

        if state["acknowledged"]:

            if state["error"]:
                self.display(
                    "REMOVE ERROR",
                    "LEFT=BACK",
                )

            elif state["removed"]:
                self.display(
                    "FAV REMOVED",
                    f"TG {number}",
                )

            else:
                self.display(
                    "NOT A FAVOURITE",
                    f"TG {number}",
                )

        else:
            self.display(
                f"REMOVE TG {number}?",
                "SEL=YES LEFT=NO",
            )


    def render_save_favourite(self):

        state = self.save_favourite
        number = state["number"]

        if state["acknowledged"]:

            if state["error"]:
                self.display(
                    "FAVOURITE ERROR",
                    "LEFT=BACK",
                )

            elif state["saved"]:
                self.display(
                    "FAVOURITE SAVED",
                    f"TG {number}",
                )

            else:
                self.display(
                    "ALREADY SAVED",
                    f"TG {number}",
                )

        else:
            self.display(
                f"SAVE TG {number}?",
                "SEL=YES LEFT=NO",
            )


    def render_confirmation(self):

        if self.confirmation["acknowledged"]:

            if self.confirmation.get("error"):
                self.display(
                    "CONTROL ERROR",
                    "CHECK NODE STATUS",
                )

            elif self.confirmation.get("transmitted"):
                number = self.confirmation["value"]

                can_save = (
                    self.confirmation["action"] == "talkgroup"
                    and not any(
                        entry["number"] == number
                        for entry in load_favourites()
                    )
                    and any(
                        entry["tg"] == number
                        for entry in get_monitored_talkgroups()
                    )
                )

                self.display(
                    "DTMF COMMAND SENT",
                    "RIGHT=SAVE" if can_save
                    else "LEFT=BACK",
                )

            else:
                self.display(
                    "PREVIEW ONLY",
                    "NO DTMF SENT",
                )

            return

        self.display(
            self.confirmation["label"],
            "SEL=YES LEFT=NO",
        )

    def render_detail(self):

        detail = self.detail
        status = self.get_status()
        system = self.get_system()
        radio = self.get_radio()

        if detail == "radio":
            self.display(
                f"RADIO {self.get_activity()}",
                f"SQL {radio.get('input', 'Unknown')}",
            )

        elif detail == "reflector":
            self.display(
                f"REF {self.get_connection()}",
                f"TG {self.get_talkgroup()}",
            )

        elif detail == "service":
            self.display(
                "SVXLINK SERVICE",
                str(
                    status.get("service_status", "Unknown")
                ).upper(),
            )

        elif detail == "ip":
            self.display(
                "IP ADDRESS",
                system.get("ip") or "Unknown",
            )

        elif detail == "temperature":
            self.display(
                "CPU TEMPERATURE",
                system.get("cpu_temp") or "Unknown",
            )

        elif detail == "uptime":
            self.display(
                "SVXLINK UPTIME",
                status.get("uptime") or "Unknown",
            )

        elif detail == "no_macros":
            self.display(
                "MACROS",
                "NOT CONFIGURED",
            )

        else:
            self.display(
                "SVXLINK LCD",
                "UNKNOWN SCREEN",
            )

    def render(self):

        # Local favourites operations do not depend
        # on Dashboard API availability.
        if self.remove_favourite_state is not None:
            self.render_remove_favourite()
            return

        if self.save_favourite is not None:
            self.render_save_favourite()
            return

        if not self.api_available:
            self.display(
                "DASHBOARD ERROR",
                "RECONNECTING",
            )
            return

        if self.confirmation is not None:
            self.render_confirmation()

        elif self.detail is not None:
            self.render_detail()

        elif self.menu_stack:
            self.render_menu()

        else:
            self.render_home()

    # ----------------------------------------------
    # Command preview
    # ----------------------------------------------

    def prepare_command(self, target):

        if target.startswith("tg:"):

            number = int(target.split(":", 1)[1])

            # Confirm that the selected TG is still
            # either a favourite or a monitored TG.
            favourites = load_favourites()
            monitored = get_monitored_talkgroups()

            is_favourite = any(
                entry["number"] == number
                for entry in favourites
            )

            is_monitored = any(
                entry["tg"] == number
                for entry in monitored
            )

            if not (is_favourite or is_monitored):
                raise ValueError(
                    f"Talkgroup {number} is not available"
                )

            action = "talkgroup"
            value = number

            command = build_talkgroup_command(number)
            label = f"TG {number} {command}"

        elif target.startswith("module:"):

            index = int(target.split(":", 1)[1])
            modules = self.available_modules()

            entry = modules[index]
            action = "module"
            value = entry["name"]

            command = build_module_command(
                entry["dtmf_id"]
            )

            label = f"{entry['name']} {command}"

        else:
            return

        self.confirmation = {
            "label": label,
            "command": command,
            "action": action,
            "value": value,
            "acknowledged": False,
            "transmitted": False,
            "error": False,
            "selected_port": (
                self.status_data.get("selected_port")
            ),
        }

        print(
            f"DTMF PREVIEW: {label}, "
            f"command={command}, "
            f"port={self.confirmation['selected_port']}",
            flush=True,
        )


    def request_control_preview(self, action, value):
        """
        Send a confirmed command request to the independent
        SvxLink-LCD control service.

        The service enforces transmission authorisation.
        """

        request = {
            "action": action,
            "value": value,
        }

        with socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        ) as connection:

            connection.settimeout(3.0)
            connection.connect(CONTROL_SOCKET)

            connection.sendall(
                (
                    json.dumps(request) + "\n"
                ).encode("utf-8")
            )

            with connection.makefile(
                "r",
                encoding="utf-8",
            ) as response:
                result = json.loads(
                    response.readline(4096)
                )

        if not isinstance(result, dict):
            raise ValueError("Invalid control service response")

        if not result.get("success"):
            raise ValueError(
                result.get("error", "Control preview failed")
            )

        if not isinstance(result.get("transmitted"), bool):
            raise ValueError(
                "Invalid transmission status"
            )

        return result

    def begin_remove_favourite(self, number):
        """Prepare a favourite removal without changing storage."""

        number = int(number)

        if not any(
            entry["number"] == number
            for entry in load_favourites()
        ):
            raise ValueError(
                f"Talkgroup {number} is not a favourite"
            )

        self.remove_favourite_state = {
            "number": number,
            "acknowledged": False,
            "removed": False,
            "error": False,
        }

    def confirm_remove_favourite(self):
        """Remove a favourite without transmitting DTMF."""

        state = self.remove_favourite_state

        if state is None or state["acknowledged"]:
            return

        try:
            state["removed"] = remove_favourite(
                state["number"]
            )

        except (OSError, ValueError, KeyError) as error:
            print(
                f"FAVOURITE REMOVE FAILED: {error}",
                flush=True,
            )
            state["error"] = True

        state["acknowledged"] = True

    def begin_save_favourite(self):
        """Offer to save a successfully selected monitored TG."""

        confirmation = self.confirmation

        if not confirmation:
            return

        if (
            confirmation["action"] != "talkgroup"
            or not confirmation["acknowledged"]
            or not confirmation["transmitted"]
            or confirmation.get("error")
        ):
            return

        number = confirmation["value"]

        if any(
            entry["number"] == number
            for entry in load_favourites()
        ):
            return

        if not any(
            entry["tg"] == number
            for entry in get_monitored_talkgroups()
        ):
            return

        self.save_favourite = {
            "number": number,
            "acknowledged": False,
            "saved": False,
            "error": False,
        }

        self.confirmation = None


    def confirm_save_favourite(self):
        """Save the selected monitored TG without sending DTMF."""

        if self.save_favourite is None:
            return

        if self.save_favourite["acknowledged"]:
            return

        number = self.save_favourite["number"]

        try:
            entry = lookup_federation_talkgroup(number)

            name = (
                entry["name"]
                if entry
                else f"TG {number}"
            )

            saved = add_favourite(number, name)

            self.save_favourite["saved"] = saved

        except (OSError, ValueError, KeyError) as error:
            print(
                f"FAVOURITE SAVE FAILED: {error}",
                flush=True,
            )
            self.save_favourite["error"] = True

        self.save_favourite["acknowledged"] = True


    def confirm_preview(self):

        if self.confirmation["acknowledged"]:
            return

        action = self.confirmation["action"]
        value = self.confirmation["value"]
        expected = self.confirmation["command"]

        try:
            result = self.request_control_preview(
                action,
                value,
            )

            if result.get("command") != expected:
                raise ValueError(
                    "Control service command mismatch"
                )

            self.confirmation["transmitted"] = (
                result["transmitted"]
            )

        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
        ) as error:

            print(
                f"DTMF CONTROL FAILED: {error}",
                flush=True,
            )

            self.confirmation["error"] = True
            self.confirmation["acknowledged"] = True
            return

        print(
            f"DTMF CONTROL RESULT: "
            f"action={action}, "
            f"command={expected}, "
            f"transmitted={result['transmitted']}",
            flush=True,
        )

        self.confirmation["acknowledged"] = True


    # ----------------------------------------------
    # Navigation
    # ----------------------------------------------

    def move_selection(self, direction):

        menu = self.current_menu()

        if menu is None:
            return

        menu_name, index = menu
        items = self.menu_items(menu_name)

        if not items:
            return

        self.menu_stack[-1] = (
            menu_name,
            (index + direction) % len(items),
        )

    def enter_selection(self):

        if self.remove_favourite_state is not None:
            self.confirm_remove_favourite()
            return

        if self.save_favourite is not None:
            self.confirm_save_favourite()
            return

        if self.confirmation is not None:
            self.confirm_preview()
            return

        if self.detail is not None:
            return

        if not self.menu_stack:
            self.menu_stack.append(("main", 0))
            return

        menu_name, index = self.current_menu()
        items = self.menu_items(menu_name)

        if not items:
            return

        index = min(index, len(items) - 1)
        _, target = items[index]

        submenus = {
            "talkgroups",
            "manage_favourites",
            "modules",
            "macros",
            "node",
            "system",
        }

        if target in submenus:
            self.menu_stack.append((target, 0))

        elif target.startswith("remove_tg:"):
            number = int(target.split(":", 1)[1])
            self.begin_remove_favourite(number)

        elif target.startswith(("tg:", "module:")):
            self.prepare_command(target)

        else:
            self.detail = target

    def go_back(self):
        if self.remove_favourite_state is not None:
            self.remove_favourite_state = None

        elif self.save_favourite is not None:
            self.save_favourite = None

        elif self.confirmation is not None:
            self.confirmation = None

        elif self.detail is not None:
            self.detail = None

        elif self.menu_stack:
            self.menu_stack.pop()

    def handle_button(self, name):

        if name == "LEFT":
            self.go_back()

        elif name == "RIGHT":

            if self.confirmation is not None:
                self.begin_save_favourite()

            elif (
                self.save_favourite is None
                and self.remove_favourite_state is None
            ):
                self.enter_selection()

        elif name == "SELECT":
            self.enter_selection()

        elif (
            self.confirmation is None
            and self.save_favourite is None
            and self.remove_favourite_state is None
            and self.detail is None
        ):

            if name == "UP":
                self.move_selection(-1)

            elif name == "DOWN":
                self.move_selection(1)

        print(
            f"Button: {name}",
            flush=True,
        )

        self.render()

    def read_buttons(self):

        return {
            "UP": self.lcd.up_button,
            "DOWN": self.lcd.down_button,
            "LEFT": self.lcd.left_button,
            "RIGHT": self.lcd.right_button,
            "SELECT": self.lcd.select_button,
        }

    def handle_buttons(self):

        current = self.read_buttons()

        for name, pressed in current.items():

            if (
                pressed
                and not self.previous_buttons[name]
            ):
                self.handle_button(name)

        self.previous_buttons = current

    # ----------------------------------------------
    # Main loop
    # ----------------------------------------------

    def stop(self, signum, frame):
        self.running = False

    def run(self):

        print(
            "SvxLink LCD Controller V0.4",
            flush=True,
        )

        print(
            "DTMF transmission disabled (preview only)",
            flush=True,
        )

        self.display(
            "SVXLINK LCD V0.4",
            "INITIALISING",
        )

        next_poll = 0.0
        error_reported = False

        try:

            while self.running:

                if time.monotonic() >= next_poll:

                    try:
                        self.fetch_status()
                        error_reported = False

                    except (
                        OSError,
                        ValueError,
                        KeyError,
                        TypeError,
                    ) as error:

                        self.api_available = False

                        if not error_reported:
                            print(
                                f"Dashboard error: {error}",
                                flush=True,
                            )
                            error_reported = True

                    self.render()

                    next_poll = (
                        time.monotonic() + POLL_INTERVAL
                    )

                self.handle_buttons()

                time.sleep(BUTTON_INTERVAL)

        finally:
            self.lcd.clear()

        print(
            "LCD controller stopped.",
            flush=True,
        )


if __name__ == "__main__":

    controller = SvxLinkLCD()

    signal.signal(signal.SIGTERM, controller.stop)
    signal.signal(signal.SIGINT, controller.stop)

    controller.run()
