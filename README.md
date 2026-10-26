# SvxLink-LCD

**Optional local monitoring and control for SvxLink using an Adafruit 16×2 RGB LCD Pi Plate and SvxLink-Dash V4.1.**

SvxLink-LCD adds a five-button, two-line LCD interface to an existing SvxLink node. It reads status from SvxLink-Dash V4.1 and, when explicitly authorised, sends restricted DTMF control commands to SvxLink. The dashboard remains the main configuration interface.

**Project status: V0.4 — experimental, operational single-logic installation tested.** On the development Raspberry Pi, LCD navigation, live talkgroup selection, monitored-TG discovery, persistent favourites, and confirmed favourite addition/removal have been demonstrated. These results do not establish full multiport control support.

## Supported arrangements and current limits

The design accommodates SimplexLogic, RepeaterLogic, radio-less nodes using an appropriate SvxLink logic, and installations with multiple ports. **Live control has been validated on one SimplexLogic installation with one active radio logic.** Repeater, radio-less and multiport hardware/control combinations require installation-specific validation; multiport DTMF destination selection is not yet enabled.

The LCD is independent of the normal audio, RF, reflector and dashboard operation. Removing or stopping `svxlink-lcd.service` should not interrupt those systems. The LCD does not replace the dashboard or edit `svxlink.conf`.

## Hardware

The tested development configuration uses:

- Raspberry Pi 3B running Debian 13 Trixie.
- Adafruit 16×2 RGB LCD Pi Plate with five buttons, connected to the Raspberry Pi GPIO header.
- An extension cable may be used to extend the panel to the front of a repeater for example.
- MCP23017 I²C port expander at address `0x20`.
- An existing working SvxLink installation and SvxLink-Dash V4.1.
- Existing node audio and radio interfaces, which remain managed by SvxLink.

Power off the Raspberry Pi before fitting or removing the plate. Check header alignment and clearance around the USB connectors.

### Prepare I²C

```bash
sudo raspi-config
```

Choose **Interface Options → I2C → Enable**, then reboot if requested.

```bash
sudo apt update
sudo apt install -y i2c-tools
ls -l /dev/i2c-1
sudo i2cdetect -y 1
```

The Pi Plate should appear at `0x20`. If not, resolve I²C wiring/configuration before starting the LCD application.

## Prerequisites

Install and configure SvxLink and SvxLink-Dash V4.1 first. Confirm the dashboard status endpoint is available:

```bash
curl -s 'http://127.0.0.1:5000/api/status?port=1' | python3 -m json.tool
```

Port `5000` and port selection `1` are the current controller defaults. Confirm the intended deployment uses this endpoint.

The installer currently expects a local account named `pi`, the service account `svxlink`, and a checkout at `/opt/svxlink-lcd`. It installs Python/venv/I²C dependencies and the Adafruit LCD library.

## Installation

On the Raspberry Pi:

```bash
sudo apt install -y git
sudo mkdir -p /opt/svxlink-lcd
sudo chown pi:pi /opt/svxlink-lcd
git clone https://github.com/f5vmr/Svxlink-LCD.git /opt/svxlink-lcd
cd /opt/svxlink-lcd
sudo bash install/install-svxlink-lcd.sh
```

For an existing checkout, do not clone again:

```bash
cd /opt/svxlink-lcd
git pull --ff-only
sudo bash install/install-svxlink-lcd.sh
```

The installer preserves existing `/etc/svxlink-lcd/lcd_config.json` and persistent talkgroups, prepares the virtual environment, and installs the following systemd units:

- `svxlink-lcd.service` — LCD display and navigation, running as `pi`.
- `svxlink-lcd-control.socket` — restricted Unix-domain control socket.
- `svxlink-lcd-control.service` — privileged DTMF control helper, running as `svxlink` and started through the socket.

Confirm operation:

```bash
sudo systemctl status svxlink-lcd.service --no-pager
sudo systemctl status svxlink-lcd-control.socket --no-pager
sudo journalctl -u svxlink-lcd.service -n 30 --no-pager
```

