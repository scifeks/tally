"""OAS3 passthrough adapter — validates and normalises OAS3 files."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import yaml
from openapi_spec_validator import OpenAPIV30SpecValidator, validate

from .base import ConverterAdapter, ConverterError


def _parse_file(path: Path) -> dict:
    """Parse a JSON or YAML file and return the parsed dict."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConverterError(f"File is not valid JSON: {exc}") from exc
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConverterError(f"File is not valid YAML: {exc}") from exc


def _normalize_full_url_paths(doc: dict) -> dict:
    """Rewrite full-URL path keys to relative paths; add matching servers entries.

    OAS3 requires paths keys to start with '/'. When a user-supplied spec
    uses full URLs as keys (e.g. https://example.com/api/users), this function
    extracts the host as a servers entry and converts each key to its path
    component. First-seen wins on collisions.
    """
    paths = doc.get("paths", {})
    if not any("://" in k for k in paths):
        return doc
    servers = list(doc.get("servers", []))
    server_urls = {s["url"] for s in servers if isinstance(s, dict) and "url" in s}
    new_paths: dict = {}
    for key, val in paths.items():
        if "://" in key:
            parsed = urlparse(key)
            server_url = f"{parsed.scheme}://{parsed.netloc}"
            if server_url not in server_urls:
                servers.append({"url": server_url})
                server_urls.add(server_url)
            rel = parsed.path or "/"
            if rel not in new_paths:
                new_paths[rel] = val
        else:
            if key not in new_paths:
                new_paths[key] = val
    result = dict(doc)
    result["paths"] = new_paths
    if servers:
        result["servers"] = servers
    return result


class OAS3PassthroughAdapter(ConverterAdapter):
    """Adapter for files already in OAS3 format — normalises, validates, writes."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json", ".yaml", ".yml"})

    def validate(self, path: Path) -> None:
        """Parse, normalise, and validate an OAS3 file."""
        doc = _parse_file(path)
        openapi_ver = doc.get("openapi", "")
        if not isinstance(openapi_ver, str) or not openapi_ver.startswith("3."):
            raise ConverterError(
                f"File does not contain a valid OAS3 'openapi' key "
                f"(found: {openapi_ver!r})"
            )
        doc = _normalize_full_url_paths(doc)
        try:
            validate(doc, cls=OpenAPIV30SpecValidator)
        except Exception as exc:
            raise ConverterError(f"OAS3 spec validation failed: {exc}") from exc

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Normalise and write OAS3 JSON to output_dir/seed.json."""
        doc = _parse_file(source)
        doc = _normalize_full_url_paths(doc)
        dest = output_dir / "seed.json"
        dest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return dest
