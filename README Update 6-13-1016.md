# ReBrewie Control Pi

**A Raspberry Pi 4B local-only web controller for Brewie+ / ReBrewie machines.**

This project is a clean-room, Pi-native replacement for the original Brewie Control Android APK. It keeps the original app concepts — connect on the same Wi-Fi/LAN, monitor brew state, start/pause/resume/stop, manage recipes, and view live progress — while adding modern transport flexibility and a developer mode for direct command injection.

---

## Feature overview

| Feature | Description |
|---|---|
| **Dashboard** | Live temperature gauges, actuator status, step progress, brew controls |
| **Progress view** | Animated ring chart showing step % complete, temperature readouts |
| **Preparation mode** | Manual one-click open/close for every valve, pump, hop cage, and heater |
| **Recipe editor** | Full JSON-backed recipe builder with multi-step P103 argument generation |
| **Developer mode** | Raw P-command terminal + quick-fire buttons for every known command |
| **WebSocket stream** | Live push to all connected browser tabs every 2 seconds |
| **Pluggable transports** | `mock` · `tcp` · `serial` · `http` — switchable via `.env` |
| **systemd service** | Auto-start on boot, watchdog restart |

---

## Quick install on Raspberry Pi OS

```bash
unzip rebrewie-control-pi.zip
cd rebrewie-control-pi
chmod +x install.sh
./install.sh
```

Then open a browser on any device on the same network:

```
http://<raspberry-pi-ip>:8080
```

The app binds to `0.0.0.0` so any LAN device can reach it.
**Do not port-forward this service to the internet.**

---

## Manual install (without the installer)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env, then:
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
```

---

## Docker (optional)

```bash
cp .env.example .env   # edit as needed
docker compose up -d
```

Runs on port 8080.  For serial access, edit `docker-compose.yml` to pass the device:

```yaml
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0
```

---

## Configuration — `.env`

| Variable | Default | Description |
|---|---|---|
| `BREWIE_TRANSPORT` | `tcp` | `mock` · `tcp` · `serial` · `http` |
| `BREWIE_HOST` | `192.168.1.132` | Machine IP (TCP transport) |
| `BREWIE_PORT` | `8332` | TCP port |
| `BREWIE_HTTP_BASE` | `http://192.168.1.113:8080` | HTTP bridge base URL |
| `BREWIE_SERIAL_PORT` | `/dev/ttyUSB0` | Serial device node |
| `BREWIE_SERIAL_BAUD` | `115200` | Baud rate |
| `LOCAL_BIND` | `0.0.0.0` | Bind address for the web server |
| `LOCAL_PORT` | `8080` | Port for the web server |
| `RECIPE_DIR` | `recipes` | Directory to store recipe JSON files |
| `TO_LITER` | `20.0` | Batch volume (sent in P80 init) |
| `MASH_TEMP_DELTA` | `0.00000` | Mash temperature calibration offset |
| `BOIL_TEMP_DELTA` | `0.00000` | Boil temperature calibration offset |

After editing `.env`, restart the service:

```bash
sudo systemctl restart rebrewie-control-pi
```

---

## Transport selection

### `mock`
Safe demo mode. No hardware required. The mock transport simulates realistic sensor readings so the full UI can be tested without a Brewie machine.

### `tcp`
Raw line-oriented TCP connection to the Brewie control daemon.  
Set `BREWIE_TRANSPORT=tcp`, `BREWIE_HOST`, and `BREWIE_PORT`.

### `serial`
USB serial connection (e.g. via a USB-to-RS232/TTL adapter).  
Set `BREWIE_TRANSPORT=serial`, `BREWIE_SERIAL_PORT` (e.g. `/dev/ttyUSB0`), and `BREWIE_SERIAL_BAUD`.

The Pi user needs serial port access:
```bash
sudo usermod -aG dialout $USER
# log out and back in
```

### `http`
HTTP/JSON bridge. Some community ReBrewie firmware builds expose a REST endpoint.  
Set `BREWIE_TRANSPORT=http` and `BREWIE_HTTP_BASE`.

---

## Brewie P-command reference

All commands are documented in `commands.md`.  The key ones are:

