# 实际环境版本记录 · 2026-10-10

产品：CunBo YunJian / 村播云剪。下载或配置不等于真实样本验收。

| 组件 | 版本／来源 | 当前验证 |
| --- | --- | --- |
| Python 隔离环境 | 3.10.22，conda-forge | 解释器正常启动 |
| FFmpeg | 9.0.1 | 实际裁剪、拼接及 A/V 时间检查通过 |
| ImageMagick | 7.1.2-26 | MoviePy 中文硬字幕渲染通过 |
| MoviePy | 1.0.3 | 本地备用环境真实渲染通过；3.10 环境依赖安装完成 |
| jieba | 0.42.1 | 自定义词典与原话保留测试通过 |
| FunClip | 官方 v2.1.0；6f29319e1b36838f943384c07b3e6dec0732c8a1 | 官方样本及 68 秒原录像真实转写通过 |
| FunASR | 锁定 1.4.0 | 3.10 隔离环境真实转写通过，好友服务已启用 |
| ModelScope | 锁定 1.40.1 | 3.10 环境安装与导入验证通过 |
| auto-editor | 官方 31.7.2，macOS arm64 | v3 导出及静音样本测试通过 |
| auto-editor SHA256 | 874310a405c88c4d06b9ee7b60b3a4e59ecbb09cfecd56ff54f1bf712b3b776e | 与官方 Release API digest 一致 |
| Ollama | 0.34.1 | 已安装；好友服务运行兼容 CPU runner |
| Qwen3 8B | Ollama 官方下载，Q4_K_M | 权重下载完成；CPU 加载后短回答超时，未通过可用性验收 |
| 好友服务选段模型 | Qwen3 1.7B | 现有备用模型，不能替代“8B 已验收”的结论 |
| OBS | 官方指定组件 | WebSocket 接口已有；真实录屏及系统权限验收待完成 |
| 剪映专业版 | 人工精修 | 安装版本与人工最终导出由用户确认 |
| RAGFlow / BGE / Qdrant / Qwen3-VL / pyJianYingDraft | 二期 | 未部署，未验收 |

没有云 API 调用。模型缓存、本机配置与媒体保持 Git 忽略。锁定的主线依赖见 requirements-first-phase.txt；实际 3.10 安装清单见 requirements-first-phase-lock.txt；pip check 无依赖冲突。

## 2026-10-10 实测补充

空间清理后已下载并加载中文 seaco-Paraformer、FSMN VAD、CT-Transformer，修订均为 v2.0.4。官方 5.55 秒样本识别为“欢迎大家来体验达摩院推出的语音识别模型”，时间 0.880–5.195 秒；首次 391.44 秒包含模型下载与加载，不能作为稳定转写延迟。


ModelScope 1.40.1 同时需要 MODELSCOPE_CACHE（权重）与 MODELSCOPE_HOME（SDK 配置）指向可写本地目录。补齐 pytorch-wpe 0.0.1 与 einops 0.8.1，pip check 无冲突。

Qwen3 8B 常规 Ollama 调用在当前运行环境触发 Metal command queue 初始化失败。CPU runner 已能加载；并发语音／语言模型测试因 RAM 压力超时，正在进行串行低内存验证。加载成功不等于选段可用，不据此标记 8B 已验收。

后续串行低内存 8B 测试使用 2048 上下文、mmap、禁用重排；44 秒完成加载，180 秒回答等待仍超时，总耗时 224.46 秒。未启用为好友服务默认模型；备用仍为 Qwen3 1.7B。

CAM++ v2.0.2 加载成功，官方样本返回 speaker 0，热词参数“达摩院”传入并保留在实际识别文本中。该单说话人测试不证明真实多人分离准确率。OBS 32.2.2 官方 Apple Silicon 安装器 SHA256 为 920d6f26703d2df6e4085bd3c1cbed30488325084136c7a6e9e37021fbd6aaf7，与官方发布摘要一致；系统挂载失败，未标记已安装。
