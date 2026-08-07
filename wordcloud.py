import json
import threading
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from wordcloud import WordCloud  # type: ignore[attr-defined]

from .data_source import _get_data_dir, fonts_dir

_FONT_PATH = str(fonts_dir / "KarnakPro-Bold.ttf")
_MASK_PATH = Path(__file__).parent / "resources" / "twitter_logo.png"

_COLORS = [
    (134, 163, 115),
    (198, 182, 109),
    (180, 130, 110),
    (110, 150, 180),
    (160, 130, 180),
    (180, 160, 110),
    (130, 170, 150),
]


def _get_stats_path() -> Path:
    return _get_data_dir() / "wordle_stats.json"


# record_word 现在线程池中执行，与 _load_stats 的读取并发，用锁保护读改写
_stats_lock = threading.Lock()


def _load_stats() -> dict[str, dict[str, int]]:
    """返回按会话隔离的词频统计；旧版扁平数据归入 "global" 会话。"""
    p = _get_stats_path()
    if not p.exists():
        return {}
    with _stats_lock:
        raw = json.loads(p.read_text(encoding="utf-8"))
    if not raw or any(isinstance(v, dict) for v in raw.values()):
        return raw
    return {"global": raw}


def _load_mask() -> np.ndarray | None:
    if not _MASK_PATH.exists():
        return None
    img = Image.open(_MASK_PATH).convert("RGBA")
    alpha = np.array(img.split()[-1])
    mask = np.where(alpha > 127, 0, 255).astype(np.uint8)
    return mask


def _color_func(_word, font_size, position, random_state=None, **__):
    _ = _word, font_size, position
    if random_state is None:
        import random

        return random.choice(_COLORS)
    return random_state.choice(_COLORS)  # type: ignore[union-attr]


def record_word(word: str, session_id: str) -> None:
    """按会话记录词频；旧版扁平数据归入 "global" 会话。"""
    p = _get_stats_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _stats_lock:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if raw and not any(isinstance(v, dict) for v in raw.values()):
                stats: dict[str, dict[str, int]] = {"global": raw}
            else:
                stats = raw
        else:
            stats = {}
        per_session = stats.setdefault(session_id, {})
        per_session[word] = per_session.get(word, 0) + 1
        p.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")


def generate_wordcloud(max_words: int = 50, session_id: str = "global") -> BytesIO:
    stats = _load_stats().get(session_id, {})
    if not stats:
        return _empty()

    wc = WordCloud(
        width=800,
        height=600,
        background_color=None,  # type: ignore[arg-type]
        mode="RGBA",
        font_path=_FONT_PATH,
        max_words=max_words,
        color_func=_color_func,
        prefer_horizontal=0.7,
        relative_scaling=0.5,  # type: ignore[arg-type]
        mask=_load_mask(),
        contour_width=0,
    )
    wc.generate_from_frequencies(stats)

    output = BytesIO()
    wc.to_image().save(output, format="PNG")
    output.seek(0)
    return output


def _empty() -> BytesIO:
    wc = WordCloud(
        width=800,
        height=200,
        background_color=None,  # type: ignore[arg-type]
        mode="RGBA",
        font_path=_FONT_PATH,
        max_words=1,
        mask=_load_mask(),
    )
    wc.generate_from_frequencies({"No data yet.": 1})
    output = BytesIO()
    wc.to_image().save(output, format="PNG")
    output.seek(0)
    return output
