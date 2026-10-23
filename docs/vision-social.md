# 识图、表情包与低频接话

这些功能在公开配置中默认关闭。先完成[基础部署](deployment.md)，修改前备份本地配置和插件，停止对应服务再更新文件。不要覆盖账号登录态或 `plugin_data/orangepi_roleplay` 中的活动计数。

## 启用识图

当前GGUF模型需要原生支持视觉，且必须搭配同版本投影器。[依赖说明](dependencies.md)列出了原机验证的9B组合及校验值。不要把其他型号的mmproj混用。

在板端校验文件后安装：

```bash
sha256sum /path/to/mmproj-F16.gguf
sudo install -m 0640 -o root -g orangepi-chat /path/to/mmproj-F16.gguf \
  /opt/orangepi-rpg-aichat/models/mmproj-F16.gguf
sudo nano /opt/orangepi-rpg-aichat/config/active-model.env
```

在该环境文件加入这一行，然后重启服务：

```text
GGUF_MMPROJ_PATH=/opt/orangepi-rpg-aichat/models/mmproj-F16.gguf
```

```bash
sudo systemctl restart orangepi-rpg-aichat
curl http://127.0.0.1:8000/health
```

等待 `status=ready`、`modality=text+image`。Windows本地部署配置设置 `enable_vision=true`，停AstrBot后重跑 `python tools/configure.py`，再用既有后台脚本启动。配置工具会备份旧插件和配置，并保留插件数据目录；如果曾直接修改运行目录内的activities.json或人格，请先备份并把所需修改合并到仓库插件源码，避免被配置工具覆盖。

群内在同一条消息中真实@机器人、附一张图片和问题；授权主号私聊可直接发图。程序处理最长边448像素的单图，GIF只取第一帧。小字和复杂细节可能看错。下载限制12MB/20秒，只接受受控QQ图片域名，包括gchat.qpic.cn和multimedia.nt.qq.com.cn。无法下载或读取时直接提示，不让模型猜测。旧图片不会在后续聊天中重传。

API兼容 `content=[{"type":"text","text":"图里是什么？"},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]`，一次请求最多一张，仅支持用户消息中的内嵌JPEG/PNG/WebP，不替客户端访问任意图片网址。浏览器页面仍是文字输入。

## 启用接话和表情

在 `config/deployment.local.json` 中按需设置下列布尔开关，停止AstrBot后重跑配置工具，再启动：

```json
{
  "enable_passive": true,
  "enable_stickers": true,
  "enable_bubbles": true
}
```

这段仅展示新增字段，需合并进已有完整配置。接话和表情开关写入插件本地settings.local.json；冒泡开关写入activities.json。

将自己有权使用的GIF放入仓库插件的 `stickers/` 后再配置，或直接放入部署后的插件目录。仓库不附第三方图片，空素材目录不会发送图片。升级时自行备份这些素材。

| 行为 | 限制 |
| --- | --- |
| 免@接话 | 合格普通消息3%概率，每群至少隔20分钟、每天最多4次尝试 |
| 回复附GIF | 普通文字回复12%概率，图文合并为同一条消息 |
| 随机冒泡 | 90–180分钟、每群每日最多3次；30%概率用GIF替代短文字 |
| GIF总量 | 每群至少隔15分钟、每天最多6次尝试 |
| 时间 | 上述主动活动仅北京时间10:00–23:00 |

接话跳过命令、搜索、带@、引用和图片消息，并继续经过原有白名单、限速、去重和模型就绪检查。图文合并走一次OneBot发送。搜索、识图和包含部分严肃/悲伤关键词的回复不随机附图；关键词不能覆盖所有语境。计数在尝试前持久化，不因重启或不确定的发送结果立即重试。不收集群友图片，也不调用额外判断模型。

## 性能与回退

固定人格前缀和动态时间已分开，缓存只复用模型计算，不复用旧答案。原机普通QQ文字实测约31秒，完整人格冷缓存识图约262秒、缓存命中后约57秒；不同问题和缓存状态会改变耗时。这些仍是CPU推理，不代表NPU已适配。

关闭三个社交开关后重跑配置，可恢复仅真实@触发。关闭QQ识图时设置 `enable_vision=false`；若也要卸载板端视觉组件，移除环境文件的GGUF_MMPROJ_PATH后重启模型服务。完整代码回退时，恢复备份的板端应用、插件和配置，同时保留账号及活动状态。

审阅过的社区方案包括[表情包管理器](https://github.com/anka-afk/astrbot_plugin_meme_manager)和[业镜主动回复](https://github.com/chengzhi-c/astrbot_plugin_self_initiated_reply)。前者适合需要素材管理界面时评估；后者使用额外判断模型，会增加当前CPU部署的推理量。本项目保留轻量概率控制，没有捆绑这两个插件。
