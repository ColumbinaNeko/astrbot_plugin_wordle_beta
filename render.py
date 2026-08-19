"""Wordle 棋盘渲染层：接收 BoardStyle 注入样式，渲染游戏状态为 PNG。"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from .data_source import load_font, save_png
from .engine import Absurdle, Wordle, _pattern


@dataclass(frozen=True)
class BoardStyle:
    block_size: tuple[int, int] = (40, 40)
    block_padding: tuple[int, int] = (10, 10)
    padding: tuple[int, int] = (20, 20)
    border_width: int = 2
    font_size: int = 20
    font_name: str = "KarnakPro-Bold.ttf"
    # 普通配色（绿 / 黄 / 灰）
    correct_color: tuple[int, int, int] = (134, 163, 115)
    exist_color: tuple[int, int, int] = (198, 182, 109)
    wrong_color: tuple[int, int, int] = (123, 123, 124)
    border_color: tuple[int, int, int] = (123, 123, 124)
    bg_color: tuple[int, int, int] = (255, 255, 255)
    font_color: tuple[int, int, int] = (255, 255, 255)


DEFAULT_STYLE = BoardStyle()
# 每日模式配色（青蓝 / 珊瑚）
DAILY_STYLE = BoardStyle(
    correct_color=(61, 165, 160),
    exist_color=(232, 115, 74),
)

_fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _get_font(style: BoardStyle) -> ImageFont.FreeTypeFont:
    """按 (font_name, font_size) 缓存字体，等价于原单例缓存。"""
    key = (style.font_name, style.font_size)
    if key not in _fonts:
        _fonts[key] = load_font(*key)
    return _fonts[key]


def _draw_block(
    color: tuple[int, int, int],
    letter: str,
    font: ImageFont.FreeTypeFont,
    style: BoardStyle,
) -> Image.Image:
    """绘制单个字母方块。"""
    block = Image.new("RGB", style.block_size, style.border_color)
    inner_w = style.block_size[0] - style.border_width * 2
    inner_h = style.block_size[1] - style.border_width * 2
    inner = Image.new("RGB", (inner_w, inner_h), color)
    block.paste(inner, (style.border_width, style.border_width))

    if letter:
        letter_upper = letter.upper()
        draw = ImageDraw.Draw(block)
        bbox = font.getbbox(letter_upper)
        x = (style.block_size[0] - bbox[2]) / 2
        y = (style.block_size[1] - bbox[3]) / 2
        draw.text((x, y), letter_upper, font=font, fill=style.font_color)
    return block


def _render_board(
    blocks_rows: list[list[Image.Image]],
    window: int | None,
    style: BoardStyle,
) -> BytesIO:
    """把方块行粘贴到棋盘。window 非空且行数超限时只取最后 window 行（滑动窗口）。"""
    rows = blocks_rows
    if not rows:
        return save_png(Image.new("RGB", (1, 1), style.bg_color))
    if window is not None and len(rows) > window:
        rows = rows[-window:]
    length = len(rows[0])
    board_w = (
        length * style.block_size[0]
        + (length - 1) * style.block_padding[0]
        + 2 * style.padding[0]
    )
    board_h = (
        len(rows) * style.block_size[1]
        + (len(rows) - 1) * style.block_padding[1]
        + 2 * style.padding[1]
    )
    board = Image.new("RGB", (board_w, board_h), style.bg_color)

    for row, blocks in enumerate(rows):
        for col, block in enumerate(blocks):
            x = style.padding[0] + (style.block_size[0] + style.block_padding[0]) * col
            y = style.padding[1] + (style.block_size[1] + style.block_padding[1]) * row
            board.paste(block, (x, y))

    return save_png(board)


def render_wordle_board(
    game: Wordle, style: BoardStyle, window: int | None = None
) -> BytesIO:
    """绘制完整的猜词棋盘。window 非空时对超出行数做滑动窗口截断。

    已猜行按 _pattern(guess, word_lower) 上色，与猜词反馈一致。
    """
    font = _get_font(style)
    blocks_rows: list[list[Image.Image]] = []
    for row in range(game.rows):
        if row < len(game.guessed_words):
            guessed = game.guessed_words[row]
            pat = _pattern(guessed, game.word_lower)
            blocks = [
                _draw_block(
                    (style.correct_color, style.exist_color, style.wrong_color)[pat[i]],
                    guessed[i],
                    font,
                    style,
                )
                for i in range(game.length)
            ]
        else:
            blocks = [
                _draw_block(style.bg_color, "", font, style) for _ in range(game.length)
            ]
        blocks_rows.append(blocks)

    return _render_board(blocks_rows, window, style)


def render_absurdle_board(
    game: Absurdle, style: BoardStyle, window: int | None = None
) -> BytesIO:
    """绘制棋盘：按已存 pattern 上色，随猜测数生长。

    默认窗口固定为 length + 1 行（与普通 Wordle 棋盘一致），超出后滚动只显示最近这些行。
    """
    if window is None:
        window = game.length + 1
    font = _get_font(style)
    blocks_rows: list[list[Image.Image]] = []
    for row, guessed_word in enumerate(game.guessed_words):
        pat = game.patterns[row]
        blocks = [
            _draw_block(
                (style.correct_color, style.exist_color, style.wrong_color)[pat[i]],
                guessed_word[i],
                font,
                style,
            )
            for i in range(game.length)
        ]
        blocks_rows.append(blocks)
    if not blocks_rows:
        # 开局空棋盘：渲染一行空白方块占位，避免 _render_board 索引越界
        blocks_rows = [
            [_draw_block(style.bg_color, "", font, style) for _ in range(game.length)]
        ]
    return _render_board(blocks_rows, window, style)


def render_hint(hint: str, style: BoardStyle) -> BytesIO:
    """绘制提示行：已揭晓字母用 correct_color 上色，'*' 用背景色。"""
    font = _get_font(style)
    length = len(hint)
    board_w = (
        length * style.block_size[0]
        + (length - 1) * style.block_padding[0]
        + 2 * style.padding[0]
    )
    board_h = style.block_size[1] + 2 * style.padding[1]
    board = Image.new("RGB", (board_w, board_h), style.bg_color)

    for i, ch in enumerate(hint):
        letter = "" if ch == "*" else ch
        color = style.correct_color if letter else style.bg_color
        x = style.padding[0] + (style.block_size[0] + style.block_padding[0]) * i
        y = style.padding[1]
        board.paste(_draw_block(color, letter, font, style), (x, y))
    return save_png(board)