The control service may be socket-activated rather than continuously running until requested.

### Updating an installed system

After a code-only update:

```bash
cd /opt/svxlink-lcd
git pull --ff-only
sudo systemctl restart svxlink-lcd-control.service
sudo systemctl restart svxlink-lcd.service
```

Rerun the installer when installation units, dependencies, or filesystem setup change. The operational configuration and favourites are intended to survive upgrades.

## Configuration and data files

| Path | Purpose |
|---|---|
| `/opt/svxlink-lcd/config/lcd_config.json` | Repository's initial/default node configuration |
| `/etc/svxlink-lcd/lcd_config.json` | Preserved operational node and control configuration |
| `/opt/svxlink-lcd/config/federation_talkgroups.json` | Bundled reference directory of 131 federation TGs |
| `/var/lib/svxlink-lcd/talkgroups.json` | Persistent favourites, including entries added from the LCD |
| `/etc/svxlink/svxlink.conf` | Existing SvxLink configuration; read to discover monitored TGs and DTMF control PTYs |

**Do not edit the repository template to manage day-to-day favourites.** The installer creates the operational favourites store from initial configuration only if it is absent; later additions and removals are managed through the LCD.

The tested storage permissions are directory `pi:svxlink` with mode `2750` (setgid), and favourites file `pi:svxlink` with mode `0640`. The display service can update the file; the restricted control helper can read it.

### Enable or disable live DTMF control

The operational configuration contains a `control` object, for example:

```json
"control": {
  "node_type": "simplex",
  "selected_port": null,
  "enabled_ports": [],
  "transmission_enabled": true
}
```

This is an **excerpt** from the JSON file, not a complete standalone JSON document. `transmission_enabled` must be a JSON boolean and is spelled **singular**. Omitting it defaults to disabled. Set it to `false` for preview-only operation.

Live transmission also requires the control-service's `ENABLE_DTMF_TRANSMISSION` switch, matching node logic, a supported unambiguous DTMF destination and successful runtime PTY validation. The helper does not accept arbitrary DTMF strings. Do not change unrelated SvxLink settings merely to enable the LCD.

Validate a configuration change with:

```bash
python3 -m json.tool /etc/svxlink-lcd/lcd_config.json > /dev/null
sudo systemctl restart svxlink-lcd-control.service
```

## LCD operation

The five buttons are **UP**, **DOWN**, **LEFT**, **RIGHT** and **SELECT**. The 16×2 display shows live node/reflector information and menus.

- **UP / DOWN:** Move among menu items when no confirmation is active.
- **SELECT:** Enter a menu or explicitly confirm a prepared command or file operation.
- **RIGHT:** Enter a menu, or offer to save a newly connected monitored TG when eligible.
- **LEFT:** Cancel or return to the previous menu.

### Talkgroup selection

Under **TALKGROUPS**, saved favourites appear first. Additional monitored TGs that are not already favourites are also listed. Entries use their actual TG numbers rather than list positions.

Selecting a TG prepares a DTMF command; for example, TG 23548 produces `9123548#`. Press **SELECT** again to confirm transmission. An acknowledged command cannot be transmitted a second time simply by pressing SELECT repeatedly. The dashboard can subsequently confirm the active TG.

The privileged control service authorises a requested TG only if it is in the persisted favourites or in SvxLink's configured `MONITOR_TGS`. Its numeric presence in the federation directory alone does not authorise transmission.

### Monitored TGs and the federation directory

The controller reads the existing `[ReflectorLogic]` setting, for example:

```ini
MONITOR_TGS=23560,23548
```

The bundled 131-entry federation directory provides names for known numbers. An unknown monitored number can still appear under a generic label such as `TG 23548`. The directory is a reference list, not the live monitored-TG state and not a guarantee that a reflector will accept a TG.

### Add a monitored TG to favourites

