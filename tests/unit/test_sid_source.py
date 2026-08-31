import unittest

from orchestrator.cli import SID_SOURCELIST_PATH
from orchestrator.sid_source import (
    SID_SOURCELIST_CONTENT,
    parse_showsrc_version,
    scoped_apt_opts,
)

FIXTURE_SHOWSRC = """\
Package: asterisk
Binary: asterisk, asterisk-dev, asterisk-doc
Version: 1:20.9.0~dfsg-1
Priority: optional
Section: comm
Maintainer: Debian VoIP Team <pkg-voip-maintainers@lists.alioth.debian.org>
Architecture: any
Standards-Version: 4.6.2
Format: 3.0 (quilt)
Files:
 3333333333333333333333333333333333333333333333333333333333cc 4000 asterisk_20.9.0~dfsg-1.dsc
Checksums-Sha256:
 1111111111111111111111111111111111111111111111111111111111aa 12000000 asterisk_20.9.0~dfsg.orig.tar.gz
Package-List:
 asterisk deb comm optional arch=any

"""


class SidSourcelistContentTests(unittest.TestCase):
    def test_is_a_sid_deb_src_line(self):
        self.assertIn("sid", SID_SOURCELIST_CONTENT)
        self.assertIn("deb-src", SID_SOURCELIST_CONTENT)

    def test_is_written_to_a_path_apt_parses_as_one_line_format(self):
        # apt picks its parser from the extension; `.sources` means deb822.
        self.assertTrue(SID_SOURCELIST_PATH.endswith(".list"))


class ScopedAptOptsTests(unittest.TestCase):
    def test_redirects_the_state_and_cache_apt_would_need_root_for(self):
        opts = scoped_apt_opts("/state/sid.list", "/state/apt")
        self.assertIn("Dir::Etc::sourcelist=/state/sid.list", opts)
        self.assertIn("Dir::State::Lists=/state/apt/lists", opts)
        self.assertIn("Dir::Cache=/state/apt/cache", opts)


class ParseShowsrcVersionTests(unittest.TestCase):
    def test_extracts_the_version_field(self):
        self.assertEqual(parse_showsrc_version(FIXTURE_SHOWSRC), "1:20.9.0~dfsg-1")

    def test_raises_when_no_version_field_present(self):
        with self.assertRaises(LookupError):
            parse_showsrc_version("N: Unable to locate package asterisk\n")


if __name__ == "__main__":
    unittest.main()
