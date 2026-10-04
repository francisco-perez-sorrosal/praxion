# Style canon

Why an architecture diagram looks the way the review checks demand: the practitioner rules, how well each is
evidenced, and the colour, shape and wording choices that follow. The checks themselves, with every threshold,
live in [`review-checks.md`](review-checks.md); this file names them and carries no number of its own. Back to
[`../SKILL.md`](../SKILL.md).

Contents: [Evidence grades](#evidence-grades) · [The canon](#the-canon) · [View types](#view-types) ·
[Palette and shape semantics](#palette-and-shape-semantics) · [Anti-patterns](#anti-patterns) ·
[Agent readability](#agent-readability) · [Sources](#sources)

## Evidence grades

| Grade | Meaning |
|---|---|
| canon | At least two independent traditions (C4 practice, notation theory, perception research, accessibility standards, documentation-for-machines) converge on a primary source |
| C4-canon | Several C4 publications agree, but all sit inside one tradition |
| single-source | One source, however authoritative |
| plausible | No primary source found; reasoned from adjacent evidence or reported only by secondary pages |

A check may be binding while its grade is low: a check pins a number so a reviewer never has to decide, and
the grade says how far the number is evidence rather than choice.

## The canon

Rules are grouped by what they protect. The last column names the check that enforces a rule; a dash means no
check can decide it from the model or the markup, so a reviewer applies it as judgement.

| Rule | Why | Grade | Check |
|---|---|---|---|
| **Orientation** | | | |
| Title the diagram with its subject and C4 type | A reader must know what question the picture answers before reading it | C4-canon | DRC-01 |
| Carry a legend for every colour, shape, line style and border, even when it looks obvious | Notation is never self-evident; an unexplained notation is the most-named C4 failure | canon | DRC-02 |
| Show name, type, technology (containers and components) and a one-line responsibility on every element | A name alone makes the reader guess the role | canon | DRC-03 |
| Label every relationship with a specific intent, consistent with its arrow direction | An unlabelled or generic arrow has no meaning; direction plus a verb makes a sentence | C4-canon | DRC-04 |
| Make the diagram understandable without a presenter | The artefact outlives the meeting | canon | DRC-02, DRC-03, DRC-04 |
| Spell out acronyms or key them | The audience spans non-technical readers | C4-canon | — |
| **Structure** | | | |
| One level of abstraction and one story per view | Mixed levels destroy the zoom metaphor; cognitive load, not canvas size, is the limit | canon | DRC-09 |
| Split a crowded view by business area, bounded context or use case, never by shrinking the type | Splitting restores a reader's working memory; shrinking only hides the problem | canon | DRC-07, DRC-08 |
| Keep peers per boundary within working-memory limits | Grouping beats counting; a budget is a trigger to chunk | principle canon, numbers plausible | DRC-08 |
| Show the boundary of the system in scope and group related elements in neutral enclosing frames | Common region is the strongest grouping cue and makes inside versus outside explicit | canon | DRC-09 |
| Keep deployment detail (replicas, balancers, failover) out of container views | It varies by environment and buries structure; use a deployment view | canon | — |
| Use dynamic views sparingly, numbered, for runtime collaborations that are not obvious | Static boxes hide order, but a chain of trivial calls is noise | C4-canon | — |
| **Encoding** | | | |
| Keep notation consistent within and across diagrams | A style that shifts per view forces the reader to relearn it | canon | DRC-05 |
| Use colour as a semantic carrier, never decoration, from a small fixed vocabulary | Each hue must answer "what kind of thing?"; extra hues dilute the code | canon | DRC-05 |
| Never carry meaning by colour alone: add shape, outline style or text | Colour-vision deficiency is common and black-and-white printing strips hue | canon | DRC-05 |
| Meet the contrast floors for text, outlines and arrows | Legibility floor, applied to images of text | canon | DRC-06 |
| Let shape carry meaning (person, cylinder for a store) and key it | Shape is a pre-attentive channel independent of hue | canon | DRC-05 |
| Spend no ink on anything that tells nothing new: no gradients, shadows or decorative icons | Ink that informs nothing competes with ink that does (contested: decoration can aid memory in some studies) | canon, contested | — |
| **Layout and legibility** | | | |
| Minimise edge crossings and bends | Crossings were the most harmful layout aesthetic in controlled studies | canon | — |
| Keep one dominant reading direction; people at the entry edge, stores at the far edge | A predictable scan path; break the convention deliberately, never by accident | C4-canon | — |
| Render at a size where the smallest text stays legible at the delivery size, including after downscaling | A diagram unreadable at delivery size is not a diagram; no source gives a point size, so the floor is derived | single-source (derived) | DRC-07 |
| **Pipeline** | | | |
| Generate diagrams from a model kept in git: one definition, many views | Rename, query, diff and validate once; no copy-paste drift; readable by agents | canon | DRC-10, DRC-12 |
| Pair every diagram with alt text and an adjacent prose description | Screen readers and language models both need non-pixel access | canon | DRC-11 |
| Review against a published checklist before merging | It turns taste into a mechanical gate | single-source (authoritative) | all |

Two limits apply to the whole canon. It targets diagrams that communicate and document; a drawing used to
argue a trade-off in a decision meeting follows other rules. And an architecture diagram is a sketch that
selects, not a blueprint that includes everything: comprehensiveness works against comprehension.

## View types

Pick the type before drawing; the `c4_*` tag in [the recipes](likec4-authoring-recipes.md#view-tags) records
it and the title block prints it.

| Type | Shows | Leaves out | Use |
|---|---|---|---|
| System Context | The system in scope, centred, with the people and systems it touches | Technology, protocols, internals | Every project |
| System Landscape | The people and systems of an organisation or department, with no single focus | Internals, runtime behaviour | When several systems matter together |
| Container | The deployable or data-holding parts of one system, major technology, communication paths | Deployment detail | Every project |
| Component | The parts of one container and their responsibilities | Whole-system scope | Only where it adds value |
| Dynamic | Numbered interactions between existing elements for one scenario | The whole architecture, obvious flows | Sparingly |
| Deployment | Nodes and instances of one environment | Mixing environments | When operations need it |

## Palette and shape semantics

The values (hues, strokes, marks) belong to the regeneration command's token table, which a project extends in
its `style.json`; the kinds and their notations live in `_spec.c4`. What follows is the reasoning, so a project
that extends the kit extends it the same way.

- **Tint fill, strong category stroke, slate text.** The system in scope is the only solid fill, so the thing
  the diagram is about carries the most contrast and every frame stays neutral. Boundaries are dashed or
  transparent so they never compete with element colours.
- **Hue families come from a colour-vision-safe set** (blue, sky, bluish-green, vermilion, reddish-purple,
  orange), not from the Structurizr or C4-PlantUML defaults. Those defaults fail the text-contrast floor for
  container, component and external roles when paired with the white text the same tools prescribe, so adopting
  them verbatim imports a defect.
- **Hue is the third channel**, after shape or outline style and the category name printed on the element. Any
  pair of categories that hue alone separates poorly (checked with a colour-vision simulation) also differs
  in shape or outline.
- **Shape tells the category kind.** Person gets the person glyph; a data store is a cylinder; the system in
  scope has a heavy outline; an external system has a dashed outline and a muted fill; a component is
  double-bordered; a container is rounded. A project's extra categories each take a mark no other category in
  its views uses (a folder tab, a wavy-base document, a three-dimensional box).
- **Frames and boxes are different forms.** A category drawn as a frame (an enclosing boundary) and as a box
  needs two drawings, each unique across every render, and the legend shows both.
- **Three line meanings, a closed set.** An arrow either acts on its target (solid), only reads from it
  (dashed) or is a numbered step in a dynamic view (heavier, in the accent colour). Every arrow has exactly one
  head, at the target. A relationship that only reads uses the `reads` kind so the legend can tell flows from
  writes.
- **One typeface, one size for every line of an element**, with the hierarchy carried by structure (name, then
  the category line in brackets, then the responsibility) rather than size. The renderer embeds its font, so
  text metrics, and with them layout, stay reproducible.
- **One icon, the person glyph.** Identity (a vendor, a product) goes in the category line as text. An icon on
  one element of a category makes that category draw two ways, and icons absent from the legend are decoration.
- **Light only for now.** Dark values are reserved, not emitted. A dark variant needs its own contrast
  derivation: the strokes that pass on white fail on a near-black canvas (grade: plausible).

## Anti-patterns

Names marked *coined* are labels this guide assigns, not phrases from a source.

| Name | What it is | Caught by |
|---|---|---|
| Confused mess of boxes and lines | Unlabelled, unstructured boxes and arrows | DRC-03, DRC-04 |
| Level mixing | People, systems, containers and components in one view | DRC-09 |
| Unexplained or shifting notation | Colours, shapes or line styles not keyed, or different per view | DRC-02, DRC-05 |
| Self-evident-with-a-presenter | Needs narration to be understood | DRC-02 to DRC-04 |
| Acronym wall | Abbreviations nobody defined | review |
| Giant diagram | One view for everything | DRC-07, DRC-08 |
| Mystery arrow *(coined)* | An arrow labelled "uses" or "calls", or not at all | DRC-04 |
| Bidirectional arrow | A double-headed line with no intent | DRC-04 |
| Colour-only encoding *(coined)* | Meaning carried by hue alone | DRC-05 |
| Palette-fail *(coined)* | A fill whose text or outline misses the contrast floor | DRC-06 |
| Rainbow diagram *(coined)* | Many hues with no semantic role | DRC-05 |
| Spaghetti *(coined)* | Heavy edge crossing and long routes | review |
| Icon soup *(coined)* | Vendor icons everywhere, absent from the key | DRC-02, DRC-05 |
| Deployment leakage *(coined)* | Replicas and balancers in a container view | review |
| Orphan box *(coined)* | An element with no relationship in its view | review |
| Stale render *(coined)* | A committed image that no longer matches the model | DRC-10 |

## Agent readability

The model is the source; the image is a view. An agent that must answer a question about the architecture
reads the model (see the query rubric in [`../SKILL.md`](../SKILL.md)), not the picture: language models count
and locate objects in images only approximately, downscale large images, and lose small text.

- **Put every fact as text** (responsibility, technology, protocol), so a reader that cannot see the colour or
  the icon loses nothing. This is also the colour-blind rule.
- **Write alt text as a short summary and the long description as adjacent prose**; "diagram of X" alone says
  nothing. Name the view title and its C4 type in the alt text.
- **Prefer vector or lossless images** and keep the text legible after any resize.
- **Name elements as the code names them** where a code module or package exists; one rename in the model
  reaches every view (plausible for the code alignment, canon for rename propagation).
- **Provide a text alternate beside a rendered diagram**, such as the model source or a catalog of renders
  (single-source: the proposal is not a standard).

## Sources

Primary: the C4 model notation, checklist, container, dynamic and deployment pages (c4model.com/diagrams/...);
WCAG 2.2 Understanding pages for contrast minimum, non-text contrast and use of colour; the Okabe-Ito
colour-universal-design guidance (jfly.uni-koeln.de/color); W3C WAI complex-images tutorial; Anthropic's vision
documentation for image limits.

Secondary or derived, so graded down: Simon Brown's talk notes and Moody's notation principles (slide
summaries of the published work); Tufte's data-ink and Gestalt grouping (encyclopaedic summaries); the graph-
drawing studies behind the crossings rule (read through abstracts); any numeric element budget (reported only
by tertiary pages); the minimum text size (derived from image-downscaling limits); dark-mode values (computed
here against the standards, with no primary source).
