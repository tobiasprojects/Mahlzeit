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
import unittest
from pathlib import Path
from unittest import mock

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


class TempPackageMixin:
    """setUp/tearDown for a throwaway importable package under `sys.path`."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.package_dir = Path(self._tmpdir) / "test_sources"
        self.package_dir.mkdir()
        (self.package_dir / "__init__.py").write_text("")
        sys.path.insert(0, self._tmpdir)
        self.addCleanup(self._remove_modules)
        self.addCleanup(sys.path.remove, self._tmpdir)
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)

    def _remove_modules(self):
        for name in list(sys.modules):
            if name == "test_sources" or name.startswith("test_sources."):
                del sys.modules[name]

    def write_source(self, name, class_name, id_value):
        (self.package_dir / f"{name}.py").write_text(
            SOURCE.format(class_name=class_name, id_value=repr(id_value), id=id_value)
        )

    def discover(self):
        return discover_sources(
            package_path=[str(self.package_dir)], module_prefix="test_sources"
        )


class DiscoveryTest(TempPackageMixin, unittest.TestCase):
    def test_discovers_instances_keyed_by_id(self):
        self.write_source("dummy", "Dummy", "dummy")
        sources = self.discover()
        self.assertEqual({"dummy"}, set(sources))
        source = sources["dummy"]
        self.assertIsInstance(source, Source)
        self.assertEqual("dummy", source.id)
        self.assertEqual("Test", source.name)
        self.assertEqual("https://example.invalid/dummy", source.source_url)

    def test_discovery_returns_working_instances(self):
        self.write_source("dummy", "Dummy", "dummy")
        source = self.discover()["dummy"]
        self.assertEqual([], source.fetch(Path("unused")))
        self.assertEqual([], source.parse([]))

    def test_skips_non_source_classes(self):
        (self.package_dir / "mixed.py").write_text(
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
        sources = self.discover()
        self.assertEqual({"mixed"}, set(sources))
        self.assertEqual("mixed", sources["mixed"].id)

    def test_skips_modules_without_sources(self):
        (self.package_dir / "base.py").write_text(
            "from mahlzeit.sources.base import Source\n"
        )
        self.assertEqual({}, self.discover())

    def test_skips_sources_without_id(self):
        self.write_source("noid", "NoId", "")
        self.assertEqual({}, self.discover())

    def test_empty_package_discovers_nothing(self):
        self.assertEqual({}, self.discover())

    def test_duplicate_id_raises(self):
        self.write_source("a", "A", "dup")
        self.write_source("b", "B", "dup")
        with self.assertRaisesRegex(RuntimeError, "duplicate source id: 'dup'"):
            self.discover()


class _FakeSource(Source):
    id = "fake"
    name = "Fake"
    source_url = "https://example.invalid/fake"

    def fetch(self, cache_dir):
        return []

    def parse(self, pdf_paths):
        return []


class RegistryTest(unittest.TestCase):
    def test_all_sources_returns_discovered_instances(self):
        sources = all_sources()
        self.assertIsInstance(sources, list)
        for source in sources:
            self.assertIsInstance(source, Source)
            self.assertTrue(source.id)
            self.assertTrue(source.name)
            self.assertTrue(source.source_url)

    def test_all_sources_ids_are_unique(self):
        ids = [source.id for source in all_sources()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_get_source_returns_registered_instance(self):
        for source in all_sources():
            self.assertIs(get_source(source.id), source)

    def test_unknown_source_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_source("does-not-exist")

    def test_unknown_source_error_lists_available(self):
        available = sorted(source.id for source in all_sources())
        with self.assertRaises(KeyError) as ctx:
            get_source("does-not-exist")
        self.assertIn("does-not-exist", str(ctx.exception))
        for source_id in available:
            self.assertIn(source_id, str(ctx.exception))

    def test_registry_mirrors_sources_dict(self):
        fake = _FakeSource()
        with mock.patch.object(registry, "SOURCES", {"fake": fake}):
            self.assertEqual([fake], all_sources())
            self.assertIs(fake, get_source("fake"))


if __name__ == "__main__":
    unittest.main()
