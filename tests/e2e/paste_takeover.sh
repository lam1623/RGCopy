#!/usr/bin/env bash
# End-to-end check of the TeraCopy-style paste: Ctrl+C a file, open a file manager, press Ctrl+V
# and expect RGCopy (not the file manager) to copy it. Then `--uninstall` must give Ctrl+V back.
#
# Needs: rgcopy on PATH, Xvfb, xdotool, xclip, dbus-run-session and at least one of nautilus
# (+ python3-nautilus, gir1.2-gtk-4.0), nemo, caja. Run it as a regular user (Nautilus refuses root):
#   tests/e2e/paste_takeover.sh [nautilus nemo caja]
set -euo pipefail

MANAGERS=("${@:-nautilus nemo caja}")
read -r -a MANAGERS <<<"${MANAGERS[*]}"
WORK=$(mktemp -d)
DISPLAY_NUM=${DISPLAY_NUM:-:97}
trap 'kill $(jobs -p) 2>/dev/null || true; [[ -n ${KEEP:-} ]] || rm -rf "$WORK"' EXIT

export HOME=$WORK/home XDG_CONFIG_HOME=$WORK/home/.config XDG_DATA_HOME=$WORK/home/.local/share
export XDG_RUNTIME_DIR=$WORK/run RGCOPY_RUNTIME_DIR=$WORK/run/rgcopy
export DISPLAY=$DISPLAY_NUM GDK_BACKEND=x11 NO_AT_BRIDGE=1 RGCOPY_AUTOBUILD=off
mkdir -p "$HOME" "$XDG_RUNTIME_DIR" "$WORK/src" "$WORK/dst"
chmod 700 "$XDG_RUNTIME_DIR"
Xvfb "$DISPLAY" -screen 0 1280x800x24 >/dev/null 2>&1 &
sleep 1

# One file manager session: put the file on the clipboard, press Ctrl+V, report what happened
attempt() {
  local fm=$1 target=x-special/gnome-copied-files
  [[ $fm == caja ]] && target=x-special/mate-copied-files
  rm -rf "$WORK/dst"/* "$RGCOPY_RUNTIME_DIR"
  echo data >"$WORK/src/copied.txt"
  printf 'copy\nfile://%s/src/copied.txt' "$WORK" | xclip -selection clipboard -t "$target" -i >/dev/null 2>&1
  case $fm in
    nautilus) nautilus --new-window "$WORK/dst" ;;
    nemo) nemo "$WORK/dst" ;;
    caja) caja --no-desktop "$WORK/dst" ;;
  esac >"$WORK/$fm.log" 2>&1 </dev/null &
  sleep "${STARTUP:-9}"
  local window
  window=$(xdotool search --onlyvisible --class "$fm" | tail -1)
  xdotool windowactivate --sync "$window" >/dev/null 2>&1 || xdotool windowfocus --sync "$window"
  sleep 1
  xdotool key ctrl+v
  sleep "${SETTLE:-8}"
  local by=none
  if [[ -f $RGCOPY_RUNTIME_DIR/instance.json ]]; then
    by=$(python3 - "$RGCOPY_RUNTIME_DIR/instance.json" <<'PY'
import json, sys, urllib.request
info = json.load(open(sys.argv[1]))
request = urllib.request.Request(
    f"http://127.0.0.1:{info['port']}/api/jobs", headers={"Authorization": f"Bearer {info['token']}"}
)
jobs = json.load(urllib.request.urlopen(request))["jobs"]
print("rgcopy" if any(j["status"] == "completed" for j in jobs) else "rgcopy-unfinished")
PY
)
  elif [[ -e $WORK/dst/copied.txt ]]; then
    by=$fm
  fi
  # "[r]" keeps pgrep from matching this very script
  kill $(pgrep -u "$(id -u)" -x "$fm") $(pgrep -u "$(id -u)" -x xclip) \
    $(pgrep -u "$(id -u)" -f "[r]gcopy paste") 2>/dev/null || true
  sleep 1
  echo "$by" >"$WORK/result"
}

# Services the session bus starts (gvfsd, tracker) outlive it: never let them hold our stdout
run_attempt() {
  rm -f "$WORK/result"
  timeout 120 dbus-run-session -- bash -c "$(declare -f attempt); WORK=$WORK; attempt $1" >"$WORK/attempt-$1.log" 2>&1 || true
  cat "$WORK/result" 2>/dev/null || echo error
}

failures=0
for fm in "${MANAGERS[@]}"; do
  command -v "$fm" >/dev/null || { echo "skip  $fm (not installed)"; continue; }
  rgcopy integrate >/dev/null
  got=$(run_attempt "$fm")
  [[ $got == rgcopy ]] && echo "ok    $fm: Ctrl+V pasted with RGCopy" || { echo "FAIL  $fm: Ctrl+V handled by $got"; failures=$((failures + 1)); }
  rgcopy integrate --uninstall >/dev/null
  got=$(run_attempt "$fm")
  [[ $got == "$fm" ]] && echo "ok    $fm: Ctrl+V is the file manager's again" || { echo "FAIL  $fm: after --uninstall Ctrl+V handled by $got"; failures=$((failures + 1)); }
done
exit "$failures"
