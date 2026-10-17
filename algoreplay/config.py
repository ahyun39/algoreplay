"""Settings come from environment variables; a `.env` file in the project root is loaded if present."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / ".env"):
    """Minimal KEY=VALUE loader. Variables already set in the environment win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env(name, default=None):
    """Read at call time so tests and the UI can change settings without re-importing."""
    return os.getenv(name) or default


load_dotenv()
