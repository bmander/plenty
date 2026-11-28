# Brief for crosswalk verifiers

The capability taxonomy in `taxonomy/domains/*.json` claims to integrate published taxonomies.
Each node carries `crosswalk` entries: `{scheme, code, label, basis, url}`. Almost all were
written from memory by the domain authors. Your job is to check one domain's entries against
the published sources themselves, and report what you could and could not confirm.

You verify; you do not edit. **Do not change any file under `taxonomy/domains/`.** Write one
file, `taxonomy/verify/<domain>.json`, and nothing else.

## Method

1. Load `taxonomy/domains/<domain>.json` with `.venv/bin/python`. Collect every crosswalk entry
   on capabilities and on tasks, with the id of the node it sits on. Group them by `scheme`.
2. For each scheme, most-used first, find the authoritative public page that lists its
   structure (the standards body's own site, an official browser or API, or the document
   itself). Read it. Budget: about 30 page reads in total; spend them on the schemes with the
   most entries and on entries that carry a `code`.
3. For each entry, give a verdict:
   - `confirmed`: you read a page in this session showing this code with this label (or, for
     an entry without a code, showing this label as an item of the scheme). Small wording
     differences are a correction, not a confirmation.
   - `corrected`: the item exists but the code or the label differs. Give the right ones.
   - `contradicted`: you read the scheme's structure and this item is not in it, or the code
     means something else and no close item exists.
   - `unverifiable`: you could not read the scheme (paywalled standard, blocked download,
     nothing authoritative found), or you read only part of it and this item was not in the
     part you read.
4. A search-result snippet is not a read. Only text of a page you opened counts. If you only
   have a snippet, the verdict is `unverifiable`.
5. Do not use your own memory to confirm anything. Memory is what is being checked.

## Tools

Use web search to find pages and a page-fetch tool to read them. If you have no direct
page-fetch tool and must use a helper agent to fetch, **run it in the foreground and wait for
its result**; never start one in the background, because its report will not come back to you.
Paywalled standards (most ISO, IEC, SAE, ASTM, ISA documents) usually publish a free table of
contents or scope page; that is enough to confirm a part number and title, and nothing more.
Do not send anything about this project or its author to an external service.

## Output

`taxonomy/verify/<domain>.json`, valid JSON:

```json
{
  "domain": "science",
  "sources": [
    {"scheme": "NIST GAMS", "url": "https://gams.nist.gov/cgi-bin/serve.cgi", "status": "read",
     "note": "top level and classes D, G, L read; M not read"}
  ],
  "entries": [
    {"node": "science.optimization.linear_programming", "scheme": "NIST GAMS", "code": "G2a",
     "label": "Linear programming", "verdict": "confirmed", "correct_code": "", "correct_label": "",
     "url": "https://gams.nist.gov/cgi-bin/serve.cgi/Class/G2", "evidence": "G2a Linear programming"}
  ]
}
```

- `sources[].status`: `read`, `partly_read`, `paywalled`, `blocked`, or `not_found`.
- One `entries` item for **every** crosswalk entry in the domain file, in file order, copying
  `node`, `scheme`, `code` and `label` exactly as they appear there.
- `evidence`: the words on the page that support the verdict, 15 words or fewer. Empty for
  `unverifiable`.
- `correct_code` / `correct_label`: filled only for `corrected`.

Entries the file already marks `"basis": "fetched"` still get a verdict: re-check them.

## Report

When done, reply in under 150 words: entries by verdict, which schemes you could read and
which you could not, and any correction that changes what a node means (not just its wording).
