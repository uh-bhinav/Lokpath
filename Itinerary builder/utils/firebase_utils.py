import os
from pathlib import Path


def get_service_account_path() -> str:
    """Return path to Firebase service account JSON key.

    Order of resolution:
    1. ``FIREBASE_SERVICE_ACCOUNT_PATH`` environment variable if it points to an
       existing file.
    2. ``credentials/lokpath-admin.json`` relative to the project root.

    Raises
    ------
    FileNotFoundError
        If neither location contains a valid credentials file.
    """

    env_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    if env_path:
        expanded = Path(env_path).expanduser().resolve()
        if expanded.is_file():
            return str(expanded)

    project_root = Path(__file__).resolve().parents[2]
    fallback = project_root / "credentials" / "lokpath-admin.json"
    if fallback.is_file():
        return str(fallback)

    raise FileNotFoundError(
        "Firebase credentials not found. Set the FIREBASE_SERVICE_ACCOUNT_PATH "
        "environment variable or place the service account key at "
        "'credentials/lokpath-admin.json'."
    )
