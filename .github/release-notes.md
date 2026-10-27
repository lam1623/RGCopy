## Install

| Distribution | Package | Install with |
| --- | --- | --- |
| Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pop!_OS 22.04+ | `rgcopy_@VERSION@-1_amd64.deb` | `sudo apt install ./rgcopy_@VERSION@-1_amd64.deb` |
| Fedora, openSUSE Tumbleweed | `rgcopy-@VERSION@-1.x86_64.rpm` | `sudo dnf install ./rgcopy-@VERSION@-1.x86_64.rpm` or `sudo zypper install --allow-unsigned-rpm ./rgcopy-@VERSION@-1.x86_64.rpm` |
| Arch, Manjaro, EndeavourOS | `rgcopy-@VERSION@-1-x86_64.pkg.tar.zst` | `sudo pacman -U ./rgcopy-@VERSION@-1-x86_64.pkg.tar.zst` |
| Any other distribution with glibc 2.35+ | `rgcopy-@VERSION@-linux-x86_64.tar.gz` | unpack it and run `./rgcopy`, or `./install.sh` to add it to your menu |
| Docker or a home server (amd64, arm64) | `@IMAGE@:@VERSION@` | `docker pull @IMAGE@:@VERSION@` |

Then run `rgcopy integrate` once, as your user, so that Ctrl+V in Nautilus, Nemo and Caja pastes with RGCopy (Nautilus also needs `python3-nautilus`). Your package manager installs rsync along with RGCopy.

Every package was installed and tried on fresh Ubuntu 24.04, Ubuntu 22.04, Debian 12, Fedora 42, openSUSE Tumbleweed and Arch containers before this release; `SHA256SUMS` lists their checksums.
