# 部署指南

本指南部署当前文字角色机器人。开发板负责模型，Windows电脑负责QQ、人格策略和联网搜索。电脑需要保持运行并登录Windows；不能只插着开发板就让QQ链路独立工作。

示例目录为Windows上的 `D:\projects\orangepi-rpg-aichat` 和板上的 `/opt/orangepi-rpg-aichat`。按自己的磁盘修改Windows路径。仓库不含模型权重、QQ程序、账号密码或登录缓存。

## 1. 准备环境

| 位置 | 要求 |
| --- | --- |
| 开发板 | 原机为AIpro 20T，Ubuntu 22.04 / AArch64，约24GB内存、4核CPU；9B模型与编译建议预留至少15GB磁盘 |
| Windows | Python 3.12+、Git、OpenSSH客户端、可访问GitHub和公开搜索；AstrBot完整依赖也会占用磁盘 |
| QQ | 自己可控制的机器人账号和一个用于测试的主号，机器人已加入目标群 |

当前是CPU GGUF路线，不需要重新安装CANN或刷写固件。其他硬件及后端需要另行适配，不把下述速度当作保证。

在Windows克隆并创建工具环境：

```powershell
git clone https://github.com/ericx-007/orangepi-rpg-aichat.git
cd orangepi-rpg-aichat
python -m venv .venv-pc
.\.venv-pc\Scripts\Activate.ps1
python -m pip install -r requirements-pc.txt
```

后续Windows命令均在仓库根目录、已激活 `.venv-pc` 的PowerShell中运行。下载失败时可换能访问上游的网络或使用离线安装包，不要把凭据写进下载地址。

## 2. 板端CPU后端与模型

在开发板克隆同一仓库，安装构建工具。以下命令在板端执行：

```bash
sudo apt-get update
sudo apt-get install -y git curl cmake build-essential python3-venv
git clone https://github.com/ericx-007/orangepi-rpg-aichat.git
cd orangepi-rpg-aichat
bash board/build-llama.sh
sudo bash board/install.sh
sudo install -m 0750 -o root -g orangepi-chat \
  llama-build/build/bin/llama-server /opt/orangepi-rpg-aichat/bin/llama-server
```

编译脚本固定经过验证的llama.cpp源码版本，核对归档哈希并按CPU特性选择ARM指令。编译在本机完成，默认两路并行。若板端不能访问GitHub，可以在电脑下载同一固定归档并校验后上传到 `llama-build/source.tar.gz`，编译脚本会复用它；APT及Python依赖也需通过可联网环境准备。

模型由部署者另行取得。原部署使用的文件、revision和SHA256见 [依赖说明](dependencies.md)。把完整GGUF文件放入板端 `models` 目录并验证：

```bash
sudo install -m 0640 -o root -g orangepi-chat /path/to/Qwen3.5-9B-Q4_K_M.gguf \
  /opt/orangepi-rpg-aichat/models/Qwen3.5-9B-Q4_K_M.gguf
sha256sum /path/to/Qwen3.5-9B-Q4_K_M.gguf
sudo nano /opt/orangepi-rpg-aichat/config/active-model.env
sudo systemctl enable --now orangepi-rpg-aichat.service
curl http://127.0.0.1:8000/health
```

编辑环境文件时，`GGUF_FILENAME` 必须与实际文件名一致。默认3个CPU线程、4096上下文、关闭思考。模型在开发板上就够了，电脑不必长期保留第二份权重。可从下载位置直接上传，确认板端哈希后自行清理下载副本。

`/health` 初期可显示 `loading`，等到 `ready` 再测试。API只监听板端回环地址；已有服务占用8000/18080时，先检查并处理端口冲突，不要同时启动两套实例。

```bash
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"local","messages":[{"role":"user","content":"17乘23等于多少？只答数字"}],"max_tokens":32,"stream":false}'
```

## 3. Windows到开发板的SSH转发

在Windows复制示例，填写自己的板端地址和SSH用户：

```powershell
Copy-Item config/ssh.example.conf config/ssh.local.conf
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\orangepi_chat"
```

