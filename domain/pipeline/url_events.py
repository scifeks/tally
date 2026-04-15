"""URL discovery pipeline events."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class URLSourceChanged:
    """Fired when a URL source produces new output.

    Triggers the dedup-and-format pipeline.  Emitted by:
    - ``URLSourceEmitter`` when Katana or Noir completes successfully.
    - ``InteractiveProjectWizard`` directly when a user-provided endpoint
      file is converted and saved (tool_name="user").
    """

    repo_name: str
    project_name: str
    base_path: str
    base_url: str
    tool_name: str  # "katana", "noir", or "user"


@dataclass
class ConversionOutputs:
    """Mutable result bag populated by format-conversion handlers.

    Both ``URLSeedsHandler`` and ``URLOS3Handler`` write their output paths
    here.  ``URLDedupeHandler`` reads the paths after
    ``bus.dispatch(URLsDeduped)`` returns.
    """

    seeds_path: str = ""
    oas3_path: str = ""


@dataclass
class URLsDeduped:
    """Fired after URL sources have been merged and deduplicated.

    Carries the deduplicated URL list and a mutable ``ConversionOutputs``
    bag so multiple subscribers can write their generated file paths back
    to the emitter.
    """

    urls: list[str]
    repo_name: str
    project_name: str
    base_path: str
    outputs: ConversionOutputs = field(default_factory=ConversionOutputs)


@dataclass
class URLsConverted:
    """Fired after seeds.txt and merged_oas3.json have been written.

    Carries the final artifact paths so ``ConfigUpdateHandler`` can persist
    them to project.json.
    """

    repo_name: str
    project_name: str
    base_path: str
    seeds_path: str
    oas3_path: str
