from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = BACKEND_ROOT / "storage"
SQLITE_DB_PATH = STORAGE_DIR / "creatorlens.db"
