"""CivicLens Ethiopia — central configuration.

Everything is driven by environment variables (prefix CL_) so the same code
runs against SQLite (dev) or PostgreSQL (prod), local disk or S3 storage,
console e-mail or SMTP, in-process worker or Redis queue.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- core ---
    app_name: str = "CivicLens Ethiopia"
    env: str = "development"                       # development | production
    secret_key: str = "dev-secret-change-me"       # override in prod!
    session_ttl_hours: int = 24 * 14

    # --- database (any SQLAlchemy URL: sqlite, postgresql+psycopg://...) ---
    database_url: str = "sqlite:///./civiclens.db"

    # --- storage ---
    storage_backend: str = "local"                 # local | s3
    storage_dir: str = "./storage"                 # local backend root
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # --- uploads ---
    max_video_mb: int = 100
    max_image_mb: int = 10
    max_video_seconds: int = 300           # reject extremely long videos
    max_attachments: int = 6               # per report
    allowed_video_types: str = "video/mp4,video/webm,video/quicktime"
    allowed_image_types: str = "image/jpeg,image/png,image/webp"

    # --- AI service ---
    ai_service_url: str = "http://127.0.0.1:8090"  # local FastAPI AI service
    ai_frames_per_video: int = 3
    ai_model_name: str = ""                        # informational override
    ai_conf_high: float = 0.75                     # >= high: normal review
    ai_conf_low: float = 0.5                       # < low: manual classification required

    # --- jobs ---
    job_backend: str = "thread"                    # thread | redis
    redis_url: str = "redis://localhost:6379/0"
    job_max_attempts: int = 3
    job_backoff_base_s: int = 5

    # --- notifications ---
    email_backend: str = "console"                 # console | smtp
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = True
    email_from: str = "no-reply@civiclens.et"
    email_from_name: str = "CivicLens Ethiopia"

    # --- rate limiting ---
    rate_limit_reports_per_hour: int = 10
    rate_limit_auth_per_minute: int = 10

    # --- account lockout ---
    login_max_failures: int = 8
    login_lock_minutes: int = 15

    # --- privacy ---
    public_coord_decimals: int = 4                 # ~11 m fuzz for public map
    sensitive_coord_decimals: int = 3              # ~110 m for sensitive categories
    sensitive_categories: str = "Education,Safety"
    retention_days: int = 0                        # 0 = keep forever (configurable)


    # --- cities (comma separated; first one is the default) ---
    cities: str = "Addis Ababa,Adama,Bahir Dar,Hawassa,Mekelle,Dire Dawa,Gondar,Jimma"
    default_city_lat: float = 9.0108
    default_city_lng: float = 38.7613

    # --- duplicate detection ---
    duplicate_radius_m: int = 150
    duplicate_window_days: int = 7

    frontend_dist: str = "../frontend/dist"

    class Config:
        env_prefix = "CL_"
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
