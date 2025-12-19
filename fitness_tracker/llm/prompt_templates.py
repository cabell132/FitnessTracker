from fitness_tracker.apis.hevy_app.types import MUSCLE_GROUPS

CONTEXTUAL_PROMPT = """
    Prentend you are a fitness expert filling out a workout routine.\n"""

PROMPT_EXTRACT_INFO_SETS = (
    CONTEXTUAL_PROMPT
    + """
    Instructions:
    You are given a piece of set data in the format {{'exercise_type': '<type>', 'info': '<details>'}}. Your task is to break this down into a list of sets following these requirements:

    Interpret the exercise_type and info fields:

    Extract details like the number of sets, repetitions, weight, distance, or duration from info.
    Follow the rules and examples provided below to structure the output.
    Output Format:

    The output must strictly conform to the JSON schema provided below.
    Use the schema's fields like reps, weight_kg, distance_meters, or duration_seconds as appropriate.
    Ensure the type field defaults to "normal", unless otherwise specified.
    Validation:

    Your output must be a well-formatted JSON instance as defined by the schema.
    The result must strictly adhere to the schema constraints for each field.
    Examples:
    Here are examples of how to transform inputs into the correct output format:

    1. Input: {{'exercise_type': 'reps_only', 'info': '3 x 4'}} Output: {{"sets": [{{"type": "normal", "reps": 4}}, {{"type": "normal", "reps": 4}}, {{"type": "normal", "reps": 4}}]}}
    2. Input: {{exercise_type: "weight_reps", info: "3 x 12"}} Output: {{"sets": [{{"type": "normal", "reps": 12}}, {{"type": "normal", "reps": 12}}, {{"type": "normal", "reps": 12}}]}}
    3. Input: {{exercise_type: "weight_reps", info: "3 x 12 @90"}} Output: {{"sets": [{{"type": "normal", "reps": 12, "weight_kg": 90}}, {{"type": "normal", "reps": 12, "weight_kg": 90}}, {{"type": "normal", "reps": 12, "weight_kg": 90}}]}}
    4. Input: {{exercise_type: "weight_reps", info: "3 x 6 ES"}} Output: {{"sets": [{{"type": "normal", "reps": 6}}, {{"type": "normal", "reps": 6}}, {{"type": "normal", "reps": 6}}]}}
    5. Input: {{exercise_type: "weight_reps", info: "3 x max"}} Output: {{"sets": [{{"type": "failure"}}, {{"type": "failure"}}, {{"type": "failure"}}]}}
    6. Input: {{exercise_type: "weight_reps", info: "3 x 8-12"}} Output: {{"sets": [{{"type": "normal", "reps": 12}}, {{"type": "normal", "reps": 12}}, {{"type": "normal", "reps": 12}}]}}
    7. Input: {{exercise_type: "distance_duration", info: "3 x 150m"}} Output: {{"sets": [{{"type": "normal", "distance_meters": 150}}, {{"type": "normal", "distance_meters": 150}}, {{"type": "normal", "distance_meters": 150}}]}}
    8. Input: {{exercise_type: "distance_duration", info: "3 x 200m @ 80%"}} Output: {{"sets": [{{"type": "normal", "distance_meters": 200}}, {{"type": "normal", "distance_meters": 200}}, {{"type": "normal", "distance_meters": 200}}]}}
    9. Input: {{exercise_type: "duration", info: "30mins"}} Output: {{"sets": [{{"type": "normal", "duration_seconds": 1800}}]}}
    10. Input: {{exercise_type: "weight_reps", info: "3 x (6+8)"}} Output: {{"sets": [{{"type": "normal", "reps": 6}}, {{"type": "dropset", "reps": 8}}, {{"type": "normal", "reps": 6}}, {{"type": "dropset", "reps": 8}}, {{"type": "normal", "reps": 6}}, {{"type": "dropset", "reps": 8}}]}}


    {format_instructions}

    Important Notes:
    Use "type": "failure" for sets with "max" or failure-based reps.
    Always use the highest rep count for ranges like 8-12.
    Convert durations into seconds (30mins → 1800 seconds).
    Ensure the output is a valid JSON object that matches the schema, without extra fields.
    If you don't know return an empty list.
    Now process this input accordingly: '{data}'.
    """
)

PROMPT_EXERCISE = (
    CONTEXTUAL_PROMPT
    + f"""
    for the exercise '{{data}}' and with this list of muscle groups {MUSCLE_GROUPS} can you provide the following information:

    From the given list of muscle groups, select the primary muscle group targeted by this exercise.
    From the given list of muscle groups, select a list of secondary muscle groups targeted by this exercise?
    What is the equipment required for this exercise?
    What is the type of this exercise?

    {{format_instructions}}
    """
)

