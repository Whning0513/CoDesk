# Credential and Actor boundary

The v2 launcher unsets inherited provider-key environment variables and reads
the provider credential only from an owner-only mode-0600 local file. It passes
the value in the coordinator's environment; it is not a command-line argument,
fixture, Git file or intentional log field. The run-owned loopback relay gets
the provider key by environment variable. Its log records model request metadata,
not the authorization header or key.

`_run_model_actor` configures the Codex harness to remove the provider key from
Actor and MCP child environments; the separate ephemeral relay client token is
retained only to authenticate to that run's loopback relay. Actor requests are
restricted to desktop and collaboration MCP tools. The existing relay sentinel
tests check that a synthetic provider key is absent from Actor environment and
relay event logs and that the request tool allowlist is applied.

The OSWorld Docker provider constructs an explicit Guest environment containing
VM disk/RAM/CPU and runtime variables; it does not copy the coordinator's
provider key. The `.qcow2` base mount is read-only and the run-owned overlay is
separate. The case installs only the public asset, report and brief; the private
scorer module and Gold are not mounted into the Guest. Same-user Shared desktop
permissions are not a security sandbox.

This is a code-and-test audit. No v2 Guest or Actor run has yet demonstrated the
runtime boundary; the first real smoke/Pilot must verify the container's
configured environment and the Actor request/tool records without printing
credential values.
