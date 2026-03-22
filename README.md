# Genomic Hit Locator

Placeholder web application for future pooled CRISPR screen analyses at ISAB.

## Current state

- Separate repo and runtime from `crispr-tools`
- Served as its own app on the same machine
- Intended public hostname: `genomic-hit-locator.isab.science`
- Intended LAN hostname: `genomic-hit-locator.lan`
- Designed to be embedded inside `isab.science` via `iframe`
- Intended to sit behind the same shared Cloudflare login worker as the rest of `*.isab.science`

## Local run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8082
```

## Deployment notes

Systemd, nginx, and Cloudflare tunnel templates live in `deploy/`.

One Cloudflare-side step still exists outside this machine:

- add `genomic-hit-locator.isab.science` to the shared auth worker `ORIGIN_MAP`

Suggested value:

```json
{
  "genomic-hit-locator.isab.science": "http://appenzell.internet-box.ch:8082"
}
```

