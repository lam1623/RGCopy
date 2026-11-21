## Install

| Distribution | x86_64 | aarch64 | Install with |
| --- | --- | --- | --- |
| Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pop!_OS, elementary, Zorin | `rgcopy_@VERSION@-1_amd64.deb` | `rgcopy_@VERSION@-1_arm64.deb` | `sudo apt install ./rgcopy_@VERSION@-1_amd64.deb` |
| Fedora, RHEL / AlmaLinux / Rocky 9 and 10 | `rgcopy-@VERSION@-1.x86_64.rpm` | `rgcopy-@VERSION@-1.aarch64.rpm` | `sudo dnf install ./rgcopy-@VERSION@-1.x86_64.rpm` |
| openSUSE Leap 16, Tumbleweed | `rgcopy-@VERSION@-1.x86_64.rpm` | `rgcopy-@VERSION@-1.aarch64.rpm` | `sudo zypper install --allow-unsigned-rpm ./rgcopy-@VERSION@-1.x86_64.rpm` |
| Arch, Manjaro, EndeavourOS, CachyOS | `rgcopy-@VERSION@-1-x86_64.pkg.tar.zst` | `rgcopy-@VERSION@-1-aarch64.pkg.tar.zst` | `sudo pacman -U ./rgcopy-@VERSION@-1-x86_64.pkg.tar.zst` |
| Any other glibc distribution | `RGCopy-@VERSION@-x86_64.AppImage` | `RGCopy-@VERSION@-aarch64.AppImage` | `chmod +x RGCopy-*.AppImage && ./RGCopy-*.AppImage` |
| Same, without AppImage | `rgcopy-@VERSION@-linux-x86_64.tar.gz` | `rgcopy-@VERSION@-linux-aarch64.tar.gz` | unpack it and run `./rgcopy`, or `./install.sh` to add it to your menu |
| Docker or a home server | `@IMAGE@:@VERSION@` | same image | `docker pull @IMAGE@:@VERSION@` |

Needs glibc 2.34+ on x86_64 and 2.39+ on aarch64. "Paste with RGCopy" is in the right-click menu of Dolphin (Plasma 5 and 6), Nemo and PCManFM-Qt right after installing.

Then run `rgcopy integrate` once, as your user, so that Ctrl+V in Nautilus, Nemo, Caja and Thunar pastes with RGCopy (Nautilus also needs `python3-nautilus`). Your package manager installs rsync along with RGCopy.

Every package was installed and tried (copies, file manager hooks, web UI, and the window on X11 and Wayland) on fresh containers before this release: Ubuntu 22.04, 24.04 and 26.04, Debian 12 and 13, Fedora 43 and 44, AlmaLinux 9 and 10, openSUSE Leap 16.0 and Tumbleweed and Arch on x86_64; Ubuntu 24.04, Debian 13, Fedora 44, AlmaLinux 10 and openSUSE Tumbleweed on aarch64. `SHA256SUMS` lists their checksums.
