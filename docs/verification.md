# 验证说明

整理自2026-10-21已运行的部署；公开版本整理于2026-10-22。

## 原部署实测

- 同一硬件上的9B Q4_K_M CPU模型完成真实文本问答，约1.6 tokens/s。
- 实际 AstrBot + 板端模型经过本地模拟 OneBot 验证，模拟端截获所有测试回复，未向真实群发送测试消息。
- 短回复测试为24、27、18字，分别生成16、20、15 tokens，均 `finish_reason=stop`，每次只发送一次。完整角色提示仍使每条等待约三分钟。
- 原服务实际正常重启开发板后恢复网络、SSH、模型及转发，约296秒就绪。QQ在Windows上持续在线。
- Windows进程恢复检查中，AstrBot约29秒恢复，QQ约5秒使用缓存恢复。没有做Windows整机重启或直接断电测试。

这些记录针对原机及当时组件版本。公开安装目录、服务名和账号配置已经泛化，没有在清空的新开发板上重新完成整套安装，也不保证QQ登录缓存永不失效。

## 公开版本测试

公开版本的33项测试已全部通过，Python编译、Bash和PowerShell语法检查也通过。完整测试使用合成QQ号和群号，搜索结果由受控测试页面代替。不会调用真实QQ发送接口，也不读取运行中的账号配置。

安装好AstrBot后，在仓库根目录运行：

```powershell
.\qq-runtime\astrbot-venv\Scripts\python.exe -m unittest discover -s tests -v
python -m compileall -q board plugins tools experiments auto-tunnel.py
```

开发时可以用环境变量 `ASTRBOT_SOURCE` 指向另一个已安装的同版本AstrBot源码目录，解释器也必须有相应依赖。`tests/bootstrap.py` 强制使用仓库内的合成身份，不采用部署的身份文件。

覆盖范围包括群白名单/真实@、主号私聊权限、通知和空消息、原生白名单先于历史隔离、重放拒绝、关键词不调用模型、联网开关和每日限频、网页正文与摘要区分、私有网络目标拒绝、低频冒泡及重启持久化、正常/截断回复处理、配置生成与上游默认配置保持。

GitHub Actions只运行不依赖AstrBot完整环境的策略和搜索测试、Python编译与Shell语法检查；完整框架事件测试按上面的本地步骤运行。CI不登录QQ、不下载模型、不运行板端性能测试。
