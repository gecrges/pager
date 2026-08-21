# pager
pygame pseudo-OS for a minimal DAP. for linux.

---

point to music folder in loc.txt

---
## Setup
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
cp lpr.otf /usr/share/fonts
fc-list
```
important for vm: turn audio on... as stupid as that sounds

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
