import random
from enum import Enum
from io import BytesIO
from typing import ClassVar, cast

from PIL import Image, ImageDraw, ImageFont

from .data_source import legal_word, load_font, save_png

_font: ImageFont.FreeTypeFont | None = None


def _get_font() -> ImageFont.FreeTypeFont:
    """Lazily load and cache the Wordle block font."""
    global _font
    if _font is None:
        _font = load_font(Wordle.FONT_NAME, Wordle.FONT_SIZE)
    return cast(ImageFont.FreeTypeFont, _font)


class GuessResult(Enum):
    WIN = 0  # 猜出正确单词
    LOSS = 1  # 达到最大可猜次数，未猜出
    DUPLICATE = 2  # 单词重复
    ILLEGAL = 3  # 单词不合法


class Wordle:
    # 默认配色（绿 / 黄 / 灰）
    CORRECT_COLOR: ClassVar[tuple[int, int, int]] = (134, 163, 115)
    EXIST_COLOR: ClassVar[tuple[int, int, int]] = (198, 182, 109)
    # 每日模式配色（青蓝 / 珊瑚 / 灰）
    DAILY_CORRECT_COLOR: ClassVar[tuple[int, int, int]] = (61, 165, 160)
    DAILY_EXIST_COLOR: ClassVar[tuple[int, int, int]] = (232, 115, 74)

    WRONG_COLOR: ClassVar[tuple[int, int, int]] = (123, 123, 124)
    BORDER_COLOR: ClassVar[tuple[int, int, int]] = (123, 123, 124)
    BG_COLOR: ClassVar[tuple[int, int, int]] = (255, 255, 255)
    FONT_COLOR: ClassVar[tuple[int, int, int]] = (255, 255, 255)

    BLOCK_SIZE: ClassVar[tuple[int, int]] = (40, 40)
    BLOCK_PADDING: ClassVar[tuple[int, int]] = (10, 10)
    PADDING: ClassVar[tuple[int, int]] = (20, 20)
    BORDER_WIDTH: ClassVar[int] = 2
    FONT_SIZE: ClassVar[int] = 20
    FONT_NAME: ClassVar[str] = "KarnakPro-Bold.ttf"

    def __init__(
        self, word: str, meaning: str, *, daily: bool = False, hint_ratio: float = 0.5
    ):
        self.word = word
        self.meaning = meaning
        self.word_lower = word.lower()
        self.length = len(word)
        self.rows = self.length + 1  # 可猜次数
        self.hint_ratio = hint_ratio
        self.guessed_words: list[str] = []
        self.result = f"【单词】：{self.word}\n【释义】：{self.meaning or '（暂无）'}"

        if daily:
            self.correct_color = self.DAILY_CORRECT_COLOR
            self.exist_color = self.DAILY_EXIST_COLOR
        else:
            self.correct_color = self.CORRECT_COLOR
            self.exist_color = self.EXIST_COLOR

        self.hint_forced = False  # 是否触发了半程援助（随机亮出一个正确字母）
        self.font = _get_font()

    def guess(self, word: str) -> GuessResult | None:
        word = word.lower()
        if word == self.word_lower:
            self.guessed_words.append(word)
            return GuessResult.WIN
        if word in self.guessed_words:
            return GuessResult.DUPLICATE
        if not legal_word(word):
            return GuessResult.ILLEGAL
        self.guessed_words.append(word)
        if len(self.guessed_words) >= self.rows:
            return GuessResult.LOSS
        return None

    # ---------- 绘制工具 ----------
    def _draw_block(self, color: tuple[int, int, int], letter: str = "") -> Image.Image:
        """绘制单个字母方块。"""
        block = Image.new("RGB", self.BLOCK_SIZE, self.BORDER_COLOR)
        inner_w = self.BLOCK_SIZE[0] - self.BORDER_WIDTH * 2
        inner_h = self.BLOCK_SIZE[1] - self.BORDER_WIDTH * 2
        inner = Image.new("RGB", (inner_w, inner_h), color)
        block.paste(inner, (self.BORDER_WIDTH, self.BORDER_WIDTH))

        if letter:
            letter_upper = letter.upper()
            draw = ImageDraw.Draw(block)
            bbox = self.font.getbbox(letter_upper)
            x = (self.BLOCK_SIZE[0] - bbox[2]) / 2
            y = (self.BLOCK_SIZE[1] - bbox[3]) / 2
            draw.text((x, y), letter_upper, font=self.font, fill=self.FONT_COLOR)
        return block

    def draw(self) -> BytesIO:
        """绘制完整的猜词棋盘。"""
        board_w = (
            self.length * self.BLOCK_SIZE[0]
            + (self.length - 1) * self.BLOCK_PADDING[0]
            + 2 * self.PADDING[0]
        )
        board_h = (
            self.rows * self.BLOCK_SIZE[1]
            + (self.rows - 1) * self.BLOCK_PADDING[1]
            + 2 * self.PADDING[1]
        )
        board = Image.new("RGB", (board_w, board_h), self.BG_COLOR)

        for row in range(self.rows):
            if row < len(self.guessed_words):
                guessed_word = self.guessed_words[row]
                # 构造位置记录：已正确匹配的字母标记为 '_'，其余保留原字母
                remaining_letters = list(self.word_lower)
                # 先标记绿色位置
                for i in range(self.length):
                    if guessed_word[i] == self.word_lower[i]:
                        remaining_letters[i] = "_"

                blocks: list[Image.Image] = []
                for i in range(self.length):
                    letter = guessed_word[i]
                    if letter == self.word_lower[i]:
                        color = self.correct_color
                    elif letter in remaining_letters:
                        # 消耗掉一个未匹配的字母，防止重复标记黄色
                        remaining_letters[remaining_letters.index(letter)] = "_"
                        color = self.exist_color
                    else:
                        color = self.WRONG_COLOR
                    blocks.append(self._draw_block(color, letter))
            else:
                blocks = [self._draw_block(self.BG_COLOR) for _ in range(self.length)]

            # 将本行方块粘贴到棋盘
            for col, block in enumerate(blocks):
                x = self.PADDING[0] + (self.BLOCK_SIZE[0] + self.BLOCK_PADDING[0]) * col
                y = self.PADDING[1] + (self.BLOCK_SIZE[1] + self.BLOCK_PADDING[1]) * row
                board.paste(block, (x, y))

        return save_png(board)

    def get_hint(self) -> str:
        """返回当前提示：已猜中的字母显示，未猜中的用 '*' 遮盖。

        若猜测次数超过一半仍未定位到任何字母，则随机亮出一个位置的正确字母作为半程援助。
        """
        revealed = set()
        for w in self.guessed_words:
            for letter in w:
                if letter in self.word_lower:
                    revealed.add(letter)

        hint = "".join(ch if ch in revealed else "*" for ch in self.word_lower)
        self.hint_forced = False
        if not revealed and len(self.guessed_words) / self.rows > self.hint_ratio:
            pos = random.randrange(self.length)
            hint = hint[:pos] + self.word_lower[pos] + hint[pos + 1 :]
            self.hint_forced = True
        return hint

    def draw_hint(self, hint: str) -> BytesIO:
        """绘制提示行。"""
        board_w = (
            self.length * self.BLOCK_SIZE[0]
            + (self.length - 1) * self.BLOCK_PADDING[0]
            + 2 * self.PADDING[0]
        )
        board_h = self.BLOCK_SIZE[1] + 2 * self.PADDING[1]
        board = Image.new("RGB", (board_w, board_h), self.BG_COLOR)

        for i, ch in enumerate(hint):
            letter = "" if ch == "*" else ch
            color = self.correct_color if letter else self.BG_COLOR
            x = self.PADDING[0] + (self.BLOCK_SIZE[0] + self.BLOCK_PADDING[0]) * i
            y = self.PADDING[1]
            board.paste(self._draw_block(color, letter), (x, y))
        return save_png(board)
