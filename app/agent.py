from typing import Any, List, Optional, Sequence

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
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


def create_world_cup_agent(
    callbacks: Optional[Sequence[BaseCallbackHandler]] = None,
    streaming: bool = False,
    verbose: bool = True,
) -> Any:
    settings = load_settings()
    model_kwargs = {
        "model": settings.model_name,
        "api_key": settings.api_key,
        "streaming": streaming,
    }

    if settings.base_url:
        model_kwargs["base_url"] = settings.base_url

    if settings.disable_thinking:
        model_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    if callbacks:
        model_kwargs["callbacks"] = list(callbacks)

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
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_openai_tools_agent(model, tools, prompt)

    return AgentExecutor(agent=agent, tools=tools, verbose=verbose)


def run_agent(question: str, chat_history: Optional[List[BaseMessage]] = None) -> str:
    agent = create_world_cup_agent()
    response = agent.invoke({"input": question, "chat_history": chat_history or []})

    content = response.get("output", "")
    if isinstance(content, str):
        return content

    return str(content)


def run_chat_loop() -> None:
    agent = create_world_cup_agent()
    chat_history: List[BaseMessage] = []

    print("进入多轮对话模式。输入 exit / quit / 退出 结束。")
    while True:
        question = input("\n你：").strip()
        if question.lower() in {"exit", "quit"} or question == "退出":
            break
        if not question:
            continue

        response = agent.invoke({"input": question, "chat_history": chat_history})
        answer = response.get("output", "")
        if not isinstance(answer, str):
            answer = str(answer)

        print(f"\nAgent：{answer}")
        chat_history.extend([HumanMessage(content=question), AIMessage(content=answer)])
