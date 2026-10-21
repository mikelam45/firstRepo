# Sample mbox fixtures

Place Thunderbird-compatible **mbox** files here for local/CI runs without a macOS profile.

Expected usage:

```bash
THUNDERBIRD_MAIL_PATH="./fixtures/mbox"
TARGET_MAIL_FOLDER="Applications"
```

`Applications` should be a single mbox file (no extension) in this directory.

Acceptance fixtures to add when implementing the pipeline:

| Message | Intent |
| --- | --- |
| Strong keyword coverage + logistics in band | Expect Tier 1 |
| Fewer than `min_must_match` keywords | Expect Tier 3 knockout |
| Salary above band when disclosed | Expect Tier 3 knockout |
