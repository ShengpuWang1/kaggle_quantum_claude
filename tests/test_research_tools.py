import json

import pytest

from autoresearch.providers import ToolCall
from autoresearch.research_tools import ResearchSourceError, ResearchToolContext

NOTEBOOK_URL = "https://www.kaggle.com/code/example/published-notebook"
PAPER_URL = "https://arxiv.org/abs/2610.23832"
COMPETITION = "google-verifiable-quantum-circuit-compilation"


def kaggle_payload(
    *, competitions=None, source=None, kernel_type="notebook", is_private=False
):
    if source is None:
        source = json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["Published approach"]},
                    {"cell_type": "code", "source": ["useful_idea = True\n"]},
                ]
            }
        )
    return json.dumps(
        {
            "metadata": {
                "title": "Published notebook",
                "kernelType": kernel_type,
                "isPrivate": is_private,
                "currentVersionNumber": 3,
                "competitionDataSources": (
                    [COMPETITION] if competitions is None else competitions
                ),
            },
            "blob": {"source": source},
        }
    ).encode()


def context(tmp_path, monkeypatch):
    root = tmp_path / "project"
    workspace = root / "autoresearch" / "experiments" / "EXP-test" / "director"
    workspace.mkdir(parents=True)
    tools = ResearchToolContext(
        workspace,
        writable=False,
        read_root=root,
        papers_directory=root / "docs" / "papers",
    )

    tools.fetch_calls = []

    def fetch(url, *, max_bytes):
        tools.fetch_calls.append(url)
        if "/api/v1/kernels/pull/" in url:
            return url, "application/json", kaggle_payload()
        if "/abs/" in url:
            return url, "text/html", b"<html><body>Useful paper idea</body></html>"
        return url, "application/pdf", b"%PDF-1.4\n% tiny offline test\n%%EOF"

    monkeypatch.setattr(tools, "_fetch", fetch)
    return tools


def test_notebook_and_paper_evidence_require_inspection(tmp_path, monkeypatch):
    tools = context(tmp_path, monkeypatch)
    notebook = {
        "source_type": "notebook",
        "title": "Published notebook",
        "url": NOTEBOOK_URL,
        "local_path": "",
        "insight": "Adapt the published circuit idea",
    }
    with pytest.raises(ResearchSourceError, match="not fetched"):
        tools.validate_evidence([notebook])

    result = tools.execute(ToolCall("1", "fetch_research_source", {"url": NOTEBOOK_URL}))
    assert not result.is_error
    assert "useful_idea = True" in result.content
    assert "Current public version: 3" in result.content
    assert tools.fetch_calls == [
        "https://www.kaggle.com/api/v1/kernels/pull/example/published-notebook"
    ]
    tools.validate_evidence([notebook])

    paper = {
        "source_type": "paper",
        "title": "Published paper",
        "url": PAPER_URL,
        "local_path": "docs/papers/2610.23832.pdf",
        "insight": "Adapt the paper's verified construction",
    }
    with pytest.raises(ResearchSourceError, match="not fetched"):
        tools.validate_evidence([paper])
    assert not tools.execute(
        ToolCall("2", "fetch_research_source", {"url": PAPER_URL})
    ).is_error
    with pytest.raises(ResearchSourceError, match="downloaded"):
        tools.validate_evidence([paper])
    downloaded = tools.execute(
        ToolCall(
            "3",
            "download_paper",
            {"url": PAPER_URL, "filename": "2610.23832.pdf"},
        )
    )
    assert not downloaded.is_error
    tools.validate_evidence([paper])
    assert (tools.papers_directory / "2610.23832.pdf").read_bytes().startswith(b"%PDF")


def test_research_download_rejects_unallowed_host_and_overwrite(tmp_path, monkeypatch):
    tools = context(tmp_path, monkeypatch)
    denied = tools.execute(
        ToolCall(
            "1",
            "download_paper",
            {"url": "https://example.com/paper.pdf", "filename": "paper.pdf"},
        )
    )
    assert denied.is_error
    assert not (tools.papers_directory / "paper.pdf").exists()

    first = ToolCall(
        "2", "download_paper", {"url": PAPER_URL, "filename": "paper.pdf"}
    )
    assert not tools.execute(first).is_error

    def changed(url, *, max_bytes):
        return url, "application/pdf", b"%PDF-different"

    monkeypatch.setattr(tools, "_fetch", changed)
    assert tools.execute(first).is_error
    assert (tools.papers_directory / "paper.pdf").read_bytes() != b"%PDF-different"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (kaggle_payload(competitions=["another-competition"]), "required competition"),
        (kaggle_payload(source=""), "no readable notebook source"),
        (kaggle_payload(source="{"), "malformed notebook source"),
        (kaggle_payload(kernel_type="script"), "not a notebook"),
        (kaggle_payload(is_private=True), "notebook is private"),
    ],
)
def test_kaggle_api_validation_fails_closed(tmp_path, monkeypatch, payload, message):
    tools = context(tmp_path, monkeypatch)
    monkeypatch.setattr(
        tools,
        "_fetch",
        lambda url, *, max_bytes: (url, "application/json", payload),
    )
    result = tools.execute(
        ToolCall("1", "fetch_research_source", {"url": NOTEBOOK_URL})
    )
    assert result.is_error
    assert message in result.content
    assert NOTEBOOK_URL not in tools.fetched_urls


def test_kaggle_rejects_non_notebook_page_without_fetch(tmp_path, monkeypatch):
    tools = context(tmp_path, monkeypatch)
    result = tools.execute(
        ToolCall(
            "1",
            "fetch_research_source",
            {"url": f"https://www.kaggle.com/competitions/{COMPETITION}/code"},
        )
    )
    assert result.is_error
    assert "/code/<owner>/<slug>" in result.content
    assert tools.fetch_calls == []


def test_two_kaggle_failures_require_paper_fallback(tmp_path, monkeypatch):
    tools = context(tmp_path, monkeypatch)
    calls = []

    def unavailable(url, *, max_bytes):
        calls.append(url)
        raise ResearchSourceError("Public notebook API unavailable")

    monkeypatch.setattr(tools, "_fetch", unavailable)
    call = ToolCall("1", "fetch_research_source", {"url": NOTEBOOK_URL})
    first = tools.execute(call)
    second = tools.execute(call)
    third = tools.execute(call)
    assert first.is_error and "disabled after two failures" not in first.content
    assert second.is_error and "source='paper'" in second.content
    assert third.is_error and "source='paper'" in third.content
    assert len(calls) == 2
