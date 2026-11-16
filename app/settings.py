from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    image_model: str = ""  # 포스터 배경 그림 모델 (비우면 app.promo.DEFAULT_IMAGE_MODEL)

    jeju_hub_key: SecretStr = SecretStr("")

    max_agent_steps: int = Field(default=6, ge=1, le=20)
    request_timeout_seconds: int = Field(default=30, ge=1, le=120)
