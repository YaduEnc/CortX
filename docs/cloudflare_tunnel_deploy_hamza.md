# Deploy Backend via Cloudflare Tunnel (`hamza.yaduraj.me`)

This runbook exposes your local/hosted backend at:
- `https://hamza.yaduraj.me`

## 0) Prerequisites
- Domain `yaduraj.me` is active in Cloudflare.
- `hamza.yaduraj.me` should be proxied through Cloudflare (orange cloud).
- Backend runs on local machine at `http://localhost:8000`.

## 1) Start backend
```bash
cd /Users/sujeetkumarsingh/Desktop/CortX
docker compose down -v
docker compose up -d --build
curl -sS http://localhost:8000/v1/health
```

Expected:
```json
{"status":"ok"}
```

## 2) Install and login `cloudflared`
```bash
brew install cloudflared
cloudflared --version
cloudflared tunnel login
```

## 3) Create tunnel and DNS route
```bash
cloudflared tunnel create secondmind-hamza
cloudflared tunnel route dns secondmind-hamza hamza.yaduraj.me
```

## 4) Create local tunnel config
```bash
TUNNEL_UUID=$(cloudflared tunnel list | awk '/secondmind-hamza/{print $1}')

cat > ~/.cloudflared/config.yml <<EOF_CFG
tunnel: ${TUNNEL_UUID}
credentials-file: /Users/$USER/.cloudflared/${TUNNEL_UUID}.json

ingress:
  - hostname: hamza.yaduraj.me
    service: http://localhost:8000
  - service: http_status:404
EOF_CFG

cloudflared tunnel ingress validate
```

## 5) Run tunnel
Foreground (for first test):
```bash
cloudflared tunnel run secondmind-hamza
```

In a second terminal, verify public API:
```bash
curl -sS https://hamza.yaduraj.me/v1/health
```

Expected:
```json
{"status":"ok"}
```

## 6) Run tunnel as background service
```bash
sudo cloudflared service install
sudo launchctl list | grep cloudflared || true
```

## 7) Logs and troubleshooting
```bash
cloudflared tunnel info secondmind-hamza
cloudflared tunnel list
```

If you get `Error 1016`:
- Check backend is up on `localhost:8000`.
- Check tunnel process is running.
- Re-run `cloudflared tunnel run secondmind-hamza`.

## 8) Handout URL for IoT team
- API base URL: `https://hamza.yaduraj.me/v1`
