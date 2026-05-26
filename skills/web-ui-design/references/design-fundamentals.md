# Design Fundamentals

*The durable cross-cutting canon for all interface surfaces — web UI, terminal/CLI, APIs, and agent tools. An interface is the boundary where a system meets its consumer — human through a UI, machine through an API or a tool; design that boundary as a contract.*

This file is byte-identical across all four interface-design skills (`web-ui-design`, `tui-design`, `agentic-interface-design`, `api-design-craft`). The duplication is intentional: each skill loads only its own context, so the fundamentals must travel with the skill that needs them. The `sentinel` will flag this as redundancy — this is expected and correct. Do not "fix" it by consolidating or cross-referencing. Back to [SKILL.md](../SKILL.md).

---

## Dieter Rams: 10 Principles (adapted for software)

Rams designed the Braun T3 radio, SK4 turntable, and 606 shelving system. The same lens applies to every interface:

1. **Innovative** — new patterns must justify their unfamiliarity cost. Novelty is not a virtue; solving a genuine gap in the old way is.
2. **Useful** — every element must serve a function. Remove ornament that does not communicate anything. If you cannot explain why an element is there, remove it.
3. **Aesthetic** — visual quality is functional, not decorative. Ugly interfaces erode trust and cognitive willingness. An interface that looks considered *is* more trusted.
4. **Understandable** — the interface teaches itself. Users should not need a manual to discover primary actions. The UI explains its own model.
5. **Honest** — do not overstate capabilities. Disable buttons that cannot be clicked. Show real state, not aspirational state. Never fake a loading bar's progress.
6. **Unobtrusive** — the UI serves the task, not itself. Interfaces should recede and let the user's work be foreground.
7. **Long-lasting** — avoid fashion. Flat design, neumorphism, glassmorphism are trends; clear hierarchy and readable typography are not.
8. **Consistent in every detail** — micro-inconsistencies (misaligned labels, different button heights in one form, two slightly-different grays) destroy perceived quality at a subconscious level. The 100th inconsistency is felt even when it is not seen.
9. **Environmentally considerate** — for software: prefer efficiency. Fewer redraws, less CPU, less memory, less network. A fast interface is a kind interface.
10. **As little design as possible** — *less, but better*. Every element that can be removed should be removed. The goal is not minimalism as aesthetic but minimalism as respect for the user's attention.

**The Rams test**: Cover every element with your hand. If nothing changes for the user's ability to accomplish their task, remove it.

---

## Don Norman: Interaction Design Vocabulary

From *The Design of Everyday Things* (1988, revised 2013). These concepts apply whether the consumer is a person or a model:

- **Affordance**: What an element *can* do. A button affords pressing. An input field affords text entry. A draggable item affords being dragged. Affordances exist whether or not they are visible.
- **Signifier**: What *signals* what an element can do. The visual styling that makes a button look pressable. The underline that marks a link. The grab handle that marks a draggable. Signifiers make affordances visible.
- **Feedback**: Immediate system response to every action. Button press → visual depression + state change. Form submit → progress indicator. No feedback = broken affordance. *Feedback must be within 100ms to feel instant.*
- **Mapping**: Natural correspondence between control and effect. Scroll down → content moves down. Drag right → moves right. Mappings that fight expectation cause error and frustration.
- **Constraints**: Limiting possible actions to prevent errors. Disabled states are constraints. Required-field validation is a constraint. A read-only file mode is a constraint. Use constraints proactively.
- **Conceptual model**: The user's mental model of how the system works. The UI must match this model, or the mismatch becomes the primary source of errors. Never design for your internal model — design for the user's model.

**The two ways to fail**:
- **False affordance**: something *looks* interactive but isn't. Underlined text that is not a link. A div styled like a button. Users click it, nothing happens, they lose trust.
- **Hidden affordance**: something *is* interactive but doesn't look it. A clickable logo with no visual cue. A keyboard shortcut with no discoverability path. Users never find it, capability is wasted.

---

## Jakob Nielsen: 10 Usability Heuristics

Condensed from Nielsen Norman Group's foundational framework. These apply to web UIs, CLI interfaces, API error messages, and tool descriptions alike:

