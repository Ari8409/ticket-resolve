from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from app.recommendation.prompts import STRUCTURED_OUTPUT_PROMPT


def build_structuring_chain(llm: ChatOpenAI):
    """
    Secondary LCEL chain: converts free-text agent output into a structured JSON dict.
    Used as a fallback when the primary agent output cannot be parsed directly.
    """
    parser = JsonOutputParser()
    prompt = PromptTemplate(
        template=STRUCTURED_OUTPUT_PROMPT,
        input_variables=["agent_output"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    return prompt | llm | parser
