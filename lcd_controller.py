
#!/usr/bin/env python3

"""
SvxLink LCD Controller V0.1

Adafruit 16x2 RGB LCD Pi Plate
Reads live status from SvxLink-Dash V4.1.

Read-only monitoring.
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

LCD_COLUMNS = 16
LCD_ROWS = 2


# --------------------------------------------------
# LCD initialisation
# --------------------------------------------------

i2c = board.I2C()

lcd = character_lcd.Character_LCD_RGB_I2C(
    i2c,
    LCD_COLUMNS,
    LCD_ROWS
)

lcd.color = [0, 100, 0]
lcd.clear()

previous_display = None


# --------------------------------------------------
# Display handling
# --------------------------------------------------

def format_line(text):
    """Restrict text to 16 characters."""
    return str(text)[:LCD_COLUMNS].ljust(LCD_COLUMNS)


def display_lines(line1, line2):
    """Update the LCD only when content changes."""

    global previous_display

    new_display = (
        format_line(line1),
        format_line(line2)
    )

    if new_display == previous_display:
        return

    lcd.message = (
        new_display[0]
        + "\n"
        + new_display[1]
    )

    previous_display = new_display


# --------------------------------------------------
# Dashboard status
# --------------------------------------------------

def fetch_status():
    """Retrieve live status from SvxLink-Dash."""

    with urllib.request.urlopen(
        API_URL,
        timeout=2
    ) as response:
        return json.load(response)


def process_status(data):
    """Extract and display SvxLink state."""

    status = data.get("status", {})

    callsign = status.get("callsign", "UNKNOWN")
    reflector = status.get("reflector", "Unknown")
    talkgroup = str(
        status.get("active_talkgroup", "Standby")
    )

    radio = status.get("radio_state", {})

    rx_active = radio.get("rx", False)
    tx_active = radio.get("tx", False)

    # Determine radio activity

    if tx_active:
        activity = "TX"
    elif rx_active:
        activity = "RX"
    else:
        activity = "IDLE"

    # Compact reflector indication

    if str(reflector).lower() == "connected":
        connection = "ONLINE"
    else:
        connection = "OFFLINE"

    # Compose LCD lines

    line1 = f"{callsign} {connection}"

    if talkgroup.lower() == "standby":
        line2 = f"TG STANDBY {activity}"
    else:
        line2 = f"TG {talkgroup} {activity}"

    display_lines(line1, line2)


# --------------------------------------------------
# Main monitoring loop
# --------------------------------------------------

def main():

    print("SvxLink LCD Controller V0.1")
    print(f"Dashboard: {API_URL}")
    print("Press Ctrl+C to stop.")

    display_lines(
        "SVXLINK LCD",
        "INITIALISING"
    )

    while True:

        try:
            data = fetch_status()
            process_status(data)

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError
        ) as error:

            display_lines(
                "DASHBOARD ERROR",
                "RECONNECTING"
            )

            print(f"Dashboard error: {error}")

        time.sleep(POLL_INTERVAL)


# --------------------------------------------------
# Program entry
# --------------------------------------------------

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("\nLCD controller stopped.")

    finally:
        lcd.clear()
