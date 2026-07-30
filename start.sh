#!/usr/bin/env bash
# JenneBot Startup Script for Render

# Load .env if it exists, but don't fail if it doesn't (Render uses env vars)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Run the bot
exec python3 main.py
