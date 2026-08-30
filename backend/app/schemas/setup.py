from pydantic import BaseModel, Field


class SetupUpdate(BaseModel):
    qwen_api_key: str | None = Field(default=None, max_length=500)
    deepseek_api_key: str | None = Field(default=None, max_length=500)
    tavily_api_key: str | None = Field(default=None, max_length=500)
    use_demo: bool = False
    clear_tavily: bool = False
