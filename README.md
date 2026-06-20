# ReBrewie-Pi-Control

![ReBrewie-Pi-Control logo](assets/rebrewie-pi-control-logo.jpg)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-local%20web%20controller-009688.svg)](https://fastapi.tiangolo.com/)
[![Platform](https://img.shields.io/badge/Tested%20on-Raspberry%20Pi%20Zero%20W-red.svg)](https://www.raspberrypi.com/)

## Project Title

**ReBrewie-Pi-Control**

## Description

This is a Raspberry Pi-native (tested on a RPi Zero W with 512 MB of RAM) local-only web controller for Brewie+ / ReBrewie machines. It is a replacement for the original Brewie Control Android APK, but keeps the original app concepts - connect on the same Wi-Fi/LAN, monitor brew state, start/pause/resume/stop, manage recipes, and view live progress - while adding modern transport flexibility and a ReBrewie project mirroring "Developer" mode (to access the additional functionality provided by the ReBrewie project), which allows direct command injection.

The app runs a FastAPI web server on the Raspberry Pi and communicates with the Brewie machine over TCP, HTTP bridge, serial, or mock transport. The verified local setup uses the Pi web UI at `http://<pi-ip>:8080` and a Brewie TCP bridge at `<brewie-ip>:9000`.

> Experimental software: use at your own risk. Brewie machines include pumps, valves, heaters, and water paths. Always supervise physical operation.

## Features

- Local-only responsive web dashboard for Brewie/ReBrewie control.
- Live telemetry parsing for Brewie V7-style status frames.
- Manual preparation controls for water inlet, valves, pumps, heaters, fan, and stop commands.
- Brewing recipe list, editor, upload/import flow, and recipe start/pause/resume/stop controls.
- Stock Brewie JSON recipe importer that converts original `instructions` arrays into internal `P103` controller steps.
- Separate Cleaning Programs area for Short Clean, Full Clean, and Sanitizing Clean routines.
- Emergency stop path that sends valve/pump/heater shutdown commands.
- Developer Mode terminal for raw P-command testing.
- Stock Brewie TCP framing support (`$ packet length payload check *`) with ACK parsing.
- Discovery helpers and Brewie-side diagnostic tools for local troubleshooting.
- Raspberry Pi deployment scripts for Windows PowerShell and Linux/macOS shell users.

## Screenshots

The web interface is available from any browser on the same LAN at `http://<pi-ip>:8080` after installation.

### Dashboard

![Dashboard](docs/screenshots/dashboard.jpeg)

### Progress

![Progress](docs/screenshots/progress.jpeg)

### Preparation

![Preparation](docs/screenshots/preparation.jpeg)

### Cleaning

![Cleaning](docs/screenshots/cleaning.jpeg)

### Recipes

![Recipes](docs/screenshots/recipes.jpeg)

### Developer

![Developer](docs/screenshots/developer.jpeg)

## Tech Stack

- Python 3.11+ / Python 3.13 on Raspberry Pi OS
- FastAPI, Starlette, Uvicorn
- Pydantic and pydantic-settings
- Jinja2 templates
- Vanilla JavaScript and CSS
- pyserial and httpx
- systemd service for Raspberry Pi deployment
- PowerShell and shell deployment scripts
- OpenAI Codex App, used during development, review, and documentation preparation

## Installation

### 1. Raspberry Pi prerequisites

Use Raspberry Pi OS or another Debian-like Linux image.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip openssh-server rsync
```

Make sure the Pi and Brewie machine are on the same local network. DHCP reservations are recommended so their IP addresses do not change.

### 2. Brewie machine prerequisites

The verified setup expects a TCP bridge on the Brewie machine, usually listening on port `9000`. Helper tools are included in:

```text
contrib/brewie-machine/
```

Deploy from Windows:

```powershell
.\deploy-to-brewie.ps1 -Host 192.168.1.132 -User root -Password "your-password"
```

Then review `contrib/brewie-machine/README.md` for probe and bridge options.

### 3. Configure project settings

Copy `.env.example` to `.env` on the Pi and adjust device-specific values:

```bash
cp .env.example .env
nano .env
```

Important values:

```env
BREWIE_TRANSPORT=tcp
BREWIE_HOST=192.168.1.132
BREWIE_PORT=9000
BREWIE_TCP_FRAMING=true
LOCAL_BIND=0.0.0.0
LOCAL_PORT=8080
TO_LITER=20.0
```

Reminder: update the Raspberry Pi and Brewie IP addresses for your own network.

### 4. Install on the Raspberry Pi

From the project folder on the Pi:

```bash
./install.sh
sudo systemctl enable --now rebrewie-control-pi
```

Open:

```text
http://<pi-ip>:8080
```

## Usage

### Dashboard

View connection status, temperatures, actuator echoes, telemetry, and current program state.

### Preparation

Use manual controls for preparation and testing. These commands affect real hardware.

### Cleaning

Use the Cleaning page for maintenance programs:

- Short Clean
- Full Clean
- Sanitizing Clean

Each run requires confirmation. Emergency Stop remains available on the same page.

### Recipes

Upload ReBrewie-format JSON or original stock Brewie JSON recipes. Stock recipe JSON files are converted into internal controller steps and saved into `recipes/`.

### Developer

Send raw P-commands directly to the controller. This mode is intended for careful troubleshooting and protocol development.

## API Reference

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/status` | Current application and telemetry state |
| GET | `/api/log?n=100` | Recent in-memory event log |
| POST | `/api/command` | Send a raw command, JSON body `{ "cmd": "P999" }` |
| POST | `/api/control/start` | Start a brew recipe, body `{ "recipe_id": "..." }` |
| POST | `/api/control/pause` | Pause by closing all valves |
| POST | `/api/control/resume` | Re-initialize and resume/requeue current step |
| POST | `/api/control/stop` | Stop program and send shutdown commands |
| POST | `/api/control/step` | Manually enqueue a recipe step |
| POST | `/api/developer/raw` | Send raw developer P-command |
| GET | `/api/developer/commands` | List configured command map |
| GET | `/api/recipes` | List recipes |
| POST | `/api/recipes` | Create recipe |
| GET | `/api/recipes/{recipe_id}` | Fetch recipe |
| PUT | `/api/recipes/{recipe_id}` | Update recipe |
| DELETE | `/api/recipes/{recipe_id}` | Delete recipe |
| POST | `/api/recipes/upload` | Upload `.json` recipe and convert if needed |
| GET | `/api/cleaning` | List cleaning programs |
| POST | `/api/cleaning/upload` | Upload `.json` cleaning program |
| POST | `/api/cleaning/{program_id}/start` | Start a cleaning program |
| GET | `/api/device/scan` | Scan/discover likely Brewie devices |
| POST | `/api/device/configure` | Configure discovered device transport |
| WebSocket | `/ws` | Live state updates |

## Configuration

Configuration is handled by environment variables, usually through `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BREWIE_TRANSPORT` | `tcp` | `tcp`, `http`, `serial`, or `mock` |
| `BREWIE_HOST` | `192.168.1.132` | Brewie machine IP |
| `BREWIE_PORT` | `9000` | Brewie TCP bridge port |
| `BREWIE_TCP_FRAMING` | `true` | Enable stock Brewie frame wrapping |
| `BREWIE_HTTP_BASE` | `http://192.168.1.113:8080` | HTTP bridge base URL |
| `BREWIE_SERIAL_PORT` | `/dev/ttyUSB0` | Serial device path |
| `BREWIE_SERIAL_BAUD` | `115200` | Serial baud rate |
| `LOCAL_BIND` | `0.0.0.0` | Web bind address |
| `LOCAL_PORT` | `8080` | Web port |
| `RECIPE_DIR` | `recipes` | Recipe storage folder |
| `DISCOVERY_ENABLED` | `true` | Enable discovery helpers |
| `TO_LITER` | `20.0` | Default batch/session volume |
| `MASH_TEMP_DELTA` | `0.0` | P80 mash calibration delta |
| `BOIL_TEMP_DELTA` | `0.0` | P80 boil calibration delta |

## Tests

Basic validation:

```bash
python3 -m py_compile app/config.py app/main.py app/recipes.py app/routers/api.py
bash scripts/verify_app_import.sh
```

TCP bridge checks:

```bash
python3 scripts/test_brewie_tcp_bridge.py --host <brewie-ip> --port 9000
```

Pi telemetry check:

```bash
python3 scripts/check_pi_telemetry.py --url http://<pi-ip>:8080
```

## Deployment

### Windows to Raspberry Pi

```powershell
.\deploy-to-pi.ps1 -HostName 192.168.1.113 -User pi -Password "your-password"
```

### Linux/macOS to Raspberry Pi

```bash
PI_HOST=192.168.1.113 PI_USER=pi APP_DIR=/opt/rebrewie-control-pi scripts/deploy_to_pi.sh
```

### Brewie helper tools

```powershell
.\deploy-to-brewie.ps1 -Host 192.168.1.132 -User root -Password "your-password"
```

## Run Locally

Mock mode is useful for web UI development without a Brewie machine:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
BREWIE_TRANSPORT=mock uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`.

## Code Example

Build the P80 initialization command:

```python
from app.config import settings

cmd = settings.build_p80_command(volume_l=20.0)
print(cmd)  # P80 20.0 0 0.00000 0.00000
```

Convert a recipe step to a `P103` command:

```python
from app.recipes import load_recipe

recipe = load_recipe("demo-ipa1")
args = recipe.to_p103_args(0)
print("P103", args)
```

Send a raw command through the API:

```bash
curl -X POST http://<pi-ip>:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"cmd":"P999"}'
```

## Code Structure

- `app/main.py` starts FastAPI, the transport, and receive loop.
- `app/config.py` loads settings and defines canonical command strings.
- `app/transports/` contains TCP, HTTP, serial, and mock transports.
- `app/parser.py` parses Brewie telemetry into shared state.
- `app/state.py` stores live state and command echoes.
- `app/recipes.py` models recipes, import conversion, and cleaning programs.
- `app/routers/` exposes REST, WebSocket, page, and discovery routes.
- `app/templates/` and `app/static/` implement the web interface.
- `contrib/brewie-machine/` contains Brewie-side helper tooling.

## File Structure

```text
ReBrewie-Control-Pi/
  app/
    routers/
    static/
    templates/
    transports/
  assets/
  cleaning_programs/
  contrib/brewie-machine/
  docs/
  recipes/
  scripts/
  systemd/
  .env.example
  install.sh
  deploy-to-pi.ps1
  deploy-to-brewie.ps1
  README.md
  requirements.txt
```

## Documentation

Class-level documentation is available in `docs/`, including:

- `docs/Settings.md`
- `docs/Recipe.md`
- `docs/RecipeStep.md`
- `docs/BrewState.md`
- `docs/TcpTransport.md`
- `docs/BaseTransport.md`
- `docs/BrewieDiscovery.md`

Brewie machine helper documentation is in `contrib/brewie-machine/README.md`.

## Contributing

Contributions are welcome. Recommended workflow:

1. Fork the repository.
2. Create a feature branch.
3. Keep changes focused and documented.
4. Test with mock transport where possible.
5. For hardware changes, document the machine, network, and command sequence used.
6. Open a pull request with clear safety notes.

## Contributors

| Contributor | Role |
| --- | --- |
| CommoGrunt | Original author and project maintainer |

## FAQ

### Is this official Brewie software?

No. This is an experimental community project.

### Does it require internet access?

No. The web controller is designed for local network use.

### Can I use DHCP?

Yes, but DHCP reservations are recommended for the Raspberry Pi, Brewie machine, and development computer.

### Do I need both `.json` and `.brewie` recipe files?

No. This app imports JSON recipe files. Original `.brewie` files are compressed Qt Binary JSON packages and are not required for this importer.

### Why does the UI say actuator state is commanded?

Some Brewie telemetry echoes the last command rather than confirming every actuator electrically. The UI labels this distinction where possible.

## Roadmap

Future additions and updates may include features to facilitate webhosting to allow secure remote access outside of a local network, monitoring and controlling multiple machines registered via their unique machine ID/Serial #, and the addition of a webcam feed option to the Progress screen to allow live remote observation to better detect issues such as a boil over situation which may not set off any error messages.

## Security

- This app is designed for trusted local networks only.
- Do not expose it directly to the public internet.
- Developer Mode allows direct command injection and can actuate real hardware.
- Change default passwords on Raspberry Pi and Brewie SSH accounts.
- Use DHCP reservations or static addressing only on trusted LANs.
- Review uploaded recipes before brewing.

## Support

This is experimental software, please use at your own risk as no support is currently available other than the information already provided.

## Acknowledgements

I have no programming experience and have taken this project on to learn as I go, so please forgive all of my coding errors. Original source code files and examples borrowed from the Brewie+ stock software, ReBrewie project improvements, Facebook Brewie Owners Group, https://think.gusius.com/, and multiple others that deserve all the credit for compiling and updating the original code to improve and keep our Brewie machines going.

## Acknowledgement Codes

The original manufacturer Android APK file was inspected to understand the original app layout and styling.

## References

- Original Brewie+ software and Android App APK
- ReBrewie project source code files
- Brewie Owners community knowledge and troubleshooting notes

## Related Projects

Related information and developments you might find interesting can be found by visiting the Facebook Brewie Owners Group.

## Changelog

### 0.2.0 - Current public release

- Added stock Brewie TCP frame encoding and ACK parsing.
- Added recipe JSON upload and conversion.
- Added Cleaning Programs page and separate cleaning program storage.
- Added improved stop behavior and actuator echo labeling.
- Added Brewie helper tools and deployment scripts.
- Added class-level documentation.

### 0.1.0 - Initial prototype

- FastAPI web UI with dashboard, preparation controls, progress, recipes, and developer terminal.
- Initial TCP, HTTP, serial, and mock transports.

## License

MIT License. See [LICENSE](LICENSE).

## Contact

No contact information is provided. The author is unable to provide direct support.


