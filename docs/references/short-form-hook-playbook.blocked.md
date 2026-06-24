# Short-Form Hook Playbook Blocker

Eddy blocks final Shorts until `docs/references/short-form-hook-playbook.jsonl` contains at least
1,000 validated hook records.

Build or refresh it from a supplied list of proven public short-form URLs:

```bash
SUPADATA_API_KEY=... eddy hooks build-supadata proven-short-urls.txt \
  --out docs/references/short-form-hook-playbook.jsonl
```

Normal editing should then use the baked local JSONL file offline. Supadata is not required at
runtime after the playbook is built.

If Supadata is unavailable, maintainers can build a weaker but still provenance-labeled public
metadata-derived corpus:

```bash
eddy hooks build-youtube-metadata \
  --out docs/references/short-form-hook-playbook.jsonl
```

That fallback stores public titles and metadata only. It does not download videos or commit
transcript dumps, and every record marks `title_as_opening_surrogate=true` in provenance. Treat it
as a metadata-derived taste aid, not a transcript-proven viral-hooks dataset.
