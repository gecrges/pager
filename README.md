# pager
pygame pseudo-OS for a minimal DAP. for linux.

## Setup
This setup is written specifically for Debian on Radxa Zero 3W.
### 1. in the Debian terminal
```
sudo apt update
sudo apt full-upgrade -y
```

```
sudo apt install -y python3 python3-pip python3-venv python3-dev build-essential pkg-config git nano
sudo apt install -y mpv libmpv-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libfreetype6-dev i2c-tools
```

```
ls /dev/i2c-*
sudo apt install -y i2c-tools
i2cdetect -l
```
If nothing shows up, Radxa's Debian image ships a hardware config tool (sudo rsetup → Hardware/Overlays menu). Enable the `i2c0` (or whichever bus your header pins map to) overlay there and reboot. Once you have a `/dev/i2c-N` device, wire the SSD1306's `VCC/GND/SDA/SCL` to the matching `3.3V/GND/SDA/SCL` pins on the 40-pin header, then confirm the panel is seen (SSD1306 boards are almost always at address `0x3C`):
```
i2cdetect -y N   # N = your bus number
```
Setup and activate the Python venv:
```
mkdir -p ~/pager && cd ~/pager
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install numpy tinytag pygame python-mpv luma.oled pillow
sudo cp ~/pager/lpr.otf /usr/share/fonts/truetype/
sudo fc-cache -f
```
### 2. (TODO) for pager.py: rewrite display output
Specifically for SSD1306 (128x32 px LCD)
```
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"   # no real display
import pygame
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306

_oled_serial = i2c(port=1, address=0x3C)   # set port to actual i2c bus number
oled = ssd1306(_oled_serial, width=SCREEN_WIDTH, height=SCREEN_HEIGHT)

_last_oled_frame = None
```
Replace the `pygame.display.flip()` with:
```
def flip_to_oled():
    global _last_oled_frame

    pygame.display.flip()

    raw = pygame.image.tostring(screen, "RGB")
    if raw == _last_oled_frame:
        return  # nothing changed since last push - skip the I2C write entirely

    _last_oled_frame = raw
    frame = Image.frombytes("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), raw).convert("1")
    oled.display(frame)
```
```
flip_to_oled()  # was: pygame.display.flip()
```

### 3. in Debian terminal
Autostart + poweroff on exit
```
sudo nano /root/pager/run.sh
```
in `/root/pager/run.sh`, write:
```
#!/bin/sh
cd /root/pager
. .venv/bin/activate
python pager.py
systemctl poweroff
```
then:
```
sudo chmod +x /root/pager/run.sh
sudo nano /etc/systemd/system/pager.service
```
in `/etc/systemd/system/pager.service`, write:
```
[Unit]
Description=Pager display app (SSD1306)
After=multi-user.target

[Service]
ExecStart=/root/pager/run.sh
Restart=no
User=root

[Install]
WantedBy=multi-user.target
```
then:
```
sudo systemctl enable pager.service
sudo reboot
```

## TODO: user-customized MAX_OUTPUT_VRMS -> V = SQRT(PR)
---

point to music folder in loc.txt

---
## Setup for Alpine Linux, VirtualBox (for testing)
### Important: if you are installing Alpine on a virtual machine, DO NOT reboot after installing. Close the VM, remove iso attachment, and restart.
```
setup-alpine
ping -c 3 google.com
```
## After reboot: APK packages
```
ping -c 3 google.com

apk update
apk upgrade
apk add python3 py3-pip py3-virtualenv python3-dev build-base pkgconf git nano
apk add --update --no-cache --repository http://dl-cdn.alpinelinux.org/alpine/edge/community/ mpv mpv-dev sdl2 sdl2-dev sdl2_image sdl2_image-dev sdl2_mixer sdl2_mixer-dev sdl2_ttf sdl2_ttf-dev freetype freetype-dev xorg-server xinit xf86-video-fbdev xf86-input-libinput mesa mesa-dri-gallium mesa-gl

mkdir -p /root/pager
echo 'vmshared /root/pager vboxsf defaults,nofail 0 0' >> /etc/fstab
mount -a

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install numpy tinytag pygame python-mpv
```
test if packages were installed correctly:
```
python -c "import numpy, tinytag, pygame, mpv; print('OK')"
find /usr/lib /lib -iname '*mpv*' 2>/dev/null
```
test if music folder is mounted:
```
ls -lah ~/pager/mu
```
install Lower Pixel font:
```
cp ~/pager/lpr.otf /usr/share/fonts
fc-list
```
important for vm: turn audio on... as stupid as that sounds

## Compile Python for machine
```
python
import py_compile
py_compile.compile('/root/pager/pager.py')
```
`ctrl z` to exit out of py console
compiling will print the new compiled file path, probably something like `/root/pager/__pycache__/pager.cpython-314.pyc`. for the next step, it will be referred to as [x].
```
mv [x] /root/pager/pager.pyc
```

### Make pyscript run on boot
```
rc-update add local default
mkdir -p /etc/local.d
nano /etc/local.d/pager.start
```
in `/etc/local.d/pager.start`, write:
```
#!/bin/sh
LOG=/root/pager.log
MOUNTPOINT=/root/pager
KILLSWITCH=/root/pager/DISABLE_AUTOSTART

echo "[$(date)] boot attempt" >> "$LOG"

if [ -f "$KILLSWITCH" ]; then
  echo "killswitch present, skipping" >> "$LOG"
  exit 0
fi

i=0
while ! mountpoint -q "$MOUNTPOINT"; do
  i=$((i+1))
  [ "$i" -ge 15 ] && { echo "mount not ready after 15s, aborting" >> "$LOG"; exit 1; }
  sleep 1
done

cd /root || exit 1
setsid sh -c '. .venv/bin/activate && exec python /root/pager/2144_optimized.py' >> "$LOG" 2>&1 &
```
`ctrl o` -> `enter` -> `ctrl x` to save & quit
```
chmod +x /etc/local.d/pager.start
ls -l /dev/snd
groups root                            (check if 'audio' is listed. if not, run the next line)
adduser root audio 2>/dev/null || addgroup root audio
```
test without rebooting:
```
rc-service local restart
sleep 3
cat /root/pager.log
ps aux | grep 2144
```
view the log for no issues
```
touch /root/pager/DISABLE_AUTOSTART
```
