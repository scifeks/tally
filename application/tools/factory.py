"""Factory for creating tool wrapper instances from config."""

import importlib
import inspect

from domain.tools.interface import ToolInterface


def _get_extra_deps(tool_name: str) -> dict:
    if tool_name == "katana":
        from infrastructure.endpoints.converters.katana import (
            KatanaAdapter,
        )

        return {"endpoint_converter": KatanaAdapter()}
    return {}


class ToolWrapperFactory:
    def create(self, tool_name: str, config) -> ToolInterface:
        location = config.location
        file_stem = tool_name.replace("-", "_")
        module_name = f"infrastructure.tools.wrappers.{location}.{file_stem}"
        module = importlib.import_module(module_name)
        for _attr, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ToolInterface)
                and not inspect.isabstract(obj)
                and obj.__module__ == module_name
            ):
                kwargs: dict = {"config": config}
                kwargs.update(_get_extra_deps(tool_name))
                return obj(**kwargs)  # type: ignore[call-arg]
        raise ValueError(
            f"No ToolInterface implementation found for {tool_name!r} in {module_name}"
        )
