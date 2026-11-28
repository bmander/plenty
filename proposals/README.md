# Proposals

A proposal is something that could be built, said plainly enough to be scored: what it is, how a
stranger would check that it works, which work it would do, and what it would cost to make. The
site scores each one against the account (`plenty/site.py`) and gives it a page.

One file to a proposal, `<name>.toml`:

```toml
name  = "Household handwork"
by    = "who proposes it"
what  = "What it is, in a sentence or two: what goes in and what comes out."
check = "How someone else could measure that it works, against a need and not against sales."

[chance]
works = 0.2               # the chance that it passes its own check, above zero and at most one
basis = "Why that chance."

[cost]                    # optional; without it the proposal has no return
hours = 1e9               # hours of people's work to make it
basis = "Where that number comes from."

[[does]]                  # one for each work activity it would do part of
activity = "4.A.3.a.1.c"  # an intermediate work activity of O*NET, as in config/activities.csv
share    = 1.0            # the part of that activity it would do, above zero and at most one
basis    = "Why that much of it."

[[replaces]]              # one for each set of sectors it would make the goods of
sectors = "33"            # the start of the sectors' codes in the Bureau's accounts: every sector whose code begins so
share   = 0.5             # the part of what they make that it would make, buying nothing and with nobody's hours
basis   = "Why that much of it."

[[lifts]]                 # one for each cause of ill health it would take something off
cause = "1530"            # the cause's code in data/health/burden_2019.csv; a cause that others are filed under stands for all of them
share = 0.5               # the part of the healthy life the cause takes that it would give back
basis = "Why that much of it."
```

A proposal claims activities, replaces sectors, lifts causes of ill health, or any of these
together. The work of a sector it replaces is counted there, with the work behind everything the
sector bought, so the same work is not also claimed by activity.

The rules:

- It is a way of doing work for a need. It may not change whose needs count.
- The check must be something a third party can run.
- Every share has a reason beside it, so that it can be disputed one row at a time.
- Scores never add. Where two proposals claim the same activity, the larger claim is counted once.

A share is the proposer's claim, and a cost is the proposer's estimate. Neither is checked by the
account, which only says how much work the claims come to.
