"""Desktop / portable launcher for 智能题库生成器.

Portable layout (installer payload)::

    QuizGen/
      launcher.py
      runtime/python/python.exe
      runtime/node/node.exe
      app/backend/
      app/frontend/   (Next standalone)
      app/prompts/

Source-tree fallback: uses backend/.venv and local Node when runtime/ is absent.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_TITLE = "智能题库生成器"
FRONTEND_URL = "http://127.0.0.1:3000"
BACKEND_URL = "http://127.0.0.1:8000"
HEALTH_URL = f"{BACKEND_URL}/health"
BACKEND_PORT = "8000"
FRONTEND_PORT = "3000"

CREATE_NO_WINDOW = 0x08000000


def _win_no_window() -> int:
    return CREATE_NO_WINDOW if sys.platform == "win32" else 0


def install_root() -> Path:
    here = Path(__file__).resolve().parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if (here / "runtime" / "python").exists() and (here / "app" / "backend").exists():
        return here
    if here.name == "packaging" and (here.parent / "backend").exists():
        return here.parent
    return here


def data_dir() -> Path:
    override = os.environ.get("QUIZGEN_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        path = base / "QuizGen"
    else:
        path = Path.home() / ".local" / "share" / "quizgen"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    override = os.environ.get("QUIZGEN_CONFIG")
    if override:
        return Path(override)
    return data_dir() / "config.env"


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 智能题库生成器 — 本机配置（不要分享含有 API Key 的文件）",
        f"APP_NAME={values.get('APP_NAME', APP_TITLE)}",
        f"APP_ENV={values.get('APP_ENV', 'desktop')}",
        f"SECRET_KEY={values['SECRET_KEY']}",
        f"DATABASE_URL={values.get('DATABASE_URL', 'sqlite+aiosqlite:///./quizgen.db')}",
        f"REDIS_URL={values.get('REDIS_URL', 'memory://')}",
        f"FRONTEND_URL={values.get('FRONTEND_URL', FRONTEND_URL)}",
        f"MOCK_LLM={values.get('MOCK_LLM', 'true')}",
        f"ENABLE_OCR={values.get('ENABLE_OCR', 'false')}",
        f"QWEN_API_KEY={values.get('QWEN_API_KEY', '')}",
        f"QWEN_BASE_URL={values.get('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')}",
        f"QWEN_MODEL={values.get('QWEN_MODEL', 'qwen-plus')}",
        f"DEEPSEEK_API_KEY={values.get('DEEPSEEK_API_KEY', '')}",
        f"DEEPSEEK_BASE_URL={values.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}",
        f"DEEPSEEK_MODEL={values.get('DEEPSEEK_MODEL', 'deepseek-chat')}",
        f"ANTHROPIC_API_KEY={values.get('ANTHROPIC_API_KEY', '')}",
        f"OPENAI_API_KEY={values.get('OPENAI_API_KEY', '')}",
        f"EMBEDDING_PROVIDER={values.get('EMBEDDING_PROVIDER', 'local')}",
        f"EMBEDDING_MODEL={values.get('EMBEDDING_MODEL', 'hashed-bigram')}",
        f"DAILY_GEN_QUOTA={values.get('DAILY_GEN_QUOTA', '20')}",
        f"ACCESS_TOKEN_EXPIRE_MINUTES={values.get('ACCESS_TOKEN_EXPIRE_MINUTES', '10080')}",
        f"MAX_UPLOAD_MB={values.get('MAX_UPLOAD_MB', '20')}",
        f"MAX_KEY_SENTENCES={values.get('MAX_KEY_SENTENCES', '30')}",
        f"MAX_QUESTIONS={values.get('MAX_QUESTIONS', '40')}",
        f"SETUP_COMPLETE={values.get('SETUP_COMPLETE', 'true')}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def default_config(existing: dict[str, str] | None = None) -> dict[str, str]:
    values = dict(existing or {})
    values.setdefault("APP_ENV", "desktop")
    values.setdefault("SECRET_KEY", secrets.token_urlsafe(32))
    values.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./quizgen.db")
    values.setdefault("REDIS_URL", "memory://")
    values.setdefault("FRONTEND_URL", FRONTEND_URL)
    values.setdefault("MOCK_LLM", "true")
    values.setdefault("ENABLE_OCR", "false")
    values.setdefault("SETUP_COMPLETE", "true")
    return values


def message_box(text: str, title: str = APP_TITLE, error: bool = False) -> None:
    if sys.platform == "win32":
        flags = 0x10 if error else 0x40
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, flags)
            return
        except Exception:
            pass
    print(f"{title}: {text}")


def run_first_run_wizard(existing: dict[str, str]) -> dict[str, str] | None:
    values = default_config(existing)
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        write_env(config_path(), values)
        message_box(
            "已写入演示模式配置。\n"
            f"如需真实出题，请编辑：\n{config_path()}\n"
            "填写 QWEN_API_KEY 或 DEEPSEEK_API_KEY，并将 MOCK_LLM 设为 false。"
        )
        return values

    root = tk.Tk()
    root.title(f"{APP_TITLE} — 首次设置")
    root.resizable(False, False)
    root.geometry("460x320")

    mode = tk.StringVar(value="demo")
    key_var = tk.StringVar()
    cancelled = {"v": True}

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="选择出题方式", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="演示模式不调用网络模型。真实出题需要你自己的 API Key，密钥只保存在本机。",
        wraplength=420,
    ).pack(anchor="w", pady=(4, 12))

    for value, label in (
        ("demo", "演示模式（无需 Key）"),
        ("qwen", "通义千问 Qwen"),
        ("deepseek", "DeepSeek"),
    ):
        ttk.Radiobutton(frame, text=label, variable=mode, value=value).pack(anchor="w")

    ttk.Label(frame, text="API Key（演示模式可留空）").pack(anchor="w", pady=(12, 4))
    ttk.Entry(frame, textvariable=key_var, show="*", width=48).pack(anchor="w", fill="x")

    def on_ok() -> None:
        chosen = mode.get()
        key = key_var.get().strip()
        if chosen != "demo" and not key:
            messagebox.showerror(APP_TITLE, "请填写 API Key，或改选演示模式。")
            return
        if chosen == "demo":
            values["MOCK_LLM"] = "true"
        elif chosen == "qwen":
            values["QWEN_API_KEY"] = key
            values["MOCK_LLM"] = "false"
        else:
            values["DEEPSEEK_API_KEY"] = key
            values["MOCK_LLM"] = "false"
        values["SETUP_COMPLETE"] = "true"
        cancelled["v"] = False
        root.destroy()

    def on_cancel() -> None:
        cancelled["v"] = True
        root.destroy()

    btns = ttk.Frame(frame)
    btns.pack(fill="x", pady=(18, 0))
    ttk.Button(btns, text="开始", command=on_ok).pack(side="right")
    ttk.Button(btns, text="取消", command=on_cancel).pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()
    if cancelled["v"]:
        return None
    return values


def resolve_layout(root: Path) -> dict[str, Path]:
    portable_py = root / "runtime" / "python" / "python.exe"
    portable_pyw = root / "runtime" / "python" / "pythonw.exe"
    portable_node = root / "runtime" / "node" / "node.exe"
    if portable_py.exists() and (root / "app" / "backend").exists():
        python = portable_pyw if portable_pyw.exists() else portable_py
        return {
            "python": python,
            "python_console": portable_py,
            "node": portable_node,
            "backend": root / "app" / "backend",
            "frontend": root / "app" / "frontend",
            "prompts": root / "app" / "prompts",
            "tesseract": root / "runtime" / "tesseract" / "tesseract.exe",
        }

    backend = root / "backend"
    venv_py = backend / ".venv" / "Scripts" / "python.exe"
    python = venv_py if venv_py.exists() else Path(sys.executable)
    node = Path(os.environ.get("NODE_EXE") or _which("node") or "")
    return {
        "python": python,
        "python_console": python,
        "node": node,
        "backend": backend,
        "frontend": root / "frontend",
        "prompts": root / "prompts",
        "tesseract": Path(),
    }


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def already_running() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_http(url: str, attempts: int = 60) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(1)
    return False


def child_env(cfg: Path, layout: dict[str, Path]) -> dict[str, str]:
    parsed = parse_env(cfg)
    env = os.environ.copy()
    env["APP_ENV"] = "desktop"
    env["QUIZGEN_DATA_DIR"] = str(data_dir())
    env["QUIZGEN_CONFIG"] = str(cfg)
    env["QUIZGEN_PROMPTS"] = str(layout["prompts"])
    env["PYTHONPATH"] = str(layout["backend"])
    env["PYTHONUNBUFFERED"] = "1"
    env["FRONTEND_URL"] = FRONTEND_URL
    env["REDIS_URL"] = parsed.get("REDIS_URL") or "memory://"
    env["DATABASE_URL"] = parsed.get("DATABASE_URL") or "sqlite+aiosqlite:///./quizgen.db"
    tess = layout["tesseract"]
    if tess.exists():
        env["TESSERACT_CMD"] = str(tess)
        env["TESSDATA_PREFIX"] = str(tess.parent / "tessdata")
        env["PATH"] = str(tess.parent) + os.pathsep + env.get("PATH", "")
        parsed = parse_env(cfg)
        if parsed.get("ENABLE_OCR", "").lower() != "false":
            env["ENABLE_OCR"] = "true"
    return env


def start_backend(layout: dict[str, Path], env: dict[str, str], log_file) -> subprocess.Popen[bytes]:
    python = layout["python_console"]
    return subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            BACKEND_PORT,
        ],
        cwd=str(layout["backend"]),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=_win_no_window(),
    )


def start_frontend(layout: dict[str, Path], env: dict[str, str], log_file) -> subprocess.Popen[bytes]:
    fe = layout["frontend"]
    node = layout["node"]
    fe_env = env.copy()
    fe_env["PORT"] = FRONTEND_PORT
    fe_env["HOSTNAME"] = "127.0.0.1"
    fe_env["INTERNAL_API_URL"] = BACKEND_URL
    standalone = fe / "server.js"
    if standalone.exists():
        if not node.exists():
            raise FileNotFoundError("未找到便携 Node：runtime/node/node.exe")
        return subprocess.Popen(
            [str(node), "server.js"],
            cwd=str(fe),
            env=fe_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=_win_no_window(),
        )
    npm = _which("npm.cmd") or _which("npm")
    if not npm:
        raise FileNotFoundError("开发模式需要本机 Node/npm，或使用打包后的 standalone 前端")
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(fe),
        env=fe_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=_win_no_window(),
        shell=False,
    )


def stop_process(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def open_data_dir() -> None:
    path = data_dir()
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])


def tray_icon_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (15, 118, 110, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((12, 12, 52, 52), outline=(255, 255, 255, 255), width=4)
    draw.rectangle((22, 22, 42, 42), fill=(255, 255, 255, 230))
    return img


def run_tray(on_exit) -> None:
    try:
        import pystray
        from pystray import MenuItem as Item
    except Exception:
        run_status_window(on_exit)
        return

    def open_web(icon=None, item=None) -> None:
        webbrowser.open(FRONTEND_URL)

    def open_dir(icon=None, item=None) -> None:
        open_data_dir()

    def quit_app(icon, item=None) -> None:
        icon.stop()
        on_exit()

    icon = pystray.Icon(
        "QuizGen",
        tray_icon_image(),
        APP_TITLE,
        menu=pystray.Menu(
            Item("打开网页", open_web, default=True),
            Item("打开数据目录", open_dir),
            Item("退出", quit_app),
        ),
    )
    icon.run()


def run_status_window(on_exit) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        message_box(f"{APP_TITLE} 已启动。\n关闭本控制台将停止服务。")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            on_exit()
        return

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("360x160")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=f"{APP_TITLE} 正在运行", font=("Microsoft YaHei UI", 11, "bold")).pack(
        anchor="w"
    )
    ttk.Label(frame, text=FRONTEND_URL).pack(anchor="w", pady=(4, 12))

    def close() -> None:
        root.destroy()
        on_exit()

    btns = ttk.Frame(frame)
    btns.pack(fill="x")
    ttk.Button(btns, text="打开网页", command=lambda: webbrowser.open(FRONTEND_URL)).pack(side="left")
    ttk.Button(btns, text="数据目录", command=open_data_dir).pack(side="left", padx=8)
    ttk.Button(btns, text="退出", command=close).pack(side="right")
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


def main() -> int:
    root = install_root()
    cfg = config_path()
    existing = parse_env(cfg)
    if existing.get("SETUP_COMPLETE", "").lower() != "true" or not existing.get("SECRET_KEY"):
        values = run_first_run_wizard(existing)
        if values is None:
            return 0
        write_env(cfg, values)
    elif not cfg.exists():
        write_env(cfg, default_config(existing))

    if already_running():
        webbrowser.open(FRONTEND_URL)
        return 0

    try:
        layout = resolve_layout(root)
    except Exception as exc:
        message_box(f"无法定位程序文件：{exc}", error=True)
        return 1

    if not layout["python_console"].exists():
        message_box("未找到 Python 运行时。请重新安装，或先在 backend 下创建 .venv。", error=True)
        return 1

    env = child_env(cfg, layout)
    logs = data_dir() / "logs"
    logs.mkdir(exist_ok=True)
    backend_log = open(logs / "backend.log", "ab")
    frontend_log = open(logs / "frontend.log", "ab")
    backend_proc: subprocess.Popen[bytes] | None = None
    frontend_proc: subprocess.Popen[bytes] | None = None

    def cleanup() -> None:
        stop_process(frontend_proc)
        stop_process(backend_proc)
        try:
            backend_log.close()
        except Exception:
            pass
        try:
            frontend_log.close()
        except Exception:
            pass

    try:
        backend_proc = start_backend(layout, env, backend_log)
        if not wait_http(HEALTH_URL, attempts=45):
            cleanup()
            message_box(
                "后端启动失败。请查看数据目录 logs/backend.log。\n" + str(data_dir() / "logs"),
                error=True,
            )
            return 1
        frontend_proc = start_frontend(layout, env, frontend_log)
        wait_http(FRONTEND_URL, attempts=45)
        webbrowser.open(FRONTEND_URL)
        run_tray(cleanup)
    except Exception as exc:
        cleanup()
        message_box(f"启动失败：{exc}", error=True)
        return 1
    cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
