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

| 指令                 | 别名                  | 说明                                                   |
|--------------------|---------------------|------------------------------------------------------|
| `/wordle`          | `猜词` `wd`           | 开启一局 Wordle。支持 `-l` 指定长度、`-d` 指定词典                   |
| `/wordle help`     | `猜词 help` `wd help` | 输出全部指令的帮助信息                                          |
| `/dailyword`       | `今日词汇` `dw`         | 每日词汇挑战（每用户每天一次，计入词云；完成后再次触发显示当天单词）                   |
| `/guess <单词>`      | `g`                 | 提交猜测                                                 |
| `/hint`            | —                   | 获取当前棋盘提示（已揭示的字母用 `*` 遮盖未揭示部分；猜测过半仍未定位到字母时随机亮出一个正确位置） |
| `/dailyword reset` | `今日词汇 reset`        | 管理员重置自己当天的每日挑战进度                                     |
| `/stop_game`       | —                   | 管理员强制结束当前游戏                                          |
| `/wordcloud`       | `词云` `wc`           | 生成历史猜测单词的词云图                                         |

## 使用示例

```
/wordle                          # 默认 5 字母 CET4 单词
/wordle help                     # 查看指令帮助
/wordle -l 6 -d CET4             # 6 字母 CET4 单词
/wordle -l 4 -d TOEFL            # 4 字母 TOEFL 单词
/dailyword                       # 今日词汇每日挑战
/guess apple                     # 猜测单词 apple
/hint                            # 获取提示
/dailyword reset                 # 管理员重置当天每日挑战进度
/stop_game                       # 管理员强制结束
/wordcloud                       # 查看词云
```

## 配置

插件通过 `_conf_schema.json` 声明配置项，可在 AstrBot 管理面板可视化调整，配置文件保存于 `data/config/astrbot_plugin_wordle_beta_config.json`：

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `timeout` | int | 300 | 普通局无操作超时秒数 |
| `default_length` | int | 5 | 默认单词长度（3~最大长度） |
| `default_dict` | string | CET4 | 默认词典 |
| `max_length` | int | 8 | 单词最大长度（6~10） |
| `daily_reset_hour` | int | 4 | 每日挑战重置时间（UTC+8 小时） |
| `wordcloud_max_words` | int | 50 | 词云最大单词数 |
| `hint_forced_ratio` | float | 0.5 | 半程援助触发阈值 |

## 功能特性

### 彩色棋盘

每次猜测后生成图片反馈，颜色规则与经典 Wordle 一致：

- 🟩 **绿色** — 字母正确且位置正确
- 🟨 **黄色** — 字母存在但位置不对
- ⬜ **灰色** — 字母不在目标单词中

每日模式（`/dailyword`）使用独立配色：
- 🟦 **青蓝色** — 字母正确且位置正确
- 🟧 **珊瑚色** — 字母存在但位置不对
- ⬜ **灰色** — 字母不在目标单词中

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

3. 插件启动时自动扫描并加载，重启后可用 `/wordle -d <文件名>` 调用

### 超时机制

非每日模式下的游戏设有 5 分钟超时：无操作将自动结束当前对局，超时后需重新开局。

### 半程援助

`/hint` 在半程处提供保底线索：当猜测次数已超过总次数的一半，却仍未定位到任何正确字母时，提示会随机亮出一个位置的正确字母，帮助打破僵局。

### 每日挑战

`/dailyword` 每天每用户限玩一次（UTC+8 凌晨 4:00 刷新）。挑战单词同样计入词云统计，完成挑战后再触发 `/dailyword` 会显示当天已猜的单词。

### 多人协同

群聊中所有成员均可使用 `/guess` 参与同一局游戏，共同推理解谜。

## 项目结构

```
astrbot_plugin_wordle_beta/
├── main.py              # 插件入口，指令注册与会话管理
├── wordle.py            # 游戏核心逻辑与棋盘绘制
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

- 棋盘图片使用 Pillow 逐块绘制，尺寸自适应单词长度
- 拼写校验基于 pyspellchecker 的 `en` 语料库 (~49K 词)
- 词云以 Twitter Logo 为遮罩，配色与棋盘主题统一
- SQLite 存储词典数据，支持热加载自定义词典
- 跨词典随机抽词按单词去重，保证每个单词被抽中概率均等

## 更新日志

版本更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 致谢

- 默认词库来源于 [nonebot-plugin-wordle](https://github.com/noneplugin/nonebot-plugin-wordle) 项目
- Wordle 棋盘卡片风格参考同上项目设计

## 许可证

MIT