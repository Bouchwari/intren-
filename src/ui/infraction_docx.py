"""
src/ui/infraction_docx.py
Builds the Word version of محضر المخالفة.

Every other Word export in this app FILLS an existing template in
`templets/`, but the ministry guide ships this form only as a printed annex
(p.93) — there is no .docx to fill. So the document is assembled from
scratch here, as raw OOXML written straight into a zip: this project has no
python-docx (CLAUDE.md §3 fixes the stack, and §9 forbids adding a library
unasked), and the same hand-rolled approach already works for the Excel
roster's header image.

The output is a plain black-and-white RTL document the user can edit in
Word or LibreOffice — same content and order as the PDF.
"""
from pathlib import Path
import sys
from typing import List, Optional
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from core.models import InfractionRecord, SchoolSettings

# The ministry crest, reused from the template that already ships it.
_CREST_TEMPLATE = "البرنامج الغذائي لشهر رمضان المبارك.docx"
_CREST_MEMBER = "word/media/image1.jpeg"

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="jpeg" ContentType="image/jpeg"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.styles+xml"/>'
    '</Types>'
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>'
)

_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rIdCrest" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/image" Target="media/image1.jpeg"/>'
    '</Relationships>'
)

# Same, minus the picture, for a build where the crest could not be read.
_DOC_RELS_NO_CREST = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)

_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:docDefaults><w:rPrDefault><w:rPr>'
    '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
    '<w:sz w:val="24"/><w:szCs w:val="24"/><w:rtl/>'
    '</w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:bidi/></w:pPr></w:pPrDefault>'
    '</w:docDefaults></w:styles>'
)

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
_WP = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
_A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
_PIC = 'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'

# Half-points: Word sizes are doubled, so 24 = 12pt.
_BODY_HALF_POINTS = 24
_TITLE_HALF_POINTS = 32
_IDENTITY_HALF_POINTS = 22


def _crest_bytes() -> Optional[bytes]:
    runtime_base = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    for base in (runtime_base, Path.cwd(), Path(__file__).resolve().parents[2]):
        candidate = base / "templets" / _CREST_TEMPLATE
        if candidate.exists():
            try:
                with ZipFile(candidate) as archive:
                    return archive.read(_CREST_MEMBER)
            except Exception:
                return None
    return None


