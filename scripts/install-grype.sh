#!/bin/sh
# Fixed official release + SHA-256, independent of mutable action tags/checksum downloads.
set -eu
archive="$(mktemp)"
trap 'rm -f "$archive"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  https://github.com/anchore/grype/releases/download/v0.118.0/grype_0.118.0_linux_amd64.tar.gz -o "$archive"
printf '%s  %s\n' '1d444c5e7360471815f7158f71935fcecc68a3c417d85c7344f770854300bba2' "$archive" | sha256sum -c -
mkdir -p "${1:?Provide an installation directory}"
tar -xzf "$archive" -C "$1" grype
