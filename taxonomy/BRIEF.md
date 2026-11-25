# Brief for domain authors: the plenty capability taxonomy

## What this is for

Plenty keeps an account of what people need, the capabilities the work of meeting those needs
depends on, and which of those capabilities exist in the open. A **capability** here is
something software does for the people doing that work: model a part, solve a flow field,
schedule a fleet, keep a patient's record.

We need one hand-written taxonomy of those capabilities, across the whole economy, that:

1. classifies by **function** (what is computed or done), not by who uses it or how popular it is;
2. **integrates published taxonomies** instead of inventing categories, and records where each
   node comes from;
3. is deep enough at the bottom that each leaf is something a person could build an open
   benchmark or leaderboard for;
4. can be tied back to data: O\*NET lists the software each US occupation uses (8,753 products
   in 134 categories), and every leaf should be recognizable in that list where it exists.

Two earlier attempts failed and you should avoid their mistakes. A hand-made list of 18
engineering capabilities was too narrow and had no stated source. Clustering products by which
occupations use them grouped tools by popularity, not function: Python, C++, SQL, MATLAB and
QuickBooks landed in one cluster, and "software development" was left with Ada and FoxPro.

## The structure

- **Level 0, domain.** Fixed. Fourteen domains in `taxonomy/structure.json`. You own one.
- **Level 1, capability.** A named function at about the grain of "structural finite element
  analysis", "electronic health records", "warehouse management". Your domain has seed
  capabilities in `structure.json`; treat them as a first draft. Merge, split, rename, add or
  drop them, and say why in `notes` when you change one. Aim for 6 to 14 per domain.
- **Level 2, task.** The leaves. A task is a class of problem with definable inputs and
  outputs, at the grain of "linear static stress analysis", "modal analysis", "medication
  order entry with interaction checking", "vehicle routing with time windows". Aim for 3 to 8
  per capability. Go deeper where the published taxonomies do; do not pad.

## Rules

1. **Function, not user or industry.** "Software used by hospitals" is not a capability;
   "clinical order entry" is. An industry-specific node is right only when the function itself
   is specific to that industry.
2. **General tools live in their general home.** Python belongs to programming languages,
   Excel to spreadsheets, SQL Server to database management, MATLAB to numerical computing.
   Never list a general tool as an example in an applied domain just because that domain's
   people use it.
3. **One parent per node; many nodes per product.** A node appears once in the tree. A product
   may be an example of several nodes (SolidWorks: solid modeling and CAM; ArcGIS: GIS and
   cartography).
4. **Integrate, and say from what.** Your domain lists source taxonomies in `structure.json`.
   Use them to decide the breakdown, and record a crosswalk entry for each node that
   corresponds to something in a source. You may add sources. Record how you know:
   `"basis": "fetched"` with a `url` only if you retrieved it in this session;
   otherwise `"basis": "memory"`. **Never invent a code.** If you remember the concept but not
   its exact code, leave `code` empty and give the label. A node with no counterpart in any
   source is allowed: give it an empty crosswalk and explain in `notes`.
5. **Names are plain.** No brand names, no acronyms without the words, five words or fewer
   where possible. Definitions are one sentence: what goes in, what comes out.
6. **Examples must be real.** `onet_products` must be exact product strings from
   `taxonomy/input/products.csv` (they are checked by script). `state_of_art` and `open_tools`
   are from your knowledge; list only tools you are confident exist and do this task. An empty
   `open_tools` is information, not a failure.
7. **Stay inside your boundary** (next section). When you see products or functions that
   belong to another domain, do not model them; list them under `handoffs`.

## Boundaries between domains

| Question | Owner |
|---|---|
| Authoring geometry, drawings, building and plant models, circuits; PDM/PLM | `design` |
| Circuit, HDL and timing simulation; signal integrity inside the EDA flow | `design` (with IC and PCB design) |
| Solving physics for a design: structures, fluids, heat, fields, mechanisms, flowsheets | `simulate` |
| Structural frame analysis and code checking; geotechnical analysis | `simulate` |
| Engineered networks (water and sewer pipes, gas, pipelines, power grids): analysis | `simulate` |
| Natural water and air (rivers, watersheds, groundwater, coasts, atmosphere) | `earth` |
| System dynamics simulation and control-law design (block diagrams, acausal models) | `simulate` |
| PLC, robot and CNC programming; SCADA/HMI/DCS on the plant floor; MES; SPC; metrology | `produce` |
| Factory discrete-event simulation and production scheduling | `produce` |
| Maintenance, diagnostics, reliability and safety engineering, EHS | `operate` |
| Building automation; facility management; utility network operations (EMS, DMS, OMS) | `operate` |
| Building energy simulation | `simulate` |
| GIS, cartography, surveying, remote sensing, subsurface, agriculture, forestry | `earth` |
| General mathematics, statistics, machine-learning methods, optimization solvers | `science` |
| Instrument control and data acquisition; research laboratory informatics | `science` |
| Bioinformatics, cheminformatics, molecular modeling | `science` |
| Clinical laboratory systems; anything about a patient | `health` |
| Applied routing, scheduling, warehousing, supply-chain planning; vehicle and vessel operations | `move` |
| ERP, accounting, tax, payroll, HR, procurement, projects, documents, BI, office tools | `enterprise` |
| Quantity takeoff and estimating from drawings | `design`; project scheduling and controls | `enterprise` |
| CRM, marketing, point of sale, contact centers, restaurants, hospitality, real estate | `commerce` |
| Banking, lending, markets, insurance, legal practice, regulation, public safety, government | `govern` |
| Medical coding and billing | `health`; general billing | `enterprise` |
| Teaching, assessment, school administration, training authoring, libraries | `learn` |
| Images, layout, video, audio, animation, games, web pages and content management | `media` |
| Programming languages and tools, embedded toolchains, databases, OS, cloud, networks, security | `computing` |
| Machine-learning platforms and operations | `computing`; the methods | `science` |