def _run(text: str, *, bold: bool = False, underline: bool = False,
         size: int = _BODY_HALF_POINTS) -> str:
    """One run of RTL Arabic text.

    **Element order inside w:rPr is not cosmetic** — the OOXML schema fixes
    the sequence (b, bCs, … sz, szCs, … u, … rtl) and Word/LibreOffice
    silently DROP properties that arrive out of order. Getting this wrong is
    what made the first version of this export render left-to-right.
    """
    properties = []
    if bold:
        properties.append('<w:b/><w:bCs/>')
    properties.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if underline:
        properties.append('<w:u w:val="single"/>')
    properties.append('<w:rtl/>')
    return (f'<w:r><w:rPr>{"".join(properties)}</w:rPr>'
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')


def _paragraph(text: str = "", *, bold: bool = False, underline: bool = False,
               size: int = _BODY_HALF_POINTS, align: str = "start",
               space_after: int = 120) -> str:
    """One RTL paragraph.

    Two OOXML traps here, both of which produced a left-to-right document:

    1. `w:pPr` has a schema-fixed order (bidi → spacing → jc); properties
       out of sequence are silently dropped.
    2. **`w:jc` is LOGICAL, not visual.** In a `w:bidi` paragraph "right"
       means *end*, and the end of right-to-left text is the LEFT edge — so
       asking for "right" actively pushed every line to the left. A bidi
       paragraph already starts at the right margin, so the correct thing is
       to emit no `w:jc` at all and only name it when centring.
    """
    body = _run(text, bold=bold, underline=underline, size=size) if text else ""
    justification = f'<w:jc w:val="{align}"/>' if align == "center" else ""
    return (f'<w:p><w:pPr><w:bidi/>'
            f'<w:spacing w:after="{space_after}"/>'
            f'{justification}</w:pPr>{body}</w:p>')


def _crest_paragraph(width_emu: int = 4200000, height_emu: int = 700000) -> str:
    """The header image, centred, as an inline drawing."""
    return (
        '<w:p><w:pPr><w:bidi/><w:spacing w:after="60"/><w:jc w:val="center"/>'
        '</w:pPr><w:r><w:drawing>'
        f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{width_emu}" cy="{height_emu}"/>'
        '<wp:docPr id="1" name="crest"/><a:graphic><a:graphicData '
        'uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="crest"/><pic:cNvPicPr/>'
        '</pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdCrest"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr>'
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    )


def _two_column_row(right_text: str, left_text: str) -> str:
    """A borderless two-cell table — the reliable way to put two labels side
    by side in Word without depending on tab stops the user might drag."""
    def cell(text: str) -> str:
        return ('<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
                f'{_paragraph(text, underline=True, space_after=0)}</w:tc>')
    return (
        '<w:tbl><w:tblPr><w:bidiVisual/>'
        '<w:tblW w:w="9000" w:type="dxa"/>'
        '<w:tblBorders>'
        + "".join(f'<w:{edge} w:val="none" w:sz="0" w:space="0"/>'
                  for edge in ("top", "left", "bottom", "right", "insideH", "insideV"))
        + '</w:tblBorders></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
        f'<w:tr>{cell(right_text)}{cell(left_text)}</w:tr></w:tbl>'
    )


def build_infraction_document_xml(
    record: InfractionRecord, settings: Optional[SchoolSettings], *,
    strings: dict, with_crest: bool,
) -> str:
    """Assemble word/document.xml. `strings` carries the Arabic labels from
    the screen so the wording lives in exactly one place."""
    parts: List[str] = []
    if with_crest:
        parts.append(_crest_paragraph())

    for line in (
        (settings.aref if settings else "") or "",
        (settings.direction_provinciale if settings else "") or "",
        (settings.school_name if settings else "") or "",
    ):
        if line.strip():
            parts.append(_paragraph(
                line, align="center", size=_IDENTITY_HALF_POINTS, space_after=40))

    parts.append(_paragraph(
        f"{strings['title']} رقم: {record.reference}",
        bold=True, underline=True, size=_TITLE_HALF_POINTS,
        align="center", space_after=280))

    parts.append(_paragraph(strings["body"], space_after=200))
    parts.append(_paragraph(strings["holder"]))
    parts.append(_paragraph(strings["date_and_meal"]))
    parts.append(_paragraph(strings["place"]))
    parts.append(_paragraph(strings["infraction_type"]))
    if strings["description"]:
        parts.append(_paragraph(strings["description"], space_after=200))
    else:
        for _ in range(3):
            parts.append(_paragraph(strings["dotted"], space_after=60))
    parts.append(_paragraph(strings["reported_by"]))
    parts.append(_paragraph(strings["written"], space_after=280))

    parts.append(_paragraph(strings["sign_company"], bold=True, underline=True,
                            space_after=1200))
    parts.append(_paragraph(strings["sign_committee"], bold=True, underline=True,
                            space_after=200))
    parts.append(_two_column_row(strings["sign_warden"], strings["sign_steward"]))
    parts.append(_paragraph(space_after=1200))
    parts.append(_paragraph(strings["sign_director"], underline=True, align="center"))

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document {_W} {_R} {_WP} {_A} {_PIC}><w:body>'
        + "".join(parts)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
          '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
          '<w:bidi/></w:sectPr></w:body></w:document>'
    )


def write_infraction_docx(
    path: Path, record: InfractionRecord, settings: Optional[SchoolSettings],
    strings: dict,
) -> None:
    """Write an editable Word version of the PV."""
    crest = _crest_bytes()
    document_xml = build_infraction_document_xml(
        record, settings, strings=strings, with_crest=crest is not None)

    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", _CONTENT_TYPES)
        docx.writestr("_rels/.rels", _ROOT_RELS)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", _STYLES)
        if crest is None:
            docx.writestr("word/_rels/document.xml.rels", _DOC_RELS_NO_CREST)
        else:
            docx.writestr("word/_rels/document.xml.rels", _DOC_RELS)
            docx.writestr("word/media/image1.jpeg", crest)
