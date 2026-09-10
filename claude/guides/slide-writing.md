---
guide_id: slide-writing
language: en
status: active
description: Apply shared source-fidelity, meaning, structure, and layout criteria when creating, revising, or reviewing slides, in any presentation format.
use_when:
  - creating, revising, or reviewing slides and presentation materials
  - deciding slide headlines, logical relationships, body hierarchy, spacing, or alignment
resources:
  - Read `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/slide-writing/RUNBOOK.md` only when using the paired static HTML/PDF execution and review path.
core_rules:
  - Read this primary guide for every slide or presentation task; it is the shared semantic source.
  - Use the companion runbook and scripts only for an explicitly applicable static HTML/PDF job.
---

<!-- criterion:c0000 -->
# Principles for Writing Slides

Structure slides so the reader first understands the central judgment, then can verify on the same screen the evidence and conditions supporting it. Visualizations express logical relationships between concepts through position, shape, size, grouping, and connections. The relationship stated by the wording must match the relationship read from the screen.

After deciding which meaning from the source must be preserved, design the groupings and relationships, body hierarchy, space, and reading order. Set specific values for presentation specifications for each task. When preserving meaning, readability, and use of space conflict, first reconsider the arrangement and content composition. Do not conceal a space problem by combining independent concepts or by making only a particular body level smaller.
<!-- /criterion -->

<!-- criterion:c0001 -->
## 1. Define the central judgment of each slide and the role of its body

Each slide answers what the reader needs to understand or judge. Groupings in the body connect the evidence, comparisons, processes, and conditions that explain that answer. When independent questions are mixed together, split the slide or define the higher-level question that explains why they belong together.

A slide may contain multiple facts. Each fact's role in the central judgment and its relationship to the others must be clear. Make the key relationships findable on the screen before the reader must assemble the content and infer them. Rather than connect every detailed condition with lines, reveal first the relationships needed to understand the central judgment.
<!-- /criterion -->

<!-- criterion:c0002 -->
## 2. Write headlines so the subject and conclusion are clear even when only the headlines are read

For a slide that explains content, state the subject and central judgment in its headline. Replace with a concrete sentence any reference that requires the preceding slide to understand, a title that only previews a count, or wording that omits the subject or predicate excessively. State the judgment within the scope and degree of certainty that the evidence supports.

Slides for overview, definition, or transition use a title that reveals their role and the content they convey. Do not force a claim onto a slide that has no conclusion. The sequence of problem framing and judgments must also connect when all headlines are read in order.

Headline line breaks follow units of meaning such as phrases and clauses. If only one final character or grammatical ending remains on the next line, adjust the headline width, phrasing, or line break. Distinguish a deliberately short line containing an independent word from a line that remains because a word was split off.
<!-- /criterion -->

<!-- criterion:c0003 -->
## 3. Preserve the names and distinctions of key concepts

Use the same name for the same concept. Explain a technical concept where needed, and do not alternate synonyms merely to vary the writing style. Even when shortening an explanation, retain each item's name and its difference from other items.

Before summarizing, identify the concepts, indicators, and conditions that must be read, recorded, or judged independently. An item defined separately in the source must remain findable in the result under its own name and definition. If distinct items are collapsed into one combined name, restore the distinction. Multiple items may appear in the same box; confirm their independence through the correspondence of names, definitions, and values rather than through the number of boxes.

Distinguish subjects, roles, activities, outputs, outcomes, and evaluation criteria. Distinguish examples from selection results, hypotheses from confirmed facts, and temporal order from causality. Also retain the conditions, exceptions, and applicable scope under which a relationship holds. When comparing numbers, align units, periods, subjects, and denominators; if the bases differ, state that difference.

If the source does not establish a relationship or scope, retain that uncertainty. Do not add an unsupported cause, sequence, or superiority merely to create a connection needed for visualization.
<!-- /criterion -->

<!-- criterion:c0004 -->
## 4. Create a reading order from conclusion to evidence

Arrange information on one screen according to the following roles. Use the roles needed for the slide's purpose, and do not repeat the same content in multiple locations.

