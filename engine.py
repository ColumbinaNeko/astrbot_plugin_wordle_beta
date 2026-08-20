"""Wordle 猜词引擎：纯逻辑，零第三方依赖。

不 import 本包任何模块、不 import PIL；校验与释义通过构造参数注入。
"""

import random
from collections.abc import Callable
from enum import Enum


class GuessResult(Enum):
    WIN = 0  # 猜出正确单词
    LOSS = 1  # 达到最大可猜次数，未猜出
    DUPLICATE = 2  # 单词重复
    ILLEGAL = 3  # 单词不合法


def _pattern(guess: str, cand: str) -> tuple[int, ...]:
    """绿/黄/灰判定：0=绿 1=黄 2=灰。两遍扫描防重复字母重复标黄。"""
    remaining = list(cand)
    pat = [2] * len(cand)
    for i in range(len(cand)):
        if guess[i] == cand[i]:
            pat[i] = 0
            remaining[i] = "_"
    for i in range(len(cand)):
        if pat[i] == 0:
            continue
        if guess[i] in remaining:
            remaining[remaining.index(guess[i])] = "_"
            pat[i] = 1
    return tuple(pat)


def apply_hint_forced(game: "Wordle", hint: str) -> tuple[str, bool]:
    """半程援助：hint 全 '*' 且已猜次数过半(hint_ratio)时随机亮一字母，返回 (新hint, 是否触发)。"""
    if hint.replace("*", "") or len(game.guessed_words) / game.rows <= game.hint_ratio:
        return hint, False
    pos = random.randrange(game.length)
    return hint[:pos] + game.word_lower[pos] + hint[pos + 1 :], True


class Wordle:
    def __init__(
        self,
        word: str,
        meaning: str,
        *,
        hint_ratio: float = 0.5,
        is_valid: Callable[[str], bool] = lambda _: True,
    ):
        self.word = word
        self.meaning = meaning
        self.word_lower = word.lower()
        self.length = len(word)
        self.rows = self.length + 1
        self.hint_ratio = hint_ratio
        self.is_valid = is_valid
        self.guessed_words: list[str] = []
        self.result = f"『单词』：{self.word}\n『释义』：{self.meaning or '(?)'}"

    def guess(self, word: str) -> GuessResult | None:
        word = word.lower()
        if word == self.word_lower:
            self.guessed_words.append(word)
            return GuessResult.WIN
        if word in self.guessed_words:
            return GuessResult.DUPLICATE
        if not self.is_valid(word):
            return GuessResult.ILLEGAL
        self.guessed_words.append(word)
        if len(self.guessed_words) >= self.rows:
            return GuessResult.LOSS
        return None

    def get_hint(self) -> str:
        """纯提示：已猜中且属于答案的字母显示，其余 '*'（半程援助见 apply_hint_forced）。"""
        revealed = set()
        for w in self.guessed_words:
            for letter in w:
                if letter in self.word_lower:
                    revealed.add(letter)
        return "".join(ch if ch in revealed else "*" for ch in self.word_lower)


class Absurdle:
    """对抗式无限猜词：不预设答案，每猜一次保留对玩家最不利的候选子集。

    不限制猜测次数；难度影响选桶策略（见 _pick_bucket）。
    """

    def __init__(
        self,
        candidates: list[str],
        length: int,
        *,
        difficulty: str = "normal",
        hint_ratio: float = 0.5,
        is_valid: Callable[[str], bool] = lambda _: True,
        meaning_of: Callable[[str], str] = lambda _: "",
    ):
        self.candidates = list(candidates)
        self.length = length
        self.difficulty = difficulty
        self.hint_ratio = hint_ratio
        self.is_valid = is_valid
        self._meaning_of = meaning_of
        self.guessed_words: list[str] = []
        self.patterns: list[tuple[int, ...]] = []  # 每次猜测实际反馈
        self.result = ""

    def guess(self, word: str) -> GuessResult | None:
        """提交猜测。候选集收束为 {猜测} 时返回 WIN，其余情况永不结束。"""
        word = word.lower()
        if word in self.guessed_words:
            return GuessResult.DUPLICATE
        if not self.is_valid(word):
            return GuessResult.ILLEGAL

        buckets: dict[tuple[int, ...], list[str]] = {}
        for cand in self.candidates:
            buckets.setdefault(_pattern(word, cand), []).append(cand)

        chosen = self._pick_bucket(buckets)
        self.candidates = chosen
        self.guessed_words.append(word)
        self.patterns.append(self._bucket_pattern(word, chosen))

        if len(self.candidates) == 1 and self.candidates[0] == word:
            meaning = self._meaning_of(word)
            self.result = f"『单词』：{word}\n『释义』：{meaning or '(?)'}"
            return GuessResult.WIN
        return None

    @staticmethod
    def _bucket_pattern(guess: str, bucket: list[str]) -> tuple[int, ...]:
        """选中的桶对应的反馈（桶内候选与猜测的 pattern 相同，取第一个）。"""
        return _pattern(guess, bucket[0])

    def _pick_bucket(self, buckets: dict[tuple[int, ...], list[str]]) -> list[str]:
        """按难度选桶；pattern 字典序 0(绿)<1(黄)<2(灰)。"""
        if self.difficulty == "easy":
            # 中位桶：收束较快但有过程，避免大词池下最小桶导致秒赢
            items = sorted(buckets.items(), key=lambda kv: (len(kv[1]), kv[0]))
            return items[len(items) // 2][1]
        if self.difficulty == "hard":
            # 最大桶；平手选灰更多
            return max(buckets.items(), key=lambda kv: (len(kv[1]), kv[0]))[1]
        # normal：最大桶；平手选绿更多
        return max(
            buckets.items(), key=lambda kv: (len(kv[1]), tuple(-x for x in kv[0]))
        )[1]

    def get_hint(self) -> str:
        """公共字母提示：某位置在所有剩余候选中的字母唯一时亮出，否则 '*'。"""
        positions = [{c[i] for c in self.candidates} for i in range(self.length)]
        return "".join((next(iter(s)) if len(s) == 1 else "*") for s in positions)
