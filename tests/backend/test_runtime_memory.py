import importlib
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FIXTURE = ROOT / "tests" / "fixtures" / "mock-vault"


@pytest.fixture()
def runtime_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    work = tmp_path / "mock-vault"
    shutil.copytree(FIXTURE, work)
    monkeypatch.setenv("LMZ_CONFIG_PATH", str(work / "config.yaml"))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for name in list(sys.modules):
        if name in {"utils", "runtime_context"} or name.startswith(("api.", "logger", "db.")):
            del sys.modules[name]
    return importlib.import_module("api.runtime")


class FakeMem:
    def __init__(self, rss):
        self.rss = rss


class FakeProc:
    def __init__(self, pid, name, rss_mb=0, exe="", cmdline=None):
        self.pid = pid
        self._name = name
        self._rss = int(rss_mb * 1024 * 1024)
        self._exe = exe
        self._cmdline = cmdline or []
        self._parent = None
        self._children = []
        self.memory_error = False

    def name(self):
        return self._name

    def exe(self):
        return self._exe

    def cmdline(self):
        return self._cmdline

    def memory_info(self):
        if self.memory_error:
            raise RuntimeError("denied")
        return FakeMem(self._rss)

    def parent(self):
        return self._parent

    def children(self, recursive=True):
        if not recursive:
            return list(self._children)
        result = []
        stack = list(self._children)
        while stack:
            child = stack.pop(0)
            result.append(child)
            stack.extend(child._children)
        return result

    def add_child(self, child):
        child._parent = self
        self._children.append(child)
        return child


class FakePsutil:
    def __init__(self, processes):
        self._processes = processes

    def process_iter(self, attrs=None):
        return list(self._processes)


def test_backend_only_fallback_tree(runtime_module):
    backend = FakeProc(100, "python.exe", 80, cmdline=["python", "web_api.py"])
    backend.add_child(FakeProc(101, "ffmpeg.exe", 20))

    processes, mode, warnings = runtime_module._collect_process_group(backend)
    payload = runtime_module._aggregate_memory_processes(processes, backend.pid, mode, warnings)

    assert payload["mode"] == "backend_tree"
    assert payload["roles"]["backend_mb"] == 80
    assert payload["roles"]["subprocess_mb"] == 20
    assert payload["app_mb"] == 100
    assert payload["warnings"]


def test_packaged_sidecar_tree_counts_tauri_and_webview(runtime_module):
    tauri = FakeProc(10, "LMZ.exe", 40, exe="C:/Program Files/LMZ/LMZ.exe")
    backend = tauri.add_child(FakeProc(11, "lmz-api.exe", 90))
    tauri.add_child(FakeProc(12, "msedgewebview2.exe", 160))

    processes, mode, warnings = runtime_module._collect_process_group(backend)
    payload = runtime_module._aggregate_memory_processes(processes, backend.pid, mode, warnings)

    assert mode == "packaged_sidecar"
    assert payload["roles"]["tauri_mb"] == 40
    assert payload["roles"]["backend_mb"] == 90
    assert payload["roles"]["webview_mb"] == 160
    assert payload["app_mb"] == 290
    assert warnings == []


def test_dev_launcher_tree_counts_sibling_tauri_and_tools(runtime_module):
    dev = FakeProc(
        1,
        "python.exe",
        30,
        cmdline=["python", "F:/ARCHIVE/main/software/python/projects/local_media_zettelkasten/dev.py"],
    )
    backend = dev.add_child(FakeProc(2, "python.exe", 85, cmdline=["python", "backend/web_api.py"]))
    dev.add_child(FakeProc(3, "node.exe", 70, cmdline=["node", "vite"]))
    dev.add_child(FakeProc(4, "msedgewebview2.exe", 120))

    processes, mode, warnings = runtime_module._collect_process_group(backend)
    payload = runtime_module._aggregate_memory_processes(processes, backend.pid, mode, warnings)

    assert mode == "dev_launcher"
    assert payload["roles"]["backend_mb"] == 85
    assert payload["roles"]["dev_tool_mb"] == 70
    assert payload["roles"]["webview_mb"] == 120
    assert payload["roles"]["other_mb"] == 30
    assert payload["app_mb"] == 305


def test_unavailable_process_memory_is_skipped_with_warning(runtime_module):
    backend = FakeProc(100, "python.exe", 80)
    denied = backend.add_child(FakeProc(101, "ffmpeg.exe", 20))
    denied.memory_error = True

    processes, mode, warnings = runtime_module._collect_process_group(backend)
    payload = runtime_module._aggregate_memory_processes(processes, backend.pid, mode, warnings)

    assert payload["roles"]["backend_mb"] == 80
    assert payload["roles"]["subprocess_mb"] == 0
    assert payload["app_mb"] == 80
    assert any("memory unavailable" in warning for warning in payload["warnings"])


def test_dev_scan_counts_project_matched_process_tree(runtime_module, monkeypatch):
    backend = FakeProc(100, "python.exe", 80, cmdline=["python", "web_api.py"])
    node = FakeProc(
        200,
        "node.exe",
        60,
        cmdline=["node", "F:/ARCHIVE/main/software/python/projects/local_media_zettelkasten/frontend/node_modules/vite/bin/vite.js"],
    )
    node.add_child(FakeProc(201, "msedgewebview2.exe", 140))
    unrelated = FakeProc(300, "msedgewebview2.exe", 500, cmdline=["msedgewebview2", "unrelated"])
    fake_psutil = FakePsutil([backend, node, unrelated])
    monkeypatch.setattr(runtime_module, "_project_path_token", lambda: "local_media_zettelkasten")

    processes, mode, warnings = runtime_module._collect_process_group(backend, fake_psutil)
    payload = runtime_module._aggregate_memory_processes(processes, backend.pid, mode, warnings)

    assert mode == "dev_scan"
    assert payload["roles"]["backend_mb"] == 80
    assert payload["roles"]["dev_tool_mb"] == 60
    assert payload["roles"]["webview_mb"] == 140
    assert payload["app_mb"] == 280
    assert all(row["pid"] != 300 for row in payload["processes"])
