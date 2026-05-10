"""Unit tests for ``application.url_inventory.providers._oas3_to_findings``.

The ingest gate is the single boundary at which vendor / dependency
URLs are dropped before they enter ``url_findings``. These tests pin
that contract independently of the Noir / Katana / user-file
adapters.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.url_inventory.ports import UrlProviderContext
from application.url_inventory.providers._oas3_to_findings import iter_oas3_rows
from core.config.schemas import Repository
from domain.url_inventory.entry import UrlSource, UrlTool


def _make_repo(ignore_dirs: list[str] | None = None) -> Repository:
    return Repository.model_construct(
        name="dvna",
        type=["api"],
        path="/tmp/dvna",
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=["http://localhost:9090"],
        test_dirs=[],
        ignore_dirs=ignore_dirs or [],
    )


def _make_ctx(repo: Repository) -> UrlProviderContext:
    return UrlProviderContext(
        repo=repo,
        repo_id=1,
        base_path="/tmp",
        project_name="DVPA",
        run_id=42,
    )


def _doc(*paths_methods: tuple[str, str]) -> dict:
    out: dict = {"paths": {}}
    for path, method in paths_methods:
        out["paths"].setdefault(path, {})[method.lower()] = {}
    return out


def _collect(doc: dict, ctx: UrlProviderContext) -> list[str]:
    rows = list(
        iter_oas3_rows(
            doc,
            ctx,
            source=UrlSource.SCAN,
            tool=UrlTool.NOIR,
            run_id=ctx.run_id,
            file_path=None,
        )
    )
    return [r.path for r in rows]


class TestVendorFilterAtIngestBoundary:
    def test_real_endpoint_passes(self) -> None:
        ctx = _make_ctx(_make_repo())
        doc = _doc(("/api/users", "GET"))
        assert _collect(doc, ctx) == ["/api/users"]

    def test_static_vendor_indicator_dropped(self) -> None:
        # The php-goof regression: a real OAS3 path under /vendor/.
        ctx = _make_ctx(_make_repo())
        doc = _doc(
            ("/api/users", "GET"),
            ("/vendor/dompdf/dompdf/lib/html5lib/Data.php", "POST"),
        )
        assert _collect(doc, ctx) == ["/api/users"]

    def test_node_modules_dropped(self) -> None:
        ctx = _make_ctx(_make_repo())
        doc = _doc(
            ("/api/users", "GET"),
            ("/node_modules/react/index.js", "GET"),
        )
        assert _collect(doc, ctx) == ["/api/users"]

    def test_repo_ignore_dirs_extends_filter(self) -> None:
        ctx = _make_ctx(_make_repo(ignore_dirs=["third_party"]))
        doc = _doc(
            ("/api/users", "GET"),
            ("/third_party/lib/router.py", "GET"),
        )
        assert _collect(doc, ctx) == ["/api/users"]

    def test_repo_ignore_dirs_does_not_relax_static_rule(self) -> None:
        # /vendor/ must still drop even when ignore_dirs adds an unrelated
        # entry.
        ctx = _make_ctx(_make_repo(ignore_dirs=["third_party"]))
        doc = _doc(
            ("/vendor/x.php", "POST"),
            ("/api/clean", "GET"),
        )
        assert _collect(doc, ctx) == ["/api/clean"]

    def test_substring_match_does_not_fire(self) -> None:
        ctx = _make_ctx(_make_repo())
        # "/vendor-api/users" contains "vendor" but not as a path segment.
        doc = _doc(("/vendor-api/users", "GET"))
        assert _collect(doc, ctx) == ["/vendor-api/users"]

    def test_method_filter_still_runs(self) -> None:
        # Non-HTTP keys ("trace" is allowed by OAS3 but iter_oas3_rows
        # excludes it; verify a clearly bogus method drops too).
        ctx = _make_ctx(_make_repo())
        doc = {"paths": {"/api/users": {"get": {}, "bogus": {}}}}
        rows = list(
            iter_oas3_rows(
                doc,
                ctx,
                source=UrlSource.SCAN,
                tool=UrlTool.NOIR,
                run_id=42,
                file_path=None,
            )
        )
        methods = sorted(r.method for r in rows)
        assert methods == ["GET"]

    def test_repo_without_ignore_dirs_attr_is_safe(self) -> None:
        # Defensive: getattr fallback path when a stripped-down stub repo
        # is wired in.
        repo = MagicMock(spec=Repository)
        repo.base_urls = ["http://localhost"]
        repo.ignore_dirs = []
        ctx = UrlProviderContext(
            repo=repo,
            repo_id=1,
            base_path="/tmp",
            project_name="DVPA",
            run_id=1,
        )
        doc = _doc(("/api/users", "GET"), ("/vendor/x", "GET"))
        rows = list(
            iter_oas3_rows(
                doc,
                ctx,
                source=UrlSource.SCAN,
                tool=UrlTool.NOIR,
                run_id=1,
                file_path=None,
            )
        )
        assert [r.path for r in rows] == ["/api/users"]


class TestNonVendorPathHandling:
    """Sanity checks unrelated to the vendor filter. Guard that the rest of
    the iterator's contract didn't drift when the filter was added."""

    def test_path_with_no_methods_yields_nothing(self) -> None:
        ctx = _make_ctx(_make_repo())
        doc: dict = {"paths": {"/api/users": {}}}
        assert _collect(doc, ctx) == []

    def test_paths_missing_returns_empty(self) -> None:
        ctx = _make_ctx(_make_repo())
        assert _collect({}, ctx) == []

    def test_paths_not_a_dict_returns_empty(self) -> None:
        ctx = _make_ctx(_make_repo())
        assert _collect({"paths": []}, ctx) == []
