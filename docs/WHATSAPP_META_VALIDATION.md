# Meta WhatsApp integration validation

Issue: [#45](https://github.com/sami77337/khaled-badran-clinic/issues/45).
Branch: `feat/production-whatsapp-cloud-api`.
Local validation date: 2026-09-10.

## Implementation

- Opt-in Meta Cloud API transport, environment-only configuration, and Django checks.
- Authentication OTP and neutral consultation-reply templates using the existing
  sender contracts and website authorization routes.
- Signed webhook with Arabic/English menus, website CTA routing, staff handoff,
  shared-cache coordination and receipt-based retry handling.
- After-commit booking confirmations and a reminder command that rechecks
  eligibility under PostgreSQL row locks before recording provider acceptance.
- Callback log filtering, private/no-store responses, bounded parsing, strict
  timestamps and website-origin validation. Provider diagnostics contain no
  request bodies, credentials, recipient numbers, or medical text.

No new dependency or model migration was introduced. The local database was
backed up under the ignored `.cache/` directory before applying the existing
`patients.0007_transient_consultations` migration, which was pending locally.

## PostgreSQL compatibility fixes

The broader database validation identified two existing incompatibilities:

1. Confirming appointment cancellation for a closed clinic day selected related
   optional visit types while locking all joined tables. PostgreSQL rejects a lock
   on the nullable side of an outer join. The query now locks only appointment
   rows, matching existing booking-operation locking.
2. Direct `response.close()` calls in media tests fired Django's request-finished
   database cleanup inside the enclosing test transaction. This closed the
   PostgreSQL connection and caused cascading failures. Tests now use Django's
   test-client cleanup wrapper through `close_test_response`; files still close
   and other request-finished receivers still run.

These fixes preserve the existing permission, ownership, cancellation confirmation,
publication consent and private-file assertions.

## Recorded checks

- Initial SQLite/LocMem full suite: 892 tests, passing with one optional skip.
- Final complete suite after all fixes on PostgreSQL 16 and Redis 7: 899 tests
  in 406.450 seconds, zero failures, one optional skip. The skipped check requires
  an explicitly supplied external owner-review dataset; the synthetic review,
  browser, media, booking, guest-access and WhatsApp checks ran successfully.
- Final WhatsApp suite on isolated PostgreSQL 16 and Redis 7: 54 tests, all passing.
- WhatsApp plus affected PostgreSQL compatibility regressions: 68 tests, all passing.
- Separate database workers verified reminder exclusion and persistence.
- A separate Python process verified Redis conversation locks and completed receipts.
- Django checks and migration drift checks passed.
- Local deployment smoke: 16 passed, zero failed; four development-settings warnings.
- Reminder dry run completed without sends or record changes.
- New integration files pass Ruff lint/format checks. Modified tracked Python files
  introduce no new Ruff findings compared with the branch base; older unrelated
  test files retain eight pre-existing unused-import/local findings.
- Dependency consistency (`pip check`) and Git whitespace checks passed.
- `check --deploy` reports the six expected local development configuration
  warnings. This does not represent production settings approval.

The final full-suite output is retained locally in the ignored
`.cache/whatsapp-verified-full-suite.log`. The focused provider and compatibility
results are in `.cache/whatsapp-postgres-redis.log` and
`.cache/whatsapp-compatibility-regressions.log`. These contain synthetic test
diagnostics only. Temporary test containers were removed after validation.

## Resumed branch reconciliation

The local implementation at `28d3c4a` and the remote PR implementation at
`32b1601` were developed from the same base. They are reconciled with a merge
that preserves both commit histories. The final runtime uses the tested
`meta`, `menu`, `webhook` and `booking` modules and retains the PostgreSQL
compatibility fixes described above. Superseded adapter, signal and URL modules
are removed so booking confirmations and callbacks have one execution path.

The remote existing-number coexistence requirement is preserved and linked from
the canonical setup guide. The earlier `WHATSAPP_META_CLOUD_API.md` entry point
now directs operators to that guide instead of retaining conflicting template
names and callable paths.

`start` and `ابدأ` join the existing menu commands. A regression test covers ten
AR/EN command combinations, verifies staff-handoff suppression before resuming,
preserves the selected language, and deduplicates a repeated resume event.

A supplementary CI job was prepared to run the focused WhatsApp suite against
isolated PostgreSQL 16 and Redis 7 services. Publishing that workflow change was
rejected because the signed-in GitHub OAuth credential lacks `workflow` scope.
The existing CI configuration remains in use. The proposed job is preserved in
the local `.cache/whatsapp-postgres-redis-ci.patch` and
`local/whatsapp-postgres-redis-ci` branch for a separately authorized workflow
update. Provider HTTP remains mocked; proposed CI credentials are synthetic.

Validation of the reconciled tree on 2026-09-10:

- Full suite on isolated PostgreSQL 16 and Redis 7: **900 tests in 402.127
  seconds, zero failures, one optional external-review-dataset skip**. Browser
  layout and recorder lifecycle checks also passed. Evidence is retained in
  `.cache/whatsapp-resume-merged-full-suite.log`.
- Focused SQLite/LocMem suite: 55 tests, zero failures, two expected database/cache
  concurrency skips. Both concurrency tests ran in the full PostgreSQL/Redis suite.
- Django checks, migration drift, dependency consistency and Git whitespace
  checks passed. WhatsApp lint and formatting of the two changed Python files
  passed; no dependency or migration changes were introduced.
- Added-line credential-pattern scan found no private-key material or GitHub,
  Meta or AWS access tokens. The proposed CI patch contains only explicitly
  synthetic test-service credentials.

## External activation

All provider HTTP calls in validation were mocked with synthetic fixtures. Local
PostgreSQL/Redis services were dedicated temporary containers without production
data. This evidence does not validate Meta delivery, template rendering on a real
device, business-number registration, staff tooling, or a production scheduler.

Follow [the setup guide](WHATSAPP_META_SETUP.md) for operator credentials,
approved templates, callback subscription, infrastructure configuration and
controlled live acceptance. Ambiguous provider timeouts and process failures can
still lead to duplicate delivery on retry; the adapter does not claim exactly-once
transport across Meta, the database and cache.