| Information role | What the reader confirms |
|---|---|
| Headline | The subject and central judgment of this slide |
| Introduction | The judgment's scope and premise, and how to read the body |
| Current-position indicator | The discussion this slide belongs to in the overall document |
| Body | The evidence and relationships supporting the judgment |
| Conclusion or implication | An additional judgment or action derived from the body |
| Source | The material and location for verifying the evidence |

In the body, make visible where reading begins, what is compared together, and where to move next. Put information compared on the same basis in corresponding positions, and reveal any branch or convergence point. If two flows mix, divide the space or redefine the higher-level grouping.

Separate conclusions that only hold after reading the body's explanation from source indicators. Make conditions, exceptions, and responsibility scope that change the interpretation readable in the body close to the relevant claim. Set the order of emphasis so decorative position indicators or repeated titles do not draw attention away from the body.
<!-- /criterion -->

<!-- criterion:c0005 -->
## 5. Design both the composition within groupings and the relationships between them

Group the body into units with connected meaning, such as comparison targets, processes, responsibilities by subject, use of results, or common conditions. Arrange them so relationships within a grouping appear closer than relationships between groupings. Elements grouped by the same box, background, or boundary need a reason to be read together.

Boxes, background contrast, dividing lines, and whitespace are means to reveal grouping boundaries. A box is unnecessary when alignment, a common axis, connections, or continuity of shape make one object clear. Tables retain the comparison basis and the correspondence of rows and columns. A process may use boxes by step or be divided within one area; either way, the overall flow must read as continuous.

Set the unit for dividing boxes according to concepts or steps that must be read independently. Before putting every sentence in a separate box or gathering distinct judgments in one large box, check what distinction the reader gains. If the relationship between boxes must be left only to sentence interpretation, reinforce the arrangement, containment, or connections.
<!-- /criterion -->

<!-- criterion:c0006 -->
## 6. Express logical relationships through space, shape, and connections

First determine what is related to what, and how. Confirm the direction, conditions for holding, and applicable scope of the relationship, then select an expression that makes it readable. A relationship may have several valid arrangements.

| Relationship to show | Expressions that can be used | Meaning to preserve |
|---|---|---|
| Causality | Directional arrangement and connections among cause, action, and result | What affects what, and the strength and conditions of the evidence |
| Hierarchy or classification | A composition that divides branches or stages beneath a higher-level concept | What is classified according to which criteria |
| Containment or composition | Nested boxes, common boundaries, and the arrangement of component elements | What is part of what, and the scope of containment |
| Dependency or reliance | Layers of foundation and dependent elements, and connections showing prerequisites | What requires what; do not turn dependency into causality or containment |
| Equivalence or parallelism | Same-level columns, rows, comparison tables, or matrices | Independent alternatives or parallel evidence, and the common comparison basis |
| Equality or correspondence | An equals sign or a correspondence indicator between objects | The scope of the same meaning or value and its distinction from simple correspondence; use equals signs for equality |
| Correlation | A connection that explicitly states the association, or a chart using actual data | The fact that things vary together or are associated, and its distinction from a causal claim |
| Sequence or transition | Connected boxes, wedges, flowcharts, or timelines | Direction of progress, branching or convergence, and transition conditions; if using a time axis, periods and points in time |
| Roles or handoffs | Areas or lanes by subject, and handoff points | Boundaries of execution responsibility and what is handed over |
| Numeric magnitude, change, or distribution | A chart appropriate to the data and comparison purpose | Actual values and units, axes, and comparison basis |

The table's composition is a set of options, not a fixed symbol dictionary. Use visual markers with the same role consistently within a document. If a symbol's meaning could be confused, place a short relationship explanation near the connected objects. When position and connecting lines alone do not settle the meaning, make the wording readable with them.

Use nesting and layering to reveal containment, dependency, or differences in level. Do not treat a simple shadow or overlap as evidence of a logical relationship. Adjust the arrangement if boundaries or content are obscured. Make equivalent elements recognizable as being at the same level, but differing amounts of content do not require every box to have the same area. Check that a difference cannot be mistaken for superiority or quantity.

### Selection order for directional expressions

