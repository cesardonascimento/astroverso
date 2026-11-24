from __future__ import annotations

import importlib.util
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from kit import ui
from kit.app import REQUIRED, Action

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"


@dataclass
class LoadedApp:
    name: str
    module: ModuleType | None = None
    problem: str | None = None

    @property
    def description(self) -> str:
        return str(getattr(self.module, "DESCRIPTION", ""))

    def actions(self) -> list[Action]:
        actions = getattr(self.module, "actions", None)
        return list(actions()) if callable(actions) else []


def load(folder: Path) -> LoadedApp:
    app = LoadedApp(folder.name)
    spec = importlib.util.spec_from_file_location(f"astroverso_app_{folder.name}", folder / "app.py")
    if spec is None or spec.loader is None:
        app.problem = "app.py não pode ser lido"
        return app
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except Exception as problem:
        sys.modules.pop(spec.name, None)
        app.problem = f"erro ao carregar: {problem}"
        return app
    missing = [name for name in REQUIRED if not hasattr(module, name)]
    if missing:
        app.problem = f"falta {', '.join(missing)}"
        return app
    app.module = module
    return app


def discover(folder: Path = APPS) -> list[LoadedApp]:
    if not folder.is_dir():
        return []
    return [
        load(path)
        for path in sorted(folder.iterdir())
        if path.is_dir() and not path.name.startswith((".", "_")) and (path / "app.py").is_file()
    ]


def call(app: LoadedApp, function: Callable[..., object], *args: object) -> tuple[bool, object]:
    ui.set_app(app.name)
    try:
        return True, function(*args)
    except SystemExit as exit:
        return exit.code in (0, None), None
    except KeyboardInterrupt:
        raise
    except Exception as problem:
        ui.error(f"falha inesperada: {problem}")
        ui.prefixed(traceback.format_exc().rstrip(), sys.stderr)
        return False, None
    finally:
        ui.set_app("astroverso")


def installed(app: LoadedApp) -> bool:
    success, result = call(app, app.module.status) if app.module else (False, None)
    return success and bool(result)
