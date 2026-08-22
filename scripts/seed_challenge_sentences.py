#!/usr/bin/env python3
import argparse
import csv
import getpass
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_PROJECT_REF = "nuofcxkxoaahnofytckg"
REQUIRED_FIELDS = {
    "prompt_text",
    "dialect_text",
    "standard_text",
    "eojeol_list",
    "region_code",
    "syllable_count",
    "variant_count",
    "region_count",
    "active_date",
    "source_type",
}
ALLOWED_SOURCES = {"aihub", "synthetic", "user"}


DIALECT_REGIONS_SQL = """
with raw as (
  select distinct region_code
  from jsonb_to_recordset($1::jsonb) as r(region_code text)
  where region_code is not null
),
inserted_dialect_regions as (
  insert into public.dialect_regions (
    code,
    name,
    level
  )
  select
    raw.region_code,
    raw.region_code,
    case
      when exists (
        select 1
        from public.regions
        where regions.code = raw.region_code
      ) then 'city'
      else 'province'
    end
  from raw
  on conflict (code) do nothing
  returning 1
)
select count(*) as inserted_dialect_regions from inserted_dialect_regions;
"""


SEED_SQL = """
with raw as (
  select *
  from jsonb_to_recordset($1::jsonb) as r(
    prompt_text text,
    dialect_text text,
    standard_text text,
    eojeol_list jsonb,
    region_code text,
    syllable_count integer,
    variant_count integer,
    region_count integer,
    active_date date,
    source text
  )
),
dialect_tokens as (
  select distinct
    e.value->>'standard' as standard_form,
    e.value->>'surface' as surface,
    raw.region_code
  from raw
  cross join lateral jsonb_array_elements(raw.eojeol_list) as e(value)
  where coalesce((e.value->>'is_dialect')::boolean, false)
),
inserted_challenges as (
  insert into public.challenges (
    prompt_text,
    syllable_count,
    variant_count,
    region_count,
    active_date
  )
  select
    raw.prompt_text,
    raw.syllable_count::smallint,
    raw.variant_count,
    raw.region_count,
    raw.active_date
  from raw
  where not exists (
    select 1
    from public.challenges c
    where c.prompt_text = raw.prompt_text
  )
  returning 1
),
inserted_lemmas as (
  insert into public.lemmas (
    standard_form,
    gloss,
    aihub_count,
    user_count
  )
  select distinct
    dialect_tokens.standard_form,
    null::text,
    0,
    0
  from dialect_tokens
  on conflict (standard_form) do nothing
  returning 1
),
inserted_utterances as (
  insert into public.utterances (
    source,
    region_code,
    dialect_text,
    standard_text,
    syllable_count,
    dialect_density
  )
  select
    raw.source,
    raw.region_code,
    raw.dialect_text,
    raw.standard_text,
    raw.syllable_count,
    (
      select count(*) filter (
        where coalesce((e.value->>'is_dialect')::boolean, false)
      )::numeric / nullif(jsonb_array_length(raw.eojeol_list), 0)
      from jsonb_array_elements(raw.eojeol_list) as e(value)
    )
  from raw
  where not exists (
    select 1
    from public.utterances u
    where u.source = raw.source
      and u.region_code = raw.region_code
      and u.dialect_text = raw.dialect_text
      and u.standard_text = raw.standard_text
  )
  on conflict (source, region_code, dialect_text, standard_text) do nothing
  returning 1
)
select
  (select count(*) from raw) as csv_rows,
  (select count(*) from inserted_challenges) as inserted_challenges,
  (select count(*) from inserted_utterances) as inserted_utterances,
  (select count(*) from inserted_lemmas) as inserted_lemmas;
"""


