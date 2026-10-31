# 拾光 · 开发路线与验收清单

> 本文件由 [desktop-pet-workflow.md](docs/desktop-pet-workflow.md) 导入后按当前项目适配。
> 原始工作流保留在 `docs/desktop-pet-workflow.md`，本文件只记录「拾光」实际怎么落地。
> 更新日期：2026-10-31

## 一、和原工作流的差异

| 原工作流 | 本项目现状 |
| --- | --- |
| 仓库在 `E:\pet` | 项目在 `C:\Users\HP\Desktop\work\longmem-pet`，`E:\pet` 当前不存在 |
| 用 DeepSeek Harness 承接模型/会话/工具 | 当前用 `pet/llm.py` 直连 OpenAI 兼容 API；Harness 适配器尚未接入 |
| 已有 Git 第一次提交的计划 | 项目尚未 `git init`，第一次提交待做 |
| 临时角色图片 | 已按 `拾光` 设计稿用 QPainter 重绘 |
| 先做 CLI，再做 UI | CLI 与 UI 同时存在；`ChatEngine` 可脱离 Qt 使用 |

**结论**：UI、聊天、角色和长记忆已经走到原工作流第 2～4 步；真正待补的是「Git 基线」和「面向其他用户的配置/打包」。
如果后续确定要用 Harness，只需要在 `pet/llm.py` 的 `ChatModel` 接口后面加一个适配器，不需要重写界面和记忆层。

## 二、当前进度

### 第 0 步：保存可运行基线

- [x] 固定解释器：`.venv`，Python 3.13.14，PySide6 6.12.0（Essentials）
- [x] 再跑一次当前程序：`15` 个单元测试通过，真实桌面启动检查通过
- [x] 根目录 `.gitignore` 已建立，覆盖 `.venv/`、`data/`、`.env`、缓存和构建产物
- [ ] `git init` 并形成第一次提交
- [ ] 打 `v0.1.0` 标签

> 当前没有 Git 仓库。第一次提交前先确认 `data/`、`.venv/`、`.tmp/` 没有被加入暂存区。

### 第 1 步：跑通模型调用

原工作流验收的是 Harness 返回 `completed`；本项目对应的是 OpenAI 兼容调用：

- [x] `MockLLM` 离线可跑，完整记忆流程不依赖网络
- [x] `OpenAICompatibleClient` 支持 DeepSeek / OpenAI / Ollama / vLLM 等兼容服务
- [x] 失败有明确 `LLMError`，界面显示错误但不退出
- [ ] 用真实 Key 在本机走通一次在线对话（当前主要用 Mock 验证）
- [ ] 如果确定采用 Harness：实现 `DSHClient` 适配 `ChatModel`，并验证 `runtime_cwd`

### 第 2 步：自己的桌宠外壳

- [x] 透明背景、无边框、置顶
- [x] 鼠标拖动
- [x] 右键菜单 / 托盘退出，退出时隐藏气泡和窗口
- [x] 启动后无残留控制台窗口（`run.bat` 使用 `pythonw`）
- [x] 窗口大小可通过 `ui.scale` 调整

### 第 3 步：桌宠与模型连起来

**3A 封装调用代码**

- [x] `pet/llm.py` 封装模型客户端
- [x] `pet/core/chat.py` 封装 prompt 组装与会话生命周期
- [x] `MemoryService` 封装记忆读写，不依赖 UI
- [x] 结果区分成功、失败和可排错信息
- [x] 终端/库方式可直接调用 `ChatEngine`

**3B 接入聊天窗口**

- [x] 双击桌宠打开聊天窗
- [x] 输入后异步请求，界面不冻结（`QThreadPool`）
- [x] 等待、成功、错误状态都有反馈
- [x] 报错不会让整个界面退出
- [x] 同一会话保留上下文，并用最近消息验证上下文
- [x] 退出时隐藏托盘、关闭窗口、停止活动任务

### 第 4 步：自己的角色与行为

- [x] 换上「拾光」角色：半透明光灵、记忆珠、薄荷色书签尾巴
- [x] 待机动画：呼吸、眨眼、尾巴摇摆、记忆珠漂浮
- [x] 请求开始进入「思考」表情，回复后切换「开心/兴奋」
- [x] 请求失败显示「委屈」表情，随后回到待机
- [x] 鼠标全局视线跟随 + 伪 3D 倾斜
- [x] 右键「摸摸头 / 打招呼 / 睡一觉」切换表情
- [x] 记忆珠光点数量随活跃记忆数增长
- [ ] 随机走动 / 屏幕边缘吸附（原工作流列为可选后续）

### 面向其他用户发布

**用户配置**

- [ ] 首次启动 GUI 填写 API Key
- [ ] 测试连接、更新、清除密钥
- [ ] 普通配置与凭据分开保存，日志不泄露密钥
- [ ] 用户不需要开发电脑的路径或 `.env`

**Windows 打包**

- [ ] PyInstaller 打包桌宠、素材和依赖
- [ ] 干净 Windows 虚拟机启动成功
- [ ] 不同盘符、空格、中文路径验证
- [ ] 完整验证显示、拖动、聊天、报错、退出

## 三、下一步分支顺序

当前没有 Git 仓库，建议先完成基线，再按小分支推进：

1. `chore/git-baseline`
   - `git init`
   - 确认 `.gitignore` 生效
   - 第一次提交：`feat: establish working long-memory desktop pet`
   - 标签：`v0.1.0`
2. `feat/settings-key`
   - 设置窗口：API Key、Base URL、Model、测试连接
   - 密钥只存本地；日志和界面不回显完整 Key
   - 未配置时自动回退 Mock，并给明确提示
3. `feat/harness-adapter`（可选）
   - 在 `ChatModel` 协议后实现 DSH 客户端
   - 继续沿用 `ChatEngine` / `MemoryService`
   - 单独验证 `runtime_cwd`，不要把它写死到 UI
4. `build/windows-release`
   - `PyInstaller --collect-all PySide6`
   - 数据目录用 `LONGMEM_PET_HOME` 外置，升级不丢记忆
   - 干净环境验收

## 四、每次合并前的检查

- [ ] 功能满足本阶段验收条件
- [ ] 原有入口仍能运行：`python app.py --mock --demo`
- [ ] 记忆内核单测通过：`python -m unittest discover -s tests -p "test_*.py"`
- [ ] 没有把 `data/`、`.env`、`.venv/`、密钥加入提交
- [ ] 配置、素材、依赖变化已写进 README 或提交说明
- [ ] 合并后再次运行主干版本

## 五、固定运行配置

```powershell
cd C:\Users\HP\Desktop\work\longmem-pet
.\.venv\Scripts\python.exe app.py --mock --demo
```

- 解释器：`.venv\Scripts\python.exe`（Python 3.13.14）
- GUI：PySide6 6.12.0 Essentials
- 数据：默认 `data/`，可用 `LONGMEM_PET_HOME` 覆盖
- 测试：15 个单测 + `tests/visual_smoke.py` + `tests/live_gui.py`

## 六、进度回报格式

```text
当前阶段：
当前分支：
已完成：
本次要实现：
遇到的问题／完整报错：
```
