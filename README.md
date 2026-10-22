# ZhiHuiShuMeow2.0

智慧树/知到 智慧课程/翻转课自动刷课脚本

是 [ZhiHuiShuMeow] Sonamiの智慧树智慧课程刷课脚本
是https://github.com/LemSonami/FxxkZhiHuiShuMeow 的 2.0 版本
主要更新了对翻转课的依赖
### 目前有更新了基于前端的对共享课的支持的4.0版本https://github.com/Liang1jp/zhihuishu4.0

## 前置依赖

需要 Windows 和 Python 3.11+（安装 Python 时勾选 “Add Python to PATH”）。默认使用系统自带的 Edge，不需要额外下载浏览器。

首次运行 `run.bat` 会自动检查并安装 `script/requirements.txt` 里的 Playwright；如果自动安装失败，再按下面的手动命令装。

```powershell
python -m pip install -r script/requirements.txt
```

## 运行

双击根目录的 `run.bat`，会打开猫猫的小屋（界面）；在项目根目录执行也一样：

```powershell
.\run.bat
```

带参数时还是原来的命令行，参数会原样传给 `script/run.py`，比如只处理指定翻转课：

```powershell
.\run.bat --flip-course 11542857
```

之后也可以直接运行 `python script/run.py`；默认使用系统 Edge，用 Chrome 时加 `--channel chrome`。

在打开的浏览器中，自行使用 `知到APP` 扫码登录。

**⚠WARNING 不要同时运行多个脚本 ⚠**

## 智慧树喵

之后，脚本便会**自动开始刷课**：

后台保持运行，可以直接最小化窗口后去干别的事。<br>
*注：但是**不要**把脚本终端界面或打开的浏览器关掉*

可以定期打开脚本窗口观赏猫猫的工作日志。<br>
如果遇到界面报错，就类似下面这样的：

```error
喵qwq 本次运行已停止：xxxxx。结果已经保存到xxxxx
```

直接关掉脚本，过段时间后重新打开即可。

## 界面（UI）

双击 `run.bat` 打开的小屋分四块：

1. **DeepSeek 官方 API**：填 API Key（默认 `https://api.deepseek.com`、模型 `deepseek-chat`），点“保存”写进 `script/config.json`，点“测试”看看猫猫能不能连上。
2. **课程表**：点“读取课程”，智慧课程和翻转课都列出来；点“刷课 / 测验作业”两列切换勾选。
3. **作业 / 测验表**：给勾了“测验作业”的课点“读取作业/测验”，作业和章测试就都出来了；勾选要处理的条目。
4. **日志**：猫猫干活的全过程，实时刷。

- “开始刷课”只处理课程表里勾了“刷课”的课；
- “AI 答题（选中）”只处理作业表里勾选的条目，全程只发数据包、不点页面：抓题 → DeepSeek 出答案 → **弹出确认窗口**（绿色=把握高、黄色=中等、红色=偏低，选中某题还能自己改答案），然后三个按钮：**仅保存草稿** / **确认提交** / **取消**，不点“确认提交”就不会交卷喵；
- 单选、多选、判断和问答类文字题都能做；填空题猫猫不猜，会写进日志；
- 带人脸识别 / 身份验证的正式考试会自动跳过，猫猫不做绕过；
- 只勾你想处理的条目，不勾的猫猫一根毛都不碰。

> `script/config.json` 里是 API Key，**打包发送前请删掉**；`script/.session`（登录缓存）和 `script/output`（运行报告）也是本机数据，不要一起发出去。

## 翻转课学习资源

登录后脚本还会自动读取账号下的翻转课，按“学习资源”逐条处理：

- 视频：每 30 秒一批上报 `saveStuStudyRecord`，每 5 批读回一次进度；
- 文档 / PPT / PDF：调用一次 `stuViewFile`，再把 0/1 读回来核验；
- 作业 / 测验：命令行模式下不处理，脚本不会替你作答；要用 AI 答作业 / 测验，请走上面的界面；
- 压缩包（zip/rar）：网页只提供下载，脚本不猜它的完成方式，会留在“未完成”计数里。

只处理指定翻转课（课程 ID 或 `studyResource` 网址，可重复）：

```powershell
python script/run.py --flip-course 11542857
```

跳过翻转课，只刷智慧课程：

```powershell
python script/run.py --no-flip
```

## 一些附加功能（不重要）

`--interval 2` 调整批次间隔，支持 0.5～60 秒；<br>
`--login-timeout 1800` 调整等待登录时间；<br>
`--course 11542857` 只刷指定智慧课程（可重复）；<br>
`--no-smart` 跳过智慧课程，只留翻转课。

按 `Ctrl+C` 可以强制停止命令行运行。

已在脚本中登陆过一次后，后续重新打开脚本会免登录**直接登入**；<br>
想登出请运行：

```powershell
python script/run.py --fresh-login
```

脚本来源于suda，为vibe coding作品

## 都给我去看超时空辉夜姬喵
