# 依赖与来源

仓库只包含本项目的 API、插件和部署脚本，不包含第三方运行包、模型权重或用户数据。

| 依赖 | 原部署验证版本 | 上游 |
| --- | --- | --- |
| AstrBot | 4.29.1，Python 3.12+ | [AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot)，AGPL-3.0-or-later |
| NapCat | 4.18.38，Windows Node 便携包 | [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.38) |
| llama.cpp | `339f3242c761f16c27e5ffcde1d35dcc31933a55` | [固定源码](https://github.com/ggml-org/llama.cpp/tree/339f3242c761f16c27e5ffcde1d35dcc31933a55)，MIT |
| 日常模型 | Qwen3.5-9B Q4_K_M | [原模型](https://huggingface.co/Qwen/Qwen3.5-9B)、[Unsloth GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) |

这些是已验证版本，不表示最新版本。升级外部组件后需要复查配置字段、OneBot 登录、模型模板和恢复行为。

## 模型文件

原机使用的 GGUF 来源与校验：

```text
repo: unsloth/Qwen3.5-9B-GGUF
revision: 3885219b6810b007914f3a7950a8d1b469d598a5
filename: Qwen3.5-9B-Q4_K_M.gguf
bytes: 5680522464
sha256: 03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8
```

请先阅读原模型与量化仓库的许可。下载时固定 revision，完成后核对 SHA256；若换文件，不能沿用这个校验值。本项目不会自动下载大模型。

## 编译源码

识图使用同一模型仓库与revision的 `mmproj-F16.gguf`，918166080字节，SHA256为 `f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f`。只对这组9B权重和投影器组合做过实测；其他模型需要各自匹配的投影器。

`board/build-llama.sh` 固定上述 llama.cpp commit，校验归档 SHA256 为 `901a2a2b2eb389a08cae3fec3269914f5c03e8d39b1352db9a29cbd1886727f3`，只编译 CPU 后端。参考[官方构建说明](https://github.com/ggml-org/llama.cpp/blob/339f3242c761f16c27e5ffcde1d35dcc31933a55/docs/build.md)。

Python依赖在 `board/requirements.txt`、`requirements-pc.txt` 和插件的 `requirements.txt` 中给出兼容范围。AstrBot 的完整依赖按其固定版本安装；这些范围不是完整的依赖锁文件。

## QQ 接入

使用普通 QQ 账号的 NapCat + OneBot v11 反向 WebSocket。它与 QQ 官方机器人平台是不同的接入方式；参考[AstrBot OneBot 接入文档](https://docs.astrbot.app/en/platform/aiocqhttp.html)。首次登录和账号安全验证由部署者在本地面板完成，仓库不处理 QQ 密码。
