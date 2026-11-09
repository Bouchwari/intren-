"""Embed original template headers without requiring Pillow at runtime."""
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from PySide6.QtGui import QImage
from ui.document_branding import replace_header_image

_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_ART = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _xml_bytes(element: ET.Element) -> bytes:
    # OPC readers expect the package roots in their default namespace.
    namespace = element.tag[1:].partition("}")[0]
    ET.register_namespace("", namespace)
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def embed_template_header(path: Path, image_bytes: bytes, extension: str,
                          boxes: list[tuple[int, float, float]]) -> None:
    """Add a centered, proportional image to each (sheet index, width, height).

    Boxes and image sizes are in 96-DPI pixels. Only newly generated worksheets
    without drawings are supported, so existing artwork cannot be overwritten.
    """
    image_bytes = replace_header_image(image_bytes, extension)
    picture = QImage.fromData(image_bytes)
    if picture.isNull() or extension not in {"png", "jpeg"}:
        raise ValueError("Invalid template header image")
    new_parts = {}
    media = f"xl/media/image1.{extension}"
    with ZipFile(path) as source:
        content = ET.fromstring(source.read("[Content_Types].xml"))
        if not any(item.get("Extension") == extension for item in content):
            ET.SubElement(content, f"{{{_CONTENT}}}Default", Extension=extension,
                          ContentType=f"image/{extension}")
        for index, width, height in boxes:
            sheet_path = f"xl/worksheets/sheet{index}.xml"
            sheet = ET.fromstring(source.read(sheet_path))
            rel_path = f"xl/worksheets/_rels/sheet{index}.xml.rels"
            if sheet.find(f"{{{_SHEET}}}drawing") is not None or rel_path in source.namelist():
                raise ValueError("The generated sheet already has relationships")
            ET.SubElement(sheet, f"{{{_SHEET}}}drawing", {f"{{{_REL}}}id": "rIdHdr"})
            new_parts[sheet_path] = _xml_bytes(sheet)
            rels = ET.Element(f"{{{_PACKAGE}}}Relationships")
            ET.SubElement(rels, f"{{{_PACKAGE}}}Relationship", Id="rIdHdr",
                          Type=f"{_REL}/drawing", Target=f"../drawings/drawing{index}.xml")
            new_parts[rel_path] = _xml_bytes(rels)
            scale = min((width - 20) / picture.width(), (height - 10) / picture.height())
            image_w, image_h = picture.width() * scale, picture.height() * scale
            drawing = ET.Element(f"{{{_DRAW}}}wsDr")
            anchor = ET.SubElement(drawing, f"{{{_DRAW}}}absoluteAnchor")
            ET.SubElement(anchor, f"{{{_DRAW}}}pos", x=str(round((width - image_w) / 2 * 9525)),
                          y=str(round((height - image_h) / 2 * 9525)))
            ET.SubElement(anchor, f"{{{_DRAW}}}ext", cx=str(round(image_w * 9525)),
                          cy=str(round(image_h * 9525)))
            pic = ET.SubElement(anchor, f"{{{_DRAW}}}pic")
            nv = ET.SubElement(pic, f"{{{_DRAW}}}nvPicPr")
            ET.SubElement(nv, f"{{{_DRAW}}}cNvPr", id="1", name="Official header")
            props = ET.SubElement(nv, f"{{{_DRAW}}}cNvPicPr")
            ET.SubElement(props, f"{{{_ART}}}picLocks", noChangeAspect="1")
            fill = ET.SubElement(pic, f"{{{_DRAW}}}blipFill")
            ET.SubElement(fill, f"{{{_ART}}}blip", {f"{{{_REL}}}embed": "rId1"})
            stretch = ET.SubElement(fill, f"{{{_ART}}}stretch")
            ET.SubElement(stretch, f"{{{_ART}}}fillRect")
            shape = ET.SubElement(pic, f"{{{_DRAW}}}spPr")
            geometry = ET.SubElement(shape, f"{{{_ART}}}prstGeom", prst="rect")
            ET.SubElement(geometry, f"{{{_ART}}}avLst")
            ET.SubElement(anchor, f"{{{_DRAW}}}clientData")
            new_parts[f"xl/drawings/drawing{index}.xml"] = _xml_bytes(drawing)
            drawing_rels = ET.Element(f"{{{_PACKAGE}}}Relationships")
            ET.SubElement(drawing_rels, f"{{{_PACKAGE}}}Relationship", Id="rId1",
                          Type=f"{_REL}/image", Target=f"../media/image1.{extension}")
            new_parts[f"xl/drawings/_rels/drawing{index}.xml.rels"] = _xml_bytes(drawing_rels)
            ET.SubElement(content, f"{{{_CONTENT}}}Override",
                          PartName=f"/xl/drawings/drawing{index}.xml",
                          ContentType="application/vnd.openxmlformats-officedocument.drawing+xml")
        new_parts["[Content_Types].xml"] = _xml_bytes(content)
        new_parts[media] = image_bytes
        handle, temp_name = tempfile.mkstemp(suffix=".xlsx", dir=path.parent)
        os.close(handle)
        temporary = Path(temp_name)
        try:
            with ZipFile(temporary, "w") as target:
                for item in source.infolist():
                    target.writestr(item, new_parts.pop(item.filename, source.read(item.filename)))
                for name, data in new_parts.items():
                    target.writestr(name, data)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
