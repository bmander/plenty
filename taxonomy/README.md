# Capability taxonomy

A hand-written taxonomy of what software does for the people who meet human needs:
14 domains, 223 capabilities, 1,440 tasks. Draft, 2026-11-25. The site's capabilities page shows it, and
`plenty/flows.py` traces each need dollar to its capabilities through `products_seed.csv`.

It replaces two earlier attempts. A list of 18 engineering capabilities was too narrow and had
no stated source. Clustering O\*NET products by which occupations use them grouped tools by
popularity, not function.

## Structure

| Level | What it is | Example |
|---|---|---|
| 0 Domain | Fixed, written first (`structure.json`) | Simulate and analyze physical behavior |
| 1 Capability | A named function | Structural finite element analysis |
| 2 Task | A class of problem with definable inputs and outputs | Linear static stress analysis |

Each task records its inputs and outputs, example products from O\*NET, state-of-the-art and
open-source tools, and whether an open benchmark is possible (`yes` 652, `partly` 612, `no` 176).
Each node carries a crosswalk to the published taxonomies it was drawn from.

## How it was made

1. The editor wrote the domains, their boundaries, seed capabilities and the published
   taxonomies each must integrate (`structure.json`, `BRIEF.md`).
2. One author per domain (Claude Opus) wrote the capabilities and tasks from the brief, the
   source taxonomies and the O\*NET product list (`domains/*.json`).
3. The editor read the whole tree and gave each task modeled twice a single owner, added one
   orphaned capability, and repointed cross-references (`EDITS.md`, passes 1 and 2).
4. A separate verifier per domain (Claude Sonnet) checked every crosswalk entry against the
   published source itself (`VERIFY.md`, `verify/*.json`); the editor applied the verdicts
   (`EDITS.md`, pass 3).

## How far to trust it

- **Crosswalk: 1,082 of 1,803 entries (60%) were checked against the source** and are marked
  `basis: fetched` with the page read. The other 721 are `basis: memory`: the source could not
  be read (ISO, IEC, SAE, ASTM, SEMI and several other bodies refuse automated reads or are
  paywalled). Checking found 192 entries to correct and 11 to remove, so expect roughly one in
  six of the unchecked entries to be wrong in wording or code, and about one in a hundred to
  cite something that does not exist.
- Weakest sourcing: `produce` (20 of 164 checked), `operate` (24 of 154), `earth` (15 of 79).
  Strongest: `science`, `health`, `simulate` (all above 95%).
- **Not checked at all:** the `state_of_art`, `open_tools` and `benchmarkable` fields. They are
  the authors' knowledge. An empty `open_tools` means the author knew of none, not that none exists.
- **Product examples are exact O\*NET strings** (checked by `check.py`): 5,670 of 8,753 products
  are cited on some task, including 92% of those listed by ten or more occupations. The rest
  are mostly products a single occupation lists.
- No one who works in these fields has reviewed it.

## Known gaps and open questions

- Robotics outside factory cells (mobile robots, autonomous vehicles) has no node.
- Several domains exceed the 6 to 14 capabilities asked for (`simulate` has 25). The editor kept
  them: each merge on offer would have joined different physics.
- Some pairs are deliberately kept in two places as general method and applied use (discrete-event
  simulation; corrective-action tracking; nondestructive evaluation of new and in-service parts).
- Each domain file ends with its author's `open_questions` and `unplaced_products`.

## Files

    structure.json     domains, seeds, sources, O*NET category assignment (hand-written)
    BRIEF.md           the rules the domain authors followed
    domains/*.json     the taxonomy itself, one file per domain (source of truth)
    VERIFY.md          the rules the verifiers followed
    verify/*.json      one verdict per crosswalk entry, with the page read
    EDITS.md           every change the editor made, with reasons
    capabilities.csv   flat table of all nodes          (built by build.py)
    crosswalk.csv      flat table of all crosswalk entries
    products_seed.csv  task -> O*NET product examples
    check.py           validates the domain files against the brief
    review.py          cross-domain report: overlaps, sourcing, hand-offs
    input/             O*NET products by category; saved source lookups

    python taxonomy/check.py && python taxonomy/build.py