VARIANTS_SQL = """
with raw as (
  select *
  from jsonb_to_recordset($1::jsonb) as r(
    prompt_text text,
    dialect_text text,
    standard_text text,
    eojeol_list jsonb,
    region_code text,
    syllable_count integer,
    variant_count integer,
    region_count integer,
    active_date date,
    source text
  )
),
dialect_tokens as (
  select distinct
    e.value->>'standard' as standard_form,
    e.value->>'surface' as surface,
    raw.region_code
  from raw
  cross join lateral jsonb_array_elements(raw.eojeol_list) as e(value)
  where coalesce((e.value->>'is_dialect')::boolean, false)
),
inserted_variants as (
  insert into public.variants (
    lemma_id,
    surface,
    region_code,
    aihub_count,
    user_count
  )
  select distinct
    lemmas.id,
    dialect_tokens.surface,
    dialect_tokens.region_code,
    0,
    0
  from dialect_tokens
  join public.lemmas
    on lemmas.standard_form = dialect_tokens.standard_form
  on conflict (lemma_id, surface, region_code) do nothing
  returning 1
)
select count(*) as inserted_variants from inserted_variants;
"""


LINKS_AND_COUNTS_SQL = """
with raw as (
  select *
  from jsonb_to_recordset($1::jsonb) as r(
    prompt_text text,
    dialect_text text,
    standard_text text,
    eojeol_list jsonb,
    region_code text,
    syllable_count integer,
    variant_count integer,
    region_count integer,
    active_date date,
    source text
  )
),
inserted_links as (
  insert into public.utterance_variants (
    utterance_id,
    variant_id
  )
  select distinct
    utterances.id,
    variants.id
  from raw
  cross join lateral jsonb_array_elements(raw.eojeol_list) as e(value)
  join public.utterances
    on utterances.source = raw.source
   and utterances.region_code = raw.region_code
   and utterances.dialect_text = raw.dialect_text
   and utterances.standard_text = raw.standard_text
  join public.lemmas
    on lemmas.standard_form = e.value->>'standard'
  join public.variants
    on variants.lemma_id = lemmas.id
   and variants.surface = e.value->>'surface'
   and variants.region_code = raw.region_code
  where coalesce((e.value->>'is_dialect')::boolean, false)
  on conflict (utterance_id, variant_id) do nothing
  returning 1
),
lemma_counts as (
  select
    variants.lemma_id,
    count(*) filter (where utterances.source in ('aihub', 'synthetic'))::int as reference_count,
    count(*) filter (where utterances.source = 'user')::int as user_count
  from public.utterance_variants
  join public.variants
    on variants.id = utterance_variants.variant_id
  join public.utterances
    on utterances.id = utterance_variants.utterance_id
  group by variants.lemma_id
),
updated_lemmas as (
  update public.lemmas
  set
    aihub_count = lemma_counts.reference_count,
    user_count = lemma_counts.user_count
  from lemma_counts
  where lemmas.id = lemma_counts.lemma_id
  returning 1
),
variant_counts as (
  select
    variants.id as variant_id,
    count(*) filter (where utterances.source in ('aihub', 'synthetic'))::int as reference_count,
    count(*) filter (where utterances.source = 'user')::int as user_count
  from public.variants
  join public.utterance_variants
    on utterance_variants.variant_id = variants.id
  join public.utterances
    on utterances.id = utterance_variants.utterance_id
  group by variants.id
),
updated_variants as (
  update public.variants
  set
    aihub_count = variant_counts.reference_count,
    user_count = variant_counts.user_count
  from variant_counts
  where variants.id = variant_counts.variant_id
  returning 1
)
select
  (select count(*) from inserted_links) as inserted_utterance_variants,
  (select count(*) from updated_lemmas) as updated_lemmas,
  (select count(*) from updated_variants) as updated_variants;
"""


VERIFY_SQL = """
select 'challenges' as table_name, count(*)::int as count from public.challenges
union all select 'dialect_regions', count(*)::int from public.dialect_regions
union all select 'lemmas', count(*)::int from public.lemmas
union all select 'variants', count(*)::int from public.variants
union all select 'utterances', count(*)::int from public.utterances
union all select 'utterance_variants', count(*)::int from public.utterance_variants
order by table_name;
"""


