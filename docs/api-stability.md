# API stability policy

This policy applies to the documented HTTP API from 0.6.0 onward. Surgite follows semantic versioning: incompatible API changes require a major release.

## Stable within a minor release

- Documented route paths, methods, request fields, status codes, and `operationId`s.
- Response top-level types and documented fields. New optional response fields may be added.
- Error responses shaped as `{"detail": "..."}`.
- Documented authentication, session-cookie, bearer-token, and `Retry-After` behavior.

## Not a compatibility promise

Default values, human-readable error text, response ordering, internal identifiers, logs, undocumented headers, health-check implementation details, and UI routes may change in a minor release.

## Deprecation and major upgrades

We announce deprecations in [CHANGELOG.md](../CHANGELOG.md) and retain them for at least one full minor release. For example, a feature deprecated in 1.4 is not removed before 1.6. A major release includes migration guidance and retains the previous major version on its published support terms.

We do not remove documented fields or make silent breaking wire-format changes in patch releases. Security fixes may narrow unsafe behavior; see [SECURITY.md](../SECURITY.md).
