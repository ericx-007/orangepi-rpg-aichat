# 现成短语音

当前功能播放预先录好的短台词。不会把模型生成的任意文字转换成这个声线，也没有训练好的专属TTS权重。公开版默认关闭，不分发第三方音频。

## 启用

先完成[基础部署](deployment.md)。停止本工作区的AstrBot，备份本地插件和配置。把 `config/deployment.local.json` 的 `enable_voice` 设为true，运行 `python tools/configure.py`。该工具会更新插件和本地开关，保留plugin_data；不要用空白示例替换已有账号配置。

在Windows运行目录创建素材文件夹：

```powershell
$voiceFolder = 'qq-runtime/astrbot/data/plugin_data/orangepi_roleplay/voice-pack'
New-Item -ItemType Directory -Force $voiceFolder
Copy-Item config/voice-pack.example.json "$voiceFolder/config.json"
```

把自己有权使用的WAV或MP3放入这个文件夹，修改config.json的clips数组：file是该目录中的相对文件名，text是录音实际台词，seconds填写实测时长且不超过8秒，triggers填写适合该录音回复的完整短句。bubble只给可以脱离问题独立播放的日常台词开启。attribution填写实际作者、许可和来源链接。只有几秒的素材也需要保留来源。

使用现有后台脚本启动：

```powershell
.\experiments\qq-bridge\start-background.ps1 -Role astrbot
```

群中真实@后发送“来句语音”“发条语音”或“说句语音”可试听，仍受语音限额。私聊不发送录音。修改素材配置后重启AstrBot加载，计数文件留在素材目录之外，不要删除。

## 触发与限频

- 合格的既有冒泡有20%概率替换为语音，继续沿用90–180分钟调度和原冒泡上限。
- 真实@消息精确匹配triggers时，有25%概率用对应录音替代文字；不会同时再请求一次模型回答。匹配时忽略首尾少量空白和标点。
- 语音合计每群每天最多3次尝试、两次至少隔30分钟，时间为北京时间10:00–23:00。手动请求也占额度。
- 白名单、真实@、去重和普通消息限速仍生效。免@接话、搜索、图片和不匹配的问题不随机播放录音。
- 每群当日首次使用前发送一次来源说明。语音与来源各是一条消息，之后同日只发语音。失败尝试和发送结果不确定时不立即重试。

素材缺失时普通聊天继续文字流程；显式语音请求不可用或受限时返回提示。声音不会由LLM伪造，也不会把固定录音声称为对任意问题的新回答。

## 原部署记录与边界

原机语音库来自 [YinZilu/da-fei-yu-girl-voice-zh](https://www.modelscope.cn/datasets/YinZilu/da-fei-yu-girl-voice-zh)，作者Yin Zilu Fantasy Studio（Bilibili），采用CC BY-NC 4.0。完整库有56段，约10MB，原部署保存于开发板；Windows只缓存挑选的4段短录音，共约0.83MiB，由NapCat编码发送。项目MIT许可证不覆盖这些素材。

已实际发送并回读确认过6.02秒录音。自动功能通过真实AstrBot与模拟OneBot验证，发送被本机截获：一次来源加一次record，音频哈希匹配语音库，重复消息与通知不补发。控制器测试使用程序生成的测试文件，不使用实际账号或第三方素材。

TTS方向审阅了 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 和 [CPUFast](https://github.com/baicai-1145/GPT-SoVITS-CPUFast)，后者固定到03706cce25085a3f2522679193dd437896e0be21。板端只下载预编译依赖的预检未找到jieba_fast的匹配AArch64二进制包，因此本次使用用户授权的录音备用方案。这不证明源码构建或完整TTS无法运行；没有生成新语音，也没有测得TTS速度。生产Torch/CANN没有被替换。

关闭时将enable_voice设为false、停止AstrBot后重跑配置并启动；也可把素材config.json的enabled设为false后重启。保留voice-state.json，重新启用时继续原有冷却。
