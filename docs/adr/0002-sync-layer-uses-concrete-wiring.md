# The sync layer uses concrete wiring; ports/adapters were tried and reverted

The directional syncers in `fitness_tracker/sync/` take their dependencies
(`Store`, `HevyAppClient`, `TrueCoachClient`, `FitnessLLM`) as concrete types.

A ports & adapters layer was built for the sync subsystem (issue #2) and
wired into all seven syncers (issue #3, commit `7ea2e9c`), then deliberately
reverted 75 minutes later (commit `f5ce01c`) in favour of concrete wiring.
The `sync/ports/` and `sync/adapters/` packages still hold the now-unused
files from issue #2; the `CheckpointStore` port and its `FileCheckpointStore`
adapter are the one live exception, used by `SyncService.run()`.

Do not re-introduce port-wiring across the syncers without a concrete,
feature-driven reason. Deleting the unused `ports/`/`adapters/` files
completes this decision; it does not reverse it.
