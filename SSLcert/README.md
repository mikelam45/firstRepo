# TLS cert and API token (local secrets)

Place these files here (not committed):

| File | Env var | Purpose |
| --- | --- | --- |
| `qwen-tls.crt` | `CERT_FILE` | CA/server cert for HTTPS verify |
| `token_qwen3_8.txt` | `TOKEN_FILE` | Bearer token for chat completions |

Paths expected by `.env`:

```env
CERT_FILE="./SSLcert/qwen-tls.crt"
TOKEN_FILE="./SSLcert/token_qwen3_8.txt"
API_URL="https://redhataiqwen38-27b-int4-rhoai-test.apps.demo.rhoai.demo/v1/chat/completions"
MODEL_NAME="redhataiqwen38-27b-int4"
```

Token file should contain a single line with the bearer token (no `Bearer ` prefix).