PROMPT_EXTRACT_COMPLETED_SETS = (
    CONTEXTUAL_PROMPT
    + """
    Instructions:
    You are given a piece of set data in the format {{'exercise_type': '<type>', 'info': '<details>', 'result': <details>}}. Your task is to break this down into a list of sets following these requirements:

    Interpret the exercise_type and info fields:

    Extract details like the number of sets, repetitions, weight, distance, or duration from comment you can use the info.
    Follow the rules and examples provided below to structure the output.
    Output Format:

    The output must strictly conform to the JSON schema provided below.
    Use the schema's fields like reps, weight_kg, distance_meters, or duration_seconds as appropriate.
    Ensure the type field defaults to "normal", unless otherwise specified.
    Validation:

    Your output must be a well-formatted JSON instance as defined by the schema.
    The result must strictly adhere to the schema constraints for each field.
    Examples:
    Here are examples of how to transform inputs into the correct output format:

    1. Input: {{'exercise_type': 'weight_reps', 'info': '3 x 6 EW (Each Way)', 'result': '10'}} Output: {{"sets": [{{"type": "normal", "reps": 6, "weight_kg": 10}}, {{"type": "normal", "reps": 6, "weight_kg": 10}}, {{"type": "normal", "reps": 6, "weight_kg": 10}}]}}
    2  Input: {{'exercise_type': 'distance_duration', 'info': '3 x 200m @ 80%', 'result': '36.4\n36.9\n38.3'}} Output: {{"sets": [{{"type": "normal", distance_meters": 200, duration_seconds: 36}}, {{"type": "normal", distance_meters": 200, duration_seconds: 37}}, {{"type": "normal", distance_meters": 200, duration_seconds: 38}}]}}
    3. Input: {{'exercise_type': 'weight_reps', 'info': '3 x 10', 'result': '42.4kg\n7 reps on 3rd set'}} Output: {{"sets": [{{"type": "normal", "reps": 10, "weight_kg": 42.4}}, {{"type": "normal", "reps": 10, "weight_kg": 42.4}}, {{"type": "normal", "reps": 7, "weight_kg": 42.4}}]}}
    4. Input: {{'exercise_type': 'weight_reps', 'info': '3 x 8-12', 'result': '10'}} Output: {{"sets": [{{"type": "normal", "reps": 12, "weight_kg": 10}}, {{"type": "normal", "reps": 12, "weight_kg": 10}}, {{"type": "normal", "reps": 12, "weight_kg": 10}}]}}
    5. Input: {{'exercise_type': 'distance_duration', 'info': '6km', 'result': '33m 33s'}} Output: {{"sets": [{{"type": "normal", "distance_meters": 6000, "duration_seconds": 2013}}]}}
    6. Input: {{'exercise_type': 'weight_reps', 'info': '3 x 8+8 (Drop Set)', 'result': '2 x 73 > 59\n1 x 73 > 52'}} Output: {{"sets": [{{"type": "normal", "reps": 8, "weight_kg": 73}}, {{"type": "dropset", "reps": 8, "weight_kg": 59}}, {{"type": "normal", "reps": 8, "weight_kg": 73}}, {{"type": "dropset", "reps": 8, "weight_kg": 52}}, {{"type": "normal", "reps": 8, "weight_kg": 73}}, {{"type": "dropset", "reps": 8, "weight_kg": 52}}]}}


    {format_instructions}

    Important Notes:
    Use "type": "failure" for sets with "max" or failure-based reps.
    Always use the highest rep count for ranges like 8-12.
    Convert durations into seconds (30mins → 1800 seconds).
    Ensure the output is a valid JSON object that matches the schema, without extra fields.
    If you don't know return an empty list.
    Now process this input accordingly: '{data}'.
    """
)

PROMPT_HEVY_TO_TRUE_COACH_WORKOUT_ITEMS = CONTEXTUAL_PROMPT + """

    You are tasked with creating a mapping between two lists of exercises, hevy_app_list and true_coach_list, based on their similarity. Your output should ensure accuracy and adherence to the rules outlined below.

    1. Match by Position:

    First, pair items where the order field in hevy_app_list matches the order field in true_coach_list.

    2.Exact Title/Name Match:

    If the name field in hevy_app_list matches the name field in true_coach_list exactly (ignoring spaces and case), consider them a match.

    3.Partial String Match:

    For unmatched items, calculate string similarity (e.g., using Levenshtein distance or fuzzy matching).
    Items with a similarity score of 80% or higher should be paired.

    4. Handle Unmatched Entries:

    If an item in hevy_app_list cannot be matched, set its true_coach_id to None.
    Similarly, if an item in true_coach_list cannot be matched, set its hevy_app_id to None.

    5. Manual Overrides for Domain-Specific Matches:

    Use domain-specific overrides for cases where naming conventions differ but refer to the same exercise. 
    For example:
        'Decline Crunch (Weighted)' in hevy_app_list should map to 'Weighted Dumbbell Decline Bench Sit-Up' in true_coach_list.

    Input Format:
        A JSON object containing two lists:

        {{
        "hevy_app_items": [
            {{"hevy_app_id": 257, "name": "Alternating Dumbbell Curl", "order": 10}},
            {{"hevy_app_id": 258, "name": "Triceps Rope Pushdown", "order": 11}}
        ],
        "true_coach_items": [
            {{"true_coach_id": -1796978224, "name": "SL Hip Flexor Sit Up", "order": 10}},
            {{"true_coach_id": -1796978221, "name": "Bicycle Crunch", "order": 11}},
            {{"true_coach_id": -1796978214, "name": "Alternating Dumbbell Curl", "order": 12}},
            {{"true_coach_id": -1796978223, "name": "Standing Cable Tricep Extension", "order": 13}},
            {{"true_coach_id": -1796978216, "name": "Down Regulate", "order": 15}},
            {{"true_coach_id": -1796978215, "name": "Incline Treadmill Walk", "order": 14}}
        ]
        }}


    Output Format:
        The output should be a list of mappings in the format:

        [
        {{'hevy_app_id': 257, 'true_coach_id': -1796978214}},
        {{'hevy_app_id': 258, 'true_coach_id': -1796978223}},
        {{'hevy_app_id': null, 'true_coach_id': -1796978215}},
        {{'hevy_app_id': null, 'true_coach_id': -1796978216}},
        {{'hevy_app_id': null, 'true_coach_id': -1796978221}},
        {{'hevy_app_id': null, 'true_coach_id': -1796978224}}
        ]

    {format_instructions}

    Notes:
        Your output should follow the outlined rules in the given priority order.
        Ensure that unmatched items are clearly identified with null values.

    Now process this input accordingly: '{data}'.

    Remember to format the output as a JSON object.
    """
