# Hevy web API audit

Verified 5 September 2026. The website API exposes useful training data that the
public developer API omits, especially set completion timestamps, workout rest
settings, stable set IDs and PR metadata. It also supports custom-exercise edits
and deletions, routine/folder management, social functions and account settings.
These are two different contracts, not interchangeable API versions.

## Scope and evidence

The comparison uses the current [official public OpenAPI](https://api.hevyapp.com/docs/swagger-ui-init.js)
and the API client shipped in [Hevy’s website bundle](https://hevy.com/_next/static/chunks/pages/_app-5fa98d71810f0958.js).
The website build ID was `MbSY8lILUmrvmTUrjhBma`. The public schema documents
22 operations across 14 paths. The main web client contains 94 endpoint-calling
wrappers, including authentication, billing and onboarding. That count is not a
claim to have discovered every endpoint in Hevy’s backend.

This audit made 17 web GET requests: 16 returned HTTP 200 and the webhook
subscription GET returned 404. Three public GET requests returned HTTP 200 for
raw workout, routine and exercise-template comparisons. Earlier timestamp checks
in this session compared four workouts against the iPhone backup. No workout,
routine, preference, subscription or social data was modified during this audit.
Existing web authentication may refresh and rotate its saved credentials.

Evidence labels below mean:

- **Live:** response inspected on this account.
- **Source:** first-party website calls the endpoint; operation not executed here.
- **Prior:** a separate existing repository note records a successful test.

Raw responses remain outside the repository under `/tmp/hevy-web-audit/`.
Only endpoint descriptions, field names and aggregate observations are recorded
here. Temporary files are not a permanent evidence archive. The source links
and wrapper inventory provide reproducible discovery; future website builds may
replace these URLs.

## Capabilities that add to the public API

| Capability | Website API / fields | Public API difference | Evidence |
| --- | --- | --- | --- |
| Set completion time | `GET /workout/{id}`; sets have `completed_at` | Absent from raw public workout response and schema | Live |
| Stable set/exercise occurrence IDs | Workout sets and exercise blocks have `id` | Public returns positional `index` and template ID, not occurrence IDs | Live |
| Rest setting on completed workouts | Exercise `rest_seconds` | Public workout exercise omits it; public routines already expose it | Live |
| PR annotations | Set `prs`, `personalRecords` | Absent from public workout schema and raw response | Live fields; populated examples in backup |
| Rich workout context | `apple_watch`, `wearos_watch`, `gym`, `estimated_volume_kg`, `include_warmup_sets`, `is_private`, social/media fields | Not in public read payload; public writes already accept privacy | Live |
| Biometric/geospatial containers | `biometrics`, set `geospatial_data` | Absent from public workout schema | Live fields only; no useful populated values in this account’s export |
| Bulk rich workouts | `GET /user_workouts_paged`, `GET /workouts_batch/{index}` | Public lists omit the same rich fields as public individual workouts | Live |
| Rich routine context | Parent routine, short sharing ID, ordering, program/coach IDs; exercise media/localised titles, pinned notes | Public routine schema is smaller | Live fields; some optional fields empty |
| Custom exercise edit/delete | `PUT` and `DELETE /custom_exercise_template/{id}` | Public supports list/get/create, no documented update/delete | Source; deletion Prior |
| Custom exercise metadata | `is_archived`, `priority` | Absent from public template schema | Live |
| Routine delete/copy | `DELETE /routine/{id}`, `POST /routine_copy` | No documented public delete/copy operation; copying can also be implemented by public read/create | Source |
| Folder rename/delete/reorder | `PUT /routine_folder`, `DELETE /routine_folder/{id}`, `PUT /routine_folder_order` | Public folders support read/create only | Source |
| Routine placement/order | `PUT /routine_locations` | Public routine writes already accept `folder_id`; web adds dedicated placement/order operation | Source |
| Exercise-specific units | `GET /exercise_template_units` | Not documented publicly | Live |
| Preferences | `GET /v2/user_preferences`, `PUT /user_preferences` | Not documented publicly | GET Live; PUT Source |
| Rich profile and social graph | Profiles, search, followers/following, feed, likes and comments | Public user info is only ID/name/URL | Own profile and empty workout likes/comments Live; remaining Source |
| Precomputed calendar/metrics | `user_calendar_workouts`, `user_workout_metrics`; profile weekly durations | No corresponding public routes; much can be derived locally | Live |
| Exercise statistics context | `GET /user_exercise_sets/{templateId}/{afterDate}` includes bodyweight/geospatial field slots | Public exercise history has set metrics but lacks these extra fields | Live fields, not proof of populated values |
| Webhook subscription setup | `GET`/`POST /webhook-subscription` | Not in current public OpenAPI | Source; GET 404 on this account |
| Coach/program sharing | Invite, coach, trainer program, shared folder/program endpoints | Not in public OpenAPI | Source; trainer GET returned empty object |
| Account, auth, billing, integrations | Profile/preferences updates, login/refresh, API-key management, Paddle, OAuth, Wellhub | Outside documented public training API | Source only except preference GET |

Sources: [web API client](https://hevy.com/_next/static/chunks/pages/_app-5fa98d71810f0958.js),
[public schema](https://api.hevyapp.com/docs/swagger-ui-init.js), and live response
observations recorded below. Custom exercise deletion’s prior test and existing
implementation are documented in [the deletion investigation](hevy-custom-exercise-deletion.md).

## What is already public

Do not count these as reasons to use the private API:

- Workout `routine_id`, confirmed in the raw public response. The repository’s
  current `Workout` model drops it, which caused the earlier mistaken comparison.
- Routine rest settings, notes, supersets and rep ranges. The raw routine response
  is wrapped in `routine`; the schema and write contracts support `rest_seconds`.
- Set `custom_metric`, RPE, weights, reps, distances and durations.
- Exercise history with start/end date filters.
- Basic user info and body measurements, including read/create/update.
- Workout change polling through `/v1/workouts/events`, including deletion events.
- Core workout and routine creation/update and custom exercise creation.

These conclusions use the [current public OpenAPI](https://api.hevyapp.com/docs/swagger-ui-init.js),
not just the repository’s Pydantic models. Undocumented public behaviour was not
exhaustively tested. No documented public DELETE operation exists in this snapshot.

## Timestamp and rest findings

The individual web workout endpoint exactly matched all set IDs and completion
timestamps for four backup workouts. Two had populated timestamps, 19 and 26
sets respectively; two older workouts had none in either source. A separate
`user_workouts_paged` request returned those two recent workouts with all 45
timestamps populated and matching the backup.

The tested `workouts_batch/0` response returned ten old workouts. Their set schema
included `completed_at`, but all 313 values were empty. That is not evidence the
batch endpoint removes timestamps: these are old records. The full backup has
12,204 populated timestamps across 19,574 sets, so a collector must preserve
missing values rather than invent timing for older records.

Both web exercise-history routes tested are unsuitable as the primary timestamp
source: `/user_exercise_history_paged` and `/user_exercise_sets/...` returned no
`completed_at` field. Fetch workouts instead.

`rest_seconds` describes an exercise’s configured rest duration. The audited
workout/set payloads contain no separate rest-start, rest-end, timer-skip or
set-start events. Therefore, completion-to-completion time cannot identify actual
rest independently from execution time, transitions and logging delays. This is
a finding about these payloads, not proof that no internal mobile endpoint could
hold other events.

The export contains populated `prs` on 512 sets and `personalRecords` on 371.
Those fields are also present in the live web workout response. Their detailed
semantics and agreement with UI PR calculations were not tested. Biometric
containers in the export were empty/zero and no set had populated geospatial data;
these fields offer no additional actual measurements for the examined snapshot.

## Useful read contracts and test results

All web paths below use `https://api.hevyapp.com` without `/v1`.

| Request | Observed result |
| --- | --- |
| `GET /workout/{id}` | 200; 11 exercise entries, 19 sets with completion timestamps |
| `GET /user_workouts_paged?username={ownUsername}&limit=2&offset=0` | 200; two full workouts, 45 populated set timestamps |
| `GET /workouts_batch/0` | 200; ten old full workouts, timestamp fields null |
| `GET /routine/{id}` | 200; wrapped `routine`, 17 exercise entries |
| `GET /custom_exercise_templates` | 200; 249 records, including archive/priority metadata |
| `GET /exercise_template_units` | 200; one override with template ID and weight unit |
| `GET /routine_folders` | 200; one folder |
| `GET /v2/user_preferences` | 200; nine fields, including RPE, inline timer, warmup volume and default privacy settings |
| `GET /user_exercise_history_paged?exerciseTemplateId={id}&offset=0` | 200; five workout entries, nine sets, no completion timestamps |
| `GET /user_exercise_sets/{id}/2026-06-01T00:00:00Z` | 200; nine set records, no completion timestamps |
| `GET /user_calendar_workouts/2026/9` | 200; four workout calendar entries |
| `GET /user_workout_metrics/duration/1785542400/1788652800` | 200; 23 workout-duration records |
| `GET /user_profile/{ownUsername}` | 200; 64 routine references, weekly durations, follower/profile fields |
| `GET /workout_comments/{id}` | 200; empty list on selected workout |
| `GET /workout_likes/{id}` | 200; empty list on selected workout |
| `GET /hevy_trainer/program` | 200; empty object, so populated trainer schema unverified |
| `GET /webhook-subscription` | 404; reason not established |

Website call sites establish pagination parameters and date handling in the
[exercise page](https://hevy.com/_next/static/chunks/pages/exercise/[[...exerciseTemplateId]]-a5612a1b0a936d2b.js),
[profile page](https://hevy.com/_next/static/chunks/pages/profile-6fcf287d5b3bc75e.js),
and [settings page](https://hevy.com/_next/static/chunks/pages/settings-8334ec8ddb336f1b.js).
The settings export loop advances `workouts_batch` using the last returned
workout’s `index + 1`; it is not a conventional page number. The main client uses
`username`, `limit`, and `offset` for `user_workouts_paged`.

## Webhooks: promising, not verified

The settings page reads `/webhook-subscription` and submits
`POST /webhook-subscription` with `{url, authToken}`. Its read handler expects
`url` and `auth_token` and suppresses read failures. The observed GET 404 could
mean there is no subscription, but that interpretation is not confirmed.

No webhook was registered and no event was triggered. Delivery payload, event
coverage, retry behaviour and whether timestamps are included remain unknown.
Treat a future webhook as a trigger to fetch the rich workout until proved
otherwise. Public workout-events polling already provides a documented fallback.
[Source: developer settings implementation](https://hevy.com/_next/static/chunks/pages/settings-8334ec8ddb336f1b.js).

## Suggested integration

1. Keep the public API as the documented source of workout changes and deletions.
2. Fetch each new or updated workout through `/workout/{id}` and store raw web
   JSON plus normalised set ID, exercise occurrence ID, `completed_at`, workout
   rest setting and PR metadata.
3. Backfill rich records using the verified own-user paginated endpoint. Do not
   substitute exercise-history endpoints for timestamp collection.
4. Keep web and public parsing separate. For example, public `title` is web
   `name`, public set `type` is web `indicator`, and web workout start/end times
   are Unix seconds while public ones are ISO strings. `completed_at` is ISO.
5. Preserve provenance and nulls. Stable web IDs allow timestamp enrichment, but
   test ID stability across edits before relying on them as immutable identifiers.
6. Consider webhook triggering later, after verifying registration and delivery.

The existing [web session](../../fitness_tracker/apis/hevy_app/web_session.py)
and [rotating credential helper](../../fitness_tracker/apis/hevy_app/web_auth.py)
worked for these reads. The website uses bearer access tokens, its client
identifier `shelobs_hevy_web`, and `Hevy-Platform: web`, separately from public
`api-key` credentials. No fixed rate limit or backwards-compatibility guarantee
was established. No recurring collector or integration change was implemented
as part of this audit.

## Complete discovered web-client inventory

Every row below is **source evidence**, not a claim of successful live execution.
The 94 wrappers come from the main website API client at the linked build. The
third column preserves the minified call arguments with symbolic variables to
avoid guessing parameter names. `e`, `a`, `n`, etc. refer to wrapper arguments;
see the linked source for their definitions. Some wrappers include multiple
parameters or branches.

Do not assume a GET is harmless merely from its method: the source includes
`accept_client_invite`, `become_client`, and OAuth-code actions implemented as
GETs. Those actions were not called. Billing, account deletion, API-key changes,
password/email operations, invitations, uploads and social writes were likewise
not tested.

[Source: first-party web API client](https://hevy.com/_next/static/chunks/pages/_app-5fa98d71810f0958.js).

| Website wrapper | Method | Source call arguments |
| --- | --- | --- |
| `sendSignupVerificationEmail` | `POST` | `"send_signup_verification_email",{email:a})}` |
| `signup` | `POST` | `"signup",{email:a,password:n,recaptchaToken:t,gympassUserId:i},{params:{coachInviteShortId:r}})}` |
| `signupWithVerifiedEmail` | `POST` | `"signup_with_verified_email",{email:a,password:n,gympassUserId:t,verificationCode:i})}` |
| `login` | `POST` | `"login",{emailOrUsername:e,password:a,gympassUserId:n,recaptchaToken:t})` |
| `logout` | `DELETE` | `"/auth/session")` |
| `authMigrate` | `POST` | `"auth/migrate")` |
| `signInWithApple` | `POST` | `"login_apple_web",{identityToken:a,email:n,gympassUserId:t})}` |
| `signUpWithApple` | `POST` | `"signup_apple_web",{identityToken:a,email:n,gympassUserId:t})}` |
| `signInWithGoogle` | `POST` | `"login_google_web",{code:e,gympassUserId:a})` |
| `signUpWithGoogle` | `POST` | `"sign_up_google_web",{code:e,gympassUserId:a})` |
| `generatePasswordRecoveryEmail` | `POST` | `"recover_password",{email:e})` |
| `generateDownloadLinkEmail` | `POST` | `"email_download_link")` |
| `getAccount` | `GET` | `"user/account")` |
| `updateAccount` | `PUT` | `"account",{account:e})` |
| `updatePassword` | `PUT` | `"update_password_with_password",e)` |
| `updatePasswordWithToken` | `POST` | `"update_password",e)` |
| `updateUsername` | `PUT` | `"username",{username:e,isInitialOnboardingUsername:a})` |
| `getPresignedUrl` | `POST` | `"presigned_url",{file_name:e})` |
| `getUserSubscription` | `GET` | `"user_subscription")` |
| `getUserPreferences` | `GET` | `"v2/user_preferences")` |
| `updateUserPreferences` | `PUT` | `"user_preferences",e)` |
| `getUserKeyValues` | `GET` | `"user_key_values")` |
| `updateUserKeyValues` | `PUT` | `"user_key_values",e)` |
| `getRoutinesSync` | `POST` | `"routines_sync_batch",e)` |
| `getRoutine` | `GET` | `"routine/".concat(e))` |
| `getRoutineWithShortId` | `GET` | `"routine_with_short_id/".concat(e))` |
| `postRoutine` | `POST` | `"routine",{routine:e},{params:{sendSyncEventToMobileApp:!0}})` |
| `postRoutineCopy` | `POST` | `"routine_copy",e,{params:{sendSyncEventToMobileApp:!0}})` |
| `updateRoutine` | `PUT` | `"routine/".concat(e),{routine:a},{params:{sendSyncEventToMobileApp:!0}})` |
| `deleteRoutine` | `DELETE` | `"routine/".concat(e),{params:{sendSyncEventToMobileApp:!0}})` |
| `getRoutineFolders` | `GET` | `"routine_folders")` |
| `postRoutineFolder` | `POST` | `"routine_folder",{folder:e},{params:{sendSyncEventToMobileApp:!0}})` |
| `updateRoutineFolder` | `PUT` | `"routine_folder",e,{params:{sendSyncEventToMobileApp:!0}})` |
| `deleteRoutineFolder` | `DELETE` | `"routine_folder/".concat(e),{params:{sendSyncEventToMobileApp:!0}})` |
| `updateRoutineLocations` | `PUT` | `"routine_locations",{locations:e},{params:{sendSyncEventToMobileApp:!0}})` |
| `updateRoutineFolderOrder` | `PUT` | `"routine_folder_order",{reorders:e},{params:{sendSyncEventToMobileApp:!0}})` |
| `getCustomExerciseTemplates` | `GET` | `"custom_exercise_templates")` |
| `getExerciseTemplateUnits` | `GET` | `"exercise_template_units")` |
| `postFeedback` | `POST` | `"v2/feedback",{feedback:e})` |
| `getFeedPaged` | `GET` | `e?"feed_workouts_paged/".concat(e):"feed_workouts_paged")` |
| `userSearch` | `GET` | `"users/".concat(e))` |
| `getRecommendedUsers` | `GET` | `"recommended_users")` |
| `getFollowingStatuses` | `GET` | `"following_statuses")` |
| `getFollowing` | `GET` | `"following/".concat(e))` |
| `getFollowCounts` | `GET` | `"follow_counts")` |
| `followUser` | `POST` | `"follow",{username:e})` |
| `unfollowUser` | `POST` | `"unfollow",{username:e})` |
| `getFollowersPaged` | `GET` | `"followers_paged/".concat(e,"/").concat(a))` |
| `searchFollowers` | `GET` | `"followers_search/".concat(e,"/").concat(a))` |
| `getUserProfile` | `GET` | `"user_profile/".concat(e))` |
| `getUserPublicApiKey` | `GET` | `"user_public_api_key")` |
| `createUserPublicApiKey` | `POST` | `"user_public_api_key")` |
| `deleteUserPublicApiKey` | `DELETE` | `"user_public_api_key")` |
| `getPublicUserProfile` | `GET` | `"public_user_profile/".concat(e))` |
| `getUserWorkoutImages` | `GET` | `"/user_workout_images/".concat(e,"/").concat(a))` |
| `getUserWorkoutMetrics` | `GET` | `"user_workout_metrics/".concat(e,"/").concat(a,"/").concat(n))` |
| `getUserCalendarWorkouts` | `GET` | `"user_calendar_workouts/".concat(a,"/").concat(e))` |
| `getWorkout` | `GET` | `"workout/".concat(e))` |
| `getUserWorkoutsPaged` | `GET` | `"user_workouts_paged",{params:e})` |
| `getWorkoutComments` | `GET` | `"workout_comments/".concat(e))` |
| `getWorkoutLikes` | `GET` | `"workout_likes/".concat(e))` |
| `postWorkoutComment` | `POST` | `"workout_comment",{workoutId:e,comment:a})` |
| `deleteWorkoutComment` | `DELETE` | `"workout_comment/".concat(e))` |
| `likeWorkout` | `POST` | `"workout/like/".concat(e))` |
| `unlikeWorkout` | `POST` | `"workout/unlike/".concat(e))` |
| `getWorkoutCount` | `GET` | `"workout_count")` |
| `getWorkoutsBatch` | `GET` | `"workouts_batch/".concat(e))` |
| `postCustomExerciseTemplate` | `POST` | `"custom_exercise_template",{exercise:e})` |
| `updateCustomExerciseTemplate` | `PUT` | `"/custom_exercise_template/".concat(e.id),{exercise:e})` |
| `deleteCustomExerciseTemplate` | `DELETE` | `"/custom_exercise_template/".concat(e))` |
| `getUserExerciseSets` | `GET` | `"user_exercise_sets/".concat(e,"/").concat(a))` |
| `getUserExerciseHistory` | `GET` | `"user_exercise_history_paged",{params:e})` |
| `getPaddlePrices` | `GET` | `"paddle_prices")` |
| `getPaddleUrls` | `GET` | `"user/paddle_urls")` |
| `changePaddlePlan` | `POST` | `"user/change_paddle_plan",e)` |
| `cancelPaddlePlan` | `DELETE` | `"user/paddle_plan")` |
| `getPaddlePromoCodeDetails` | `GET` | `"paddle_promo_code_details/".concat(e))` |
| `getCoachInvites` | `GET` | `"client_invites")` |
| `getCoachInfoForInvite` | `GET` | `"/invite/".concat(e))` |
| `getCoachJoinFormMetadata` | `GET` | `"/coach/join_form_metadata/".concat(e))` |
| `getBecomeClient` | `GET` | `"/become_client/".concat(e))` |
| `acceptCoachInvite` | `GET` | `"/accept_client_invite/".concat(e))` |
| `acceptCoachInviteWithShortId` | `GET` | `"/accept_client_invite_with_short_id/".concat(e))` |
| `getCoach` | `GET` | `"clients_coach")` |
| `declineCoachInvite` | `DELETE` | `"/client_invites/".concat(e))` |
| `declineCoachInviteWithShortId` | `DELETE` | `"/client_invites_with_short_id/".concat(e))` |
| `deleteAccount` | `DELETE` | `"/user"),attachErrorHandler:c.attachErrorHandler` |
| `getShareableFolderById` | `GET` | `"shareable_folder/".concat(e))` |
| `getHevyTrainerProgram` | `GET` | `"hevy_trainer/program")` |
| `getOAuthAuthorise` | `GET` | `"oauth/code?client_id=".concat(e))` |
| `postSubscribeToWebhook` | `POST` | `"/webhook-subscription",{url:a,authToken:n})}` |
| `getWebhookSubscription` | `GET` | `"webhook-subscription")` |
| `linkUserWithGympass` | `POST` | `"/link_with_gympass",{gympassUserId:a})}` |
| `getOAuthClient` | `GET` | `"oauth/client/".concat(e))}` |
