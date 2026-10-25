# SvxLink-LCD

**An optional LCD monitoring and control interface for SvxLink and SvxLink-Dash V4.1.**

SvxLink-LCD provides a local operating interface using an I²C character display and navigation buttons.

The project is intended to complement the existing SvxLink-Dash V4.1 browser interface, not replace it.

The initial implementation uses the Adafruit 16×2 RGB LCD Pi Plate, incorporating five navigation buttons and an MCP23017 I²C expander.

## 1. Project Status

**Development version: V0.1 — Experimental**

The following functions have been successfully tested:

- Raspberry Pi I²C communication.
- Detection of the MCP23017 at address `0x20`.
- LCD text display.
- RGB backlight operation.
- Detection of all five navigation buttons.
- Interactive menu navigation using UP, DOWN and SELECT.
- Retrieval of live SvxLink information through the SvxLink-Dash V4.1 API.
- Display of live callsign, talkgroup and reflector information.

These tests were performed on a Raspberry Pi 3B running Debian 13 Trixie with Python 3.13.

The standalone V0.1 controller has not yet completed validation.

## 2. Hardware Requirements

The initial development hardware consists of:

- Raspberry Pi 3B.
- Adafruit 16×2 RGB LCD Pi Plate.
- Existing USB sound card.
- Working SvxLink installation.
- SvxLink-Dash V4.1.

The Adafruit Pi Plate connects to the first 26 pins of the Raspberry Pi GPIO header.

It uses an MCP23017 I²C port expander, normally configured at address `0x20`.

The display, RGB backlight and five navigation buttons are controlled through the I²C interface.

**Important:** Always disconnect power before installing or removing the Pi Plate. Check connector alignment and clearance around the Raspberry Pi USB connectors.

## 3. Software Prerequisites

A working installation of SvxLink and SvxLink-Dash V4.1 is required for live node monitoring.

The dashboard is expected to provide its status API on port 5000, unless configured otherwise.

The LCD controller uses the existing Raspberry Pi Python 3 installation with additional Adafruit libraries installed into an isolated virtual environment.

The LCD software must not interfere with the operation of SvxLink, its audio hardware or the browser dashboard.

## 4. Enable I²C

On the Raspberry Pi, run:

```bash
sudo raspi-config
```

Navigate to:

**Interface Options → I2C → Enable**

Exit `raspi-config` and reboot if requested.

Install the I²C utilities:

```bash
sudo apt update
sudo apt install -y i2c-tools
```

Verify that the I²C device is available:

```bash
ls -l /dev/i2c*
```

For the standard Raspberry Pi GPIO I²C interface, `/dev/i2c-1` should be present.

## 5. Verify the Adafruit Pi Plate

With the Pi Plate connected, run:

```bash
sudo i2cdetect -y 1
```

The expected MCP23017 address is:

```text
0x20
```

If this address is not detected, check the I²C configuration, board connection and hardware before proceeding.

Do not assume the LCD is available merely because I²C is enabled.

## 6. Install Python Dependencies

The initial development installation uses Python 3.13 on Debian 13 Trixie.

Install the required Python development packages:

```bash
sudo apt install -y \
  python3-venv \
  python3-dev
```

The Python development headers are important. Without them, some Adafruit dependencies may fail to compile with an error such as:

```text
fatal error: Python.h: No such file or directory
```

On the tested Python 3.13 installation, the corresponding development package is:

```bash
sudo apt install -y python3.13-dev
```

The final installer should detect the installed Python version rather than assume Python 3.13 is present.

## 7. Create the LCD Python Environment

Create the application directory:

```bash
sudo mkdir -p /opt/svxlink-lcd
sudo chown pi:pi /opt/svxlink-lcd
```

Create the virtual environment:

```bash
python3 -m venv --system-site-packages \
  /opt/svxlink-lcd/venv
```

Install the official Adafruit library:

```bash
/opt/svxlink-lcd/venv/bin/python -m pip install \
  adafruit-circuitpython-charlcd
```

The installation also installs the necessary Python dependencies, including Adafruit Blinka and the MCP23017 support library.

The use of a virtual environment keeps these dependencies separate from the system Python packages used by SvxLink-Dash.

