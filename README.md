# moracano-server

## Seed Challenge Sentences

CSV seed files are normalized into `challenges`, `dialect_regions`, `lemmas`,
`variants`, `utterances`, and `utterance_variants`.

Required CSV columns:

```text
prompt_text,dialect_text,standard_text,eojeol_list,region_code,syllable_count,variant_count,region_count,active_date,source_type
```

`eojeol_list` must be a JSON array. Only items with `is_dialect: true` are used
to create `lemmas` and `variants`.

Dry run:

```bash
python3 scripts/seed_challenge_sentences.py /path/to/challenge_sentences.csv --dry-run
```

Apply:

```bash
export SUPABASE_ACCESS_TOKEN="management-api-token-with-database-write"
python3 scripts/seed_challenge_sentences.py /path/to/challenge_sentences.csv
```

Use `source_type=aihub` for AI-Hub source data and `source_type=synthetic` for
generated seed data. `region_code` is the source dialect region, such as `GB`,
`포항`, or `경주`; user-selected app regions remain in `voices.region_code`.
