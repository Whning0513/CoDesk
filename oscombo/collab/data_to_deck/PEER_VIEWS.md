# Optional immutable peer views

`SavedArtifactBridge` can expose a saved role output through a separate,
revision-specific read-only file in either desktop topology. This feature is
disabled unless the coordinator supplies `peer_view_dirs`, for example
`{"A": "views/B"}`. The case setup creates that directory in **every Guest**
before the bridge starts. It is one directory on a Shared Guest and one in each
Guest for Isolated. A missing directory is a bridge failure, not a task failure.

For A's `outputs/agent_A/forecast.ods`, a committed revision 1 is available to B
at the task-root-relative `views/B/forecast-r000001.ods`. The public
`list_saved_artifacts` metadata includes `peer_view_path`, `revision`, `sha256`
and `delivered`. The bridge writes a temporary file in the same directory,
sets mode 0444, creates the revision with an exclusive hard link, verifies its
bytes and mode, and only then atomically publishes the metadata. An existing
revision is accepted only if bytes and mode match; otherwise it is never
overwritten and a conflict is recorded. A's original output remains writable.
Earlier peer view files and host revision archives remain available.

`events.jsonl` records `revision_pending`, `peer_view_verified`,
`peer_view_error`, and `peer_view_conflict` in addition to normal revision and
transfer events. A host-only pending journal records the archived SHA before
copying so an interrupted publication can be retried even if the peer's
ordinary copy advanced before the view failed. After a later save, a conflicting
uncommitted archive is retained and the next available revision number is used.
The coordinator must treat an unexplained bridge failure as an infrastructure
problem, not as an Actor task failure. A successful final sync does not prove
there were no earlier errors; preserve and review the event/error history.

With peer views enabled, a nonblocking host file lock permits one bridge writer
per run root across processes. `stop()` joins the worker, performs final sync,
then releases the writer lock even if that sync fails. If the worker does not
stop, the lock remains held. `close()` is for an already stopped or never-started
bridge; process death releases the OS lock. A replacement may use `resume=True`
only after the old writer has exited or closed; ownership and committed archive
hashes are checked before accepting state. This lock protects files and metadata
only and is never a GUI input lock.

A published view is rechecked on subsequent syncs. If it becomes inaccessible,
has unexpected bytes, or loses mode 0444, its committed metadata is marked
`delivered=false` and an error is recorded; after an external repair the same
bytes can be reverified. An Actor already awakened before a later corruption
cannot be recalled, so such a run requires infrastructure review. The 0444 mode
discourages accidental writes; Shared Actors run as the same Ubuntu user, so it
is not a role-level security boundary. Actor behavior and actual GUI reading
still require independent trace review.
