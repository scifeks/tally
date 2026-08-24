"""Tests for Psalm Docker config generation."""

import xml.etree.ElementTree as ET

from infrastructure.tools.wrappers.docker.psalm import PsalmDockerTool


class TestBuildDockerXml:
    def test_includes_ignore_files(self) -> None:
        tool = PsalmDockerTool.__new__(PsalmDockerTool)
        xml_str = tool._build_docker_xml(
            ["../src"],
            [],
            None,
            ignored_dirs=["../tests", "../vendor"],
        )

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        pf = root.find(f"{{{ns}}}projectFiles")
        assert pf is not None

        ignore = pf.find(f"{{{ns}}}ignoreFiles")
        assert ignore is not None
        assert ignore.get("allowMissing") == "true"

        dirs = ignore.findall(f"{{{ns}}}directory")
        names = [d.get("name") for d in dirs]
        assert names == ["../tests", "../vendor"]

    def test_omits_ignore_files_when_no_dirs(self) -> None:
        tool = PsalmDockerTool.__new__(PsalmDockerTool)
        xml_str = tool._build_docker_xml(["../src"], [], None)

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        pf = root.find(f"{{{ns}}}projectFiles")
        assert pf is not None

        ignore = pf.find(f"{{{ns}}}ignoreFiles")
        assert ignore is None
