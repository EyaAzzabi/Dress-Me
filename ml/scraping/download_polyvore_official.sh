#!/bin/sh
# Downloads the full official Polyvore Outfits dataset (Vasileva et al. 2018), refactored
# and re-hosted on Hugging Face by owj0421 across two companion, ungated repos:
# - polyvore-outfits: outfit structure (which items go together), nondisjoint_default
#   split -> {train,valid,test}.json (53,306 / 5,000 / 10,000 outfits)
# - polyvore: item metadata (category, title) + embedded images, 6 parquet shards, ~2.1GB
#
# Uses curl, which has native, battle-tested resume (-C -) — a hand-rolled httpx version
# kept paying full reconnect/TLS overhead on every stall and effectively crawled at
# ~9KB/s on this connection; curl alone sustains ~150-300KB/s.
set -e
cd "$(dirname "$0")/../data/raw/polyvore_official"

CURL_OPTS="-L -C - --retry 50 --retry-delay 3 --retry-all-errors --speed-limit 2000 --speed-time 20 --connect-timeout 20"

OUTFITS_BASE="https://huggingface.co/datasets/owj0421/polyvore-outfits/resolve/main/nondisjoint_default"
for split in train valid test; do
  echo "=== ${split}.json ==="
  curl $CURL_OPTS -o "${split}.json" "$OUTFITS_BASE/${split}.json"
done

ITEMS_BASE="https://huggingface.co/datasets/owj0421/polyvore/resolve/main/data"
for i in 0 1 2 3 4 5; do
  f="data-0000${i}-of-00005.parquet"
  echo "=== $f ==="
  curl $CURL_OPTS -o "$f" "$ITEMS_BASE/$f"
done

echo "Official Polyvore dataset fully downloaded."
