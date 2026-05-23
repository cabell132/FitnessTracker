# Routine replacement uses strict-safe artifact planning and disposable marked Hevy Routines

Automatic sync may create Hevy Routines from due True Coach Workouts only through the Routine creation planner, and only when every plan in the Routine replacement batch has no warnings or blockers. If any due Workout requires review, automatic sync writes review artifacts for the whole batch, applies none of the Routines, and must not clear the Athlete's existing Hevy Routine menu.

Hevy Routines created from True Coach are disposable and are not durable local identities. Durable linkage comes from a Routine source marker carrying the True Coach Workout id into the later performed Hevy Workout; automatic replacement also marks generated Routines with a Routine batch marker so old generated Routines can be distinguished from the newly-created batch. Automatic sync should delete only generated Routines carrying these markers, not unrelated manual Hevy Routines.

This replaces the legacy direct clear-then-create behavior because a partial or unsafe Routine menu is worse than leaving the previous menu in place. The trade-off is that automatic sync becomes more conservative and may require Agent review more often, but it preserves the Athlete's usable Hevy menu and keeps ambiguous prescription interpretation in review artifacts.
