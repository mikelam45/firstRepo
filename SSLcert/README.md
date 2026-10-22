# TLS secrets — Mac absolute paths

On the MacBook, secrets live **outside the git repo**:

| Absolute path | Env var |
| --- | --- |
| `/Users/mikelam/SSLcert/qwen-tls.crt` | `CERT_FILE` |
| `/Users/mikelam/SSLcert/token_qwen3_8.txt` | `TOKEN_FILE` |

```bash
mkdir -p /Users/mikelam/SSLcert
cp ~/Downloads/qwen-tls.crt /Users/mikelam/SSLcert/qwen-tls.crt
cp ~/Downloads/token_qwen3_8.txt /Users/mikelam/SSLcert/token_qwen3_8.txt
ls -la /Users/mikelam/SSLcert/
```

`.env`:

```env
CERT_FILE="/Users/mikelam/SSLcert/qwen-tls.crt"
TOKEN_FILE="/Users/mikelam/SSLcert/token_qwen3_8.txt"
```

This repo folder (`SSLcert/`) may still hold a README only; do not commit real cert/token files.
Optional compose on the same Mac can mount `/Users/mikelam/SSLcert` → `/app/SSLcert`.
