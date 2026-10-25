
#!/usr/bin/env python3

"""
SvxLink LCD Controller V0.2

Adafruit 16x2 RGB LCD Pi Plate
Live monitoring via SvxLink-Dash V4.1.

Read-only interactive status navigation.
"""

import json
import time
import urllib.request

import board
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd


# --------------------------------------------------
# Configuration
# --------------------------------------------------

API_URL = "http://127.0.0.1:5000/api/status?port=1"

POLL_INTERVAL = 1.0
BUTTON_INTERVAL = 0.05

LCD_COLUMNS = 16
LCD_ROWS = 2

SCREENS = [
    "HOME",
    "RADIO",
    "REFLECTOR",
    "MODULES",
    "SYSTEM",
]


# --------------------------------------------------
# LCD controller
# --------------------------------------------------

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

        self.screen_index = 0
        self.previous_display = None

        self.status_data = {}
        self.api_available = False

        self.previous_buttons = {
            "UP": False,
            "DOWN": False,
            "LEFT": False,
            "RIGHT": False,
            "SELECT": False,
        }

    # ----------------------------------------------
    # Display handling
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
    # API handling
    # ----------------------------------------------

    def fetch_status(self):

        with urllib.request.urlopen(
            API_URL,
            timeout=2,
        ) as response:

            data = json.load(response)

        if not isinstance(data, dict):
            raise ValueError("Invalid dashboard API response")

        if not isinstance(data.get("status"), dict):
            raise ValueError("Missing status object")

        self.status_data = data
        self.api_available = True

    # ----------------------------------------------
    # Screen rendering
    # ----------------------------------------------

    def render(self):

        if not self.api_available:
            self.display(
                "DASHBOARD ERROR",
                "RECONNECTING",
            )
            return

        screen = SCREENS[self.screen_index]

        status = self.status_data.get("status", {})
        system = self.status_data.get("system_info", {})
        radio = status.get("radio_state") or {}

        callsign = status.get("callsign") or "UNKNOWN"
        reflector = status.get("reflector") or "Unknown"
        talkgroup = str(
            status.get("active_talkgroup") or "Standby"
        )

        rx = bool(radio.get("rx", False))
        tx = bool(radio.get("tx", False))

        if tx:
            activity = "TX"
        elif rx:
            activity = "RX"
        else:
            activity = "IDLE"

        connection = (
            "ONLINE"
            if str(reflector).strip().lower() == "connected"
            else "OFFLINE"
        )

        # HOME
        if screen == "HOME":

            self.display(
                f"{callsign} {connection}",
                f"TG {talkgroup} {activity}",
            )

        # RADIO
        elif screen == "RADIO":

            input_state = radio.get("input", "Unknown")

            self.display(
                f"RADIO {activity}",
                f"SQL {input_state}",
            )

        # REFLECTOR
        elif screen == "REFLECTOR":

            self.display(
                f"REF {connection}",
                f"TG {talkgroup}",
            )

        # MODULES
        elif screen == "MODULES":

            modules = status.get("modules") or []

            if modules:
                self.display(
                    "MODULES AVAILABLE",
                    f"{len(modules)}: {modules[0]}",
                )
            else:
                self.display(
                    "MODULES",
                    "NONE AVAILABLE",
                )

        # SYSTEM
        elif screen == "SYSTEM":

            ip_address = system.get("ip") or "Unknown"
            cpu_temp = system.get("cpu_temp") or "Unknown"

            self.display(
                f"IP {ip_address}",
                f"CPU {cpu_temp}",
            )

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

    def handle_buttons(self):

        current = self.read_buttons()

        for name, pressed in current.items():

            was_pressed = self.previous_buttons[name]

            if pressed and not was_pressed:

                if name == "UP":
                    self.screen_index = (
                        self.screen_index - 1
                    ) % len(SCREENS)

                elif name in ("DOWN", "RIGHT"):
                    self.screen_index = (
                        self.screen_index + 1
                    ) % len(SCREENS)

                elif name in ("LEFT", "SELECT"):
                    self.screen_index = 0

                print(
                    f"Button: {name}, "
                    f"Screen: {SCREENS[self.screen_index]}",
                    flush=True,
                )

                self.render()

        self.previous_buttons = current

    # ----------------------------------------------
    # Main loop
    # ----------------------------------------------

    def run(self):

        print("SvxLink LCD Controller V0.2")
        print(f"Dashboard API: {API_URL}")
        print("Press Ctrl+C to stop.")

        self.display(
            "SVXLINK LCD V0.2",
            "INITIALISING",
        )

        next_poll = 0.0

        try:

            while True:

                now = time.monotonic()

                if now >= next_poll:

                    try:
                        self.fetch_status()

                    except (
                        OSError,
                        ValueError,
                        KeyError,
                        TypeError,
                    ) as error:

                        self.api_available = False

                        print(
                            f"Dashboard error: {error}",
                            flush=True,
                        )

                    self.render()
                    next_poll = (
                        time.monotonic() + POLL_INTERVAL
                    )

                self.handle_buttons()

                time.sleep(BUTTON_INTERVAL)

        except KeyboardInterrupt:
            print("\nLCD controller stopped.")

        finally:
            self.lcd.clear()


# --------------------------------------------------
# Program entry
# --------------------------------------------------

if __name__ == "__main__":

    controller = SvxLinkLCD()
    controller.run()