For a relationship that must show direction, secure both the spacing between boxes and room for their content.

1. First check whether changing the box's end or boundary can express the content and direction together. The width for text and the distinction between concepts must remain intact.
2. If a modified box is unnatural, connect the flow with a short wedge within the standard spacing.
3. If a wedge cannot make the relationship and connected objects clear, use an arrow. Within the readable range, reduce the connection length and space reserved solely for it.

An arrow may be selected directly when it ensures visibility while also minimizing empty space. It is unnecessary to produce every alternative in sequence. Judge appropriateness by the actual screen's relationships, spacing, and readability rather than by the reason a symbol was selected. Do not apply this order to a relationship that does not need direction.

It must be clear what arrows, wedges, and pointed ends of boxes point from and to. When connecting lines obscure content or several lines overlap so the target becomes ambiguous, first redesign box positions, groupings, and the branch structure.

A step guide that states periods may use equal widths. If using a quantitative axis where length represents time, represent actual periods. Do not use axes, area, or height that makes a concept map appear to be a measured result; if confusion is possible, indicate near the diagram that it is a concept map. Retain the units, axes, and legends necessary to interpret numeric charts.
<!-- /criterion -->

<!-- criterion:c0007 -->
## 7. Allocate space to the body area and within groupings

First determine the area the body will use between the headline and introduction, and the conclusion and source. Allocate area to each grouping according to the amount of information needed to explain the central judgment, the reading order, and the relationship structure. Content slides should align the outer boundaries of higher-level groupings and use the entire body area.

Apply consistent horizontal and vertical spacing between groupings at the same level. For areas compared side by side, align their starting points and comparison baselines, and preserve row and column correspondence. Distinguish the internal whitespace of nested groupings from the spacing between higher-level groupings because their roles differ. When spacing differs, check the relationship that the difference conveys.

Space allocation must continue from outer boxes to internal titles, tables, rows, and text. If a box with a short explanation is largely empty while another box concentrates essential evidence in small text, reconsider the area allocation. Do not treat the space problem as solved merely because all boxes have the same size or text was moved to vertical center.

Check separately the space between the body boundary and the final grouping, and the space between the end of a grouping and its actual content. Also examine the space occupied by connecting symbols. Retain whitespace that distinguishes groupings and supports reading order. Reduce unnecessary empty areas by adjusting the arrangement, content amount, or line breaks, rather than filling them by only expanding spacing between sentences.

Cover, transition, or closing slides, and slides focused on one visual object, may use whitespace for attention and distinction. Judge its appropriateness by the slide's reading purpose and actual content arrangement. Do not make one empty-space ratio the passing threshold for every slide.
<!-- /criterion -->

<!-- criterion:c0008 -->
## 8. Adjust content volume and text arrangement together

Information density is achieved when the evidence and conditions needed for a judgment are included faithfully and can be read. In a presentation, the key point and relationships appear first; when read alone, definitions, interpretation, and conditions can be followed.

When space is lacking, remove redundant wording and adjust column widths, paragraph divisions, row heights, internal whitespace, and the area of each grouping. Place sentences with different roles separately, as with definitions and interpretations in a comparison table. Do not hide essential evidence by shrinking type or moving it to footnotes.

When space remains, first check whether necessary explanation is missing, then adjust grouping proportions, line arrangement, and actual content size. Do not add claims or figures absent from the source, or pad with the same statement. Line breaks in sentences and names follow units of meaning, and related units and conditions must not be read separately from the body.

When adjusting size, apply the document-wide criteria for each body level. Do not enlarge or reduce only the same level in a particular slide or box. If a common size changes, check every slide that uses that level.

When it is difficult to maintain semantic distinction and readability, simplify the structure or divide the slides at units where meaning is complete. If slide-count or output constraints make resolution impossible, state the conflicting constraints and remaining issue. Confirm readability at the actual delivery size.
<!-- /criterion -->

<!-- criterion:c0009 -->
## 9. Connect semantic levels within a slide to document-wide text sizes

Determine semantic hierarchy within each slide's body. First distinguish what is the higher-level concept and which items and explanations belong below it. Do not determine body text sizes by constructing a hierarchy among concepts across the whole document or by judging which slide's topic is more important.

