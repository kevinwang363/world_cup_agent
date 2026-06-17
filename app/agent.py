from typing import Any

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.config import load_settings
from app.prompts import SYSTEM_PROMPT
from app.tools.football_api import (
    get_daily_report,
    get_fixtures,
    get_match_analysis,
    get_match_result,
    get_prediction_context,
    get_team_profile,
)
from app.tools.knowledge import query_vector_knowledge
from app.tools.search import search_web


def create_world_cup_agent() -> Any:
    settings = load_settings()
    model_kwargs = {
        "model": settings.model_name,
        "api_key": settings.api_key,
    }

    if settings.base_url:
        model_kwargs["base_url"] = settings.base_url

    if settings.disable_thinking:
        model_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    model = ChatOpenAI(**model_kwargs)
    tools = [
        get_daily_report,
        get_team_profile,
        get_match_analysis,
        get_prediction_context,
        get_fixtures,
        get_match_result,
        query_vector_knowledge,
        search_web,
    ]
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_openai_tools_agent(model, tools, prompt)

    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def run_agent(question: str) -> str:
    agent = create_world_cup_agent()
    response = agent.invoke({"input": question})

    content = response.get("output", "")
    if isinstance(content, str):
        return content

    return str(content)
