from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ============================================================
    # LOG FILE LOCATION
    # ============================================================
    # Your large FreeSWITCH logs stay on the Z: drive.
    # They do NOT need to be copied into the project.
    log_dir: Path = Path(
        r"Z:\Downloads\event_logs_10_08_2026\EVENT_LOG_SMALL"
    )

    # ============================================================
    # CALL HISTORY DATABASE
    # ============================================================
    history_db: Path = Path("call_history.db")

    # ============================================================
    # ELASTICSEARCH
    # ============================================================
    elasticsearch_url: str | None = None
    elasticsearch_index: str | None = None
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None

    # ============================================================
    # KAFKA
    # ============================================================
    kafka_brokers: str | None = None
    kafka_topic: str | None = None
    kafka_group_id: str = "xlogix-call-tracer"

    # ============================================================
    # PYDANTIC SETTINGS
    # ============================================================
    model_config = SettingsConfigDict(
        env_prefix="CALL_TRACE_",
        env_file=".env",
        extra="ignore",
    )


# ================================================================
# APPLICATION SETTINGS INSTANCE
# ================================================================
settings = Settings()