Connect the levels determined on each slide to sizes shared across the document. Within a slide, express a higher level larger than a lower level, and make the difference between levels discernible on the actual screen. Text at the same level uses the same size even when it is on a different slide or in a different box. The number of levels and actual size values are set in the task specification; do not force a level that a slide does not need. If values have not been set, the author selects them based on delivery purpose, screen size, and content volume, then records them as the application standard.

| Situation | Basis for setting size |
|---|---|
| Different concepts on different slides occupy the same body level | Apply the same size without comparing the concepts' relationship or importance. |
| The same concept is used as a higher-level grouping on one slide and a detailed explanation on another | Apply the size appropriate to its level within each slide. |
| Text at the same level is long or differs only in form, such as a sentence versus a word | Keep the same size and adjust through width, line breaks, alignment, and arrangement. |

Do not determine a semantic level merely from the form of being a table header or bold. Base it on the actual role it plays in that slide's body. Classify table values and units by their meaning and reading role as well; do not rename a level as lower merely to fit content in smaller type. Manage size criteria for headlines, introductions, and sources separately from body levels.

Make the roles of higher-level area titles, column titles, lower-level titles, and body values visible. Distinguish them by adding background contrast, dividing lines, or boldness to size based on semantic level, while using the same emphasis treatment consistently for the same role within the document. Distinguish table headers from the first data row, and do not layer further emphasis when the distinction is already sufficient. Do not rely only on differences in a specific color.

Adjust if hierarchy is reversed or blurred on the actual screen even when level names or style settings are correct. Check size consistency and the validity of semantic-level classification separately.
<!-- /criterion -->

<!-- criterion:c0010 -->
## 10. Align text according to its form and reading purpose

Choose alignment according to the content form of the relevant block and the reading or comparison the reader performs. Even at the same semantic level, sentences and short labels may use different alignment.

| Content and reading mode | Basis for choosing alignment |
|---|---|
| Continuous sentences, long explanations, or multi-line evidence | Use alignment that makes it easy to read from the beginning of each line. Left alignment is usually appropriate. |
| Short labels, independent words, or a list of similarly sized words | Consider whether center alignment enables faster recognition of the grouping and comparison targets. Do not require it merely because the content is words. |
| Numbers whose magnitude is compared | Align the baseline needed for comparison, such as digit places or decimal points. Standardize units and notation. |
| Titles and explanations, table headers and values | Choose alignment appropriate to each role while preserving the correspondence between titles and content. |

Choose horizontal and vertical alignment separately. Centering a short label within a cell and aligning the starting line of a long explanation to the top may suit different reading tasks. Within the same comparison, standardize the alignment basis for items with the same role, form, and reading purpose.

Vertical centering is a choice that changes position within a cell. It does not justify excessive box height. When line breaks or content volume changes, recheck alignment and row-column correspondence.
<!-- /criterion -->

<!-- criterion:c0011 -->
## 11. Verify the source, wording, and visual expression separately

When comparing against the source, check that key concepts, figures, conditions, subjects, and relationships are preserved. On the screen, read separately the relationship stated by the actual wording and the relationship indicated by the arrangement, shape, and symbols, then check that they agree. Correct the expression if wording states correlation but a symbol implies causality, or if independent alternatives appear to be consecutive stages.

First verify the composition method on representative slides, then review the entire document after expansion. Titles, groupings, hierarchy, and flow must be readable without the author's explanation. When changing a common size or style, recheck every affected slide type.

In the final delivery format, inspect line breaks, contrast, dividing lines, backgrounds, connection targets, and page breaks. Check versions that omit some elements so they do not leave an empty space or broken reference. Also check whether the screen actually reviewed and the document to be delivered represent the same content.

Successful rendering, no overflow beyond the page, and the author's declaration of completion do not replace quality review. Retain evidence from source comparison and screen review, and distinguish items that were not verified from items whose judgment is ambiguous. After correcting remaining issues, recheck, or deliver with unresolved limitations stated.
<!-- /criterion -->
