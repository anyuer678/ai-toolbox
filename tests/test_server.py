"""ai-toolbox unit tests — pure helpers + collector against temp fixtures."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("ai_toolbox_server", SERVER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_toolbox_server"] = mod
    spec.loader.exec_module(mod)
    return mod


srv = load_server()


class TestSafeFn:
    def test_strips_control_and_illegal(self):
        assert "/" not in srv.safe_fn('a/b\\c:d*e?f"g<h>i|j')
        assert "\n" not in srv.safe_fn("a\nb\tc")

    def test_caps_length(self):
        assert len(srv.safe_fn("x" * 200)) <= 60

    def test_empty_fallback(self):
        assert srv.safe_fn("   ") == "untitled"


class TestReasonixCollector:
    def test_missing_dir_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "REASONIX_DIR", tmp_path / "nope")
        st = srv.get_reasonix_stats()
        assert st["models"] == {}
        assert st["totals"]["prompt"] == 0

    def test_jsonl_totals(self, tmp_path, monkeypatch):
        stats = tmp_path / "stats"
        stats.mkdir()
        day = stats / "2026-09-22.jsonl"
        rows = [
            {"model": "m1", "prompt": 10, "completion": 5, "cache_hit": 2, "requests": 1, "total": 15},
            {"model": "m1", "prompt": 5, "completion": 1, "cache_hit": 1, "requests": 1, "total": 6},
            {"model": "m2", "prompt": 1, "completion": 1, "cache_hit": 0, "requests": 1, "total": 2},
        ]
        day.write_text("\n".join(json.dumps(r) for r in rows) + "\nbad-line\n", encoding="utf-8")
        monkeypatch.setattr(srv, "REASONIX_DIR", tmp_path)
        st = srv.get_reasonix_stats()
        assert set(st["models"]) == {"m1", "m2"}
        assert st["models"]["m1"]["prompt"] == 15
        assert st["totals"]["prompt"] == 16
        assert st["totals"]["requests"] == 3
        assert "2026-09-22" in st["daily"]


class TestCollectAll:
    def test_collect_all_keys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "REASONIX_DIR", tmp_path / "r")
        monkeypatch.setattr(srv, "OPENCODE_DB", tmp_path / "o.db")
        monkeypatch.setattr(srv, "ZCODE_DB", tmp_path / "z.db")
        out = srv.collect_all()
        assert "reasonix" in out and "opencode" in out and "zcode" in out
