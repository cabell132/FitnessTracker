# Circuits sync as superset Routine exercise blocks

Coach-authored Circuit blocks and multi-movement AMRAP blocks should sync to
Hevy as multiple Routine exercise blocks sharing one `superset_id`, rather than
as a generic Circuit or AMRAP placeholder template. The split is allowed only
when movement boundaries, round count or AMRAP time cap, and concrete Hevy
exercise templates can be resolved deterministically; otherwise the item is
review-blocked.

This preserves the Coach's prescription in a Hevy shape the Athlete can log
against directly, while avoiding silent partial or placeholder routines. A
time-boxed multi-movement AMRAP uses a practical logging scaffold of
`floor(minutes / 2)` set rows per movement, with a minimum of one row, because
adding extra rows in Hevy is easier than deleting a vague placeholder block.
Complex but discernible structures, such as round-specific rep ladders, should
be surfaced in the `create-hevy-routine` review flow for an Agent decision
rather than silently interpreted during automatic request generation.
The first parser should be newline-first, supporting line, bullet, and numbered
movement boundaries from the existing True Coach data. Comma-separated movement
lists are deliberately out of scope for the first implementation because they
are not needed for the observed circuit rows and are more likely to confuse
movement boundaries with prose or rest clauses.

Rest semantics follow the Athlete's logging workflow: round-level circuit rest
is represented as the rest period on the final generated movement block,
movement-level rest attaches to the preceding generated movement block, and
cardio machine durations are not represented as rest periods. Movement duration
can still be both a structured set target and a rest-period timer when that
timer helps the Athlete perform the movement, such as for planks.

Workout backfill uses the same split-circuit language but has a stricter
linking requirement because it creates logged Hevy Workouts and repairs local
tracker links afterward. When a backfilled Circuit or AMRAP block is split, the
system should create synthetic local tracker Workout Items for the generated
movements so each created Hevy exercise row links one-to-one with a local row;
the original True Coach circuit item remains source context, not the sole local
row for every generated movement.
For split Circuit or AMRAP Workout backfill, prescribed movement targets may be
used as performed set values by default when the Athlete comment does not
contradict them; notes must preserve that those values came from the Coach
prescription. Round-duration comment lines such as `2 min 10 sec` represent
completed round times for AMRAP and non-AMRAP circuits: the number of such lines
is the completed round count, and the durations remain notes/evidence rather
than movement set values. For completed non-AMRAP round circuits with no Athlete
comment, the full prescribed round count may be backfilled as performed work
using prescribed movement targets. Missed Circuit or AMRAP items should not be
backfilled as performed work. When the Athlete comment gives a lower completed
round count than the prescription, backfill should use the completed round count
and preserve both the original prescription and Athlete comment in notes.
Backfill may omit a split movement when the Athlete comment clearly states it
was not performed, such as `W/o Cycle`; the remaining performed movements may
still be backfilled. If the comment names a replacement movement, backfill
requires an Agent decision unless the replacement can be resolved clearly.
Backfilled split Circuit and AMRAP movements should still be grouped with a
Hevy `superset_id`, inheriting any existing Coach-authored superset id or
otherwise receiving the next available group id.
If a split movement was performed or is presumed performed and has no concrete
Hevy exercise template, Workout backfill apply is blocked until the mapping is
resolved. Missing templates may be bypassed only for movements clearly omitted
by the Athlete comment.
Synthetic tracker Workout Items for split backfill movements should be persisted
in the local database, named after the generated movement, linked to the
resolved tracker Exercise and created Hevy row, and traceable back to the source
True Coach circuit item through review artifacts and notes. Durable local rows
are preferred over request-only generated rows because backfill repair and set
linking need stable local targets. Review generation remains side-effect-free;
synthetic tracker rows are created only during validated apply or repair, after
the remote Hevy Workout rows exist or have been found.
