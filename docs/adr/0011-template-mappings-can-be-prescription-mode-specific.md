# Template mappings can be prescription-mode specific

A True Coach exercise to Hevy exercise template mapping is not always globally valid. Some Coach exercises can be prescribed in different modes over time, and the correct Hevy template shape depends on the current Coach prescription rather than only the exercise name.

Cobra Stretch is the motivating example. Historical prescriptions such as `3 x 3 with a 5s hold` and performed comments such as `3 reps` made a reps-only Hevy template a reasonable mapping for rep-like prescriptions. Later prescriptions such as `2 x 10s` and `2 x 15s` are duration-like, and sending those duration sets to the same reps-only Hevy template causes Hevy to represent the work as `1 rep` rather than the intended duration.

Routine feedback review must therefore distinguish a bad exercise mapping from a mode/template incompatibility. A reps-only Cobra Stretch mapping may remain valid for rep-like prescriptions, while duration-like Cobra Stretch prescriptions require a duration-compatible template or a review blocker. Do not repair this class of feedback by blindly deleting the existing mapping or treating all future uses of that True Coach exercise as duration-only.
