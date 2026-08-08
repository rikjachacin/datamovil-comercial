from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from io import BytesIO
import re
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


def _xml(value: object) -> str:
    return escape(str(value), quote=True)


def _cell(ref: str, value: object, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, (int, float)) and not pd.isna(value):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = "N/D" if pd.isna(value) else str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t{preserve}>{_xml(text)}</t></is></c>'


def _row(number: int, cells: list[str], height: int | None = None) -> str:
    height_attr = f' ht="{height}" customHeight="1"' if height else ""
    return f'<row r="{number}"{height_attr}>{"".join(cells)}</row>'


def _sheet_xml(row: pd.Series, cutoff: date, month_start: date, week_start: date) -> str:
    sales_period = (
        f"Corte: {cutoff:%d/%m/%Y}  |  Ventas: {month_start:%d/%m/%Y} al {cutoff:%d/%m/%Y}"
        f"  |  Actividad: {week_start:%d/%m/%Y} al {cutoff:%d/%m/%Y}"
    )
    sources = f"SisCor (solo lectura): facturacion, comprobantes y unidades | {row['fuentes_actividad']}"
    activity_is_phone = row["modalidad"] == "Telemarketing"

    rows = [
        _row(1, [_cell("A1", "INFORME SEMANAL DE DESEMPEÑO", 1)], 32),
        _row(2, [_cell("A2", f"{row['nombre']}  |  {row['modalidad']}", 2)], 24),
        _row(3, [_cell("A3", sales_period, 3)], 22),
        _row(4, [_cell("A4", f"Zona SisCor: {row['zona']}", 4)], 21),
        _row(6, [_cell("A6", "RESULTADO COMERCIAL ACUMULADO DEL MES", 5)], 23),
        _row(7, [
            _cell("A7", "Objetivo mensual", 6),
            _cell("C7", "Facturacion acumulada", 7),
            _cell("E7", "% de cumplimiento", 8),
            _cell("G7", "Unidades vendidas", 9),
            _cell("I7", "Ticket promedio", 10),
        ], 23),
        _row(8, [
            _cell("A8", float(row["objetivo"]), 11),
            _cell("C8", float(row["total"]), 11),
            _cell("E8", float(row["cumplimiento"]), 12),
            _cell("G8", float(row["unidades"]), 13),
            _cell("I8", float(row["ticket_promedio"]), 11),
        ], 28),
        _row(9, [], 28),
        _row(11, [_cell("A11", "ACTIVIDAD DE LA SEMANA", 5)], 23),
    ]

    if activity_is_phone:
        rows.extend([
            _row(13, [
                _cell("A13", "Llamadas realizadas (Anura)", 7),
                _cell("F13", "Contactos unicos (Clientify)", 8),
            ], 23),
            _row(14, [
                _cell("A14", row["llamadas"], 13),
                _cell("F14", row["contactos"], 13),
            ], 29),
        ])
        activity_merges = ["A13:E13", "A14:E15", "F13:J13", "F14:J15"]
    else:
        rows.extend([
            _row(13, [_cell("A13", "Visitas registradas (Persat)", 9)], 23),
            _row(14, [_cell("A14", row["visitas"], 13)], 29),
        ])
        activity_merges = ["A13:J13", "A14:J15"]

    rows.extend([
        _row(15, [], 29),
        _row(17, [_cell("A17", "FUENTES DEL INFORME", 14)], 22),
        _row(18, [_cell("A18", sources, 15)], 27),
        _row(19, [_cell("A19", f"Generado por Bruncas Comercial el {datetime.now():%d/%m/%Y %H:%M}", 16)], 20),
    ])
    merges = [
        "A1:J1", "A2:J2", "A3:J3", "A4:J4", "A6:J6",
        "A7:B7", "A8:B9", "C7:D7", "C8:D9", "E7:F7", "E8:F9",
        "G7:H7", "G8:H9", "I7:J7", "I8:J9", "A11:J11",
        *activity_merges, "A17:J17", "A18:J18", "A19:J19",
    ]
    merge_xml = "".join(f'<mergeCell ref="{item}"/>' for item in merges)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:J19"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols><col min="1" max="10" width="14" customWidth="1"/></cols>
  <sheetData>{''.join(rows)}</sheetData>
  <mergeCells count="{len(merges)}">{merge_xml}</mergeCells>
  <pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="1"/>
