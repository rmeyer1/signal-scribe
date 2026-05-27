# Signal Scribe deployment notes

## Local Docker runtime

Create `.env` from `.env.example` and set at least:

```bash
SEC_USER_AGENT=Signal Scribe your-email@example.com
SIGNAL_SCRIBE_API_KEY=generated-shared-secret
OPENAI_API_KEY=...
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
```

Start the API:

```bash
docker compose up -d --build
```

If the Docker Compose plugin is unavailable, build and run directly:

```bash
docker build -t signal-scribe-api .
docker run -d --name signal-scribe-api --restart unless-stopped \
  --env-file .env -p 8000:8000 signal-scribe-api
```

Verify:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/companies/AAPL/profile \
  -H "Authorization: Bearer $SIGNAL_SCRIBE_API_KEY"
```

## Bearer token

Use one shared secret value for both Signal Scribe and AlphaDog:

```bash
openssl rand -base64 32
```

Signal Scribe host:

```bash
SIGNAL_SCRIBE_API_KEY=generated-value
```

AlphaDog server runtime:

```bash
SIGNAL_SCRIBE_API_BASE_URL=https://signalscribe.example.com
SIGNAL_SCRIBE_API_KEY=generated-value
```

Do not commit `.env` or paste the generated secret into shared channels. Keep values unquoted in
`.env` when Docker reads it through `--env-file`; Docker treats quotes as literal characters.

## Cloudflare Tunnel

A stable 24/7 Cloudflare Tunnel URL requires a Cloudflare account and a domain/hostname managed by Cloudflare.

One-time host setup:

```bash
cloudflared tunnel login
cloudflared tunnel create signal-scribe
cloudflared tunnel route dns signal-scribe signalscribe.example.com
```

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: signal-scribe
credentials-file: /home/nonroot/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: signalscribe.example.com
    service: http://signal-scribe-api:8000
  - service: http_status:404
```

Then uncomment the `cloudflared` service in `docker-compose.yml` and restart Compose.

For short-lived testing only, Cloudflare also supports a temporary random URL:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

That URL is not suitable as the AlphaDog production endpoint because it is ephemeral.
