# Hevy website API client

`HevyAppClient.web` exposes the website API alongside the existing public API.
Use it for richer workout records and website management operations. It shares
one existing `HevyWebSession`, including credential refresh and HTTP errors.
The [API audit](../research/hevy-web-api-audit.md) records the first-party evidence
and distinguishes live-tested reads from source-only management contracts.

## Read set completion timestamps

Use the application's existing configured `HevyAppClient` as `client`:

```python
workout = client.web.workouts.get(workout_id)
for exercise in workout.exercises:
    for workout_set in exercise.sets:
        print(
            exercise.title,
            workout_set.id,
            workout_set.completed_at,
            exercise.rest_seconds,
        )
```

`completed_at` is a timezone-aware `datetime`, or `None` when unrecorded. The
original millisecond precision is retained. A malformed or naive timestamp
raises validation errors rather than silently becoming missing data.
`rest_seconds` is the configured rest setting for that exercise, not a measured
interval. No actual rest-start/end events were found during the audit.

Workout `name` and Unix-second `start_time`/`end_time` follow the website contract.
They are not silently renamed or converted into the public API's `title` and
ISO time fields. Website sets use `indicator` instead of public `type`.
`personal_records` maps to the server's `personalRecords` field.

Response models preserve unknown fields, including nested workout/exercise/set
metadata. To serialize using server field names and JSON-compatible timestamps:

```python
payload = workout.model_dump(mode="json", by_alias=True, exclude_unset=True)
```

This is a parsed representation, not byte-identical raw JSON. Do not submit a
read model as a write request without constructing the appropriate request body.

## Page and backfill workouts

```python
page = client.web.workouts.list(username, limit=20, offset=0)
for workout in client.web.workouts.iter_all(username, page_size=20):
    consume(workout)
```

The iterator continues until an empty page, even when the server returns fewer
records than requested. It advances by the number received, deduplicates IDs,
and raises `HevyAppAPIError` if a page makes no progress. HTTP and validation
errors propagate; they are not interpreted as the end of history. Offset
pagination is not a server snapshot, so concurrent edits can still move records.

`client.web.workouts.batch(start_index)` supports the website export endpoint.
Its cursor is a workout `index`, not a page number; advance using the final
record's index plus one. There is no automatic iterator for this separate
protocol. Web exercise-history/statistics endpoints omit completion timestamps;
use full workout endpoints for timestamp collection.

## Resource interface

| Resource | Methods |
| --- | --- |
| `web.workouts` | `get`, `list`, `iter_all`, `batch`, `calendar`, `metrics`, `comments`, `likes`, `comment`, `delete_comment`, `like`, `unlike` |
| `web.routines` | `get`, `get_shared`, `create`, `update`, `delete`, `copy`, `move` |
| `web.folders` | `list`, `get_shared`, `create`, `update`, `delete`, `reorder` |
| `web.exercises` | `list_custom`, `units`, `create`, `update`, `delete`, `history`, `sets` |
| `web.users` | `profile`, `search`, `following`, `follow_counts`, `feed`, `follow`, `unfollow` |
| `web.preferences` | `get`, `update` |
| `web.webhooks` | `get`, `subscribe` |

The client covers training data, routine/exercise/folder management, basic
social operations, preferences and webhook configuration. It does not wrap all
94 audited website helpers: billing, signup/password changes, account deletion,
API-key management, OAuth, coach invitation actions and routine sync-batch
protocols remain outside this interface. Existing authentication owns login-token
refresh. Existing public resources and legacy web deletion methods remain
compatible.

Rich workouts, routine reads, folders and custom exercises have dedicated models.
Less-established read schemas use `WebRecord` and preserve their server fields;
for user search/following/feed, the shared session's `results` envelope is retained
when the server returns a top-level array. Routine exercise blocks likewise
preserve prescriptions without requiring performed-set identities/timestamps.

## Management operations

Writes accept explicit website-format dictionaries where a complete request
schema has not been established. They preserve the audited envelope differences:

- Routine create/update wrap the body in `routine`.
- Folder creation wraps it in `folder`; folder update forwards the body directly.
- Routine moves wrap records in `locations`; folder ordering uses `reorders`.
- Custom exercise create/update wrap the body in `exercise`. Updates require its
  string `id` and use that same ID in the URL.
- Routine/folder writes include `sendSyncEventToMobileApp=true`.
- Successful responses without a body are accepted by the web session.

Inner location, reorder and copy body schemas remain caller-owned web contracts;
these methods do not guess missing IDs or fields. The audit's source-only writes
were tested against fake HTTP boundaries, not executed against the live account.
Custom exercise deletion does not migrate existing references. Apply the
[existing migration/review workflow](hevy-truecoach-workflow.md) first.

Creating the client makes no network requests. Writes, social messages and
webhook subscriptions happen only when their explicit methods are called.
`web.webhooks.get()` propagates a 404 because its meaning was not established.
Its response can contain a secret token, so do not log the returned dictionary.
No webhook payload/delivery guarantees have been verified.

## Authentication and validation

The composite client uses its existing `web_api_key` and optional
`web_credentials_path`. The rotating credential file takes precedence over a
legacy token. The standalone `HevyWebClient(session)` accepts the same session
interface for dependency injection. It never falls back to public API credentials.

Validation covered API request contracts, missing and malformed timestamps,
unknown-field preservation, overlapping/stalled pagination, empty mutation
responses and existing web-auth refresh behaviour. All 450 exported workouts,
64 routines and 249 live-audit custom templates parsed successfully; all 12,204
recorded completion timestamps survived parsing. A live smoke test through the
new client compared one workout's 19 set IDs and timestamps with the export and
read a workout page, a routine and folders.

This adds API client capabilities only. It does not schedule collection, modify
the database schema or enable automatic writes. The web contract is undocumented
and may change independently of the public API.
