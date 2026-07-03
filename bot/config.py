from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    database_url: str = ""
    groq_api_key: str = ""
    groq_model: str = "mixtral-8x7b-32768"
    node_env: str = "development"
    port: int = 3000
    admin_telegram_ids: str = ""

    @property
    def admin_ids(self) -> list[int]:
        if not self.admin_telegram_ids:
            return []
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
