# ZhiHuiShuMeow2.0
智慧树/知到 智慧课程/翻转课自动刷课脚本
# [ZhiHuiShuMeow] Sonamiの智慧树智慧课程刷课脚本

## 前置依赖

需要 Windows 和 Python 3.11+（安装 Python 时勾选 “Add Python to PATH”）。默认使用系统自带的 Edge，不需要额外下载浏览器。

首次运行 `run.bat` 会自动检查并安装 `script/requirements.txt` 里的 Playwright；如果自动安装失败，再按下面的手动命令装。

## 运行

双击根目录的 `run.bat`，或在项目根目录执行：

```powershell
.\run.bat
```

参数会原样传给 `script/run.py`，比如只处理指定翻转课：

```powershell
.\run.bat --flip-course 11542857
```

自动安装失败时，手动执行：

```powershell
python -m pip install -r script/requirements.txt
```

之后运行 `python script/run.py`；默认使用系统 Edge，用 Chrome 时加 `--channel chrome`。

在打开的浏览器中，自行使用 `知到APP` 扫码登录。

**⚠WARNING 不要同时运行多个脚本 ⚠**

## 智慧树喵

之后，脚本便会**自动开始刷课**：

![刷课界面](figure/meow.png)

后台保持运行，可以直接最小化窗口后去干别的事。<br>
*注：但是**不要**把脚本终端界面或打开的浏览器关掉*

可以定期打开脚本窗口观赏猫猫的工作日志。<br>
如果遇到界面报错，就类似下面这样的：

```error
喵qwq 本次运行已停止：xxxxx。结果已经保存到xxxxx
```

直接关掉脚本，过段时间后重新打开即可。

## 翻转课学习资源

登录后脚本还会自动读取账号下的翻转课，按“学习资源”逐条处理：

- 视频：每 30 秒一批上报 `saveStuStudyRecord`，每 5 批读回一次进度；
- 文档 / PPT / PDF：调用一次 `stuViewFile`，再把 0/1 读回来核验；
- 作业 / 测验：不处理，脚本不会替你作答；
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
`--login-timeout 1800` 调整等待登录时间。

按 `Ctrl+C` 可以强制停止脚本运行。

已在脚本中登陆过一次后，后续重新打开脚本会免登录**直接登入**；<br>
想登出请运行：

```powershell
python script/run.py --fresh-login
```
脚本来源于suda，为vibe coding作品
## 都给我去看超时空辉夜姬喵
