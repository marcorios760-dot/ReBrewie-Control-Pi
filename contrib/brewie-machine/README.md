# Brewie+ machine helper scripts

These scripts are for the **Brewie+ machine itself**, not for the Raspberry Pi
controller. Running `brewie_machine_probe.sh` on the Raspberry Pi only tells you
about the Pi; it does not inspect the Brewie+ internals.

## Where the probe script lives after updating the Pi project

If you copied/unzipped this project on the Pi at `~/rebrewie-control-pi`, the
probe script is located at:

```bash
~/rebrewie-control-pi/contrib/brewie-machine/brewie_machine_probe.sh
```

## How to run the probe against the Brewie+

Replace `<brewie-machine-ip>` and `<brewie-ssh-user>` with the actual Brewie+
SSH address/user if SSH is available on the Brewie+.

From the Raspberry Pi shell:

```bash
cd ~/rebrewie-control-pi
scp contrib/brewie-machine/brewie_machine_probe.sh <brewie-ssh-user>@<brewie-machine-ip>:/tmp/brewie_machine_probe.sh
ssh <brewie-ssh-user>@<brewie-machine-ip> 'sh /tmp/brewie_machine_probe.sh > /tmp/brewie_probe.txt'
scp <brewie-ssh-user>@<brewie-machine-ip>:/tmp/brewie_probe.txt ./brewie_probe.txt
```

Then inspect the copied output on the Pi:

```bash
less ./brewie_probe.txt
```

## If you are already logged into the Brewie+

Copy `brewie_machine_probe.sh` to `/tmp` on the Brewie+, then run:

```bash
sh /tmp/brewie_machine_probe.sh > /tmp/brewie_probe.txt
cat /tmp/brewie_probe.txt
```

## Capture actuator command bytes

`brewie_capture_bridge.py` is a temporary diagnostic replacement for the stock
`tty_tcp_bridge.py`. It logs bytes from the Pi controller to `/dev/ttyS1` and
bytes coming back from the Brewie IO board.

Use this only during a short test, then restore the stock bridge:

```bash
/etc/init.d/brewie-bridge stop
stty -F /dev/ttyS1 115200 raw -echo -icanon -crtscts
TTY=/dev/ttyS1 PORT=9000 LOG=/tmp/rebrewie_capture_bridge.log \
  python /root/rebrewie-machine-tools/brewie_capture_bridge.py
```

In another shell or from the Pi web app, send `init`, then the actuator command
you want to test. Stop the capture with `Ctrl-C`, restore the stock bridge, and
read the log:

```bash
/etc/init.d/brewie-bridge start
tail -n 120 /tmp/rebrewie_capture_bridge.log
```

## If the Brewie+ does not have SSH

Use whatever file-transfer method the Brewie+ supports (USB storage, SD card,
serial console paste, or its existing web/file interface) to place the script on
the Brewie+, then run it from a Brewie+ shell. If you cannot get a shell on the
Brewie+ at all, this probe cannot inspect it remotely; use the Pi browser
endpoints (`/api/log?n=200`, `/api/status`, `/api/device/current`) to diagnose
from the outside instead.

## What not to do

Do not run this command on the Pi and assume it inspected the Brewie+:

```bash
sh brewie_machine_probe.sh > /tmp/brewie_probe.txt
```

That only works if your current shell is already on the Brewie+ machine or the
script has been copied there and invoked over SSH as shown above.
