"""Unit tests for core.detection.spa.detect_spa."""

from __future__ import annotations

import json
from pathlib import Path

from core.detection.spa import detect_spa

# Helpers


def _write_pkg(root: Path, deps: dict[str, str]) -> None:
    (root / "package.json").write_text(
        json.dumps({"dependencies": deps}), encoding="utf-8"
    )


def _write_src(root: Path, filename: str, content: str) -> None:
    (root / filename).write_text(content, encoding="utf-8")


# Non-SPA repos


class TestNonSpaRepos:
    def test_empty_dir_returns_false(self, tmp_path: Path) -> None:
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is False
        assert reason == ""

    def test_nonexistent_path_returns_false(self, tmp_path: Path) -> None:
        is_spa, _ = detect_spa(tmp_path / "does_not_exist")
        assert is_spa is False

    def test_pure_python_repo_returns_false(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("flask\nrequests\n")
        (tmp_path / "app.py").write_text(
            "from flask import Flask\napp = Flask(__name__)"
        )
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False

    def test_php_repo_returns_false(self, tmp_path: Path) -> None:
        (tmp_path / "index.php").write_text("<?php echo 'hello'; ?>")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False

    def test_package_json_with_no_spa_deps_returns_false(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"express": "^4.18.0", "lodash": "^4.17.0"})
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False


# Manifest sniff: SPA detected via package.json


class TestManifestSniff:
    def test_react_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"react": "^18.0.0", "react-dom": "^18.0.0"})
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "package.json" in reason

    def test_react_router_dom_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"react-router-dom": "^6.0.0"})
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_angular_core_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "package.json" in reason

    def test_vue_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"vue": "^3.4.0"})
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_svelte_kit_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"@sveltejs/kit": "^2.0.0"})
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_next_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"next": "^14.0.0", "react": "^18.0.0"})
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_nuxt_detected(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"nuxt": "^3.0.0"})
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_dev_dependencies_checked(self, tmp_path: Path) -> None:
        pkg = {"devDependencies": {"vite": "^5.0.0", "react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_peer_dependencies_checked(self, tmp_path: Path) -> None:
        pkg = {"peerDependencies": {"react": ">=18"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_malformed_package_json_returns_false(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{not valid json", encoding="utf-8")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False

    def test_reason_contains_dep_name(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"vue-router": "^4.0.0"})
        _, reason = detect_spa(tmp_path)
        assert "vue-router" in reason


# Source-pattern grep: SPA detected via source code patterns


class TestSourcePatternGrep:
    def test_browser_router_jsx_detected(self, tmp_path: Path) -> None:
        _write_src(
            tmp_path, "App.jsx", "import { BrowserRouter } from 'react-router-dom'"
        )
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "React Router" in reason

    def test_create_browser_router_detected(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "router.ts", "const router = createBrowserRouter(routes)")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is True

    def test_angular_router_module_detected(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "app.module.ts", "RouterModule.forRoot(routes)")
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "Angular Router" in reason

    def test_vue_create_router_detected(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "router.js", "const router = createRouter({ history })")
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "Vue Router" in reason

    def test_vue_router_view_html_detected(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "index.html", "<div><router-view /></div>")
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "router-view" in reason

    def test_angularjs_ng_app_detected(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "index.html", '<div ng-app="myApp">')
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "AngularJS" in reason

    def test_reason_contains_filename(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "router.ts", "createRouter({ history })")
        _, reason = detect_spa(tmp_path)
        assert "router.ts" in reason

    def test_node_modules_skipped(self, tmp_path: Path) -> None:
        nm = tmp_path / "node_modules" / "react-router-dom"
        nm.mkdir(parents=True)
        _write_src(nm, "index.js", "export { BrowserRouter }")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False

    def test_dist_dir_skipped(self, tmp_path: Path) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        _write_src(dist, "bundle.js", "createBrowserRouter(routes)")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False

    def test_non_js_extension_not_scanned(self, tmp_path: Path) -> None:
        _write_src(tmp_path, "router.py", "createBrowserRouter(routes)")
        is_spa, _ = detect_spa(tmp_path)
        assert is_spa is False

    def test_manifest_sniff_takes_precedence(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path, {"react": "^18.0.0"})
        _write_src(tmp_path, "App.tsx", "createBrowserRouter(routes)")
        is_spa, reason = detect_spa(tmp_path)
        assert is_spa is True
        assert "package.json" in reason