把公钥安装到板端该用户的 `~/.ssh/authorized_keys`。登录用户必须允许转发到板端 `127.0.0.1:8000`；可使用仅允许这个目标的受限账户。私钥放在用户SSH目录，不能提交进仓库。

首次手工连接板端，核对其主机指纹并保存到默认 `known_hosts`。然后测试示例配置中的Host别名：

```powershell
ssh -F config/ssh.local.conf orangepi-local-llm
```

如果使用仅转发的受限账号，Shell登录被拒绝可以是预期行为，最终以转发测试为准。后台模式使用 `BatchMode yes`，需事先验证无需交互解锁的密钥认证路径。

启动并测试转发：

```powershell
.\experiments\qq-bridge\start-background.ps1 -Role tunnel
Invoke-RestMethod http://127.0.0.1:8000/health
```

浏览器访问 `http://127.0.0.1:8000/` 可先试文字聊天。SSH转发只绑定Windows本机，不需要向局域网开放模型端口。

## 4. 安装并初始化AstrBot

下载固定版本源码和官方面板，另建其运行环境：

```powershell
python experiments/qq-bridge/fetch-astrbot.py
python -m venv qq-runtime/astrbot-venv
.\qq-runtime\astrbot-venv\Scripts\python.exe -m pip install -r qq-runtime/astrbot/requirements.txt
.\qq-runtime\astrbot-venv\Scripts\python.exe -m pip install -r plugins/astrbot_plugin_orangepi_roleplay/requirements.txt
$env:ASTRBOT_ROOT = (Resolve-Path qq-runtime/astrbot).Path
Push-Location qq-runtime/astrbot
..\astrbot-venv\Scripts\python.exe main.py --webui-dir data/dist
```

首次启动生成 `data/cmd_config.json` 后按Ctrl+C停止，再执行 `Pop-Location` 回到仓库根目录。不要让这个初始化进程和后续后台实例同时运行。

复制部署配置并填写自己的号码：

```powershell
Copy-Item config/deployment.example.json config/deployment.local.json
notepad config/deployment.local.json
.\qq-runtime\astrbot-venv\Scripts\python.exe tools/configure.py
```

必须填写 `bot_qq`、`owner_qq`；`allowed_groups` 只填允许回复的群号。所有号码使用JSON字符串；群列表为空时仅允许主号私聊。`enable_bubbles` 默认false，需要主动冒泡时再改true。

配置工具会备份旧配置、复制本项目插件、生成独立随机管理密码和OneBot令牌，并设置原生白名单、关闭分段回复、600秒请求超时及160 token输出上限。它只处理本仓库下的运行目录，检测到该目录的AstrBot进程仍运行时会退出。

```powershell
.\experiments\qq-bridge\start-background.ps1 -Role astrbot
```

面板为 `http://127.0.0.1:6185/`。用户名和随机密码可在本机 `qq-runtime/state/astrbot-access.json` 查看。不要分享这个文件；不要把QQ密码填进配置。

## 5. NapCat扫码登录与OneBot连接

下载并校验固定版本的官方Windows Node运行包，准备本地面板：

```powershell
python tools/fetch-napcat.py
python tools/prepare-napcat.py
.\experiments\qq-bridge\start-background.ps1 -Role napcat
```

