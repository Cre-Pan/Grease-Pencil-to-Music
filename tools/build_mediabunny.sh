#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Rebuild web/vendor/mediabunny.min.js: the parts of Mediabunny (MPL-2.0, unmodified) the
# video export uses, as one script that defines window.Mediabunny.
#
#     sh tools/build_mediabunny.sh [version]      # needs node + npm
set -e
VERSION=${1:-1.66.0}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
npm init -y >/dev/null
npm install --silent "mediabunny@$VERSION" esbuild >/dev/null
echo 'export { Output, Mp4OutputFormat, WebMOutputFormat, BufferTarget, CanvasSource, AudioBufferSource, canEncodeAudio, canEncodeVideo } from "mediabunny";' > entry.js
npx esbuild entry.js --bundle --minify --format=iife --global-name=Mediabunny --legal-comments=none \
  --banner:js="/*! Mediabunny $VERSION (https://github.com/Vanilagy/mediabunny), MPL-2.0: see mediabunny.LICENSE. Unmodified source, bundled with tools/build_mediabunny.sh. */" \
  --outfile="$ROOT/web/vendor/mediabunny.min.js"
cp node_modules/mediabunny/LICENSE "$ROOT/web/vendor/mediabunny.LICENSE"
