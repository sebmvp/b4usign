from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "data"
USER_AGENT = "before-you-sign/0.1 (local research; sebmvp)"


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://bys:bys@localhost:5433/before_you_sign",
    )


def engineering_enabled() -> bool:
    return os.environ.get("BYS_EXPOSE_ENGINEERING", "1") == "1"