1. Select a monitored TG that is not already saved.
2. Confirm the DTMF connection with SELECT.
3. On successful transmission, the LCD offers `RIGHT=SAVE`.
4. Press RIGHT to display `SAVE TG <number>?`.
5. Press SELECT to write the favourite, or LEFT to cancel.

Saving is a local JSON operation; it does **not** send another DTMF command. An existing favourite does not receive a save prompt and cannot be duplicated.

### Remove a favourite

1. Open **TALKGROUPS → MANAGE FAVS**.
2. Select the saved favourite.
3. Confirm `REMOVE TG <number>?` with SELECT; LEFT cancels.
4. The entry is deleted from `/var/lib/svxlink-lcd/talkgroups.json`.

Removal does **not** transmit DTMF or modify `MONITOR_TGS`, the federation directory, or the currently connected TG. If the TG remains monitored it will still appear in the normal TALKGROUPS menu.

### Modules and other menus

The MODULES menu displays configured/available modules. Module activation uses explicitly configured DTMF IDs rather than their position in the list and passes through the same restricted confirmation service. NODE STATUS and SYSTEM provide operating information from the dashboard. MACROS currently displays **NOT CONFIGURED**; arbitrary user-defined macro execution has not been implemented.

## Diagnostic commands

```bash
sudo systemctl is-active svxlink-lcd.service
sudo systemctl status svxlink-lcd-control.socket --no-pager
sudo journalctl -u svxlink-lcd.service -n 50 --no-pager
sudo journalctl -u svxlink-lcd-control.service -n 50 --no-pager
```

Inspect favourites and monitored TGs without changing them:

```bash
cd /opt/svxlink-lcd

python3 - <<'PY'
from talkgroup_store import load_favourites
from svxlink_config import get_monitored_talkgroups

print("Favourites:", load_favourites())
print("Monitored:", get_monitored_talkgroups())
PY
```

If saving fails with `Operation not permitted` while replacing a `.talkgroups-*.json` file, verify the storage directory has the setgid bit (`drwxr-s---`) and ownership `pi:svxlink`:

```bash
ls -ld /var/lib/svxlink-lcd
ls -l /var/lib/svxlink-lcd/talkgroups.json
```

Do not make these files world-writable.

If the LCD displays `DASHBOARD ERROR`, first check the configured dashboard API. If a control operation reports an error, inspect the control-service logs and the existing SvxLink DTMF PTY configuration before repeating transmission.

## Current scope and future work

**Verified in this development:** I²C LCD and five-button operation; dashboard status display; single SimplexLogic live TG command; monitored-TG discovery; 131-TG federation lookup; persistent favourites; add, remove, duplicate prevention and permission-safe updates; restricted Unix socket control.

**Not yet claimed as fully validated:** multiport live DTMF control and explicit port selection; broader repeater/radio-less deployment testing; user-defined DTMF macros; microphone/handset integrations; alternative display hardware. These are future development or installation-specific work.

## Design principles

1. SvxLink continues operating independently of the LCD.
2. SvxLink-Dash V4.1 remains responsible for browser configuration and status.
3. LCD control is restricted, explicitly confirmed and disabled unless authorised.
4. Favourites survive software updates without changing the bundled federation directory.
5. Local add/remove operations never send DTMF.
6. All development is tested first before deployment to physical nodes.

## References and credits

- [SvxLink](https://www.svxlink.org/)
- [SvxLink-Dash V4.1](https://github.com/f5vmr/SvxLink-Dash-V4.1)
- [Adafruit 16×2 LCD Pi Plate guide](https://learn.adafruit.com/adafruit-16x2-character-lcd-plus-keypad-for-raspberry-pi)
- [Adafruit CircuitPython CharLCD](https://github.com/adafruit/Adafruit_CircuitPython_CharLCD)

**Tobias Blomberg, SM0SVX** — original SvxLink author.

**Chris Jackson, G4NAB** — SvxLink-Dash and SvxLink-LCD development.

**Adafruit Industries** — LCD Pi Plate hardware and CircuitPython libraries.
