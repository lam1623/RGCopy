#!/bin/sh
# Smoke test of an installed RGCopy, run in a fresh distribution container by
# .github/workflows/packages.yml: the CLI, real copies and moves with the system rsync, the file
# manager integration, the web server and the desktop window on X11 (when Xvfb is installed) and
# on Wayland (when Weston is installed).
#   PORTABLE=1       checks the per-user install of the portable tarball (install.sh) instead
#   APPIMAGE_FILE=f  checks that AppImage instead
#   SCREENSHOT=file  saves the window to a PNG when ImageMagick is installed
set -u
work=$(mktemp -d)
fail() {
  echo "FAIL: $*" >&2
  [ -f "$work/app.log" ] && tail -n 40 "$work/app.log" >&2
  exit 1
}
cd "$work" || exit 1

echo "== $(. /etc/os-release && echo "$PRETTY_NAME")"
if [ "${PORTABLE:-0}" = 1 ]; then
  PATH="$HOME/.local/bin:$PATH"
  grep -q '^Exec=/' "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.lam1623.rgcopy.desktop" \
    || fail "no menu entry from install.sh"
elif [ -n "${APPIMAGE_FILE:-}" ]; then
  # No FUSE in a container: the runtime unpacks itself instead of mounting
  mkdir -p "$work/bin"
  printf '#!/bin/sh\nAPPIMAGE_EXTRACT_AND_RUN=1 exec "%s" "$@"\n' "$APPIMAGE_FILE" >"$work/bin/rgcopy"
  chmod +x "$work/bin/rgcopy"
  PATH="$work/bin:$PATH"
else
  for file in /usr/share/applications/io.github.lam1623.rgcopy.desktop \
    /usr/share/metainfo/io.github.lam1623.rgcopy.metainfo.xml \
    /usr/share/kio/servicemenus/rgcopy-paste.desktop \
    /usr/share/kservices5/ServiceMenus/rgcopy-paste.desktop \
    /usr/share/nemo/actions/rgcopy-paste.nemo_action \
    /usr/share/file-manager/actions/rgcopy-paste.desktop \
    /usr/share/icons/hicolor/scalable/apps/io.github.lam1623.rgcopy.svg \
    /usr/share/icons/hicolor/256x256/apps/io.github.lam1623.rgcopy.png; do
    [ -f "$file" ] || fail "missing $file"
  done
fi
rgcopy --version || fail "rgcopy --version"
rsync --version | head -n 1 || fail "rsync is not installed"
# Without a scalable font the window shows no text at all: the packages must bring one along
# (ls rather than find, which minimal images such as openSUSE's leave out)
# shellcheck disable=SC2010
ls -R /usr/share/fonts /usr/local/share/fonts 2>/dev/null | grep -qiE '\.(ttf|otf|ttc)$' \
  || fail "no scalable font installed"

# Real transfers with the system rsync: a folder with odd names, then a move
mkdir -p "src/Fotos de viaje/año 2026" dst moved
head -c 3000000 /dev/urandom >"src/Fotos de viaje/año 2026/IMG [1].jpg"
echo hola >"src/Fotos de viaje/notas.txt"
rgcopy copy "src/Fotos de viaje" dst || fail "rgcopy copy"
# cksum is in coreutils; cmp (diffutils) is missing from the Fedora and Arch images
[ "$(cksum <"src/Fotos de viaje/año 2026/IMG [1].jpg")" = "$(cksum <"dst/Fotos de viaje/año 2026/IMG [1].jpg")" ] \
  || fail "the copy differs"
rgcopy move "src/Fotos de viaje/notas.txt" moved || fail "rgcopy move"
[ -f moved/notas.txt ] && [ ! -e "src/Fotos de viaje/notas.txt" ] || fail "the move did not move"

# The file manager integration writes its files: stand-ins make every file manager look installed
mkdir -p "$work/fm"
for fm in nautilus nemo caja thunar dolphin pcmanfm-qt; do
  printf '#!/bin/sh\nexit 0\n' >"$work/fm/$fm"
  chmod +x "$work/fm/$fm"
done
PATH="$PATH:$work/fm" HOME="$work/home" XDG_DATA_HOME="$work/home/share" XDG_CONFIG_HOME="$work/home/config" \
  rgcopy integrate >/dev/null || fail "rgcopy integrate"
