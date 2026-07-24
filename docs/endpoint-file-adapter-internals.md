# Endpoint File Adapter Internals

This guide is for contributors adding support for a new endpoint file format.
It covers the adapter pattern, the interface contract, and the step-by-step
process for registering a new format.

---

## Overview

The endpoint file feature converts API specification files from various formats
into OAS3 (OpenAPI 3.x) so that ZAP can import them via `-openapifile`. The
adapter pattern was chosen because each format has independent detection logic,
validation requirements, and conversion tooling. Adding a new format requires
no changes to any existing adapter, only new files and small additions to
the detector and service.

### Code location

All converter code lives in `infrastructure/endpoints/converters/`:

```
infrastructure/endpoints/converters/
  __init__.py      # Public API: ConverterError, convert_endpoint_file
  base.py          # Abstract base class and ConverterError
  detector.py      # Format detection: FormatDetector
  service.py       # Orchestration: convert_endpoint_file()
  oas3.py          # OAS3 passthrough adapter
  oas2.py          # OAS2/Swagger → OAS3 via swagger2openapi
  postman.py       # Postman Collection → OAS3 via postman-to-openapi
  har.py           # HAR → OAS3 (pure Python)
  katana.py        # Katana JSONL → OAS3 (pure Python)
```

### Public API

Only two names are exported from `__init__.py`:

```python
from .base import ConverterError as ConverterError
from .service import convert_endpoint_file as convert_endpoint_file
```

Call sites (e.g. the project wizard) import these two names and nothing else.

---

## Interface contract

Every adapter must subclass `ConverterAdapter` from `base.py` and implement
three members. The full abstract class is reproduced here verbatim:

```python
class ConverterError(Exception):
    """Raised for validation failures and conversion errors."""


class ConverterAdapter(ABC):
    """Interface all converter adapters must implement."""

    @property
    @abstractmethod
    def supported_extensions(self) -> frozenset[str]: ...

    @abstractmethod
    def validate(self, path: Path) -> None:
        """Raise ConverterError if file is not valid for this format."""

    @abstractmethod
    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert source to OAS3. Return path to output file.

        The output file is written inside output_dir.
        Raises ConverterError on failure.
        """
```

**`supported_extensions`** is the set of file extensions this adapter handles
(e.g. `frozenset({".json", ".yaml", ".yml"})`). Used for documentation
purposes; actual format detection is done by `FormatDetector`, not by
extension matching.

**`validate(path)`** must raise `ConverterError` with a human-readable
message if the file is structurally invalid for this format. Must not
perform conversion. Called before `convert()`.

**`convert(source, output_dir)`** must write one file inside `output_dir`
and return its `Path`. Must raise `ConverterError` on any failure. The caller
creates `output_dir` before calling `convert()`.

---

## Adding a new format

### 1. Create the adapter module

Create `infrastructure/endpoints/converters/<format>.py`. The file name uses
only lowercase letters and underscores (no hyphens).

Subclass `ConverterAdapter` and implement the three members:

```python
"""<Format> adapter: converts <format> files to OAS3."""

from __future__ import annotations

from pathlib import Path

from .base import ConverterAdapter, ConverterError


class <Format>Adapter(ConverterAdapter):

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json"})

    def validate(self, path: Path) -> None:
        """Raise ConverterError if path is not a valid <format> file."""
        ...

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert source to OAS3 and return the output path."""
        output_file = output_dir / "seed.json"
        ...
        return output_file
```

### 2. Register the format in FormatDetector

Open `infrastructure/endpoints/converters/detector.py` and add a detection
branch in `FormatDetector.detect()`. Detection order matters, so add the new
branch before the final `raise ConverterError(...)` block:

```python
def detect(self, path: Path) -> str:
    # existing branches ...

    # Add your branch here, checking a reliable key in the parsed document:
    if doc.get("your_format_key") == "expected_value":
        return "your_format_name"

    raise ConverterError(...)
```

Also add the new format to the `_SUPPORTED_FORMATS` string at the top of
`detector.py` so it appears in error messages when detection fails.

### 3. Register the adapter in service.py

Open `infrastructure/endpoints/converters/service.py` and add the new format
to `_ADAPTER_MAP`:

```python
from .your_module import YourFormatAdapter

_ADAPTER_MAP = {
    "oas3": OAS3PassthroughAdapter,
    "oas2": OAS2Adapter,
    "postman": PostmanAdapter,
    "har": HARAdapter,
    "katana": KatanaAdapter,
    "your_format_name": YourFormatAdapter,   # add this
}
```

The key must match the string returned by `FormatDetector.detect()`.

### 4. Add unit tests

Add tests under `tests/unit/infrastructure/`. Test at minimum:

- `validate()` accepts a valid file
- `validate()` raises `ConverterError` for an invalid file
- `convert()` produces a valid OAS3 JSON file when given a valid input
- `convert()` raises `ConverterError` on bad input

### 5. Update the user guide

Add the new format to the Supported formats table in
`docs/endpoint-files.md`.

---

## Subprocess-based converters

`oas2.py` and `postman.py` invoke external npm tools via subprocess. The
pattern they follow:

1. Check that `node` and `npx` are on `PATH` using `shutil.which()`. If
   either is missing, raise `ConverterError` with an install hint immediately.
   Do not attempt to run the subprocess.

2. Run the tool via `subprocess.run()` with `capture_output=True` and
   `check=False` so that a non-zero exit code does not raise an exception:

   ```python
   result = subprocess.run(
       ["npx", "tool-name", str(source), "-o", str(output_file)],
       capture_output=True,
       text=True,
       check=False,
   )
   ```

3. Check `result.returncode`. If non-zero, raise `ConverterError(result.stderr)`.
   This surfaces the tool's error message directly to the user.

4. Return the output path.

---

## Pure-Python converter

`har.py` requires no external tools. It:

1. Parses the HAR file as JSON.
2. Iterates over `log.entries`, grouping by `(url_path, method)` to deduplicate
   repeated requests to the same endpoint.
3. Builds an OAS3 document from the grouped entries, extracting query
   parameters from `queryString` and request bodies from `postData`.
4. Writes the result as `seed.json` in `output_dir`.

When writing a pure-Python adapter, the same structure applies: parse the
input, build an OAS3 dict, and write it with `json.dumps`.
