# pager
pygame pseudo-OS for a minimal DAP. for linux.

---

expects 'mu' folder in /mnt/vmshared/ -- will be altered later, but this is kept for debugging.

---
## Setup
```
setup-alpine
ping -c 3 google.com
```
if that doesn't work, do  the following
```
ip link set eth0 up
udhcpc -i eth0
ip route                  (optional)
ping -c 3 google.com
```
close, save state of drive
remove attachment (optical drive)
close fully
restart


## After reboot: APK packages
```
ping -c 3 google.com

apk update
apk upgrade
apk add python3 py3-pip py3-virtualenv python3-dev build-base pkgconf git
apk add --update --no-cache --repository http://dl-cdn.alpinelinux.org/alpine/edge/community/ mpv mpv-dev sdl2 sdl2-dev sdl2_image sdl2_image-dev sdl2_mixer sdl2_mixer-dev sdl2_ttf sdl2_ttf-dev freetype freetype-dev

mkdir -p ~/pager
mount -t vboxsf vmshared ~/pager

mkdir -p ~/p
cd ~/p
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install numpy tinytag pygame python-mpv
python -c "import numpy, tinytag, pygame, mpv; print('OK')"
find /usr/lib /lib -iname '*mpv*' 2>/dev/null

ls -lah ~/pager/mu

**HERE FIX BACKEND FOR SOUND* MPV DOESNT WORK**
```
---

good to remember when setting up alpine for pager:

```
make shared folder (auto mount) at /mnt/vmshared/
mkdir -p /mnt/vmshared/
mount -t vboxsf vmshared /mnt/vmshared/

setup-alpine

setup-apkrepos -c
apk add py3-pygame

python3 -m venv --system-site-packages
source .venv/bin/activate
pip install tinytag
pip install mpv
pip install numpy

move Lower Pixel font from shared folder to ~/.fonts

apk add mpv mpv-libs xinit xorg-server
apk add 
apk add 

setup-xorg-base
```