便携包在 `qq-runtime/napcat/`，首次下载不包含本人的登录态。若该固定资产在上游不可用，按[NapCat官方Shell指南](https://napneko.github.io/guide/boot/Shell)准备同版Windows Node目录，并确认含 `node.exe`、`index.js`、`napcat/` 及其要求的QQ运行文件；不要用Desktop版直接替代这个目录结构。

打开 `http://127.0.0.1:6099/`，从本机 `qq-runtime/state/config/webui.json` 取得面板令牌，扫码完成QQ登录及可能的安全验证。确认登录的是配置里的 `bot_qq` 后执行：

```powershell
python tools/connect-napcat.py
```

工具核对实际登录号，配置到 `ws://127.0.0.1:6199/ws` 的反向WebSocket，并设置该号的缓存自动登录。检测到其他启用的OneBot连接时会退出，需在面板中检查后再继续。

用主号私聊发送一道简单问题，再在允许的群中真实@机器人测试。不@、@全体和普通其他私聊都不应触发。关键词 `区` 可先测试消息链路而不等待模型。

## 6. 人格、搜索与日常调整

公开与私聊人格分别在插件目录的 `whale-public.txt`、`whale-private.txt`。先编辑仓库内示例，再停止本实例的AstrBot，运行 `tools/configure.py` 复制到运行插件目录，然后重新启动。该工具不清空聊天历史、联网开关或冒泡时间表。

日常目标一句10–30字；解释/搜索最多两句60字。这是提示词目标，160 tokens是用于完整结束的上限，不能保证每次都精确符合字数。检测到 `finish_reason=length` 时保留最后一个完整句末，或标记 `…（未完）`，不自动连续发续写。

联网初始开启。仅配置的主号私聊发送 `开启联网`、`关闭联网`、`联网状态` 可管理。授权会话显式 `搜一下 内容` 才触发；Windows需能访问Bing搜索和目标网页。最多读取两页正文并附来源；失败会直接说明，不假装查过。30次/日是本地防刷限制，可在 `web_search.py` 中统一调整相关预算与状态文案。

原生白名单、主号身份和群权限由代码及配置判断，聊天里自称管理员无效。不要通过添加人格提示词替代这些校验。

## 7. 开机启动与恢复

手动确认整条链路可用后，在已激活工具环境的PowerShell中执行：

```powershell
.\experiments\qq-bridge\install-supervisor.ps1
```

它为当前用户创建Windows登录启动项，隐藏运行守护并复用/启动SSH帮助程序、AstrBot和NapCat。使用时仍需登录这个Windows用户。程序只认领自己运行目录的进程，进程异常退出后逐步退避重启；模型、网络和SSH服务由板端负责恢复。

QQ进程恢复可尝试缓存登录；缓存过期、异地验证或账号限制时仍需在6099面板处理。守护不会用重启循环代替人工验证。Wi-Fi开机连接也应在板上事先配置并测试；校园网认证不属于本仓库的通用配置。

需要暂停守护但保留组件运行时创建 `qq-runtime/state/supervisor.stop`。停止组件前先停止守护，再运行：

```powershell
Set-Content qq-runtime/state/supervisor.stop 'manual maintenance'
python experiments/qq-bridge/stop-owned-background.py
```

停止脚本还会写入15分钟维护窗口；手动恢复组件可立即运行 `start-background.ps1 -Role all`，恢复守护可运行 `install-supervisor.ps1`，维护窗口结束后自动恢复看护。

## 8. 排错与验证

| 现象 | 检查 |
| --- | --- |
| 8000不可用 | 板端 `systemctl status orangepi-rpg-aichat`，Windows `logs/auto-tunnel-status.json` |
| 模型加载失败 | `journalctl -u orangepi-rpg-aichat -n 80`，板端 `logs/gguf-server.log`，模型文件/权限/环境配置 |
| QQ在线但不回 | 群白名单、真实@、主号、冷却、模型 `busy`；检查 `qq-runtime/state/astrbot.stderr.log` |
| 回答慢 | CPU预填充和生成速度；9B长人格可能等待几分钟。关键词不依赖模型 |
| 总回复两次 | 确认只有一个QQ连接/一个AstrBot实例、关闭分段回复；本插件已做消息去重 |
| 开机没启动 | Windows是否登录用户、启动项是否存在、Python环境是否仍在原位置 |
| QQ掉线 | 6099面板完成验证；不要公开登录态或完整日志 |

测试步骤见 [验证说明](verification.md)。这份公开部署脚本没有在一块清空后的新开发板上重新完整执行；原机实测与公开版自动测试分开列明。

更新代码前备份本地配置和运行数据；不要把整个 `qq-runtime/` 或日志上传GitHub。仓库默认忽略这些文件、SSH私钥、大模型和本地配置，但发布自己的改动时仍应检查暂存区。