1. **Visibility of system status** — always communicate what is happening. Loading, processing, saved, failed. Silence is not acceptable.
2. **Match between system and real world** — use the user's vocabulary, not the system's internal jargon. "Save failed" beats "ETIMEOUT: connection timeout 30000ms."
3. **User control and freedom** — undo, back, cancel. Let users escape mistakes without penalty. Irreversible actions require confirmation.
4. **Consistency and standards** — follow platform conventions. Do not invent new patterns when existing patterns work. Users carry conventions from other tools.
5. **Error prevention** — prevent errors before they happen. Disable invalid states. Validate early. Show constraints before they are violated, not after.
6. **Recognition over recall** — surface options; do not require memorization. Show available commands. Show current filter state. Do not require users to remember state from previous screens.
7. **Flexibility and efficiency of use** — shortcuts for experts, simple path for novices. Command palettes, keyboard shortcuts, typeahead — all serve expert users without burdening novices.
8. **Aesthetic and minimalist design** — every extra unit of information competes with every other unit. Ruthlessly edit. The question is not "should we show this?" but "is hiding this worth the cost of not showing it?"
9. **Help users recognize, diagnose, and recover from errors** — plain-language error messages that say what went wrong, why, and exactly how to fix it. No stack traces as the primary error surface.
10. **Help and documentation** — when needed, help should be focused on the user's task, not the system's structure. Examples first, prose second.

---

## Edward Tufte: Information Design

From *The Visual Display of Quantitative Information* (1983) and subsequent work:

- **Data-ink ratio**: `data-ink ratio = data-ink / total ink used to print the graphic`. Aim for near 1.0. Every unit of ink should represent data. Non-data ink is waste. Practically: remove gridlines until they are needed, lighten tick marks, eliminate background fills that carry no information.
- **Chartjunk**: Decorative elements that do not represent data — 3D bars, gradient fills, redundant tick marks, heavy grid lines — are not merely aesthetic failure. They actively obscure data by competing with signal. Remove them.
- **Small multiples**: Show many views of the same structure side-by-side so differences emerge from pattern comparison. Far more effective than animation or toggling between views for comparative analysis. Applied to dashboards: show 12 months of a metric as 12 small sparklines rather than one animated chart.
- **Information density**: Well-organized high-density presentations are *easier* to read than low-density ones — the eye finds patterns in density. The instinct to "simplify" by removing true signal is wrong. What to simplify is *noise*, not *information*.

Applied to the Praxion dashboard: remove background grid lines from charts until they are needed, flatten bar charts, prefer sparklines over full charts for trend indication.

---

## Joshua Bloch: Principles for Interface Design

From *Effective Java* and the "How to Design a Good API" talk (Google I/O 2007). Originally for Java APIs; apply to every interface surface — REST endpoints, CLI flags, tool names, component props, database schemas:

1. **Minimal surface area** — when in doubt, leave it out. Every element you add becomes permanent maintenance burden and a constraint on future change. Start with less; you can always add. You cannot take away.
2. **Names matter** — a name is the primary interface. A bad name causes misuse every time it is called. Take the time to name things correctly. `user_id` not `uid`. `source_branch` not `branch`. `create_order` not `do_order`.
3. **Hard to misuse > easy to use** — the most important property of an interface is that correct use is easy and incorrect use is impossible or at least obvious. A function you can call wrong is a bug waiting to happen.
4. **Fail fast** — report errors at the point of failure, not later. Validate inputs early. Raise on first violation. Silent failures propagate into subtle corruption.
5. **Principle of least astonishment** — the system should do what the name and context suggest. No hidden side effects. No surprising coercions. If the behavior could surprise a reasonable user, change the behavior.
6. **Consistency over local cleverness** — identical things must look identical. Different things must look different. One naming convention, enforced everywhere, beats three clever local optimizations. Inconsistency is the leading cause of misuse.
7. **Document religiously** — an undocumented interface is a broken interface. The documentation is part of the contract. Write it as you design, not after.
8. **Avoid long parameter lists** — four or more parameters is a smell. Use a structured parameter object. This applies to function signatures, CLI flags, tool input schemas, and component props.

---

## Laws of UX

Cognitive laws that predict user behavior. These apply to every interface surface:

| Law | Statement | Design Implication |
|-----|-----------|-------------------|
| **Fitts's Law** | Time to acquire a target ∝ distance / size. | Primary actions must be large and close to the user's likely starting position. Corner buttons are slow; bottom-center on mobile is fast. |
| **Hick's Law** | Decision time grows logarithmically with the number of choices. | Limit simultaneous choices to ≤7. Use progressive disclosure to defer rare actions. Navigation should have 5–7 top-level items, not 15. |
| **Miller's Law** | Working memory holds 7 ± 2 chunks. | Group information into chunks ≤7 items. Chunked forms, paginated data, chunked settings all reduce recall burden. |

