# Shared Cloudflare Login Next Step

The local app and tunnel target can be created on this machine, but the shared ISAB login worker still needs one Cloudflare-side update so the public host resolves through the same login flow as the rest of `*.isab.science`.

Add this entry to the worker `ORIGIN_MAP`:

```json
"genomic-hit-locator.isab.science": "http://appenzell.internet-box.ch:8082"
```

If you also want a direct origin/debug hostname, add:

```json
"genomic-hit-locator-origin.isab.science": "http://appenzell.internet-box.ch:8082"
```
