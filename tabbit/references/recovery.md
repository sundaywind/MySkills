# Recovery

Use this reference after pending or interrupted work, an uncertain mutation,
transport loss, a missing receipt, or finish failure. Keep the same task name
and request identity until evidence establishes the outcome.

## Read, do not resubmit

```text
<launcher> receipt --task NAME --request-id ID --wait-ms 60000
<launcher> diagnose --task NAME
```

`mutationState` records the submission's declared side-effect class.
`mutationState: "none"` means it was submitted with `--read-only`;
`mutationState: "possible"` means it was not classified read-only and may have
changed browser or application state before stopping. It does not prove whether
a side effect occurred.

`queued` or `running` means wait on the same receipt. `failed` is safe to retry
only when its mutation state and visible application state exclude an uncertain
side effect. `interrupted` or `mutationState: "possible"` requires a read-only
verification before any retry. Never change request IDs, task names, instances,
or browser backends to evade pending work.

A client-side wait ending is not proof that evaluation failed. `TASK_BUSY`
before the hard deadline likewise means wait on the existing receipt.

## Deadline and transport boundaries

When a hard deadline reports `taskTerminated: true`, only that task executor is
terminated; its live tabs and group are retained. Resume that exact group in a
new read-only task, inspect externally visible state, and retry a mutation only
when evidence proves the original operation did not occur.

After a transport close in the same Browser generation, reconnect through the
stable launcher and read the original receipt. The CLI does not replay a fully
sent request on EOF. If the task or receipt is missing, or the response is
`OUTCOME_UNKNOWN`, the receipt lane cannot prove the mutation outcome. Create a
new read-only task, inspect externally visible state, and never replay the
possible mutation merely because the old receipt is unavailable.

For an existing resource receipt, read only the bounded slice required for the
decision:

```text
<launcher> resource --task NAME --resource ID --offset 0 --max-bytes 32768
```

If finish is interrupted, inspect the task or run `diagnose --task NAME` before
deciding whether another finish is necessary.