| Command | Action |
|---|---|
| `P80 <toLiter> 0 <mashDelta> <boilDelta>` | Initialise – sent once per second until the IO board acknowledges |
| `P103 <21 args…>` | Enqueue a brewing step (see `commands.md` for argument layout) |
| `P110` / `P111` | Water inlet open / close |
| `P124` / `P125` | Mash pump start / stop |
| `P126` / `P127` | Boil pump start / stop |
| `P150 <temp×10>` | Set mash heater target (670 = 67.0 °C, 0 = off) |
| `P151 <temp×10>` | Set boil heater target |
| `P999` | Close **all** valves (emergency / safe-state) |

The command map is in `app/config.py` — update the values there if your firmware uses different command strings.

---

## Customising the command map

Edit `app/config.py` → `COMMAND_MAP` dict.  Keys are human-readable names used by the API; values are the raw strings sent over the transport.

---

## Recipes

Recipes are stored as JSON files in `recipes/`.  Each file is a `Recipe` object containing a list of `RecipeStep` objects.

Use the **Recipe Editor** in the web UI to create and edit recipes, or place JSON files directly in the `recipes/` directory.

Each `RecipeStep` maps directly to a `P103` argument list — use the **Developer Mode** terminal to inspect the generated commands.

A sample "Classic American IPA" recipe is included as `recipes/classic-ipa_demo-ipa1.json`.

---

## Project layout

```
rebrewie-control-pi/
├── app/
│   ├── config.py          # Settings (pydantic-settings) + command map
│   ├── main.py            # FastAPI app, lifespan, routing
│   ├── state.py           # Shared in-memory brew state
│   ├── parser.py          # Parse raw Brewie response lines → state
│   ├── recipes.py         # Recipe data model + JSON file I/O
│   ├── routers/
│   │   ├── api.py         # REST API (/api/*)
│   │   ├── ws.py          # WebSocket (/ws)
│   │   └── pages.py       # Jinja2 HTML pages
│   ├── transports/
│   │   ├── base.py        # Abstract transport interface
│   │   ├── factory.py     # Transport selector
│   │   ├── mock.py        # Simulated machine
│   │   ├── tcp.py         # Raw TCP transport
│   │   ├── serial_transport.py  # USB serial transport
│   │   └── http_transport.py    # HTTP bridge transport
│   ├── templates/         # Jinja2 HTML templates
│   └── static/            # CSS + JS served at /static
├── recipes/               # JSON recipe storage
├── systemd/               # systemd service unit
├── install.sh             # One-command Pi installer
├── update.sh              # Local Pi updater wrapper for existing installs
├── Dockerfile             # Docker image
├── docker-compose.yml     # Docker Compose stack
├── requirements.txt
├── .env.example
└── commands.md            # Brewie P-command reference
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | Full brew state JSON |
| `GET` | `/api/log?n=100` | Last N log lines |
| `POST` | `/api/command` | Send raw command `{"cmd":"P999"}` |
| `POST` | `/api/control/start` | Start brew `{"recipe_id":"..."}` (optional) |
| `POST` | `/api/control/pause` | Pause (closes all valves) |
| `POST` | `/api/control/resume` | Resume from pause |
| `POST` | `/api/control/stop` | Stop / abort (safe-state) |
| `POST` | `/api/control/step` | Enqueue a specific recipe step |
| `POST` | `/api/developer/raw` | Raw P-command `{"raw":"P150 670"}` |
| `GET` | `/api/developer/commands` | Full command name → raw map |
| `GET` | `/api/recipes` | List all saved recipes |
| `POST` | `/api/recipes` | Create recipe |
| `GET` | `/api/recipes/{id}` | Get recipe by ID |
| `PUT` | `/api/recipes/{id}` | Update recipe |
| `DELETE` | `/api/recipes/{id}` | Delete recipe |
| `WS` | `/ws` | WebSocket – state push every 2 s |

Interactive API docs (Swagger UI): `http://<raspberry-pi-ip>:8080/docs`

---

## Safety note

This software is for same-LAN / local use with a machine you own.
Brewing hardware includes heaters, pumps, valves, and moving liquid.
Keep physical supervision for cleaning, heating, unclogging, and transfer steps.
Always use **P999 (Close All Valves)** when in doubt.

---

## Service management

```bash
sudo systemctl status  rebrewie-control-pi
sudo systemctl restart rebrewie-control-pi
sudo systemctl stop    rebrewie-control-pi
sudo journalctl -u rebrewie-control-pi -f   # live logs
```

---

## Developed for

