# @agent-bios/visualization-docs

## Visual Explanations

- For SVG diagrams, service blueprints, pipeline maps, or complex visual decision aids, read and use `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/svg-visualization-guide.md` as a scoped extension of this section.
- When a concept is easier to understand visually, use compact HTML, a Markdown table, or a diagram.
- Use HTML for comparisons, flows, state changes, hierarchies, or decision dashboards where layout improves understanding.
- Keep HTML self-contained, accessible, and minimal; avoid decorative complexity.
- Use plain text when it is clearer or the user asked for a concise answer.

## Implementation Map

- For the detailed `IMPLEMENTATION_MAP.html` construction rules and the SVG service-blueprint spec, read and use `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/implementation-map.md` as a scoped extension of this section.
- In repos with implementation code, when architecture, goals, or roadmap context would help future work, maintain `IMPLEMENTATION_MAP.html` as a current-state dashboard — not a changelog, handoff log, or project diary — and update it before committing, when writing a handoff, or after meaningful architecture, roadmap, risk, decision, or verification changes.
