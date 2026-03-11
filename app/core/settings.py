from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./market_analyzer.db")
    csv_fallback_path: str = Field(default="data/synthetic_djinni_vacancies_updated.csv")
    enable_remote_sources: bool = Field(default=True)

    remotive_api_url: str = Field(default="https://remotive.com/api/remote-jobs")
    remotive_limit: int = Field(default=1000)

    adzuna_enabled: bool = Field(default=False)
    adzuna_api_url: str = Field(default="https://api.adzuna.com/v1/api/jobs")
    adzuna_app_id: str | None = Field(default=None)
    adzuna_app_key: str | None = Field(default=None)
    adzuna_country: str = Field(default="gb")
    adzuna_results_per_page: int = Field(default=50)

    arbeitnow_enabled: bool = Field(default=False)
    arbeitnow_api_url: str = Field(default="https://www.arbeitnow.com/api/job-board-api")
    arbeitnow_max_pages: int = Field(default=10)

    remoteok_enabled: bool = Field(default=True)
    remoteok_api_url: str = Field(default="https://remoteok.com/api")

    hf_linkedin_enabled: bool = Field(default=True)
    hf_linkedin_limit: int = Field(default=33246)

    hf_7m_enabled: bool = Field(default=True)
    hf_7m_limit: int = Field(default=80000)

    ollama_base_url: str = Field(default="http://127.0.0.1:11434")
    ollama_model: str = Field(default="mistral:7b-instruct")
    ollama_timeout_seconds: int = Field(default=300)
    llm_provider: str = Field(default="ollama")
    llm_api_base_url: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None)
    llm_api_model: str | None = Field(default=None)
    llm_api_referer: str | None = Field(default=None)
    llm_api_title: str | None = Field(default="Market Analyzer App")
    assistant_llm_enabled: bool = Field(default=True)
    assistant_max_tokens: int = Field(default=192)
    assistant_temperature: float = Field(default=0.2)

    refresh_on_startup: bool = Field(default=False)
    refresh_interval_minutes: int = Field(default=360)
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost,http://127.0.0.1"
    )
    cors_allow_origin_regex: str = Field(default=r"https?://(localhost|127\.0\.0\.1|.*\.onrender\.com)(:\d+)?")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
