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

mkdir -p ~/pager
mount -t vboxsf vmshared ~/pager

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install numpy tinytag pygame python-mpv
python -c "import numpy, tinytag, pygame, mpv; print('OK')"
find /usr/lib /lib -iname '*mpv*' 2>/dev/null

ls -lah ~/pager/mu

cp lpr.otf /usr/share/fonts
fc-list
```
important for vm: turn audio on... as stupid as that sounds

TODO: pygame starts at boot, exiting shuts off machine
---
