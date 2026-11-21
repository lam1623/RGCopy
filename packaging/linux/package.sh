#!/bin/sh
# Turns the PyInstaller bundle in ./rgcopy into the Linux packages, written to $1 (default /out):
# .deb, .rpm, Arch, AppImage and a portable tarball for the architecture of this machine.
# Runs inside the packaging stage of packaging/linux/Dockerfile.
set -eu
out=${1:-/out}
VERSION=$(./rgcopy/rgcopy --version | awk '{print $2}')
export VERSION
mkdir -p "$out"
icon=io.github.lam1623.rgcopy

machine=$(uname -m)
case $machine in
  x86_64) ARCH=amd64 loader=ld-linux-x86-64 max_glibc=2.34 ;;
  aarch64) ARCH=arm64 loader=ld-linux-aarch64 max_glibc=2.39 ;;
  *) echo "Unsupported architecture: $machine" >&2; exit 1 ;;
esac

# Icons for every menu size, from the app logo
mkdir -p icons/hicolor/scalable/apps
cp rgcopy.svg "icons/hicolor/scalable/apps/$icon.svg"
for size in 16 24 32 48 64 128 256 512; do
  mkdir -p "icons/hicolor/${size}x${size}/apps"
  rsvg-convert -w "$size" -h "$size" -o "icons/hicolor/${size}x${size}/apps/$icon.png" rgcopy.svg
done

# The oldest glibc and libstdc++ the bundle runs on: the newest symbol versions it uses
elves=$(find rgcopy -type f \( -name '*.so*' -o -perm -u+x \) -exec sh -c 'file -b "$1" | grep -q ^ELF && echo "$1"' _ {} \;)
# shellcheck disable=SC2086
versions=$(readelf -V $elves 2>/dev/null || true)
GLIBC=$(printf '%s\n' "$versions" | sed -n 's/.*Name: GLIBC_\([0-9.]*\).*/\1/p' | sort -uV | tail -n 1)
GLIBCXX=$(printf '%s\n' "$versions" | sed -n 's/.*Name: GLIBCXX_\([0-9.]*\).*/\1/p' | sort -uV | tail -n 1)
# The GCC release that first shipped that libstdc++ (Debian names libstdc++6 by GCC version)
case $GLIBCXX in
  3.4.2[0-9] | 3.4.1[0-9]) GCC=11 ;;  # 3.4.29 is GCC 11, older ones are older GCCs
  3.4.30) GCC=12 ;;
  3.4.31 | 3.4.32) GCC=13 ;;
  3.4.33) GCC=14 ;;
  *) GCC=15 ;;
esac
if [ -z "$GLIBC" ] || [ -z "$GLIBCXX" ]; then
  echo "Could not read the glibc and libstdc++ versions of the bundle (readelf)" >&2
  exit 1
fi
echo "The bundle needs glibc $GLIBC and libstdc++ $GLIBCXX (GCC $GCC)"
# Keeps the promise of the release notes: a newer Qt wheel must not quietly drop RHEL 9 and friends
if [ "$(printf '%s\n%s\n' "$GLIBC" "$max_glibc" | sort -V | tail -n 1)" != "$max_glibc" ]; then
  echo "The bundle needs glibc $GLIBC, newer than the $max_glibc this architecture supports" >&2
  exit 1
fi
sed -e "s/@ARCH@/$ARCH/g" -e "s/@GLIBC@/$GLIBC/g" -e "s/@GLIBCXX@/$GLIBCXX/g" -e "s/@GCC@/$GCC/g" \
  nfpm.yaml >nfpm.generated.yaml

# Every library the bundle needs from the system must be a declared dependency (nfpm.yaml)
# shellcheck disable=SC2086
needed=$(readelf -d $elves 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | sort -u)
bundled=$(find rgcopy \( -type f -o -type l \) -printf '%f\n' | sort -u)
declared=$(sed -n 's/^ *- \(lib[^(]*\)()(64bit)$/\1/p' nfpm.generated.yaml | sort -u)
undeclared=$(printf '%s\n' "$needed" | grep -vxF "$bundled" \
  | grep -vE "^(libc|libm|libdl|libpthread|librt|libutil|libresolv|$loader)\.so" \
  | grep -vxF "$declared" || true)
if [ -n "$undeclared" ]; then
  echo "The bundle needs system libraries missing from nfpm.yaml:" "$undeclared" >&2
  exit 1
fi

desktop-file-validate "$icon.desktop"
# The Dolphin service menu is a KDE "Service" and the file manager action a "Type=Action": both
# are valid for the programs that read them, and desktop-file-validate rejects both by design
for key in 'Type=Service' 'X-KDE-ServiceTypes=KonqPopupMenu/Plugin' 'Exec=rgcopy paste %f'; do
  grep -qxF "$key" rgcopy-paste.desktop || { echo "rgcopy-paste.desktop lacks $key" >&2; exit 1; }
done
for key in 'Type=Action' 'TargetLocation=true' 'MimeTypes=inode/directory;' 'Exec=rgcopy paste %f'; do
  grep -qxF "$key" rgcopy-paste-action.desktop || { echo "rgcopy-paste-action.desktop lacks $key" >&2; exit 1; }
done
for key in '[Nemo Action]' 'Selection=none' 'Exec=rgcopy paste %P'; do
  grep -qxF "$key" rgcopy-paste.nemo_action || { echo "rgcopy-paste.nemo_action lacks $key" >&2; exit 1; }
done
appstreamcli validate --no-net "$icon.metainfo.xml"

for packager in deb rpm archlinux; do
  nfpm package --config nfpm.generated.yaml --packager "$packager" --target "$out/"
done

# Portable build for any other distribution: unpack it anywhere and run ./rgcopy, or ./install.sh
portable="rgcopy-$VERSION-linux-$machine"
mkdir -p "$portable"
cp -a rgcopy/. "$portable/"
cp "$icon.desktop" install.sh LICENSE "$portable/"
cp rgcopy.svg "$portable/rgcopy.svg"
tar -C . -czf "$out/$portable.tar.gz" "$portable"

# AppImage: one file that runs on any distribution with the same system libraries as the tarball
appdir=RGCopy.AppDir
mkdir -p "$appdir/usr/lib" "$appdir/usr/share/applications" "$appdir/usr/share/metainfo"
cp -a rgcopy "$appdir/usr/lib/rgcopy"
cp -a icons "$appdir/usr/share/icons"
cp "$icon.desktop" "$appdir/usr/share/applications/"
cp "$icon.desktop" "$appdir/"
cp "$icon.metainfo.xml" "$appdir/usr/share/metainfo/$icon.appdata.xml"
cp "icons/hicolor/256x256/apps/$icon.png" "$appdir/$icon.png"
cp AppRun "$appdir/AppRun"
chmod 0755 "$appdir/AppRun"
tools=https://github.com/AppImage
curl -fsSL -o appimagetool "$tools/appimagetool/releases/download/continuous/appimagetool-$machine.AppImage"
curl -fsSL -o runtime "$tools/type2-runtime/releases/download/continuous/runtime-$machine"
chmod 0755 appimagetool
appimage="RGCopy-$VERSION-$machine.AppImage"
ARCH=$machine APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool --no-appstream --runtime-file runtime \
  "$appdir" "$out/$appimage"

cd "$out"
sha256sum -- *.deb *.rpm *.pkg.tar.zst *.tar.gz *.AppImage > SHA256SUMS
ls -l
