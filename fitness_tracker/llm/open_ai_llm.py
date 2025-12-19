from typing import Any

from dotenv import load_dotenv
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts.chat import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI
from pydantic.v1 import ValidationError
from pydantic import SecretStr
import os

load_dotenv()


class OpenAILLM:
    def __init__(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_completion_tokens: int = 150,
    ):
        self.model = ChatOpenAI(
            api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
            model=model_name,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
        )

    def function_prompt(
        self, data: str, promt_template: str, pydantic_object: Any
    ) -> Any:
        """
        Perform a prompt using a template and a Pydantic object.

        Args:
            data (str): The data to be used in the prompt.
            promt_template (str): The template for the prompt.
            pydantic_object (Any): The Pydantic object used for parsing the output.

        Returns:
            The parsed output based on the Pydantic object.

        """
        message = HumanMessagePromptTemplate.from_template(
            template=promt_template,
        )
        chat_prompt = ChatPromptTemplate.from_messages(messages=[message])  # type: ignore
        # generate the response

        parser = PydanticOutputParser(pydantic_object=pydantic_object)  # type: ignore
        chat_prompt_with_values = chat_prompt.format_prompt(
            data=data, format_instructions=parser.get_format_instructions()
        )
        output = self.model.invoke(chat_prompt_with_values.to_messages())

        return parser.parse(output.content)  # type: ignore

    async def function_prompt_async(
        self, data_list: list[str], promt_template: str, pydantic_object: Any
    ) -> Any:
        """
        Perform a prompt using a template and a Pydantic object.

        Args:
            data (str): The data to be used in the prompt.
            promt_template (str): The template for the prompt.
            pydantic_object (Any): The Pydantic object used for parsing the output.

        Returns:
            The parsed output based on the Pydantic object.

        """
        message = HumanMessagePromptTemplate.from_template(
            template=promt_template,
        )
        chat_prompt = ChatPromptTemplate.from_messages(messages=[message])  # type: ignore

        # generate the response
        parser = PydanticOutputParser(pydantic_object=pydantic_object)

        chain = LLMChain(
            llm=self.model,
            prompt=chat_prompt,
        )

        input_lst = [
            {"data": data, "format_instructions": parser.get_format_instructions()}
            for data in data_list
        ]

        output = await chain.aapply(input_lst)

        results: list[Any] = []
        for res in output:
            try:
                results.append(parser.parse(res["text"]))
            except ValidationError:
                results.append(res["text"])

        return results
