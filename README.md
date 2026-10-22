# [fxxkZhiHuiShuMeow] Sonamiの智慧树智慧课程刷课脚本

## 前置依赖

需要 Windows 和 Python 3.11+（安装 Python 时勾选 “Add Python to PATH”）。默认使用系统自带的 Edge，不需要额外下载浏览器。

首次运行 `run.bat` 会自动检查并安装 `script/requirements.txt` 里的 Playwright；如果自动安装失败，再手动执行：

```powershell
python -m pip install -r script/requirements.txt
```

## 运行

双击根目录的 `run.bat` 会打开界面（UI），在项目根目录执行 `.\run.bat` 也一样。

带参数时仍然走原来的命令行，比如只处理指定翻转课（把 `12345678` 换成你的课程 ID）：

```powershell
.\run.bat --flip-course 12345678
```

第一次运行需要在打开的浏览器里用 `知到APP` 扫码登录；之后会免登录**直接登入**。想登出用：

```powershell
python script/run.py --fresh-login
```

**⚠WARNING 不要同时运行多个脚本 ⚠**

## 界面（UI）

界面分四块：

1. **DeepSeek 官方 API**：填 API Key（默认 `https://api.deepseek.com`、模型 `deepseek-chat`），点“保存”写入 `script/config.json`，点“测试”验证连通。
2. **课程表**：点“读取课程”后列出智慧课程 + 翻转课；点击“刷课 / 测验作业”两列切换勾选。
3. **作业 / 测验表**：给勾了“测验作业”的课程点“读取作业/测验”，会列出作业和章测试；勾选要处理的条目。
4. **日志**：实时输出。

- “开始刷课”只处理课程表里勾了“刷课”的课；
- “AI 答题（选中）”只处理作业表里勾选的条目，全程只发数据包、不点页面：抓题 → DeepSeek 出答案 → **弹出确认窗口**（绿色=把握高、黄色=中等、红色=偏低，可选中某题改答案），然后三个按钮：**仅保存草稿** / **确认提交** / **取消**，不点“确认提交”就不会交卷；
- 支持单选、多选、判断和问答类文字题；填空题暂不自动作答，会写进日志；
- 带人脸识别 / 身份验证的正式考试会自动跳过，不做绕过；
- 只勾你想处理的条目，不勾的不会动。

> `script/config.json` 里是 API Key，**打包发送前请删掉**；`script/.session`（登录缓存）和 `script/output`（运行报告）也是本机数据，不要一起发出去。

## 命令行刷课

不带参数时按原来的方式自动刷课，结果写到 `script/output/*.json`：

- 智慧课程：知识点目录 → 组件列表 → 视频按 10 秒一批上报、文档直接标记完成，写后读回核验；
- 翻转课：视频按 30 秒一批上报 `saveStuStudyRecord`，文档调用 `stuViewFile`，写后读回核验；
- 只放行白名单接口，写入失败不自动重试，不能确认就记 `not_confirmed`。

压缩包（zip/rar）网页只提供下载，脚本不猜它的完成方式，会留在“未完成”计数里。

只处理指定翻转课（课程 ID 或 `studyResource` 网址，可重复）：

```powershell
python script/run.py --flip-course 12345678
```

跳过翻转课只刷智慧课程：

```powershell
python script/run.py --no-flip
```

## 一些附加功能（不重要）

`--interval 2` 调整批次间隔，支持 0.5～60 秒；<br>
`--login-timeout 1800` 调整等待登录时间；<br>
`--course 12345678` 只刷指定智慧课程（可重复）；<br>
`--no-smart` 跳过智慧课程。

按 `Ctrl+C` 可以强制停止命令行运行。