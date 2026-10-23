#!/usr/bin/env bash
# Install the real Tesseract and LibreOffice packages the API tests require.
#
# The runner's default Ubuntu mirror is sometimes extremely slow (CI run #202 spent
# 15 minutes downloading LibreOffice at ~50 KB/s). So:
#   1. packages cached by actions/cache are reused (CACHE_DIR);
#   2. the download runs in bounded attempts; a stalled mirror is replaced by the
#      main Ubuntu archive and the download resumes from the partial files;
#   3. installation then works from local .deb files only.
# Nothing is skipped: the step fails if the tools are still missing.
set -euo pipefail

PACKAGES_FILE="${1:?usage: install-native-deps.sh <package-list> [cache-dir]}"
CACHE_DIR="${2:-$HOME/apt-archives}"
ATTEMPT_SECONDS="${ATTEMPT_SECONDS:-420}"
ARCHIVES=/var/cache/apt/archives

mapfile -t packages < <(grep -Ev '^\s*(#|$)' "$PACKAGES_FILE")
apt_options=(-o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30
  -o DPkg::Lock::Timeout=120)

mkdir -p "$CACHE_DIR"
if compgen -G "$CACHE_DIR/*.deb" > /dev/null; then
  echo "Reusing $(find "$CACHE_DIR" -name '*.deb' | wc -l) cached packages"
  sudo cp "$CACHE_DIR"/*.deb "$ARCHIVES"/
fi

# man-db's trigger rebuilds the manual index after every install and can take minutes.
echo "man-db man-db/auto-update boolean false" | sudo debconf-set-selections
sudo rm -f /var/lib/man-db/auto-update

use_main_archive() {
  echo "Switching to the main Ubuntu archive"
  sudo find /etc/apt/sources.list.d /etc/apt -maxdepth 1 -type f \( -name '*.sources' -o -name '*.list' \) \
    -exec sudo sed -i -E 's#https?://[a-z0-9.-]*\.?archive\.ubuntu\.com/ubuntu#http://archive.ubuntu.com/ubuntu#g' {} +
}

download() {
  timeout "$ATTEMPT_SECONDS" sudo apt-get "${apt_options[@]}" update \
    && timeout "$ATTEMPT_SECONDS" sudo apt-get "${apt_options[@]}" install -y --download-only \
      --no-install-recommends "${packages[@]}"
}

downloaded=false
for attempt in 1 2 3; do
  if download; then
    downloaded=true
    break
  fi
  echo "Package download attempt $attempt did not finish within ${ATTEMPT_SECONDS}s"
  [ "$attempt" -eq 1 ] && use_main_archive
done
if [ "$downloaded" != true ]; then
  echo "::error::Native test packages could not be downloaded; the real OCR/Office tests cannot run."
  exit 1
fi

sudo DEBIAN_FRONTEND=noninteractive apt-get "${apt_options[@]}" install -y --no-download \
  --no-install-recommends "${packages[@]}"
cp "$ARCHIVES"/*.deb "$CACHE_DIR"/ 2>/dev/null || true

tesseract --version
tesseract --list-langs
soffice --version
