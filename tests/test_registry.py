"""Tests for source discovery and the registry (IMPLEMENTATION.md Step 3).

Discovery is exercised against a throwaway package on `sys.path`, so these tests
never write into the real `src/mahlzeit/sources/` tree. Registry behavior is
tested against the live auto-discovered `SOURCES` and, deterministically, against
a patched dict.
"""

import shutil
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

import pytest

import mahlzeit.registry as registry
from mahlzeit.registry import all_sources, get_source
from mahlzeit.sources import discover_sources
from mahlzeit.sources.base import Source

SOURCE = textwrap.dedent(
    """\
    from mahlzeit.sources.base import Source

    class {class_name}(Source):
        id = {id_value}
        name = "Test"
        source_url = "https://example.invalid/{id}"

        def fetch(self, cache_dir):
            return []

        def parse(self, pdf_paths):
            return []
    """
)


class TempPackage:
    """Throwaway importable package under `sys.path`."""

    def __init__(self):
        self._tmpdir = tempfile.mkdtemp()
        self.package_dir = Path(self._tmpdir) / "test_sources"
        self.package_dir.mkdir()
        (self.package_dir / "__init__.py").write_text("")
        sys.path.insert(0, self._tmpdir)

    def cleanup(self):
        for name in list(sys.modules):
            if name == "test_sources" or name.startswith("test_sources."):
                del sys.modules[name]
        sys.path.remove(self._tmpdir)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def write_source(self, name, class_name, id_value):
        (self.package_dir / f"{name}.py").write_text(
            SOURCE.format(class_name=class_name, id_value=repr(id_value), id=id_value)
        )

    def discover(self):
        return discover_sources(
            package_path=[str(self.package_dir)], module_prefix="test_sources"
        )


@pytest.fixture
def temp_package():
    package = TempPackage()
    yield package
    package.cleanup()


def test_discovers_instances_keyed_by_id(temp_package):
    temp_package.write_source("dummy", "Dummy", "dummy")
    sources = temp_package.discover()
    assert {"dummy"} == set(sources)
    source = sources["dummy"]
    assert isinstance(source, Source)
    assert "dummy" == source.id
    assert "Test" == source.name
    assert "https://example.invalid/dummy" == source.source_url


def test_discovery_returns_working_instances(temp_package):
    temp_package.write_source("dummy", "Dummy", "dummy")
    source = temp_package.discover()["dummy"]
    assert [] == source.fetch(Path("unused"))
    assert [] == source.parse([])


def test_skips_non_source_classes(temp_package):
    (temp_package.package_dir / "mixed.py").write_text(
        textwrap.dedent(
            """\
            from mahlzeit.sources.base import Source

            class Helper:
                id = "helper"

            class Real(Source):
                id = "mixed"
                name = "Mixed"
                source_url = "https://example.invalid/mixed"

                def fetch(self, cache_dir):
                    return []

                def parse(self, pdf_paths):
                    return []
            """
        )
    )
    sources = temp_package.discover()
    assert {"mixed"} == set(sources)
    assert "mixed" == sources["mixed"].id


def test_skips_modules_without_sources(temp_package):
    (temp_package.package_dir / "base.py").write_text(
        "from mahlzeit.sources.base import Source\n"
    )
    assert {} == temp_package.discover()


def test_skips_sources_without_id(temp_package):
    temp_package.write_source("noid", "NoId", "")
    assert {} == temp_package.discover()


def test_empty_package_discovers_nothing(temp_package):
    assert {} == temp_package.discover()


def test_duplicate_id_raises(temp_package):
    temp_package.write_source("a", "A", "dup")
    temp_package.write_source("b", "B", "dup")
    with pytest.raises(RuntimeError, match="duplicate source id: 'dup'"):
        temp_package.discover()


class _FakeSource(Source):
    id = "fake"
    name = "Fake"
    source_url = "https://example.invalid/fake"

    def fetch(self, cache_dir):
        return []

    def parse(self, pdf_paths):
        return []


def test_all_sources_returns_discovered_instances():
    sources = all_sources()
    assert isinstance(sources, list)
    for source in sources:
        assert isinstance(source, Source)
        assert source.id
        assert source.name
        assert source.source_url


def test_all_sources_ids_are_unique():
    ids = [source.id for source in all_sources()]
    assert len(ids) == len(set(ids))


def test_get_source_returns_registered_instance():
    for source in all_sources():
        assert get_source(source.id) is source


def test_unknown_source_raises_key_error():
    with pytest.raises(KeyError):
        get_source("does-not-exist")


def test_unknown_source_error_lists_available():
    available = sorted(source.id for source in all_sources())
    with pytest.raises(KeyError) as ctx:
        get_source("does-not-exist")
    assert "does-not-exist" in str(ctx.value)
    for source_id in available:
        assert source_id in str(ctx.value)


def test_registry_mirrors_sources_dict():
    fake = _FakeSource()
    with mock.patch.object(registry, "SOURCES", {"fake": fake}):
        assert [fake] == all_sources()
        assert fake is get_source("fake")
