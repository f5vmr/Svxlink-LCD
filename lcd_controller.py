
#!/usr/bin/env python3

"""
SvxLink LCD Controller V0.4

Adafruit 16x2 RGB LCD Pi Plate.
Live monitoring through SvxLink-Dash V4.1.

Talkgroup and module command preview.
NO DTMF TRANSMISSION IN THIS VERSION.
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

            favourites = self.config[
                "talkgroups"
            ]["favorites"]

            return [
                (
                    f"{entry['name']} {entry['number']}",
                    f"tg:{index}",
                )
                for index, entry in enumerate(favourites)
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
            "modules": "MODULES",
            "macros": "MACROS",
            "node": "NODE STATUS",
            "system": "SYSTEM",
        }

        self.display(
            titles.get(menu_name, menu_name.upper()),
            f"> {label}",
        )

    def render_confirmation(self):

        if self.confirmation["acknowledged"]:

            if self.confirmation.get("error"):
                self.display(
                    "CONTROL ERROR",
                    "CHECK NODE STATUS",
                )

            elif self.confirmation.get("transmitted"):
                self.display(
                    "DTMF COMMAND SENT",
                    "CHECK NODE STATUS",
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

            index = int(target.split(":", 1)[1])

            entry = self.config[
                "talkgroups"
            ]["favorites"][index]

            number = entry["number"]
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
        Send a preview request to the independent
        SvxLink-LCD control service.

        The service does not transmit DTMF.
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
            "modules",
            "macros",
            "node",
            "system",
        }

        if target in submenus:
            self.menu_stack.append((target, 0))

        elif target.startswith(("tg:", "module:")):
            self.prepare_command(target)

        else:
            self.detail = target

    def go_back(self):

        if self.confirmation is not None:
            self.confirmation = None

        elif self.detail is not None:
            self.detail = None

        elif self.menu_stack:
            self.menu_stack.pop()

    def handle_button(self, name):

        if name == "LEFT":
            self.go_back()

        elif name in ("SELECT", "RIGHT"):

            if (
                self.confirmation is None
                or name == "SELECT"
            ):
                self.enter_selection()

        elif (
            self.confirmation is None
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