## 8. Verify the Python Libraries

Run:

```bash
/opt/svxlink-lcd/venv/bin/python - <<'PY'
import board
import busio
import adafruit_character_lcd.character_lcd_rgb_i2c
import adafruit_mcp230xx
import adafruit_bus_device

print("Adafruit LCD Python libraries available")
PY
```

The expected output is:

```text
Adafruit LCD Python libraries available
```

## 9. Test the LCD Display

Run:

```bash
/opt/svxlink-lcd/venv/bin/python - <<'PY'
import board
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd

lcd = character_lcd.Character_LCD_RGB_I2C(
    board.I2C(), 16, 2
)

lcd.clear()
lcd.color = [0, 100, 0]
lcd.message = "SVXLINK LCD TEST\nG4NAB READY"

print("LCD initialised and message sent")
PY
```

The display should illuminate and show two lines of text.

The callsign in this example is illustrative and may be changed.

## 10. Test the Five Navigation Buttons

The Adafruit library exposes these properties:

```python
lcd.up_button
lcd.down_button
lcd.left_button
lcd.right_button
lcd.select_button
```

All five buttons have been successfully tested on the development hardware.

The buttons will eventually provide menu navigation, talkgroup selection, module activation and access to stored commands.

These control functions are not yet implemented in the standalone controller.

## 11. SvxLink-Dash V4.1 Integration

The LCD controller obtains live operating information from the existing dashboard API.

The default single-port endpoint is:

```text
http://127.0.0.1:5000/api/status?port=1
```

Verify the endpoint using:

```bash
curl -s \
  'http://127.0.0.1:5000/api/status?port=1' \
  | python3 -m json.tool
```

Available information includes:

- Callsign.
- Active talkgroup.
- Reflector connection status.
- Receiver and transmitter activity.
- SvxLink service status.
- Available modules.
- EchoLink status.
- System information.

The dashboard remains the source of operating information.

The initial LCD controller is read-only and does not send commands to SvxLink.

## 12. Display Design

The display provides 16 characters across two lines.

A typical home screen might be:

```text
G4NAB ONLINE
TG 235 IDLE
```

The intended display logic includes:

- Live status polling.
- Updating the display only when information changes.
- Compact operating-state information.
- Temporary error indications when the dashboard is unavailable.
- Navigation between information screens.

The five buttons will eventually support interactive menus.

## 13. Planned Development

Future work may include:

- Talkgroup favourites and selection.
- Module activation.
- User-defined DTMF macros.
- Macro editing and execution.
- Local command feedback.
- Microphone DTMF integration.
- Additional hardware and display support.
- Optional systemd service installation.
- Automated installation and removal.

These functions remain proposals and are not claimed as implemented.

The project may eventually support radio-less SvxLink nodes with a local microphone, speaker and operating console.

No particular microphone, sound card or final hardware product has been selected.

## 14. Development Principles

SvxLink-LCD is intended to be an optional addition to an existing installation.

The following principles apply:

1. SvxLink remains operational without the LCD.
2. SvxLink-Dash V4.1 remains fully accessible through the browser.
3. LCD hardware is detected before attempting to initialise it.
4. The LCD controller does not alter SvxLink configuration automatically.
5. Hardware failures must not interrupt SvxLink or the dashboard.
6. Existing status and command interfaces should be reused wherever possible.
7. Development changes should be independently tested before integration.

## 15. References

- [Adafruit 16×2 LCD Pi Plate Guide](https://learn.adafruit.com/adafruit-16x2-character-lcd-plus-keypad-for-raspberry-pi)
- [Adafruit CircuitPython CharLCD](https://github.com/adafruit/Adafruit_CircuitPython_CharLCD)
- [SvxLink](https://www.svxlink.org/)
- [SvxLink-Dash V4.1](https://github.com/f5vmr/SvxLink-Dash-V4.1)

## Credits

**Tobias Blomberg, SM0SVX** — Original author of SvxLink.

**Chris Jackson, G4NAB** — SvxLink-Dash and SvxLink-LCD project development.

Adafruit Industries — Original LCD Pi Plate hardware and CircuitPython software libraries.

---

**Project status:** Experimental development. The initial hardware and live dashboard display tests have been completed successfully.
