# TLS cert and API token (local secrets)

Place these files **in this folder** (repo `SSLcert/`, not committed):

| Exact filename | Env var (`.env`) | Purpose |
| --- | --- | --- |
| `qwen-tls.crt` | `CERT_FILE=./SSLcert/qwen-tls.crt` | TLS verify for HTTPS |
| `token_qwen3_8.txt` | `TOKEN_FILE=./SSLcert/token_qwen3_8.txt` | Bearer token (one line, no `Bearer ` prefix) |

On Mac, from the repo root:

```bash
mkdir -p SSLcert
# copy your downloads with these exact names:
cp ~/Downloads/qwen-tls.crt SSLcert/qwen-tls.crt
cp ~/Downloads/token_qwen3_8.txt SSLcert/token_qwen3_8.txt
ls -la SSLcert/
```

`.env` (Mac / bare-metal — always these relative values):

```env
CERT_FILE="./SSLcert/qwen-tls.crt"
TOKEN_FILE="./SSLcert/token_qwen3_8.txt"
```

Resolved on disk (example):

```text
<repo>/SSLcert/qwen-tls.crt
<repo>/SSLcert/token_qwen3_8.txt
```

`bash scripts/run_local_mac.sh` forces the Mac relative values and exports `PROJECT_ROOT`.
The app resolves them against the repo root even if your shell cwd differs.

Podman/Docker: `compose.yml` sets `CERT_FILE=/app/SSLcert/qwen-tls.crt` and
`TOKEN_FILE=/app/SSLcert/token_qwen3_8.txt`, and bind-mounts this directory to `/app/SSLcert`.
