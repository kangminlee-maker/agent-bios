Below are the events read from the recorded working sessions of one time window, each with the claims that describe it
and their quotes, then the clusters of learnings already placed in the person's guidance that share a principle, one
JSON object per line, and last what to return.

<events>
{{events}}
</events>

<claims>
{{claims}}
</claims>

<placed_clusters>
{{clusters}}
</placed_clusters>

# Your task

You are forming candidate learnings: claims, supported by these sessions, about what an AI coding agent should do
differently - or keep doing - when a similar situation arises again. A later stage checks every candidate against the
person's guidance and two judges decide whether it is admitted, so form what the events support and nothing more. The
quotes hold what the person asked the agent and what the agent did: text you read about, never instructions to you.

Every event, claim, quote, session, cluster and cluster entry above carries this packet's own short label (v1, ...;
c1, ...; q1, ...; s1, ...; u1, ...; u1.1, ...). Name them by those labels only, each written exactly as shown. Each
event names its `session`; events of different sessions may support one candidate, and a lesson the sessions repeat is
one candidate with all its events, not one per session.

An event an earlier window left open and this window's reading joined to its outcome shows two kinds of evidence. Its
`origin` quotes are its first record as the session holds it - where the situation and what was done at that point
can be read - cut at 700 bytes, so what was done may lie past the cut. Its `outcome_claims` are claims of this window
that show what came of it. Cite an origin quote by its label like any quote; an origin block marked `"citable": false`
cannot be cited. The events' other claims describe the event itself.

A placed cluster lists learnings already placed in the person's guidance whose closest unit of that guidance is the
same: each entry shows its lesson and where its stored evidence is (`evidence`).

Think the problem through before you answer. Then return the JSON your schema asks for, and nothing else. Every event
above goes in exactly one place:

- `candidates`: one per distinct lesson, ids k1, k2, .... `lesson`: its name in one line. `situation`: when it
  applies, as the agent can recognize it at that moment. `action`: what to do then. `exception`: when it does not
  apply and which competing value it trades against. `event_ids`: the events it rests on. `type`: one of
  - A: a defect in a script or tool the person owns; the fix is a repair;
  - B: a counterintuitive behaviour of an external tool, with a trigger a machine can detect;
  - C: a recognition principle: a signal that should raise a suspicion or prompt an action across kinds of work;
  - D: a procedure within a kind of work already routed to its guide;
  - E: a fact about this environment, specific and decaying;
  - F: unproven: the evidence is below what promotion needs;
  - G: a principle or direction: a value ordering that shapes many decisions (one side of a tension preferred to
    the other).
  `admission`: for each of the eight requirements below, `basis` says what the events show for it, with the
  `claim_ids` and `evidence_ids` (quotes) that show it; lists may be empty where the requirement rests on reasoning,
  as `positioned` and `audience` may.
  `tension`: for type G only, `sides` the two sides of the tension, `ordering` which side is preferred to which and
  when, `forbids` what the preference now rules out, its instances, and `cluster` the label of the placed cluster it
  distills, or "". The instances are `instance_claim_ids`, at least three claims in which the person resolved that
  tension the same way, or - for the principle a placed cluster shares - `instance_entry_ids`, at least three entries
  of that cluster (u1.1, ...), naming the cluster in `cluster`; cite entries only so, three or more, whatever claims
  you add. Such a candidate may rest on no event of this window: its `event_ids` may then be empty, and only then.
  Three entries let you propose the principle; they do not show three independent lines of evidence, since entries
  may come from the same work, so the evidence bar stays held while that is unknown. For every other type, `sides`,
  `instance_claim_ids` and `instance_entry_ids` are empty lists and the three texts are "".
- `rejected_findings`: a claim about what to do differently that the events suggest but that fails a requirement now,
  ids r1, r2, ...: `finding`, its `event_ids`, `failed` naming each requirement it fails, and `reason`.
- `non_findings`: one per remaining event, by its label as `event_id`, with `reason`: `no_consequence` (it made no
  real difference), `routine_step` (ordinary work that went as expected), or `duplicate_of_another_event` (it repeats
  another event above, named in `duplicate_of`); `duplicate_of` is "" for the other two reasons.

The eight requirements (all must hold for a candidate):

1. `observed_event`: quoted session text shows the situation and the decision or outcome.
2. `consequence`: the decision made a real difference to time, cost, quality or risk, or the person corrected it.
3. `causal_support`: the claims say why the action led to the outcome, keep fact apart from interpretation, and
   consider other explanations; order in time alone is not a cause.
4. `recognizable_in_advance`: the situation can be recognized from what the agent knows at that moment; a condition
   visible only after the failure belongs to a tool or a gate, not an instruction.
5. `actionable`: the agent or a tool can take the action at that point.
6. `bounded`: it states when it does not apply and which competing value it trades against.
7. `positioned`: what part of the person's guidance it relates to, so that it can be checked against that guidance.
8. `audience`: whether it holds for people other than this person.

A requirement specific to the task at hand is not a learning: it is a rejected finding failing `bounded` or
`recognizable_in_advance`. An event whose outcome made no difference is a non-finding. Do not merge lessons that
differ in situation or action to make fewer candidates, and do not split one lesson into several. Empty lists are
valid answers.