def load_rows(csv_path: str) -> list[dict]:
    def optional_int(value: str, field: str, row_no: int):
        if not value:
            return None
        try:
            return int(value)
        except ValueError as error:
            raise ValueError(f"Invalid integer {field} at line {row_no}: {value}") from error

    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_fields = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Missing required CSV columns: {missing}")

        rows = []
        for row_no, row in enumerate(reader, start=2):
            source = row["source_type"] or "synthetic"
            if source not in ALLOWED_SOURCES:
                raise ValueError(f"Invalid source_type at line {row_no}: {source}")
            if not row["region_code"]:
                raise ValueError(f"Missing region_code at line {row_no}")

            try:
                eojeol_list = json.loads(row["eojeol_list"])
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid eojeol_list JSON at line {row_no}") from error
            if not isinstance(eojeol_list, list):
                raise ValueError(f"eojeol_list must be a JSON array at line {row_no}")
            if not any(item.get("is_dialect") for item in eojeol_list):
                raise ValueError(f"eojeol_list has no dialect item at line {row_no}")

            rows.append(
                {
                    "prompt_text": row["prompt_text"],
                    "dialect_text": row["dialect_text"],
                    "standard_text": row["standard_text"],
                    "eojeol_list": eojeol_list,
                    "region_code": row["region_code"],
                    "syllable_count": optional_int(row["syllable_count"], "syllable_count", row_no),
                    "variant_count": optional_int(row["variant_count"], "variant_count", row_no),
                    "region_count": optional_int(row["region_count"], "region_count", row_no),
                    "active_date": row["active_date"] or None,
                    "source": source,
                }
            )
    return rows


def run_query(project_ref: str, token: str, query: str, parameters=None) -> object:
    request = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
        data=json.dumps(
            {
                "query": query,
                "parameters": parameters or [],
                "read_only": False,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase query failed: HTTP {error.code} {body}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--project-ref", default=os.getenv("SUPABASE_PROJECT_REF", DEFAULT_PROJECT_REF))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.csv_path)
    dialect_items = [
        item
        for row in rows
        for item in row["eojeol_list"]
        if item.get("is_dialect")
    ]
    print(
        json.dumps(
            {
                "csv_rows": len(rows),
                "dialect_items": len(dialect_items),
                "unique_lemmas": len({item["standard"] for item in dialect_items}),
                "unique_variants": len(
                    {(item["standard"], item["surface"], row["region_code"]) for row in rows for item in row["eojeol_list"] if item.get("is_dialect")}
                ),
                "sources": sorted({row["source"] for row in rows}),
                "regions": sorted({row["region_code"] for row in rows}),
            },
            ensure_ascii=False,
        )
    )

    if args.dry_run:
        return 0

    token = os.getenv("SUPABASE_ACCESS_TOKEN")
    if not token:
        token = getpass.getpass("SUPABASE_ACCESS_TOKEN: ")

    payload = json.dumps(rows, ensure_ascii=False)

    dialect_regions_result = run_query(args.project_ref, token, DIALECT_REGIONS_SQL, [payload])
    print(json.dumps({"dialect_regions_result": dialect_regions_result}, ensure_ascii=False))

    seed_result = run_query(args.project_ref, token, SEED_SQL, [payload])
    print(json.dumps({"seed_result": seed_result}, ensure_ascii=False))

    variants_result = run_query(args.project_ref, token, VARIANTS_SQL, [payload])
    print(json.dumps({"variants_result": variants_result}, ensure_ascii=False))

    links_result = run_query(args.project_ref, token, LINKS_AND_COUNTS_SQL, [payload])
    print(json.dumps({"links_result": links_result}, ensure_ascii=False))

    verify_result = run_query(args.project_ref, token, VERIFY_SQL)
    print(json.dumps({"verify_result": verify_result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