</worksheet>'''


def _styles_xml() -> str:
    fills = [
        "FFFFFF", "16324F", "E8EEF5", "FFF4D6", "0F766E", "2563A6",
        "16804A", "D97706", "6B5B95", "F4F7FA",
    ]
    fill_xml = '<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    fill_xml += "".join(
        f'<fill><patternFill patternType="solid"><fgColor rgb="FF{color}"/><bgColor indexed="64"/></patternFill></fill>'
        for color in fills
    )
    fonts = [
        '<font><sz val="11"/><name val="Aptos"/></font>',
        '<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>',
        '<font><b/><sz val="12"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>',
        '<font><sz val="10"/><color rgb="FF172033"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FF8A4B08"/><name val="Aptos"/></font>',
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>',
        '<font><b/><sz val="15"/><color rgb="FF172033"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FF16324F"/><name val="Aptos"/></font>',
        '<font><sz val="9"/><color rgb="FF5B677A"/><name val="Aptos"/></font>',
        '<font><sz val="8"/><color rgb="FF5B677A"/><name val="Aptos"/></font>',
    ]
    border = '<border><left style="thin"><color rgb="FFD7DEE8"/></left><right style="thin"><color rgb="FFD7DEE8"/></right><top style="thin"><color rgb="FFD7DEE8"/></top><bottom style="thin"><color rgb="FFD7DEE8"/></bottom><diagonal/></border>'
    xfs = [
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>',
        '<xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="5" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="6" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="6" fillId="7" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="6" fillId="8" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="6" fillId="9" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="6" fillId="10" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="164" fontId="7" fillId="11" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        '<xf numFmtId="165" fontId="7" fillId="11" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        '<xf numFmtId="3" fontId="7" fillId="11" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        '<xf numFmtId="0" fontId="8" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>',
        '<xf numFmtId="0" fontId="9" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="10" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>',
    ]
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="2"><numFmt numFmtId="164" formatCode='&quot;$&quot;#,##0'/><numFmt numFmtId="165" formatCode="0.0%"/></numFmts>
  <fonts count="{len(fonts)}">{''.join(fonts)}</fonts>
  <fills count="{len(fills) + 2}">{fill_xml}</fills>
  <borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>{border}</borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="{len(xfs)}">{''.join(xfs)}</cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def build_workbook(data: pd.DataFrame, cutoff: date, month_start: date, week_start: date) -> bytes:
    titles: list[str] = []
    used: set[str] = set()
    for raw in data["nombre"].astype(str):
        base = re.sub(r"[\\/*?:\[\]]", " ", raw).strip()[:31] or "Vendedor"
        title = base
        suffix = 2
        while title in used:
            title = f"{base[:27]} {suffix}"
            suffix += 1
        used.add(title)
        titles.append(title)

    workbook_sheets = "".join(
        f'<sheet name="{_xml(title)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, title in enumerate(titles, 1)
    )
    workbook_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(titles) + 1)
    )
    workbook_rels += f'<Relationship Id="rId{len(titles) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(titles) + 1)
    )
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{overrides}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''')
        archive.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''')
        archive.writestr("xl/workbook.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>{workbook_sheets}</sheets><calcPr calcId="0"/></workbook>''')
        archive.writestr("xl/_rels/workbook.xml.rels", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{workbook_rels}</Relationships>''')
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_, row) in enumerate(data.iterrows(), 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(row, cutoff, month_start, week_start))
        archive.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Bruncas Comercial</dc:creator><cp:lastModifiedBy>Bruncas Comercial</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified></cp:coreProperties>''')
        archive.writestr("docProps/app.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Bruncas Comercial</Application><TitlesOfParts><vt:vector size="{len(titles)}" baseType="lpstr">{''.join(f'<vt:lpstr>{_xml(title)}</vt:lpstr>' for title in titles)}</vt:vector></TitlesOfParts></Properties>''')
    return buffer.getvalue()
