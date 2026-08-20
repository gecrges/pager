# pager
pygame pseudo-OS for a minimal DAP. for linux.

---

expects 'mu' folder in /mnt/vmshared/ -- will be altered later, but this is kept for debugging.

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

apk add mpv mpv-libs
apk add xinit
apk add xorg-server

setup-xorg-base
```
