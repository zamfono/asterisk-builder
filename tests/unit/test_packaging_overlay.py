import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestrator.packaging_overlay import install_patches, set_changelog_version_cmd

CONTROL_PATCH = """--- a/debian/control
+++ b/debian/control
@@ -1,1 +1,1 @@
-Package: asterisk-modules
+Package: asterisk-modules-core
"""


class InstallPatchesTests(unittest.TestCase):
    def test_applies_overlay_patches_to_the_source_tree_in_sorted_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "source"
            (source_dir / "debian").mkdir(parents=True)
            (source_dir / "debian" / "control").write_text("Package: asterisk-modules\n")

            overlay_dir = Path(tmp) / "overlay"
            overlay_dir.mkdir()
            (overlay_dir / "0001-rename-modules-package.patch").write_text(CONTROL_PATCH)

            applied = install_patches(source_dir, overlay_dir)

            self.assertEqual(applied, ["0001-rename-modules-package.patch"])
            self.assertEqual(
                (source_dir / "debian" / "control").read_text(),
                "Package: asterisk-modules-core\n",
            )

    def test_applies_an_overlay_directory_named_relative_to_the_caller(self):
        # orchestrator/cli.py passes "packaging/patches", relative to the
        # repository root it runs from — never to the source tree.
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "source"
            (source_dir / "debian").mkdir(parents=True)
            (source_dir / "debian" / "control").write_text("Package: asterisk-modules\n")

            (Path(tmp) / "overlay").mkdir()
            (Path(tmp) / "overlay" / "0001-rename-modules-package.patch").write_text(CONTROL_PATCH)

            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                install_patches(source_dir, "overlay")
            finally:
                os.chdir(cwd)

            self.assertEqual(
                (source_dir / "debian" / "control").read_text(),
                "Package: asterisk-modules-core\n",
            )

    def test_a_patch_that_does_not_apply_cleanly_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "source"
            (source_dir / "debian").mkdir(parents=True)
            (source_dir / "debian" / "control").write_text("Package: something-else\n")

            overlay_dir = Path(tmp) / "overlay"
            overlay_dir.mkdir()
            (overlay_dir / "0001-rename-modules-package.patch").write_text(CONTROL_PATCH)

            with self.assertRaises(subprocess.CalledProcessError):
                install_patches(source_dir, overlay_dir)


class SetChangelogVersionCmdTests(unittest.TestCase):
    def test_stamps_the_zamfono_version_into_debian_changelog(self):
        argv = set_changelog_version_cmd("1:20.9.0~dfsg-1+zamfono13.1")
        self.assertEqual(
            argv,
            [
                "dch",
                "--newversion", "1:20.9.0~dfsg-1+zamfono13.1",
                "--distribution", "trixie",
                "--force-distribution",
                "Zamfono rebuild for Debian 13",
            ],
        )


if __name__ == "__main__":
    unittest.main()
