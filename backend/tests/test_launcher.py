import importlib.util
from pathlib import Path
from types import SimpleNamespace

LAUNCHER_PATH = Path(__file__).resolve().parents[2] / "packaging" / "launcher.py"


def load_launcher():
    spec = importlib.util.spec_from_file_location("quizgen_launcher", LAUNCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeWebview:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.settings = {
            "ALLOW_DOWNLOADS": False,
            "OPEN_EXTERNAL_LINKS_IN_BROWSER": False,
        }
        self.windows: list[tuple[tuple, dict]] = []
        self.starts: list[dict] = []
        self.fail_start = fail_start

    def create_window(self, *args, **kwargs):
        self.windows.append((args, kwargs))
        return SimpleNamespace(title=args[0] if args else "")

    def start(self, **kwargs):
        if self.fail_start:
            raise RuntimeError("webview start failed")
        self.starts.append(kwargs)


def test_configure_webview_allows_downloads_and_external_links():
    launcher = load_launcher()
    settings = {
        "ALLOW_DOWNLOADS": False,
        "OPEN_EXTERNAL_LINKS_IN_BROWSER": False,
    }
    launcher.configure_webview(settings)
    assert settings["ALLOW_DOWNLOADS"] is True
    assert settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True


def test_run_app_window_returns_false_without_webview():
    launcher = load_launcher()
    assert launcher.run_app_window(webview=None) is False


def test_run_app_window_opens_frontend_in_desktop_shell(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setenv("QUIZGEN_DATA_DIR", str(tmp_path))
    webview = FakeWebview()

    assert launcher.run_app_window(webview=webview) is True
    assert len(webview.windows) == 1
    args, kwargs = webview.windows[0]
    assert args[0] == launcher.APP_TITLE
    assert args[1] == launcher.FRONTEND_URL
    assert kwargs["width"] == launcher.WINDOW_WIDTH
    assert kwargs["height"] == launcher.WINDOW_HEIGHT
    assert kwargs["min_size"] == launcher.WINDOW_MIN_SIZE
    assert kwargs["text_select"] is True
    assert webview.settings["ALLOW_DOWNLOADS"] is True
    assert webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True
    assert webview.starts == [
        {"private_mode": False, "storage_path": str(tmp_path / "webview")}
    ]


def test_run_app_window_returns_false_when_gui_loop_fails(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setenv("QUIZGEN_DATA_DIR", str(tmp_path))
    webview = FakeWebview(fail_start=True)
    assert launcher.run_app_window(webview=webview) is False


def test_run_desktop_ui_uses_window_when_webview_works(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setenv("QUIZGEN_DATA_DIR", str(tmp_path))
    exited: list[str] = []
    fallback_calls: list[object] = []

    mode = launcher.run_desktop_ui(
        lambda: exited.append("exit"),
        webview=FakeWebview(),
        fallback=lambda on_exit: fallback_calls.append(on_exit),
    )
    assert mode == "window"
    assert exited == ["exit"]
    assert fallback_calls == []


def test_run_desktop_ui_falls_back_when_window_unavailable():
    launcher = load_launcher()
    exited: list[str] = []
    fallback_calls: list[object] = []

    mode = launcher.run_desktop_ui(
        lambda: exited.append("exit"),
        webview=None,
        fallback=lambda on_exit: fallback_calls.append("tray") or on_exit(),
    )
    assert mode == "tray"
    assert fallback_calls == ["tray"]
    assert exited == ["exit"]


def test_open_existing_instance_attaches_window_without_message(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setenv("QUIZGEN_DATA_DIR", str(tmp_path))
    messages: list[str] = []
    monkeypatch.setattr(launcher, "message_box", lambda *a, **k: messages.append(a[0]))

    assert launcher.open_existing_instance(webview=FakeWebview()) == 0
    assert messages == []


def test_apply_wizard_choices_demo_does_not_require_keys():
    launcher = load_launcher()
    values = launcher.apply_wizard_choices({}, demo=True)
    assert values["MOCK_LLM"] == "true"
    assert values["SETUP_COMPLETE"] == "true"
    assert not values.get("QWEN_API_KEY")
    assert not values.get("DEEPSEEK_API_KEY")


def test_apply_wizard_choices_saves_both_keys_and_optional_tavily():
    launcher = load_launcher()
    values = launcher.apply_wizard_choices(
        {"SECRET_KEY": "keep-me"},
        demo=False,
        qwen_key=" qwen-key ",
        deepseek_key="ds-key",
        tavily_key=" tv-key ",
    )
    assert values["MOCK_LLM"] == "false"
    assert values["QWEN_API_KEY"] == "qwen-key"
    assert values["DEEPSEEK_API_KEY"] == "ds-key"
    assert values["TAVILY_API_KEY"] == "tv-key"
    assert values["SECRET_KEY"] == "keep-me"


def test_apply_wizard_choices_allows_qwen_only():
    launcher = load_launcher()
    values = launcher.apply_wizard_choices({}, demo=False, qwen_key="only-qwen")
    assert values["QWEN_API_KEY"] == "only-qwen"
    assert not values.get("DEEPSEEK_API_KEY")
    assert values["MOCK_LLM"] == "false"


def test_apply_wizard_choices_tavily_optional_when_live():
    launcher = load_launcher()
    values = launcher.apply_wizard_choices({}, demo=False, deepseek_key="ds-only")
    assert values["DEEPSEEK_API_KEY"] == "ds-only"
    assert not values.get("TAVILY_API_KEY")


def test_apply_wizard_choices_rejects_live_without_generator_key():
    launcher = load_launcher()
    try:
        launcher.apply_wizard_choices({}, demo=False, tavily_key="tv")
    except launcher.WizardError as exc:
        assert "至少填写" in str(exc)
    else:
        raise AssertionError("expected WizardError")


def test_apply_wizard_choices_demo_may_still_save_tavily():
    launcher = load_launcher()
    values = launcher.apply_wizard_choices({}, demo=True, tavily_key="tv-demo")
    assert values["MOCK_LLM"] == "true"
    assert values["TAVILY_API_KEY"] == "tv-demo"


def test_open_existing_instance_does_not_open_system_browser(monkeypatch):
    launcher = load_launcher()
    messages: list[str] = []
    opened: list[str] = []
    monkeypatch.setattr(launcher, "message_box", lambda *a, **k: messages.append(a[0]))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))

    assert launcher.open_existing_instance(webview=None) == 0
    assert messages == [f"{launcher.APP_TITLE} 已在运行。"]
    assert opened == []
