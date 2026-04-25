# Project Brief

This note captures the initial project context and some informal discussion.

## Requirements

- The system must store scanned document metadata in SQLite.
- Search results shall include a snippet from the matched document.
- The API is required to reject unsupported task types with a 422 response.

## Acceptance Criteria

1. The task runner must return warnings when no matches are found.

This paragraph describes rollout expectations and should stay as general background rather than a requirement.

## Constraints

- The prototype must remain localhost-only and single-user.
