import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star

from .data_source import dic_list, random_word, random_word_all
from .wordcloud import generate_wordcloud, record_word
from .wordle import GuessResult, Wordle


@dataclass
class GameSession:
    game: Wordle
    is_daily: bool = False
    date_key: str = ""
    start_ts: float = 0.0
    timer_task: asyncio.Task | None = None
    umo: str = ""


class WordlePlugin(Star):
    TIMEOUT = 300

    def __init__(self, context: Context):
        super().__init__(context)
        self._games: dict[str, GameSession] = {}
        self._daily_used: dict[tuple[str, str], str] = {}
        logger.info(f"Wordle 插件加载成功，当前挂载词典: {', '.join(dic_list)}")

    # ==================== 核心指令集 ====================

    @filter.command("wordle", alias={"猜词", "wd"})
    async def cmd_wordle(self, event: AstrMessageEvent):
        """开始游戏，支持使用 -l 参数定义长度(3~8)，使用 -d 配置词典"""
        session_id = event.get_session_id()

        if session_id in self._games:
            yield event.plain_result(
                "当前已有正在进行的 Wordle 局，请在结束后重试，或由管理员使用 /stop_game 强开。"
            )
            return

        text = event.message_str.strip()
        length = 5
        dictionary = "CET4"

        if match_l := re.search(r"-l\s+(\d+)", text, re.I):
            length = int(match_l.group(1))
            if not (3 <= length <= 8):
                yield event.plain_result("规范限制：单词设定长度必须介于 3 到 8 之间。")
                return

        if match_d := re.search(r"-d\s+([A-Za-z0-9]+)", text, re.I):
            dictionary = match_d.group(1)
            if dictionary not in dic_list:
                yield event.plain_result(
                    f"抱歉，目标词典不可用。当前可用: {', '.join(dic_list)}"
                )
                return

        word, meaning = random_word(dictionary, length)
        record_word(word)
        game = Wordle(word, meaning)

        self._games[session_id] = GameSession(
            game=game,
            start_ts=time.time(),
            timer_task=asyncio.create_task(self._timeout_monitor(session_id)),
            umo=event.unified_msg_origin,
        )

        image_comp = self._create_image_component(game.draw())
        yield event.chain_result(
            [
                image_comp,
                Comp.Plain(
                    f"🎯 Wordle 战局已拉开！目标单词长度: {length}，你有 {game.rows} 次试错机会。\n"
                    "群内群友均可发送 /guess <单词> 协同猜词，发送 /hint 抽取面板提示。"
                ),
            ]
        )

    @filter.command("dailyword", alias={"今日词汇", "dw"})
    async def cmd_dailyword(self, event: AstrMessageEvent):
        """今日词汇每日挑战（每用户每天一次，UTC+8 凌晨 4:00 重置）"""
        user_id = event.get_sender_id()
        session_id = event.get_session_id()
        date_key = self._get_daily_date_key()

        if (user_id, date_key) in self._daily_used:
            yesterday_word = self._daily_used[(user_id, date_key)]
            yield event.plain_result(
                f"你今天的每日词汇挑战已结束，明日凌晨 4:00 刷新～\n今日单词：{yesterday_word}"
            )
            return

        if session_id in self._games:
            yield event.plain_result(
                "当前已有正在进行的 Wordle 局，请在结束后重试，或由管理员使用 /stop_game 强开。"
            )
            return

        word, meaning = random_word_all()
        record_word(word)
        game = Wordle(word, meaning)

        self._games[session_id] = GameSession(
            game=game,
            is_daily=True,
            date_key=date_key,
        )

        image_comp = self._create_image_component(game.draw())
        yield event.chain_result(
            [
                image_comp,
                Comp.Plain(
                    f"📅 今日词汇挑战开始！目标单词长度: {game.length}，你有 {game.rows} 次试错机会。\n"
                    "发送 /guess <单词> 进行猜测。"
                ),
            ]
        )

    @filter.command("guess", alias={"g"})
    async def cmd_guess(self, event: AstrMessageEvent):
        """提交你的猜测结果，成功提交将无缝刷新全局计时器"""
        session_id = event.get_session_id()
        game_info = self._get_game(session_id)
        if game_info is None:
            yield event.plain_result(
                "本会话当前未开启任何 Wordle 游戏，请先发送 /wordle 或 /dailyword 开局～"
            )
            return

        is_daily = game_info.is_daily
        if not is_daily and self._is_timed_out(game_info):
            _, msg = await self._stop_game(session_id)
            yield event.plain_result(msg)
            return

        game = game_info.game

        parts = event.message_str.strip().split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result("参数格式不规范，请使用：/guess <你猜的英文单词>")
            return

        word = parts[1].strip().lower()
        if len(word) != game.length:
            yield event.plain_result(
                f"长度校验不匹配，当前关卡的单词长度应该为 {game.length} 位。"
            )
            return

        result = game.guess(word)
        if result == GuessResult.DUPLICATE:
            yield event.plain_result("该词已被同伴或你自己测试过了，换个方向吧～")
            return
        elif result == GuessResult.ILLEGAL:
            yield event.plain_result(f"经检验，'{word}' 并非一个合法的标准英文词汇。")
            return

        if not is_daily:
            self._reset_timer(session_id)

        image_comp = self._create_image_component(game.draw())

        if result == GuessResult.WIN:
            if is_daily:
                self._end_daily_game(session_id, event.get_sender_id())
            else:
                await self._stop_game(session_id)
            yield event.chain_result(
                [image_comp, Comp.Plain(f"🎉 绝佳！成功解锁正确答案！\n{game.result}")]
            )
        elif result == GuessResult.LOSS:
            if is_daily:
                self._end_daily_game(session_id, event.get_sender_id())
            else:
                await self._stop_game(session_id)
            yield event.chain_result(
                [
                    image_comp,
                    Comp.Plain(f"😭 很遗憾，本局的所有试错额度已用尽。\n{game.result}"),
                ]
            )
        else:
            remaining = game.rows - len(game.guessed_words)
            yield event.chain_result(
                [image_comp, Comp.Plain(f"提交成功，你还剩下 {remaining} 次猜测机会。")]
            )

    @filter.command("hint")
    async def cmd_hint(self, event: AstrMessageEvent):
        """提取基于当前棋盘的进度提示线索"""
        session_id = event.get_session_id()
        game_info = self._get_game(session_id)
        if game_info is None:
            yield event.plain_result("没有正在进行中的战局。")
            return

        if not game_info.is_daily and self._is_timed_out(game_info):
            _, msg = await self._stop_game(session_id, timed_out=True)
            yield event.plain_result(msg)
            return

        hint = game_info.game.get_hint()
        if not hint.replace("*", "").strip():
            yield event.plain_result(
                "棋盘上还没有出现过定位正确的已知字母，无法生成有效提示线索，再猜一下试试吧！"
            )
            return

        image_comp = self._create_image_component(game_info.game.draw_hint(hint))
        yield event.chain_result([image_comp])

    @filter.command("stop_game")
    async def cmd_stop(self, event: AstrMessageEvent):
        """强制注销并解密当前游戏面板（仅管理员可用）"""
        if not event.is_admin():
            yield event.plain_result(
                "权限拦截：该强拆指令属于特权指令，仅管理员允许调用。"
            )
            return

        session_id = event.get_session_id()
        game_info = self._get_game(session_id)
        if game_info is None:
            yield event.plain_result("当前会话环境一片安宁，并没有活动中的 Wordle 局。")
            return

        if game_info.is_daily:
            game = self._end_daily_game(session_id, event.get_sender_id())
            yield event.plain_result(
                f"今日词汇挑战已强制结束。\n{game.result}"
            )
            return

        _, msg = await self._stop_game(session_id)
        yield event.plain_result(f"游戏已被管理员强制清除。\n{msg}")

    @filter.command("wordcloud", alias={"词云", "wc"})
    async def cmd_wordcloud(self, event: AstrMessageEvent):
        img_bytes = generate_wordcloud()
        img_comp = self._create_image_component(img_bytes)
        yield event.chain_result([img_comp, Comp.Plain("Wordle 词云")])

    # ==================== 内部辅助方法 ====================

    def _get_game(self, session_id: str) -> GameSession | None:
        return self._games.get(session_id)

    @staticmethod
    def _get_daily_date_key() -> str:
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        if now.hour < 4:
            now = now - timedelta(days=1)
        return now.strftime("%Y%m%d")

    def _is_timed_out(self, session: GameSession) -> bool:
        return time.time() - session.start_ts > self.TIMEOUT

    def _end_daily_game(self, session_id: str, user_id: str) -> Wordle:
        info = self._games.pop(session_id)
        self._daily_used[(user_id, info.date_key)] = info.game.word
        return info.game

    def _reset_timer(self, session_id: str) -> None:
        session = self._games[session_id]
        old_task = session.timer_task
        if old_task is not None and not old_task.done():
            old_task.cancel()
        session.timer_task = asyncio.create_task(self._timeout_monitor(session_id))
        session.start_ts = time.time()

    @staticmethod
    def _create_image_component(img_data: bytes | BytesIO) -> Comp.Image:
        """Wrap raw image bytes as an AstrBot Image component."""
        if isinstance(img_data, BytesIO):
            return Comp.Image.fromIO(img_data)
        return Comp.Image.fromBytes(img_data)

    async def _stop_game(
        self, session_id: str, timed_out: bool = False
    ) -> tuple[Wordle | None, str]:
        """安全终止指定会话的游戏，同步注销其关联的全局超时计时任务"""
        if session_id not in self._games:
            return None, ""

        game_info = self._games.pop(session_id)
        game = game_info.game
        timer_task = game_info.timer_task

        if timer_task is not None:
            timer_task.cancel()

        msg = "⏳ 猜单词超时（5分钟无操作），游戏结束。" if timed_out else "游戏已结束。"
        if game.guessed_words:
            msg += f"\n{game.result}"

        return game, msg

    async def _timeout_monitor(self, session_id: str):
        """后台异步守候任务，监听单次猜测或新局的5分钟生命周期"""
        try:
            await asyncio.sleep(self.TIMEOUT)
            if session_id not in self._games:
                return

            game_info = self._games[session_id]
            umo = game_info.umo

            game, msg = await self._stop_game(session_id, timed_out=True)
            if msg:
                await self.context.send_message(umo, MessageChain([Comp.Plain(msg)]))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Wordle 异步计时触发器异常: {e}")

    async def terminate(self):
        """插件热卸载、生命周期终止前的终末异步任务清理"""
        logger.info("Wordle 插件正在卸载，准备异步清扫所有进行中的计时状态机...")
        for _session_id, game_info in list(self._games.items()):
            task = game_info.timer_task
            if task is None:
                continue
            if not task.done():
                task.cancel()
            logger.info(f"已强制切断会话 {_session_id} 的关联异步计时线程。")
        self._games.clear()
