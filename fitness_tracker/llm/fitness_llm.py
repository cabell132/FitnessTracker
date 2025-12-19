from typing import TypeVar

from langchain_core.language_models import BaseChatModel

from fitness_tracker.llm.open_ai_llm import OpenAILLM
from fitness_tracker.llm.prompt_models import PostRoutinesRequestSets, Exercise, WorkoutItemLinkList
from fitness_tracker.llm.prompt_templates import (
    PROMPT_EXTRACT_INFO_SETS, PROMPT_EXERCISE, PROMPT_EXTRACT_COMPLETED_SETS, PROMPT_HEVY_TO_TRUE_COACH_WORKOUT_ITEMS
)
import logging

T = TypeVar("T", bound=BaseChatModel)

# Set the logging level for SQLAlchemy and Alembic to WARNING
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING)


class FitnessLLM(OpenAILLM):
    """Fitness Related Questions."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0,
        max_completion_tokens: int = 150,
    ):
        super().__init__(model_name, temperature, max_completion_tokens)

    def parse_the_sets(self, info: str) -> PostRoutinesRequestSets:
        """
        Given the text of the exercise information, parse the sets.

        Args:
            info (str): the text of the exercise information

        Returns:
            PostRoutinesRequestSets: the parsed sets
        """

        return self.function_prompt(
            info, PROMPT_EXTRACT_INFO_SETS, PostRoutinesRequestSets
        )
    
    def parse_completeted_sets(self, exercise_type: str, info: str, result: str) -> PostRoutinesRequestSets:
        """
        Given the text of the exercise information, parse the sets.

        Args:
            exercise_type (str): the type of the exercise
            info (str): the text of the exercise information
            result (str): the result of the exercise

        Returns:
            PostRoutinesRequestSets: the parsed sets
        """

        data = str(
            {
                "exercise_type": exercise_type,
                "info": info,
                "result": result
            }
        )

        return self.function_prompt(
            data, PROMPT_EXTRACT_COMPLETED_SETS, PostRoutinesRequestSets
        )
    
    def link_workout_items(self, hevy_items: list[dict[str, str | int]], true_coach_items:  list[dict[str, str | int]]) -> WorkoutItemLinkList:
        """
        Given the text of the exercise information, parse the sets.

        Args:
            hevy_items (list[dict[str, str | int]]): the text of the exercise information
            true_coach_items (list[dict[str, str | int]]): the text of the exercise information

        Returns:
            WorkoutItemLinkList: the parsed sets
        """

        data = str(
            {
                "hevy_app_items": hevy_items,
                "true_coach_items": true_coach_items
            }
        )

        return self.function_prompt(
            data, PROMPT_HEVY_TO_TRUE_COACH_WORKOUT_ITEMS, WorkoutItemLinkList
        )

    
    def get_exercise_info(self, data: str) -> Exercise:
        """
        Given the text of the exercise information, parse the sets.

        Args:
            data (str): the text of the exercise information

        Returns:
            Exercise: the parsed sets
        """

        return self.function_prompt(
            data, PROMPT_EXERCISE, Exercise
        )

    
    async def parse_the_sets_async(self, data_list: list[str]) -> list[PostRoutinesRequestSets]:
        """
        Given the text of the exercise information, parse the sets.

        Args:
            data_list (list[str]): the text of the exercise information

        Returns:
            PostRoutinesRequestSets: the parsed sets
        """

        return await self.function_prompt_async(
            data_list, PROMPT_EXTRACT_INFO_SETS, PostRoutinesRequestSets
        )