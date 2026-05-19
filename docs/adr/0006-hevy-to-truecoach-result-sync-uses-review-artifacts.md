# Hevy to True Coach result sync uses review artifacts for Agent mapping decisions

Hevy remains the source of truth for performed Workout results, and the existing
set formatters remain responsible for deterministic True Coach result text. For
Agent-operated Hevy to True Coach sync, writes should be split into review and
apply artifacts so the Agent can resolve brittle mapping cases before mutating
True Coach: exercise replacements, meaningful order changes, repeated performed
exercises, explicit omissions, partial apply, and completion status. The first
implementation should target one explicit Hevy Workout id; it must not mark the
True Coach Workout completed while known performed Hevy items remain unresolved.