When a function straddles two owners, model the part that is yours and add a `see_also`
pointing at the other domain's likely node id (`domain.capability`), plus a `handoffs` entry.

## Inputs

- `taxonomy/structure.json`: your domain's scope, seed capabilities, source taxonomies, the
  O\*NET categories assigned to you, and the existing functions you must place.
- `taxonomy/input/products.csv`: every O\*NET product with its category, the number of
  occupations that list it, example occupations, and whether O\*NET flags it as in demand.
  Read all products in your assigned categories. Five categories are grab-bags shared by many
  domains (`grab_bag_categories` in `structure.json`; "Analytical or scientific software" alone
  has 1,687 products): scan them for products that belong to you, using product names and the
  example occupations, and ignore the rest.
- `taxonomy/input/categories.csv`: which domains each category is assigned to.
- `config/capabilities.csv` and `config/software_capabilities.csv`: the 18 existing engineering
  functions and the product patterns matched to them. Each function named in your domain's
  `existing_functions` must end up as one of your nodes or be explicitly split or merged
  (record it in `existing_function_map`).

You may use web search to check the structure of a source taxonomy. Keep it to about ten
lookups; this is a writing task, not a literature review. Do not send anything about this
project or its author to an external service.

## Output

Write exactly one file: `taxonomy/domains/<your-domain-id>.json`. Do not edit anything else.
It must be valid JSON with this shape:

```json
{
  "domain": "simulate",
  "summary": "Two or three sentences on how you broke the domain down and which sources drove it.",
  "capabilities": [
    {
      "id": "simulate.structural_fea",
      "name": "Structural finite element analysis",
      "definition": "Given a part or assembly geometry, materials, loads and constraints, compute displacements, stresses and derived failure measures.",
      "crosswalk": [
        {"scheme": "NAFEMS PSE", "code": "", "label": "Finite Element Analysis", "basis": "memory", "url": ""}
      ],
      "onet_categories": ["Analytical or scientific software"],
      "see_also": ["design.solid_modeling"],
      "notes": "Was seed 'Structural finite element analysis'; frame analysis split out because design-code checking is a different task.",
      "tasks": [
        {
          "id": "simulate.structural_fea.linear_static",
          "name": "Linear static stress analysis",
          "definition": "Given a meshed elastic body with small-displacement loads and constraints, compute displacement and stress fields.",
          "inputs": "geometry or mesh, linear elastic materials, loads, constraints",
          "outputs": "displacement, strain and stress fields; reaction forces",
          "crosswalk": [],
          "onet_products": ["ANSYS simulation software", "MSC Software Nastran"],
          "state_of_art": ["Ansys Mechanical", "Abaqus/Standard", "MSC Nastran"],
          "open_tools": ["CalculiX", "Code_Aster", "FEniCS"],
          "benchmarkable": "yes: NAFEMS LE-series problems have reference solutions",
          "notes": ""
        }
      ]
    }
  ],
  "existing_function_map": [
    {"function": "fea", "nodes": ["simulate.structural_fea"], "note": ""}
  ],
  "handoffs": [
    {"what": "AspenTech HYSYS dynamic operator training", "to_domain": "produce", "why": "plant operation, not design physics"}
  ],
  "unplaced_products": ["exact product strings from your assigned categories that fit no node of yours and no other domain you can name"],
  "open_questions": ["Anything the editor must decide, for example a boundary you think is drawn wrong."]
}
```

Field notes:

- `id`: lowercase snake_case, dot-separated, prefixed by the domain: `domain.capability` and
  `domain.capability.task`. Unique. No brand names.
- `onet_products` on a task: up to 12 exact strings from `products.csv`, the clearest examples.
  A later pass assigns the long tail, so pick representative products, not all of them.
- `benchmarkable`: "yes: ...", "partly: ...", or "no: ..." with one clause on why. This is
  what decides whether an open leaderboard is possible.
- `onet_categories` on a capability: the O\*NET categories where its products mostly sit.

## Before you finish

Check your own file: it parses as JSON; ids are unique and well-formed; every `onet_products`
string appears verbatim in `products.csv`; every existing function assigned to you is in
`existing_function_map`; no general-purpose tool is listed as an example of an applied node.
Then report back in under 200 words: counts of capabilities and tasks, which seeds you changed
and why, the sources you actually used and whether fetched or from memory, and your open
questions. Do not paste the JSON into your report.
