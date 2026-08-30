# 打包 Windows 安装包

给非开发用户的交付物是 `dist/QuizGen-Setup.exe`（若已安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)），以及始终会生成的便携包 `dist/QuizGen-portable.zip`。

**不要把仓库里的 `.env` 或真实 API Key 打进安装包。** 构建脚本只拷贝代码、prompts 和运行时。

## 构建机需要

- Windows 10/11 x64
- 本机 Node.js 20（用来 `next build`，不会装进用户环境以外的另一份也会被打进 payload）
- 网络（首次下载 Python nuget 与 Node zip，缓存在 `packaging/vendor/`）
- 可选：Inno Setup 6（`ISCC.exe`），用于生成安装程序
- 可选 OCR：把便携版 Tesseract（含 `tesseract.exe` 与 `tessdata/chi_sim.traineddata`）放到 `packaging/vendor/tesseract/`，再加 `-IncludeOcr`

构建会强制执行 `npm ci`，并校验固定版本 Python、Node 和 `get-pip.py` 的 SHA-256；校验失败请删除提示的缓存文件后重试。`-SkipFrontend` 仅适用于调试到前端复制前的阶段，不能生成可分发的 zip 或安装包。

## 命令

在仓库根目录或本目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
```

常用参数：

- `-SkipDownloads`：使用已缓存的 `vendor/` 运行时
- `-SkipFrontend`：不重新 `next build`（调试后端布局时）
- `-IncludeOcr`：若存在 `vendor/tesseract/tesseract.exe` 则打成安装器可选组件

产物：

| 文件 | 说明 |
| --- | --- |
| `packaging/dist/payload/` | 便携目录，可直接双击测（用 `runtime\python\python.exe launcher.py`） |
| `packaging/dist/QuizGen-portable.zip` | 免安装压缩包 |
| `packaging/dist/QuizGen-Setup.exe` | Inno 安装程序（有 ISCC 时） |

程序安装到当前用户的 `%LOCALAPPDATA%\Programs\QuizGen`，不需要管理员权限；用户数据在 `%APPDATA%\QuizGen`（数据库、上传、`config.env`、日志）。升级会保留该配置和数据。

## 本机试跑启动器（不打包）

需已有 `backend\.venv` 与本机 Node：

```powershell
$env:APP_ENV = "desktop"
python packaging\launcher.py
```

首次会弹出设置向导。配置写入 `%APPDATA%\QuizGen\config.env`。

前后端就绪后打开 **WebView2 独立窗口**（Edge 内核），不再默认打开系统浏览器。关闭窗口即停止本机前后端。菜单「文件 → 打开数据目录」可打开 `%APPDATA%\QuizGen`。

界面依赖系统已安装的 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2)。普通 Windows 10/11 随 Edge 自带；精简版 / LTSC / 未装 Edge 的机器需先装 Evergreen Runtime。缺少 WebView2 或 `pywebview` 无法加载时，启动器回退为系统浏览器 + 托盘（与旧行为相同）。

便携版请双击 `QuizGen.cmd`，首次配置会在命令窗口中完成；这避免依赖嵌入式 Python 不包含的图形 `tkinter` 组件。

## SmartScreen

未签名的安装包可能被 Windows SmartScreen 拦截，用户需选择「仍要运行」。正式分发前请用代码签名证书签名 `QuizGen-Setup.exe`。
