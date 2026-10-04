# Review checks

The checks a LikeC4 diagram must pass, each decidable from the model, the render's markup or a command's
output, never from looking at the picture. Back to [`../SKILL.md`](../SKILL.md).

This file is the only home of the thresholds: the rule, the agent prompts and the other references name the
checks and link here. `python3 scripts/regenerate_diagrams.py --check` applies them and prints one finding
per check and view under the same ids; apply the table by hand when the command is unavailable, and record
any check you could not run. The ids are durable; the wording of a check may be sharpened, its id never
changes meaning.

## Review checks

| Id | Check | Evidence | Pass condition |
|---|---|---|---|
| DRC-01 | Title names subject and C4 type | model (`likec4 export json`); render markup (`rendered/<view>.svg`) | One group contains the view title and one of: System Context, System Landscape, Container, Component, Dynamic, Deployment |
| DRC-02 | Legend complete | model (`likec4 export json`); render markup (`rendered/<view>.svg`) | A group holds a line reading exactly `Legend`. Inside its region, for every (category, form) drawn, a line begins with the exact category name and a sample has that category's exact drawing; one arrow sample per dash style the view's arrows use |
| DRC-03 | Element states name, category or technology, responsibility | model (`likec4 export json`); render markup (`rendered/<view>.svg`) | Each drawn element has one group that spells its name on consecutive lines, holds a line (not part of the name) containing its category name or technology, and contains its summary or description (whitespace-normalised) whenever the model records one |
| DRC-04 | Arrows state intent and point one way | model (`likec4 export json`); render markup (`rendered/<view>.svg`) | Arrows outside the legend equal the view's edges. Each carries exactly one of `marker-start` or `marker-end`. Each label is non-empty, not punctuation-only, not `[...]`, and not only one of: uses, calls, connects to, interacts with, talks to, depends on |
| DRC-05 | Categories told apart without colour | model (`likec4 export json`); render markup (`rendered/<view>.svg`) | Every element resolves to exactly one category (its kind's notation, or its `metadata.category`) that names a token. In a view no two categories share a mark (shape geometry, dash, stroke width, icon), boxes compared with boxes and frames with frames. Across renders each (category, form) has one drawing |
| DRC-06 | Contrast | render markup (`rendered/<view>.svg`) | Every text is at least 4.5:1 against the composited surface behind it. Every outline and arrow is at least 3:1 against the canvas (a transparent canvas is judged on `#FFFFFF` and `#121212`) |
| DRC-07 | Legible at the 960 px reference width | render markup (`rendered/<view>.svg`) | Every text: font-size × min(1, 960 / render width) is at least 10. No two text lines overlap by more than 1 px in both axes |
| DRC-08 | Proportions and fan-in | render markup (`rendered/<view>.svg`); model (`likec4 export json`) | 0.5 ≤ width / height ≤ 2.5. No element meets more than 9 edges in the view |
| DRC-09 | One level of abstraction | model (`likec4 export json`) | No drawn box has a model ancestor that is also drawn as a box in the same view (an ancestor appears only as an enclosing frame, or not at all) |
| DRC-10 | Renders match a fresh regeneration | command output (`python3 scripts/regenerate_diagrams.py --check`) | The command exits 0. Every view listed by `likec4 export json` has `rendered/<view-id>.svg`, byte-identical to a fresh offline regeneration |
| DRC-11 | Embeds describe what they show | document source (markdown) | Every `![alt](…/rendered/<view-id>.svg)` alt text contains the view title and its C4 type name. `docs/diagrams/README.md` lists every render |
| DRC-12 | Regenerates without failure | command output (`python3 scripts/regenerate_diagrams.py`) | No `[diagram-regen] FAIL` line of kind toolchain-error, no-views, view-without-render or render-without-names |

## Reading the table

- **View** means every entry `likec4 export json` lists for the model, including LikeC4's implicit `index`
  when the model declares none.
- **Group** means one SVG `<g>`; **render markup** means that file read as text.
- Rationale and evidence grades for the thresholds are in the style canon, which cites checks by name and
  carries no numbers of its own.
