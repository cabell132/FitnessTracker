"""Domain-specific LLM helpers built on :class:`~fitness_tracker.llm.open_ai_llm.OpenAILLM`."""

from typing import cast

from fitness_tracker.llm.open_ai_llm import OpenAILLM
from fitness_tracker.llm.prompt_models import (
    Exercise,
    PostRoutinesRequestSets,
    WorkoutItemLinkList,
)
from fitness_tracker.llm.prompt_templates import (
    PROMPT_EXERCISE,
    PROMPT_EXTRACT_COMPLETED_SETS,
    PROMPT_EXTRACT_INFO_SETS,
    PROMPT_HEVY_TO_TRUE_COACH_WORKOUT_ITEMS,
)


class FitnessLLM(OpenAILLM):
    """High-level prompts for workouts, exercises, and item linking."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0,
        max_completion_tokens: int = 150,
    ) -> None:
        """Create a fitness-tuned LLM with the given model settings.

        Args:
            model_name (str): OpenAI model id.
            temperature (float, optional): Sampling temperature. Defaults to 0.
            max_completion_tokens (int, optional): Completion cap. Defaults to 150.
        """
        super().__init__(model_name, temperature, max_completion_tokens)

    def parse_the_sets(self, info: str) -> PostRoutinesRequestSets:
        """Parse Hevy-style set text into structured set rows.

        Args:
            info (str): Free-form exercise prescription text.

        Returns:
            PostRoutinesRequestSets: Parsed normal/warmup/failure/dropset rows.
        """
        return self.function_prompt(info, PROMPT_EXTRACT_INFO_SETS, PostRoutinesRequestSets)

    def parse_completeted_sets(
        self, exercise_type: str, info: str, result: str
    ) -> PostRoutinesRequestSets:
        """Parse completed workout commentary into structured sets.

        Args:
            exercise_type (str): Hevy exercise type key.
            info (str): Planned prescription text.
            result (str): Logged result text from the client.

        Returns:
            PostRoutinesRequestSets: Parsed sets for persistence.
        """
        data = str(
            {
                "exercise_type": exercise_type,
                "info": info,
                "result": result,
            }
        )

        return self.function_prompt(data, PROMPT_EXTRACT_COMPLETED_SETS, PostRoutinesRequestSets)

    def link_workout_items(
        self,
        hevy_items: list[dict[str, str | int]],
        true_coach_items: list[dict[str, str | int]],
    ) -> WorkoutItemLinkList:
        """Propose Hevy ↔ True Coach item id pairings.

        Args:
            hevy_items (list[dict[str, str | int]]): Hevy-side exercise blocks.
            true_coach_items (list[dict[str, str | int]]): True Coach blocks.

        Returns:
            WorkoutItemLinkList: Suggested links including optional nulls.
        """
        data = str(
            {
                "hevy_app_items": hevy_items,
                "true_coach_items": true_coach_items,
            }
        )

        return self.function_prompt(
            data, PROMPT_HEVY_TO_TRUE_COACH_WORKOUT_ITEMS, WorkoutItemLinkList
        )

    def get_exercise_info(self, data: str) -> Exercise:
        """Extract primary/secondary muscles and equipment from exercise text.

        Args:
            data (str): Exercise name or description.

        Returns:
            Exercise: Structured tags for the exercise.
        """
        return self.function_prompt(data, PROMPT_EXERCISE, Exercise)

    async def parse_the_sets_async(self, data_list: list[str]) -> list[PostRoutinesRequestSets]:
        """Parse many set blobs concurrently.

        Args:
            data_list (list[str]): One prescription string per exercise.

        Returns:
            list[PostRoutinesRequestSets]: Parsed results aligned with ``data_list``.
        """
        out = await self.function_prompt_async(
            data_list, PROMPT_EXTRACT_INFO_SETS, PostRoutinesRequestSets
        )
        return cast(list[PostRoutinesRequestSets], out)
