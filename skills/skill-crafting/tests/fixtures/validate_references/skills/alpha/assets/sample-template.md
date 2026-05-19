<!-- SCENARIO: skills/*/assets/ templates are excluded from the walk -- their links are instantiation-relative placeholders that resolve only after the template is copied into a target project, so they must never be link-validated at the template's own path -->

# Sample Template

The paths below resolve at the instantiation site, not at the template's own
location. If `assets/` were walked, both would be reported FAIL:

- [decisions index](decisions/DECISIONS_INDEX.md)
- ![architecture context](diagrams/architecture/rendered/context.svg)
