import json
import sqlite3
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFont
from pydantic import BaseModel, Field
from spellchecker import SpellChecker

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

data_dir = Path(__file__).resolve().parent / "resources"
fonts_dir = data_dir / "fonts"
words_dir = data_dir / "words"
_DB_PATH = words_dir / "wordle.db"


def _get_data_dir() -> Path:
    return Path(get_astrbot_plugin_data_path()) / "wordle_data"


_CUSTOM_DIR = _get_data_dir() / "custom_dict"

_spell = SpellChecker()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS words (dict_name TEXT NOT NULL, word TEXT NOT NULL, meaning TEXT, length INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custom_words (dict_name TEXT NOT NULL, word TEXT NOT NULL, meaning TEXT, length INTEGER NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dict_len ON words (dict_name, length)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_dict_len ON custom_words (dict_name, length)")


class CustomDictEntry(BaseModel):
    """A single word entry in a custom dictionary JSON file."""

    meaning: str = Field(alias="中释", default="")


def _sync_custom_dicts(conn: sqlite3.Connection) -> None:
    existing = {r[0] for r in conn.execute("SELECT DISTINCT dict_name FROM custom_words")}
    on_disk = set()
    _CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    for f in _CUSTOM_DIR.glob("*.json"):
        dict_name = f.stem
        on_disk.add(dict_name)
        if dict_name in existing:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        rows = []
        for word, entry in data.items():
            validated = CustomDictEntry.model_validate(entry) if isinstance(entry, dict) else CustomDictEntry()
            rows.append((dict_name, word, validated.meaning, len(word)))
        conn.executemany("INSERT INTO custom_words VALUES (?,?,?,?)", rows)
    for removed in existing - on_disk:
        conn.execute("DELETE FROM custom_words WHERE dict_name = ?", (removed,))


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    _sync_custom_dicts(conn)
    return conn


def _get_dic_list() -> list[str]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT dict_name FROM words "
            "UNION SELECT DISTINCT dict_name FROM custom_words ORDER BY dict_name"
        ).fetchall()
    return [r["dict_name"] for r in rows]


dic_list: list[str] = _get_dic_list()


def legal_word(word: str) -> bool:
    return not _spell.unknown((word,))


def random_word(dic_name: str = "CET4", word_length: int = 5) -> tuple[str, str]:
    with _get_conn() as conn:
        for table in ("words", "custom_words"):
            row = conn.execute(
                f"SELECT word, meaning FROM {table} WHERE dict_name = ? AND length = ? ORDER BY RANDOM() LIMIT 1",
                (dic_name, word_length),
            ).fetchone()
            if row:
                return row["word"], row["meaning"]
    raise ValueError(f"词典 {dic_name} 中不存在长度为 {word_length} 的单词")


def save_png(img: Image.Image) -> BytesIO:
    img = img.convert("RGBA")
    output = BytesIO()
    img.save(output, format="png")
    output.seek(0)
    return output


def random_word_all(min_len: int = 3, max_len: int = 8) -> tuple[str, str]:
    """从所有词典中随机选取一个长度在 [min_len, max_len] 区间的单词。"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT word, meaning FROM ("
            "SELECT word, meaning FROM words WHERE length BETWEEN ? AND ? "
            "UNION ALL "
            "SELECT word, meaning FROM custom_words WHERE length BETWEEN ? AND ?"
            ") ORDER BY RANDOM() LIMIT 1",
            (min_len, max_len, min_len, max_len),
        ).fetchone()
    if row is None:
        raise ValueError(f"所有词典中不存在长度为 {min_len}-{max_len} 的单词")
    return row["word"], row["meaning"]


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    font_path = fonts_dir / name
    return ImageFont.truetype(str(font_path), size, encoding="utf-8")
