# SSL cert / token — skipped

This portal uses **OpenRouter API keys** only.

- Do **not** set `CERT_FILE` or `TOKEN_FILE` in `.env`
- TLS uses system CAs (`verify=True`)
- Auth uses `OPENROUTER_API_KEY` / `LLM_API_KEY`

Legacy private-host cert/token support exists only if you explicitly set:

```env
ALLOW_LEGACY_TLS=true
```

That path is not used for normal MacBook / OpenRouter runs.
