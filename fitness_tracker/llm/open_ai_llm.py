"""Thin LangChain + OpenAI wrapper for templated structured prompts."""

import asyncio
from typing import Any, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from pydantic.v1 import ValidationError


class OpenAILLM:
    """OpenAI chat client with Pydantic output parsing."""

    def __init__(  # noqa: PLR0913
        self,
        model_name: str,
        *,
        api_key: str,
        temperature: float = 0.0,
        max_completion_tokens: int = 150,
    ) -> None:
        """Create a configured chat model for prompts.

        Args:
            model_name (str): OpenAI model id (e.g. ``gpt-4o-mini``).
            api_key (str): OpenAI API key.
            temperature (float, optional): Sampling temperature. Defaults to 0.0.
            max_completion_tokens (int, optional): Cap on completion length. Defaults to 150.
        """
        self.model = ChatOpenAI(
            api_key=SecretStr(api_key),
            model=model_name,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
        )

    def function_prompt(self, data: str, promt_template: str, pydantic_object: Any) -> Any:
        """Run a single structured prompt and parse into ``pydantic_object``.

        Args:
            data (str): User or tool payload interpolated into the template.
            promt_template (str): LangChain template string (may use ``{data}``, etc.).
            pydantic_object (Any): Pydantic model class for the parser.

        Returns:
            Any: Parsed instance of ``pydantic_object``.
        """
        message = HumanMessagePromptTemplate.from_template(
            template=promt_template,
        )
        chat_prompt = ChatPromptTemplate.from_messages(messages=[message])
        parser = PydanticOutputParser(pydantic_object=pydantic_object)
        chat_prompt_with_values = chat_prompt.format_prompt(
            data=data, format_instructions=parser.get_format_instructions()
        )
        output = self.model.invoke(chat_prompt_with_values.to_messages())

        return parser.parse(cast(str, output.content))

    async def function_prompt_async(
        self, data_list: list[str], promt_template: str, pydantic_object: Any
    ) -> list[Any]:
        """Run structured prompts for many inputs concurrently.

        Args:
            data_list (list[str]): One prompt payload per item.
            promt_template (str): Shared LangChain template.
            pydantic_object (Any): Pydantic model class for each parse.

        Returns:
            list[Any]: Parsed objects (or raw content on validation failure).
        """
        message = HumanMessagePromptTemplate.from_template(
            template=promt_template,
        )
        chat_prompt = ChatPromptTemplate.from_messages(messages=[message])

        parser = PydanticOutputParser(pydantic_object=pydantic_object)

        async def process_single_item(data: str) -> Any:
            """Parse one row; fall back to raw text if validation fails.

            Args:
                data (str): Payload for this item.

            Returns:
                Any: Parsed model or raw assistant content.
            """
            chat_prompt_with_values = chat_prompt.format_prompt(
                data=data, format_instructions=parser.get_format_instructions()
            )
            output = await self.model.ainvoke(chat_prompt_with_values.to_messages())
            try:
                return parser.parse(cast(str, output.content))
            except ValidationError:
                return output.content

        return await asyncio.gather(*[process_single_item(data) for data in data_list])
