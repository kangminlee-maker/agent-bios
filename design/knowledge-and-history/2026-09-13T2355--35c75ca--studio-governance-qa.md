---
created_at: 2026-09-13T23:55:44+09:00
head: 35c75ca
kind: review
status: finite-prototype-paths-verified
subject: 2026-09-13T2336--35c75ca--studio-governance-prototype.html
---

# Governance prototype QA and coverage

## Verified subject

The dated [prototype source](2026-09-13T2336--35c75ca--studio-governance-prototype.html)
matches the displayed conversation fragment byte for byte: 41,159 bytes;
SHA-256 `e4cf1df066de167bb026af27d845e6427c300666eb9c0cfed2e70c9864d48737`.
It uses the prior Studio visual language with four content areas plus Review,
Team/access and Operations. Account switching is an explicitly fictional test
harness, not a product mechanism for becoming another principal.

The source was rendered through the visualize wrapper and exercised in
headless Chromium, with actions and assertions scoped to its sandboxed iframe.
The source is an HTML fragment; the skill's `scripts/render.py` wraps it for
standalone inspection. No network, provider or agent operation is performed by
the fragment itself.

## Completed interaction groups

Twelve grouped UI checks passed:

1. Contributor cannot execute publication; the requester and their agent cannot
   approve; the content reviewer can approve but cannot execute; a separate
   operator publishes, requests separate adoption, and starts a new task only
   after adoption approval/execution.
2. Access management alone cannot open a source body. A grant request needs a
   separate governance approval. Granting environment publication does not
   remove that environment's content-approval requirement.
3. Revoking the content approver's environment-review grant invalidates that
   person's approval for a pending publication; execution is unavailable.
4. Weakening the environment approval policy uses the current governance
   approval requirement. Once changed, a request under the earlier environment
   policy cannot execute without a new review request.
5. A contributor explicitly granted environment-review permission still cannot
   count their own approval. This separately tests independence beyond a missing
   approval grant.
6. Offline execution leaves shared state unchanged. A simulated lost response
   shows an unknown result; querying the same operation receipt resolves it
   once, without exposing a duplicate execution action.
7. A simulated changed base preserves the candidate and reports conflict; it
   does not silently publish.
8. A knowledge revision requires body, condition and question inputs. Publishing
   source version 8 leaves the environment's source reference at version 7.
9. A proposed memory record is not displayed as accepted before review and
   execution. After acceptance it appears as an accepted event, without claiming
   to run the full production current-state reducer.
10. A pre-authorized suspension immediately blocks new use. Resuming requires
    a separate approved operation. Previously delivered context is not erased.
11. Rejection preserves its stated reason. Revised input creates a new request
    with no inherited approval. The requester can withdraw the new request.
12. At 320px outer width, publication and Team adoption complete. Approval,
    environment, access, operations and knowledge screens have no horizontal
    overflow at the actual 288px fragment width inside wrapper margins.

Desktop inspection used 1,024px width. Light overview and dark approval screens
were visually inspected. The dark product background resolved to
`rgb(24, 30, 27)` and its text to `rgb(231, 239, 233)`. Browser page errors: zero.

## Defects corrected during inspection

Review visibility was restricted by request class; governance-only accounts
cannot inspect source review bodies and ordinary readers cannot inspect
governance request detail. Source candidates gained exact base-version checks.
Uncertain results retain their request-bound effect until receipt recovery;
the mock refuses another write while such a result is unresolved. The current
task indicator was clarified as the most recent virtual task.

The preview server captures source when started. One early assertion inspected
the earlier server snapshot after source changes; that server was restarted and
the governance checks rerun on the corrected fragment.

Input blur initially rerendered a text field's enclosing screen before a
clicked button received its click event. Text inputs now update local drafts
without replacing that button on blur. Source validation/publication, memory
acceptance, suspension/resume, rejection/resubmission and the narrow publication/
adoption path passed on the final source after this correction. The other
governance checks preceded this isolated input-event fix.

## What this evidence does not establish

These are finite local UI fixtures, not security enforcement tests. Buttons and
client checks are intentionally inspectable; they cannot protect a real
provider. No real identity, grant, source permission, reviewer authenticity,
publication/adoption, durable receipt, host delivery or agent behavior is proven.
Grant expiry is a displayed fixture assumption, not a tested live clock or lease.
The prototype's independent-review case has the same requester and accountable
author; the separately submitted-author case is a required provider acceptance
test in the governance design.

Knowledge form checks cover required inputs only, not domain truth or onto
lens validation. Memory demonstrates proposed versus accepted events, not full
causal closure or state reduction. In an unknown-result case the fixture stores
the committed effect in its virtual receipt and reveals it on recovery; this
does not simulate an independent server or a concurrent second client.

All previously deferred workflows are covered by the [screen contracts](2026-09-13T2338--35c75ca--studio-complete-screen-contracts.md).
Not every workflow has an interactive implementation in this fragment. Full
graph/form editing, search, derivatives, bulk import/export, ownership transfer,
retention/deletion, provider setup, and child/current-context recovery have
screen/input/authority/success/failure/acceptance contracts there. They require
their corresponding prototype or provider tests before claiming executable
coverage. They are not deferred from design scope.

No shipped runtime code changed for this design. The full product parity suite
was not rerun for these design artifacts.