**Applied to terminal/CLI**: Hick's Law governs help text design — a flat list of 40 flags is cognitively expensive; grouped flags with examples-first is fast. Miller's Law governs exit codes — document all custom codes and keep the meaningful set small.

**Applied to APIs and tools**: Fitts's Law analogue — frequently-called endpoints/tools should require minimal parameters. Hick's Law analogue — a tool surface with >20 tools needs progressive disclosure (LLM decision quality degrades past ~20–25 tools presented simultaneously).

---

## The Three Perception Thresholds

| Threshold | Perception | Required Response |
|-----------|------------|------------------|
| **< 100ms** | Instant — the system is responding to me | No indicator needed if response arrives in time |
| **100ms – 1s** | Natural task progression | Show a spinner or progress indicator |
| **1s – 10s** | User loses focus; attention begins to drift | Skeleton screen + estimated time; let user do other work |
| **> 10s** | User abandons or loses trust | Real progress bar with steps + allow cancellation |

**The 50ms input budget**: For RAIL Response, the actual processing budget is 50ms (not 100ms), because background tasks may consume the other 50ms. Process user input within 50ms to guarantee the 100ms perceived-instant threshold is met.

These thresholds apply equally to web UI loading, CLI operations, and API response times. The design response differs by surface (skeleton vs spinner vs progress bar for web; progress indicator suppressed in non-TTY for CLI; `202 + Location` for long-running API ops) but the human perception law is the same.

---

## Julie Zhuo: Taste Before Craft

From *The Making of a Manager* (2019) and her design writing:

**Design quality is a taste problem before it is a craft problem.** Taste — the ability to recognize what is good — is trained by exposure to excellent work. Before you can execute well, you must be able to see well.

*Be opinionated, not neutral.* "Here are your options" is less useful than "This pattern is better for this reason, and here is evidence." An interface designer who presents options without a recommendation is abdicating the value they provide. Make the call. Explain the reasoning. Accept that you may be wrong and update.

Applied to AI agents encoding design knowledge: the agent must be a quality advocate, not an options-enumerator. The canon below exists to make the agent's opinions grounded, not arbitrary.

---

## The Canon: One Durable Lesson Each

| Practitioner / Product | Durable Lesson |
|------------------------|----------------|
| **Dieter Rams / Braun** | Less, but better. Remove until removal breaks function. The best feature is often the one you don't build. |
| **Don Norman / Nielsen Norman Group** | Affordances must be visible; feedback must be immediate. The NNG archive is the highest-signal corpus of applied UX research. |
| **Apple HIG** | Platform coherence beats novelty. Users learn platform patterns and expect them everywhere. Fight your platform only when user experience genuinely demands it. |
| **Google Material Design** | Design systems make quality consistent at scale. The 8dp grid, typographic scale, elevation model, and motion-as-communication are still the practical defaults. |
| **Edward Tufte** | Maximize the signal; eliminate the noise. Data-ink ratio near 1.0. Small multiples beat animation. Density is friendly when organized. |
| **Bret Victor** | Most software is information software; interaction should be a last resort. Immediate connection between action and effect is a creative necessity, not a luxury. |
| **Refactoring UI** | Systematic visual design is learnable by engineers. Design in grayscale first. Use weight and color, not just size, for hierarchy. The 5-shade palette. |
| **Radix / shadcn** | Accessible primitives are the foundation; style is a separate concern. Radix handles behavior correctly; add your style. Never reimplement what Radix already solved correctly. |
| **Linear** | Speed is a feature. Keyboard-first design is respect for power users. Linear is 3.7× faster than JIRA for common operations — speed is measurable and matters. |
| **Stripe** | Clarity and density can coexist. The gold standard for developer-product design: high information density, excellent typographic hierarchy, consistent component language. |
| **Vercel** | Developer-product aesthetics set the quality bar. Dark by default, monospace where code appears, instant feedback, informative progress indicators. |
| **Inter / Rasmus Andersson** | The right typeface at system font is invisible and correct. Designed specifically for screen legibility at small sizes. The de-facto standard for developer tools and SaaS. |
