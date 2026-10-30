# Case 3 handoff (read-only audit)

Case 3 is owned by the collaborator. This branch does not modify its task card, fixture, Gold, Oracle, prompts, or case-specific adapter.

The two historical v1.0.4 full model runs both failed joint Oracle and both had postscore lifecycle errors. The Shared run showed wrong-window input; the Isolated run had A's HTML fix and B's browser check, but B's correct QA note remained unsaved at the 25-step limit. The later v1.0.5 adapter change records a dirty Text Editor buffer instead of letting the close/reopen attempt obscure the saved-file score; historical runs remain frozen. The request-level Actor tool allowlist added in the common relay is available to future Case 3 runs through the generic runner flag, but a new Case 3 pair should be versioned by its owner and validated in both topologies.

The common postscore LibreOffice recovery added here runs only after both Actors and Oracle finish. It does not alter Case 3 task semantics or Actor-time GUI scheduling. The owner should check whether its own Text Editor reopen path needs a similarly explicit saved-byte recovery policy before claiming complete end-to-end validity.
