# Natural-Language Query Orchestration

Step 12 connects the local Qwen interpreter to the deterministic analytics and
anomaly engines. The model never calculates a result or writes SQL. It produces a
validated request, and application code executes that request against the read-only
SQLite snapshot.

## Request path

1. Read the current ticket snapshot and resolve the selected reference clock.
2. Send the question to `qwen2.5:3b` through the two-stage intent and extraction
   flow in `llm.py`.
3. Apply literal-constraint safeguards. Explicit categories, priorities, statuses,
   metrics, periods, thresholds, groupings and ranking direction override omissions
   or conflicting model fields. An unstated time filter is removed.
4. Validate the compiled request with the strict Pydantic execution contract.
5. Route analytics requests to `execute_analytics` and anomaly requests to
   `detect_anomalies`.
6. Format a concise answer from the typed deterministic result. The model does not
   generate the final answer.

Clarification and unsupported intents return the model's validated explanation
without running an analytics query. Model transport, timeout and structured-output
errors remain typed so the API can map them to clear responses in a later step.

## Response contract

`NaturalLanguageQueryResult` returns:

- the normalized original question;
- a deterministic human-readable answer;
- the validated interpretation;
- the complete typed analytics or anomaly result, when execution occurred;
- the resolved reference clock and any warnings.

Relative date answers show the inclusive start and exclusive end of the applied
range. Answers based on unresolved ticket age show the reference timestamp. Aggregate
answers include both the number of matching tickets and the number of non-null values
that contributed. Ranked answers retain ties at the winning boundary.

## Verified assessment outputs

The final live run used the supplied 500-row CSV, its dataset reference time of
`2024-04-05 00:00`, Ollama, and `qwen2.5:3b`:

| Question | Verified result |
|---|---|
| How many tickets are currently open? | 111 tickets |
| Which agent resolved the most tickets this month? | AGT-07 with 1 ticket, using resolved time from April 1 through April 5 |
| Show me all Critical tickets not resolved within 12 hours. | 34 tickets, with the dataset reference time shown |
| What is the average customer rating for Technical category tickets? | 3.7403846153846154 from 104 ratings across 152 matching tickets; displayed as 3.74 |
| Are there any anomalies in resolution times this week? | TKT-108 at 119.7 hours, above the global 48.15-hour IQR fence |

Five additional regression questions also passed end to end:

| Capability | Question | Verified result |
|---|---|---|
| Multiple priorities | How many High or Critical priority tickets are there? | 189 |
| Filtered mean | Find the mean resolution time for Billing cases. | 16.33465346534654 hours from 101 values |
| Filtered list | Show me open Technical tickets. | 30 tickets, with no invented time filter |
| Grouped metric ranking | Which category has the highest average response time? | Technical at 2.6697368421052627 hours |
| Relative created date | How many tickets were created last month? | 188 |

## Verification

- Deterministic orchestration integration tests cover every result type,
  clarification, unsupported requests, serialization, custom-reference warnings and
  answer formatting.
- Unit tests deliberately provide weak model plans and verify that explicit grouping,
  metrics, statuses and the absence of temporal language are preserved.
- The final opt-in live suite passed all 34 checks against the installed local model,
  including semantic completeness, quoted-literal isolation, and safe clarification.
