import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    model_name: str
    api_key: str
    base_url: Optional[str]
    disable_thinking: bool


def load_settings() -> Settings:
    load_dotenv()

    model_name = os.getenv("MODEL_NAME", "kimi-k2.5")
    base_url = os.getenv("OPENAI_BASE_URL")
    disable_thinking = False

    if model_name in ("kimi-k2.5", "kimi-k2.6"):
        base_url = base_url or f"http://deepgate.ximalaya.local/{model_name}/api/v1"
        disable_thinking = True

    return Settings(
        model_name=model_name,
        api_key=os.getenv("DEEPGATE_API_KEY") or os.getenv("OPENAI_API_KEY", "EMPTY"),
        base_url=base_url,
        disable_thinking=disable_thinking,
    )
