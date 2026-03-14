"""Factory for creating tool wrapper instances from config."""

import importlib
import inspect

from .interface import ToolInterface


class ToolWrapperFactory:
    def create(self, tool_name: str, config) -> ToolInterface:
        location = config.location
        file_stem = tool_name.replace("-", "_")
        module_name = f"core.tools.wrappers.{location}.{file_stem}"
        module = importlib.import_module(module_name)
        for _attr, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ToolInterface)
                and not inspect.isabstract(obj)
                and obj.__module__ == module_name
            ):
                return obj(config=config)  # type: ignore[call-arg]
        raise ValueError(
            f"No ToolInterface implementation found for {tool_name!r} in {module_name}"
        )