grep -q '^Exec=/' "$work/home/share/applications/io.github.lam1623.rgcopy.desktop" || fail "no menu entry from integrate"
for file in share/nautilus/scripts/"Paste with RGCopy" share/nemo/scripts/"Paste with RGCopy" \
  config/caja/scripts/"Paste with RGCopy" config/Thunar/uca.xml config/Thunar/accels.scm \
  share/kio/servicemenus/rgcopy-paste.desktop share/kservices5/ServiceMenus/rgcopy-paste.desktop \
  share/file-manager/actions/rgcopy-paste.desktop share/nautilus-python/extensions/rgcopy_paste.py; do
  [ -e "$work/home/$file" ] || fail "integrate did not write $file"
done
grep -q 'uca-action-rgcopy-paste" "<Primary>v"' "$work/home/config/Thunar/accels.scm" || fail "no Ctrl+V for Thunar"
if [ -n "${APPIMAGE_FILE:-}" ]; then
  # The hooks must start the AppImage itself, not its temporary mount point
  grep -q '^Exec=.*\.AppImage' "$work/home/share/applications/io.github.lam1623.rgcopy.desktop" \
    || fail "the menu entry does not point at the AppImage"
fi
HOME="$work/home" XDG_DATA_HOME="$work/home/share" XDG_CONFIG_HOME="$work/home/config" \
  rgcopy integrate --uninstall >/dev/null || fail "rgcopy integrate --uninstall"

rgcopy serve --port 8799 --token smoke --root "$work" >serve.log 2>&1 &
server=$!
for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8799/api/health >/dev/null && break
  sleep 1
done
curl -fsS http://127.0.0.1:8799/api/health || { cat serve.log; fail "the web server did not start"; }
echo
curl -fs http://127.0.0.1:8799/ | grep -q '<div id="root"' || fail "the web UI is not served"
curl -fs -H 'Authorization: Bearer smoke' http://127.0.0.1:8799/api/system | grep -q '"available":true' \
  || fail "the server does not find rsync"
kill "$server"

if command -v Xvfb >/dev/null; then
  Xvfb :99 -screen 0 1280x800x24 >xvfb.log 2>&1 &
  for _ in $(seq 1 30); do
    [ -S /tmp/.X11-unix/X99 ] && break
    sleep 1
  done
  DISPLAY=:99 RGCOPY_SINGLE_INSTANCE=0 rgcopy >app.log 2>&1 &
  app=$!
  for _ in $(seq 1 60); do
    pgrep -f QtWebEngineProcess >/dev/null && break
    sleep 1
  done
  # Give the page time to load before looking at the window
  sleep 10
  kill -0 "$app" 2>/dev/null || fail "the desktop app exited"
  pgrep -f QtWebEngineProcess >/dev/null || fail "the desktop window has no web view"
  if [ -n "${SCREENSHOT:-}" ] && command -v import >/dev/null; then
    DISPLAY=:99 import -window root "$SCREENSHOT" || fail "no screenshot"
  fi
  kill "$app"
  echo "desktop window: ok"
fi
# The same window on a Wayland compositor (Weston without a screen), with Qt's Wayland backend
if command -v weston >/dev/null; then
  export XDG_RUNTIME_DIR="$work/run"
  mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
  weston --backend=headless --socket=wayland-smoke --idle-time=0 >weston.log 2>&1 &
  for _ in $(seq 1 30); do
    [ -S "$XDG_RUNTIME_DIR/wayland-smoke" ] && break
    sleep 1
  done
  [ -S "$XDG_RUNTIME_DIR/wayland-smoke" ] || { cat weston.log; fail "weston did not start"; }
  pkill -f QtWebEngineProcess 2>/dev/null || true
  sleep 1
  # WAYLAND_DEBUG logs the protocol: proof that the window really is a Wayland toplevel
  env -u DISPLAY WAYLAND_DISPLAY=wayland-smoke QT_QPA_PLATFORM=wayland WAYLAND_DEBUG=client \
    RGCOPY_SINGLE_INSTANCE=0 rgcopy >app.log 2>&1 &
  app=$!
  for _ in $(seq 1 60); do
    pgrep -f QtWebEngineProcess >/dev/null && break
    sleep 1
  done
  sleep 10
  kill -0 "$app" 2>/dev/null || fail "the desktop app exited on Wayland"
  pgrep -f QtWebEngineProcess >/dev/null || fail "the Wayland window has no web view"
  grep -q "get_toplevel" app.log || fail "the window is not a Wayland toplevel"
  kill "$app"
  echo "desktop window on Wayland: ok"
fi
echo "PASS"
