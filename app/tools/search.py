import json
from typing import Any, Dict, List

from ddgs import DDGS
from langchain_core.tools import tool


@tool
def search_web(query: str, max_results: int = 3) -> str:
    """Search the web for World Cup news background and return compact results."""
    try:
        with DDGS() as ddgs:
            results: List[Dict[str, Any]] = []
            for item in ddgs.text(query, max_results=max_results):
                results.append(
                    {
                        "title": item.get("title"),
                        "url": item.get("href") or item.get("url"),
                        "snippet": item.get("body"),
                    }
                )

        return json.dumps(
            {
                "query": query,
                "results": results,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "query": query,
                "results": [],
                "error": f"Search failed: {exc}",
            },
            ensure_ascii=False,
        )
