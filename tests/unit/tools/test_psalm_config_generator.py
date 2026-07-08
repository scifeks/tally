"""Tests for Psalm config generation."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from infrastructure.tools.wrappers.base.psalm import BasePsalmTool


class TestFindSourceDirs:
    """Tests for source directory discovery."""

    def test_extracts_psr4_from_composer_json(self, tmp_path: Path) -> None:
        composer_path = tmp_path / "composer.json"
        composer_path.write_text(json.dumps({"autoload": {"psr-4": {"App\\": "src/"}}}))

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert dirs == ["src"]

    def test_extracts_multiple_psr4_paths(self, tmp_path: Path) -> None:
        composer_path = tmp_path / "composer.json"
        composer_path.write_text(
            json.dumps(
                {
                    "autoload": {
                        "psr-4": {
                            "App\\": "src/",
                            "Tests\\": "tests/",
                        }
                    }
                }
            )
        )

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert len(dirs) == 2
        assert "src" in dirs
        assert "tests" in dirs

    def test_falls_back_to_psalm_xml_dirs(self, tmp_path: Path) -> None:
        psalm_path = tmp_path / "psalm.xml"
        psalm_path.write_text(
            '<?xml version="1.0"?>\n'
            '<psalm xmlns="https://getpsalm.org/schema/config">\n'
            "  <projectFiles>\n"
            '    <directory name="app" />\n'
            "  </projectFiles>\n"
            "</psalm>"
        )

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert dirs == ["app"]

    def test_falls_back_to_repo_root(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert dirs == ["."]

    def test_ignores_malformed_composer_json(self, tmp_path: Path) -> None:
        composer_path = tmp_path / "composer.json"
        composer_path.write_text("invalid json {")

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert dirs == ["."]

    def test_composer_json_without_autoload(self, tmp_path: Path) -> None:
        composer_path = tmp_path / "composer.json"
        composer_path.write_text(json.dumps({"name": "myapp"}))

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert dirs == ["."]

    def test_strips_trailing_slashes_from_psr4(self, tmp_path: Path) -> None:
        composer_path = tmp_path / "composer.json"
        composer_path.write_text(
            json.dumps({"autoload": {"psr-4": {"App\\": "src/app/"}}})
        )

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert dirs == ["src/app"]

    def test_extracts_multiple_directories_from_psalm_xml(self, tmp_path: Path) -> None:
        psalm_path = tmp_path / "psalm.xml"
        psalm_path.write_text(
            '<?xml version="1.0"?>\n'
            '<psalm xmlns="https://getpsalm.org/schema/config">\n'
            "  <projectFiles>\n"
            '    <directory name="src" />\n'
            '    <directory name="lib" />\n'
            "  </projectFiles>\n"
            "</psalm>"
        )

        tool = BasePsalmTool.__new__(BasePsalmTool)
        dirs = tool._find_source_dirs(str(tmp_path))

        assert len(dirs) == 2
        assert "src" in dirs
        assert "lib" in dirs


class TestResolveStubs:
    """Tests for stub file resolution."""

    def test_always_includes_php_builtins(self) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        stubs = tool._resolve_stubs([])

        assert len(stubs) > 0
        assert any("php_builtins" in s for s in stubs)

    def test_resolves_configured_stubs(self) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        stubs = tool._resolve_stubs(["slim", "eloquent"])

        assert len(stubs) >= 3
        resolved_names = [Path(s).stem for s in stubs]
        assert "php_builtins" in resolved_names
        assert "slim" in resolved_names
        assert "eloquent" in resolved_names

    def test_skips_unknown_stub(self) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        stubs = tool._resolve_stubs(["php_builtins", "nonexistent_stub"])

        resolved_names = [Path(s).stem for s in stubs]
        assert "php_builtins" in resolved_names
        assert "nonexistent_stub" not in resolved_names

    def test_deduplicates_php_builtins(self) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        stubs = tool._resolve_stubs(["php_builtins", "php_builtins", "slim"])

        resolved_names = [Path(s).stem for s in stubs]
        count = resolved_names.count("php_builtins")
        assert count == 1

    def test_returns_absolute_paths(self) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        stubs = tool._resolve_stubs(["slim"])

        for stub in stubs:
            assert Path(stub).is_absolute()
            assert stub.endswith(".phpstub")


class TestBuildPsalmXml:
    """Tests for XML configuration generation."""

    def test_generates_valid_xml(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        root = ET.fromstring(xml_str)
        assert "psalm" in root.tag

    def test_includes_project_files(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(
            ["src", "lib"],
            [],
            str(tmp_path),
        )

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        project_files = root.find(f"{{{ns}}}projectFiles")
        if project_files is None:
            project_files = root.find(".//projectFiles")

        assert project_files is not None
        directories = project_files.findall(f"{{{ns}}}directory")
        if not directories:
            directories = project_files.findall("directory")
        dir_names = [d.get("name") for d in directories]
        assert "src" in dir_names
        assert "lib" in dir_names

    def test_includes_stubs(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        stub_paths = ["/absolute/path/php_builtins.phpstub"]
        xml_str = tool._build_psalm_xml(["src"], stub_paths, str(tmp_path))

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        stubs_elem = root.find(f"{{{ns}}}stubs")
        if stubs_elem is None:
            stubs_elem = root.find(".//stubs")

        assert stubs_elem is not None
        files = stubs_elem.findall(f"{{{ns}}}file")
        if not files:
            files = stubs_elem.findall("file")
        file_names = [f.get("name") for f in files]
        assert "/absolute/path/php_builtins.phpstub" in file_names

    def test_sets_taint_analysis_attribute(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        root = ET.fromstring(xml_str)
        assert root.get("runTaintAnalysis") == "true"

    def test_sets_error_level_1(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        root = ET.fromstring(xml_str)
        assert root.get("errorLevel") == "1"

    def test_includes_autoloader_when_vendor_exists(self, tmp_path: Path) -> None:
        vendor_path = tmp_path / "vendor" / "autoload.php"
        vendor_path.parent.mkdir(parents=True)
        vendor_path.touch()

        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        autoloader = root.find(f"{{{ns}}}autoloader")
        if autoloader is None:
            autoloader = root.find(".//autoloader")

        assert autoloader is not None
        filename = autoloader.get("filename")
        assert filename is not None
        assert vendor_path.absolute() == Path(filename)

    def test_omits_autoloader_when_not_present(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        autoloader = root.find(f"{{{ns}}}autoloader")
        if autoloader is None:
            autoloader = root.find(".//autoloader")

        assert autoloader is None

    def test_xml_declaration_included(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        assert xml_str.startswith('<?xml version="1.0"?>')

    def test_no_stubs_element_when_empty(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        root = ET.fromstring(xml_str)
        ns = "https://getpsalm.org/schema/config"
        stubs_elem = root.find(f"{{{ns}}}stubs")
        if stubs_elem is None:
            stubs_elem = root.find(".//stubs")

        assert stubs_elem is None

    def test_namespace_preserved_in_xml(self, tmp_path: Path) -> None:
        tool = BasePsalmTool.__new__(BasePsalmTool)
        xml_str = tool._build_psalm_xml(["src"], [], str(tmp_path))

        assert 'xmlns="https://getpsalm.org/schema/config"' in xml_str
