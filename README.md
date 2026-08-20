# Wordle 猜单词游戏 🎯

AstrBot 群聊多人 Wordle 插件，支持彩色图片棋盘反馈、每日挑战和词云统计。

## 环境要求

- **Python** ≥ 3.10

### 依赖

| 包              | 最低版本   |
|----------------|--------|
| numpy          | 1.20   |
| Pillow         | 10.0.0 |
| pyspellchecker | 0.8.0  |
| wordcloud      | 1.9    |

## 安装

将插件文件夹放入 AstrBot 的 `data/plugins/` 目录下，重启机器人或通过插件管理面板热加载即可。

## 指令列表

| 指令                 | 别名                  | 说明                                  |
|--------------------|---------------------|-------------------------------------|
| `/wordle`          | `猜词` `wd`           | 开启一局 Wordle，支持 `-l` 长度、`-d` 词典      |
| `/absurdle`        | `wd_a`              | 对抗式无限猜词，支持 `-l` 长度、`-s` 难度；获胜答案计入词云 |
| `/wordle help`     | `猜词 help` `wd help` | 输出全部指令帮助                            |
| `/dailyword`       | `今日词汇` `dw`         | 每日挑战（每用户每天一次，计入词云；重复触发显示当天单词）       |
| `/guess <单词>`      | `g`                 | 提交猜测                                |
| `/hint`            | —                   | 获取棋盘提示（`*` 遮盖未揭晓字母，过半未定位时随机亮出一字母）   |
| `/dailyword reset` | `今日词汇 reset`        | 管理员重置当天每日挑战进度                       |
| `/stop_game`       | —                   | 管理员强制结束当前游戏                         |
| `/wordcloud`       | `词云` `wc`           | 生成历史猜测单词的词云图                        |

## 使用示例

```
/wordle                          # 默认 5 字母 CET4 单词
/wordle help                     # 查看指令帮助
/wordle -l 6 -d CET4             # 6 字母 CET4 单词
/wordle -l 4 -d TOEFL            # 4 字母 TOEFL 单词
/absurdle                        # 对抗式无限猜词（默认 normal 难度）
/absurdle -l 5 -s hard           # 5 字母 hard 难度
/dailyword                       # 今日词汇每日挑战
/guess apple                     # 猜测单词 apple
/hint                            # 获取提示
/dailyword reset                 # 管理员重置当天每日挑战进度
/stop_game                       # 管理员强制结束
/wordcloud                       # 查看词云
```

## 配置

插件通过 `_conf_schema.json` 声明配置项，可在 AstrBot 管理面板可视化调整：

| 配置项                   | 类型     | 默认值  | 说明                 |
|-----------------------|--------|------|--------------------|
| `timeout`             | int    | 300  | 普通局无操作超时秒数         |
| `default_length`      | int    | 5    | 默认单词长度（3~最大长度）     |
| `default_dict`        | string | CET4 | 默认词典               |
| `max_length`          | int    | 8    | 单词最大长度（6~10）       |
| `daily_reset_hour`    | int    | 4    | 每日挑战重置时间（UTC+8 小时） |
| `wordcloud_max_words` | int    | 50   | 词云最大单词数            |
| `hint_forced_ratio`   | float  | 0.5  | 半程援助触发阈值           |

## 功能特性

### 彩色棋盘

每次猜测后生成图片反馈，颜色规则与经典 Wordle 一致（绿=位置正确 / 黄=字母存在 / 灰=不存在），每日模式改用青蓝/珊瑚独立配色。

### 自定义词典

支持多词典切换（CET4、CET6、TOEFL、IELTS 等），也支持加载自定义词典：

1. 在 `wordle_data/custom_dict/` 目录下放置 JSON 文件
2. 文件名即为词典名称，内容格式：

```json
{
    "apple": {"中释": "苹果"},
    "grape": {"中释": "葡萄"}
}
```

1. 插件启动时自动扫描并加载，重启后可用 `/wordle -d <文件名>` 调用

### 其他机制

- **多人协同**：群聊中所有成员均可通过 `/guess` 参与同一局游戏，共同推理解谜
- **超时**：非每日模式对局 5 分钟无操作自动结束
- **半程援助**：`/hint` 猜测过半仍未定位到任何正确字母时，随机亮出一个位置的正确字母
- **每日挑战**：`/dailyword` 每天每用户限玩一次（UTC+8 凌晨 4:00 刷新），单词计入词云，重复触发显示当天已猜单词

### Absurdle 对抗模式

`/absurdle` 是 Wordle 的对抗式变体：不预设答案，每次猜测后保留对玩家最不利的候选子集，直到把候选集逼成 `{你的猜测}` 才算获胜。

- **难度**：`-s easy|normal|hard`（默认 `normal`）。easy 选中位候选桶、收束较快；normal/hard 偏向持久对抗
- **候选词池**：合并全部内置+自定义词典中该长度的单词（小写去重）
- **滑动窗口**：棋盘固定显示 `长度+1` 行，超出后滚动展示最近行
- **公共字母提示**：`/hint` 亮出所有候选在相同位置上的唯一字母
- **词云统计**：获胜时的答案词计入当前会话的词云

## 项目结构

```
astrbot_plugin_wordle_beta/
├── main.py              # 插件入口，指令注册与会话管理
├── engine.py            # 游戏核心逻辑（纯逻辑，零第三方依赖）
├── render.py            # 棋盘与提示渲染层（Pillow）
├── data_source.py       # 词典加载、拼写校验、数据持久化
├── wordcloud.py         # 词云生成与统计
├── requirements.txt     # 依赖清单
├── metadata.yaml        # 插件元信息
└── resources/
    ├── fonts/           # 棋盘字体 (KarnakPro-Bold.ttf)
    ├── words/           # 内置词典数据库 (wordle.db)
    ├── twitter_logo.png # 词云遮罩图
    └── twitter_logo.svg # 词云遮罩 SVG
```

## 技术说明

- 拼写校验基于 pyspellchecker `en` 语料库 (~49K 词)；词云以 Twitter Logo 为遮罩
- SQLite 存储词典数据，支持热加载自定义词典
- 跨词典随机抽词按单词去重，保证抽中概率均等

## 更新日志

版本更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 致谢

- 词库与棋盘卡片风格参考 [nonebot-plugin-wordle](https://github.com/noneplugin/nonebot-plugin-wordle) 项目

## 许可证

MIT