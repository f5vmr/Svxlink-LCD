
#!/usr/bin/env python3

"""
SvxLink LCD Controller V0.3

Adafruit 16x2 RGB LCD Pi Plate
SvxLink-Dash V4.1 status API

Hierarchical, read-only menu navigation.
"""

import json
import signal
import time
import urllib.request

import board
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd


API_URL = "http://127.0.0.1:5000/api/status?port=1"

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

        # An empty stack represents the HOME screen.
        # Each menu level retains its selected item.
        self.menu_stack = []
        self.detail = None

        self.previous_buttons = {
            "UP": False,
            "DOWN": False,
            "LEFT": False,
            "RIGHT": False,
            "SELECT": False,
        }

        self.running = True

    # ----------------------------------------------
    # LCD display
    # ----------------------------------------------

    def format_line(self, value):
        return str(value)[:LCD_COLUMNS].ljust(LCD_COLUMNS)

    def display(self, line1, line2):

        new_display = (
            self.format_line(line1),
            self.format_line(line2),
        )

        if new_display == self.previous_display:
            return

        self.lcd.message = (
            new_display[0] + "\n" + new_display[1]
        )

        self.previous_display = new_display

    # ----------------------------------------------
    # Dashboard API
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

        if radio.get("tx", False):
            return "TX"

        if radio.get("rx", False):
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
            return [
                ("CURRENT TG", "current_tg"),
            ]

        if menu_name == "macros":
            return [
                ("NOT CONFIGURED", "no_macros"),
            ]

        if menu_name == "modules":

            modules = self.get_status().get("modules") or []

            if not modules:
                return [("NO MODULES", "no_modules")]

            return [
                (str(module), f"module:{index}")
                for index, module in enumerate(modules)
            ]

        return []

    def current_menu(self):

        if not self.menu_stack:
            return None

        return self.menu_stack[-1]

    # ----------------------------------------------
    # Screen rendering
    # ----------------------------------------------

    def render_home(self):

        status = self.get_status()

        callsign = status.get("callsign") or "UNKNOWN"
        connection = self.get_connection()
        talkgroup = self.get_talkgroup()
        activity = self.get_activity()

        self.display(
            f"{callsign} {connection}",
            f"TG {talkgroup} {activity}",
        )

    def render_menu(self):

        menu = self.current_menu()

        if menu is None:
            self.render_home()
            return

        menu_name, index = menu
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

        title = titles.get(menu_name, menu_name.upper())

        self.display(
            title,
            f"> {label}",
        )

    def render_detail(self):

        detail = self.detail
        status = self.get_status()
        system = self.get_system()
        radio = self.get_radio()

        if detail == "current_tg":

            self.display(
                "CURRENT TALKGROUP",
                f"TG {self.get_talkgroup()}",
            )

        elif detail == "radio":

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

            service = status.get(
                "service_status", "Unknown"
            )

            self.display(
                "SVXLINK SERVICE",
                str(service).upper(),
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

        elif detail.startswith("module:"):

            modules = status.get("modules") or []

            try:
                index = int(detail.split(":", 1)[1])
                name = str(modules[index])
            except (ValueError, IndexError, TypeError):
                name = "Unavailable"

            self.display(
                "AVAILABLE MODULE",
                name,
            )

        elif detail == "no_modules":

            self.display(
                "MODULES",
                "NONE AVAILABLE",
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

        if self.detail is not None:
            self.render_detail()

        elif self.menu_stack:
            self.render_menu()

        else:
            self.render_home()

    # ----------------------------------------------
    # Button handling
    # ----------------------------------------------

    def read_buttons(self):

        return {
            "UP": self.lcd.up_button,
            "DOWN": self.lcd.down_button,
            "LEFT": self.lcd.left_button,
            "RIGHT": self.lcd.right_button,
            "SELECT": self.lcd.select_button,
        }

    def move_selection(self, direction):

        menu = self.current_menu()

        if menu is None:
            return

        menu_name, index = menu
        items = self.menu_items(menu_name)

        if not items:
            return

        index = (index + direction) % len(items)

        self.menu_stack[-1] = (menu_name, index)

    def enter_selection(self):

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
        else:
            self.detail = target

    def go_back(self):

        if self.detail is not None:
            self.detail = None

        elif self.menu_stack:
            self.menu_stack.pop()

    def handle_button(self, name):

        if name == "LEFT":
            self.go_back()

        elif name in ("SELECT", "RIGHT"):
            self.enter_selection()

        elif self.detail is None:

            if name == "UP":
                self.move_selection(-1)

            elif name == "DOWN":
                self.move_selection(1)

        menu = self.current_menu()
        location = (
            self.detail
            if self.detail is not None
            else menu[0] if menu else "HOME"
        )

        print(
            f"Button: {name}, View: {location}",
            flush=True,
        )

        self.render()

    def handle_buttons(self):

        current = self.read_buttons()

        for name, pressed in current.items():

            was_pressed = self.previous_buttons[name]

            if pressed and not was_pressed:
                self.handle_button(name)

        self.previous_buttons = current

    # ----------------------------------------------
    # Main loop
    # ----------------------------------------------

    def stop(self, signum, frame):
        self.running = False

    def run(self):

        print(
            "SvxLink LCD Controller V0.3",
            flush=True,
        )
        print(
            f"Dashboard API: {API_URL}",
            flush=True,
        )

        self.display(
            "SVXLINK LCD V0.3",
            "INITIALISING",
        )

        next_poll = 0.0
        error_reported = False

        try:
            while self.running:

                now = time.monotonic()

                if now >= next_poll:

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
                        time.monotonic()
                        + POLL_INTERVAL
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
