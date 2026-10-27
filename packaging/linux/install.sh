#!/bin/sh
# Adds this portable RGCopy to your applications menu and to ~/.local/bin, without root.
# ./install.sh --uninstall takes both out again (the folder itself stays where it is).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
bin="$HOME/.local/bin"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
entry=io.github.lam1623.rgcopy.desktop

if [ "${1:-}" = "--uninstall" ]; then
  "$here/rgcopy" integrate --uninstall >/dev/null 2>&1 || true
  rm -f "$bin/rgcopy" "$apps/$entry"
  echo "RGCopy removed from the menu and the file managers."
  exit 0
fi

command -v rsync >/dev/null 2>&1 || echo "Note: RGCopy needs rsync; install it with your package manager."
mkdir -p "$bin" "$apps"
ln -sf "$here/rgcopy" "$bin/rgcopy"
sed -e "s|^Exec=.*|Exec=$here/rgcopy|" -e "s|^Icon=.*|Icon=$here/rgcopy.svg|" "$here/$entry" > "$apps/$entry"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
echo "RGCopy is in your applications menu, and 'rgcopy' runs it from a terminal."
echo "Run 'rgcopy integrate' once to paste with Ctrl+V in Nautilus, Nemo and Caja."
