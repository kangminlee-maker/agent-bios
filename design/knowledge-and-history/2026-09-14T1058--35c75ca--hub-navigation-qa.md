---
created_at: 2026-09-14T10:58:30+09:00
head: 35c75ca
kind: review
status: navigation-prototype-verified
subject: 2026-09-14T1047--35c75ca--studio-hub-and-spoke-prototype.html
---

# Studio hub navigation QA

The [HTML fragment](2026-09-14T1047--35c75ca--studio-hub-and-spoke-prototype.html)
is 28,069 bytes; SHA-256
`ddb5a1627a9b2de5f3ee6a1be0860eadd95ccbc91cec4213b9f28ff8f1b35c87`.
The dated repository copy matches the displayed conversation source.

The visualize 1.0.37 wrapper and headless Chromium were used. Locators and
assertions were scoped to the sandboxed iframe. Five grouped checks passed:

1. Five spokes expose all W01–W10 screen families; five hub connectors render.
2. Work → evidence → back returns to W01. Recipient → recovery → back returns
   to W09, preserving the displayed origin and navigation trace.
3. First-time, invitation, direct-review and existing-host entry examples route
   correctly. Returning home from an invitation preserves the original first-
   visit state. The invitation view does not offer the member-management links.
4. W02 retains an explicit Instructions source-editor route explanation.
   Environment composition → review → back returns to that composition screen.
5. At 320px outer width, the map/branch and all four entry examples have no
   horizontal overflow at the actual 288px iframe content width.

The light desktop map and dark known-Team entry were visually inspected at
1,024px width. The dark product background resolved to `rgb(25, 31, 27)` and
text to `rgb(230, 238, 232)`. Page errors: zero. A selector initially matched
only the title of a multi-line invitation button; the assertion was rerun using
its actual action identifier. This was not counted as an application defect.

The prototype preserves a local route stack and visible origin, not durable
real drafts or request state. It shows screen roles and navigation; it does
not authenticate users, enroll members, approve changes, manage actual Teams,
transfer material or activate a host. Node selection does not prove production
authorization. The four arrival choices are a design-test harness.

Source editing is represented by a route explanation; full editors remain
in the prior wireframe/design families. The small-screen map intentionally
uses a labeled hub-and-spoke list without connectors to avoid misleading line
crossings. Browser rendering does not establish actual TUI behavior, complete
accessibility or human comprehension. Optional host design controls were not
exercised by this run.

No shipped runtime source or actual Team data changed. Full product parity was
not rerun for these navigation artifacts. Direct terminology, link, whitespace
and exact-copy checks cover the new untracked files explicitly.
