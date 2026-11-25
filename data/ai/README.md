# What AI systems are used for

Inputs to `plenty/ai.py`: three vendors' published figures on what their AI systems are used
for, each classified by the vendor into O\*NET work activities. Extracted with
`scripts/00_extract_ai.py`; rows and columns are selected and no values are changed.
Downloaded 2026-11-25.

| file | source | what is kept | licence |
|---|---|---|---|
| `anthropic_onet.csv` | Anthropic Economic Index, [Anthropic/EconomicIndex](https://huggingface.co/datasets/Anthropic/EconomicIndex) on Hugging Face, `release_2026_06_26/data/aei_claude_ai_2026-06-26.csv` and `aei_1p_api_2026-06-26.csv` | The `onet` category at the detailed, intermediate and general work-activity levels, for `GLOBAL` and `USA`, April and May 2026, and seven metrics: `pct`, `use_case_work_pct`, `collaboration_bucket_automation_pct`, `collaboration_bucket_augmentation_pct`, `ai_autonomy_mean`, `human_only_time_mean`, `human_with_ai_time_mean`. A `source` column says which file a row came from. | Data CC-BY (the dataset's README and data documentation; its metadata header says MIT) |
| `openai_iwa_us.csv` | OpenAI Signals v3.0, [data download](https://openai.com/signals/data-download/), `data-download-csv.zip`, `share_of_work_related_messages_by_onet_iwa_country_quarter.csv` | The United States rows: share of work-related consumer ChatGPT messages in each of 164 intermediate work activities and an "Other IWA" bucket, quarterly from 2025 Q1 to 2026 Q3 | CC BY 4.0 |
| `microsoft_iwa_metrics.csv` | Microsoft, [working-with-ai](https://github.com/microsoft/working-with-ai), `iwa_metrics.csv` (v1.1) | The whole file: for each of 332 intermediate work activities, the share of Bing Copilot conversations (United States, January to September 2024) with it as the user's goal and as the AI's action, with completion, scope and feedback rates | CC BY 4.0 |

## Attribution

- Anthropic: Massenkoff, Lyubich, Sacher, Hitzig, Zhang, Heller and McCrory, "Anthropic Economic
  Index report: Cadences", 26 June 2026,
  <https://www.anthropic.com/research/economic-index-june-2026-report>. Method: Handa, Tamkin et
  al., "Which Economic Tasks are Performed with AI? Evidence from Millions of Claude
  Conversations", arXiv:2503.04761.
- OpenAI: OpenAI Signals, version 3.0, 2026, <https://openai.com/signals/data-download/>.
- Microsoft: Tomlinson, Jaffe, Wang, Counts and Suri, "Working with AI: Measuring the
  Applicability of Generative AI to Occupations", arXiv:2507.07935.

## Notes

- **These are usage figures, not capability figures.** Each says what share of a vendor's
  conversations is about an activity. None says how well the system did the work.
- **Each is the vendor's own classification** of its conversations, made by a language model.
- **Identifiers.** Anthropic names activities as O\*NET does, and its task rows carry O\*NET task
  ids. OpenAI and Microsoft use an older form of the intermediate-activity id
  (`4.A.1.a.1.I01`); Microsoft's file gives the activity name beside it, which is how
  `plenty/ai.py` maps both to the O\*NET 31.0 ids in `data/occupations/`. Microsoft used O\*NET 29.0.
- **Unpublished cells.** Anthropic publishes a cell only above a sample threshold, and OpenAI
  groups rare activities into "Other IWA" and adds differential-privacy noise. A missing
  activity is not a zero in the source; `plenty/ai.py` counts it as zero.
- **Coverage.** OpenAI: consumer plans only, no enterprise accounts and no Codex. Anthropic:
  Claude chat on Free, Pro and Max plans, and the first-party API excluding Claude Code.
  Microsoft: Bing Copilot, 2024.
