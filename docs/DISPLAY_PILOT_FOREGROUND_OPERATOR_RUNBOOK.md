# Display Pilot Foreground Operator (DP4-B candidate)

This is a local-only candidate, not a live operational procedure. `setup` and
`verify` are JSON-only, bounded local checks. `start` is intentionally blocked
in DP4-B. The operator accepts only the fixed HGW selector and HAG target,
uses fakeable boundaries, writes request-scoped artifacts, and never grants
approval from generated text. It does not scan broadly, run in the background,
recover uncertain state, or perform GitHub writes.

The candidate's verification commands are restricted to `python -m pytest`
with repository-relative arguments. Any future live use requires a separately
reviewed operational package.
