#!/usr/bin/env bash
# ingest.sh — thin wrapper around `declip workflow ingest`. See docs/workflows/ingest.md.
exec declip workflow ingest "$@"
