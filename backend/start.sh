#!/bin/sh
# Container entry point (Railway): migrate, seed reference data, then serve.
set -e
python -m happysmile.migrate
python -m happysmile.seed
if [ "$TELEPHONY_PROVIDER" = "browser" ]; then
  python -m happysmile.demo_mode on   # browser voice demo: every pilot-clinic enquiry goes to the assistant
fi
exec uvicorn happysmile.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips="*" --timeout-graceful-shutdown 5
