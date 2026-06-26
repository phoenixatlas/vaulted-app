#!/usr/bin/env bash
# Helper: check Resend domain status and, when verified, switch the sender
# in /app/backend/.env to noreply@phoenix-atlas.com and restart the backend.

set -e

DOMAIN_ID="c0c910f1-365d-4931-b4cc-c20a1a192711"
RESEND_KEY="$(grep -E '^RESEND_API_KEY=' /app/backend/.env | cut -d= -f2 | tr -d '"')"

echo "Re-triggering verification…"
curl -s -X POST "https://api.resend.com/domains/${DOMAIN_ID}/verify" \
  -H "Authorization: Bearer ${RESEND_KEY}" >/dev/null

sleep 10

STATUS_JSON=$(curl -s -X GET "https://api.resend.com/domains/${DOMAIN_ID}" \
  -H "Authorization: Bearer ${RESEND_KEY}")
echo "$STATUS_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Domain:', d['name'], '->', d['status'])
for r in d.get('records', []):
    print(f\"  {r.get('record')} ({r.get('type')}) -> {r.get('status')}\")
"

STATUS=$(echo "$STATUS_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
if [ "$STATUS" = "verified" ]; then
    if ! grep -q '^RESEND_FROM=' /app/backend/.env; then
        echo 'RESEND_FROM="Vaulted <noreply@phoenix-atlas.com>"' >> /app/backend/.env
    else
        sed -i 's|^RESEND_FROM=.*|RESEND_FROM="Vaulted <noreply@phoenix-atlas.com>"|' /app/backend/.env
    fi
    sudo supervisorctl restart backend
    echo "✅ Sender switched to noreply@phoenix-atlas.com — backend restarted."
else
    echo "⏳ Not verified yet. Re-run this script later."
fi