**Raspberry Pi 4B** running **Raspberry Pi OS (Bookworm / 64-bit)** with Python 3.11+.  
Compatible with any Brewie+ or community ReBrewie machine.


## Updating an existing Raspberry Pi installation

Do **not** type the angle brackets shown in placeholders. For example, use
`PI_HOST=192.168.1.113`, not `PI_HOST=<192.168.1.113>`; in Bash, `<...>` means
input redirection and causes `No such file or directory` errors.

### Option A: run from your laptop/desktop over SSH

If the app is already installed on your Pi, deploy this checkout over SSH from a
computer that can reach the Pi:

```bash
PI_HOST=192.168.1.113 PI_USER=pi scripts/deploy_to_pi.sh
If the app is already installed on your Pi, you can deploy this checkout over SSH
without re-running the full installer:

```bash
PI_HOST=<raspberry-pi-ip> PI_USER=pi scripts/deploy_to_pi.sh
```

The deploy script syncs code to `/opt/rebrewie-control-pi` by default, installs
updated Python dependencies in the existing virtualenv, and restarts the
`rebrewie-control-pi` systemd service. It preserves the Pi's `.env`, `.venv`,
`recipes/`, and `logs/` directories by default so local configuration and saved
recipes are not overwritten.

Useful options:

```bash
# Preview file changes without installing or restarting
PI_HOST=192.168.1.113 DRY_RUN=1 scripts/deploy_to_pi.sh

# Use a different install directory or SSH username
PI_HOST=192.168.1.113 PI_USER=brew APP_DIR=/opt/rebrewie-control-pi scripts/deploy_to_pi.sh

# Also sync recipe JSON files from this checkout
PI_HOST=192.168.1.113 DEPLOY_RECIPES=1 scripts/deploy_to_pi.sh
```

### Option B: run locally on the Pi without Git

If you are already SSH'd into the Pi, you do not need `git`. Copy or unzip this
project folder onto the Pi, `cd` into that folder, and run:

```bash
sudo ./update.sh
```

For your prompt example, the command would be:

```bash
cd ~/rebrewie-control-pi
sudo ./update.sh
```

You can also call the underlying script directly if it exists:

```bash
sudo bash scripts/update_local_pi.sh
```

This local updater preserves `.env`, `.venv`, `recipes/`, and `logs/` by default,
installs any changed Python requirements, and restarts the systemd service.

If `sudo scripts/update_local_pi.sh` says `command not found`, your Pi is still
using an older project copy that does not contain the new `scripts/` helpers.
Copy or unzip the latest project folder onto the Pi first, then run `sudo
./update.sh` from that updated folder. As a first-install or emergency fallback,
run `sudo ./install.sh` from the latest folder.

PI_HOST=<raspberry-pi-ip> DRY_RUN=1 scripts/deploy_to_pi.sh

# Use a different install directory or SSH username
PI_HOST=<raspberry-pi-ip> PI_USER=brew APP_DIR=/opt/rebrewie-control-pi scripts/deploy_to_pi.sh

# Also sync recipe JSON files from this checkout
PI_HOST=<raspberry-pi-ip> DEPLOY_RECIPES=1 scripts/deploy_to_pi.sh
```

## Network-restricted development workarounds

Some CI or agent environments block outbound access to PyPI or GitHub. The
following repo-local scripts provide deterministic fallbacks.

### Verify app imports without live PyPI access

On any machine that can reach PyPI, build a wheelhouse once:

```bash
python -m pip download -r requirements.txt -d wheelhouse
```

Copy `wheelhouse/` into the restricted environment and run:

```bash
WHEELHOUSE=/path/to/wheelhouse scripts/verify_app_import.sh
```

If PyPI is reachable, the same script can run without `WHEELHOUSE` and will
install directly from `requirements.txt`.

### Export changes when `git push` is blocked

When direct `git push` fails because a proxy blocks GitHub, create bundle and
patch artifacts:

```bash
scripts/export_push_fallback.sh Improved-V2
```

Move the generated files from `/tmp/rebrewie-push-fallback/` to a machine with
GitHub access, then either push the bundle branch or apply the patch with
`git am` and push from there. These bundle/patch commands require `git`; if your
Pi says `git: command not found`, use `sudo scripts/update_local_pi.sh` from a
copied project folder instead, or install Git with `sudo apt-get install git`.
`git am` and push from there.
