import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from ui.document_header import register_docx_namespaces

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"


class RegisterDocxNamespacesTests(unittest.TestCase):
    """Regression coverage for a real bug: register_docx_namespaces()'s
    prefix table was missing "pic" (DrawingML picture — used by every
    header that embeds the ministry crest image). Without it registered,
    ET.tostring() invents its own generic prefix (e.g. "ns6") for any
    pic:-namespaced element surviving an ET.fromstring/tostring
    round-trip — an undefined prefix from Word's perspective, which is
    very likely why a real exported document's header rendered with its
    embedded image area broken even though the header's plain text was
    provably correct (caught only by comparing raw XML bytes against the
    original template, not by reading extracted text)."""

    def setUp(self) -> None:
        register_docx_namespaces()

    def test_pic_prefix_survives_an_elementtree_round_trip(self) -> None:
        xml = (
            f'<w:hdr xmlns:w="{_W_NS}" xmlns:pic="{_PIC_NS}">'
            f'<w:p><w:r><pic:pic><pic:nvPicPr/></pic:pic></w:r></w:p>'
            f'</w:hdr>'
        )
        root = ET.fromstring(xml)
        out = ET.tostring(root, encoding="unicode")
        self.assertIn("pic:pic", out)
        self.assertNotIn("ns0:pic", out)
        self.assertNotIn('xmlns:ns', out)  # no invented generic prefix at all


if __name__ == "__main__":
    unittest.main()
