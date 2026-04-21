"""Postman collection adapter — converts to OAS3 via postman-to-openapi."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

from .base import ConverterAdapter, ConverterError

_NODE_MISSING_MSG = (
    "Postman collection conversion requires Node.js and npm. "
    "Install Node.js from https://nodejs.org/, then run: "
    "npm install -g postman-to-openapi"
)
_P2O_MISSING_MSG = (
    "postman-to-openapi is not installed. Run: npm install -g postman-to-openapi"
)


class PostmanAdapter(ConverterAdapter):
    """Adapter for Postman collections — converts to OAS3."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json"})

    def validate(self, path: Path) -> None:
        """Check that file is a Postman collection."""
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConverterError(f"File is not valid JSON: {exc}") from exc
        info = doc.get("info", {})
        schema = info.get("schema", "") if isinstance(info, dict) else ""
        if "getpostman.com" not in schema:
            raise ConverterError(
                "File does not appear to be a Postman collection "
                "(expected 'info.schema' to contain 'getpostman.com')"
            )

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert Postman collection to OAS3 using postman-to-openapi."""
        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            raise ConverterError(_NODE_MISSING_MSG)

        npm_root_r = subprocess.run(
            [npm, "root", "-g"], capture_output=True, text=True, check=False
        )
        if npm_root_r.returncode != 0:
            raise ConverterError(_P2O_MISSING_MSG)
        npm_root = npm_root_r.stdout.strip()
        if not (Path(npm_root) / "postman-to-openapi").exists():
            raise ConverterError(_P2O_MISSING_MSG)

        # p2o v1.7.3 crashes when request.header is absent; patch before converting.
        script = (
            "const p2o=require('postman-to-openapi');"
            "const fs=require('fs'),os=require('os'),path=require('path');"
            "function fix(items){for(const i of (items||[]))"
            "{if(i.item)fix(i.item);"
            "else if(i.request&&!i.request.header)i.request.header=[];}}"
            "const raw=JSON.parse(fs.readFileSync(process.env.P2O_IN,'utf8'));"
            "fix(raw.item);"
            "const tmp=path.join(os.tmpdir(),'p2o_'+Date.now()+'.json');"
            "fs.writeFileSync(tmp,JSON.stringify(raw));"
            "p2o(tmp,'/dev/null')"
            ".then(s=>{try{fs.unlinkSync(tmp);}catch(e){}"
            "process.stdout.write(s);process.exit(0);})"
            ".catch(e=>{try{fs.unlinkSync(tmp);}catch(e2){}"
            "process.stderr.write(String(e.message||e));process.exit(1);});"
        )
        result = subprocess.run(
            [node, "-e", script],
            capture_output=True,
            text=True,
            env={**os.environ, "NODE_PATH": npm_root, "P2O_IN": str(source)},
            check=False,
        )
        if result.returncode != 0:
            raise ConverterError(
                result.stderr or "postman-to-openapi conversion failed"
            )

        try:
            doc = yaml.safe_load(result.stdout)
        except yaml.YAMLError as exc:
            raise ConverterError(f"Failed to parse conversion output: {exc}") from exc

        output_file = output_dir / "seed.json"
        output_file.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return output_file
