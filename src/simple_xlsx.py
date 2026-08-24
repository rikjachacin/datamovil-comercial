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


def _status_style(status: str) -> int:
    return {
        "POR ENCIMA": 22,
        "EN LINEA": 23,
        "POR DEBAJO": 24,
        "REVISAR DATOS": 24,
        "SIN DIFERENCIAS": 22,
    }.get(status, 25)


def _metric_row(
    number: int,
    label: str,
    actual: object,
    expected: object,
    performance: object,
    status: str,
    *,
    money: bool = False,
) -> str:
    actual_style = 19 if money else 20
    expected_style = 19 if money and isinstance(expected, (int, float)) else (20 if isinstance(expected, (int, float)) else 26)
    performance_style = 21 if isinstance(performance, (int, float)) and not pd.isna(performance) else 26
    return _row(
        number,
        [
            _cell(f"A{number}", label, 18),
            _cell(f"C{number}", actual, actual_style),
            _cell(f"E{number}", expected, expected_style),
            _cell(f"G{number}", performance, performance_style),
            _cell(f"I{number}", status, _status_style(status)),
        ],
        24,
    )


def _seller_reading(row: pd.Series) -> str:
    sales = (
        f"Ventas {row['estado_ventas'].lower()}: lleva {float(row['ritmo_ventas']):.1%} "
        "del nivel esperado al corte."
    )
    if row["modalidad"] == "Telemarketing":
        calls = "Llamadas: dato no disponible."
        if not pd.isna(row["ritmo_llamadas"]):
            calls = (
                f"Llamadas {str(row['estado_llamadas']).lower()}: "
                f"{int(row['llamadas'])} de {int(row['llamadas_esperadas'])} esperadas."
            )
        return f"{sales} {calls} Los contactos se informan sin calificacion porque no tienen una meta formal."
    if pd.isna(row["visitas_programadas"]):
        return f"{sales} Las visitas no se califican porque esta zona no tiene itinerario cargado."
    if pd.isna(row["visitas_cumplidas"]):
        return f"{sales} Persat no estuvo disponible para evaluar el cumplimiento del itinerario."
    return (
        f"{sales} Registro {int(row['visitas'])} visitas: cumplio "
        f"{int(row['visitas_cumplidas'])} de {int(row['visitas_programadas'])} programadas, "
        f"realizo {int(row['visitas_fuera_itinerario'])} fuera del itinerario y "
        f"quedaron {int(row['visitas_sin_clasificar'])} sin clasificar."
    )


def _sheet_xml(row: pd.Series, cutoff: date, month_start: date, period_start: date) -> str:
    sales_period = (
        f"Corte: {cutoff:%d/%m/%Y}  |  Ventas: {month_start:%d/%m/%Y} al {cutoff:%d/%m/%Y}"
        f"  |  Actividad: {period_start:%d/%m/%Y} al {cutoff:%d/%m/%Y}"
    )
    sources = f"SisCor (solo lectura): facturacion, comprobantes y unidades | {row['fuentes_actividad']}"
    activity_is_phone = row["modalidad"] == "Telemarketing"
    has_itinerary = not pd.isna(row["visitas_programadas"])
    expected_progress = float(row["avance_esperado_mes"])

    rows = [
        _row(1, [_cell("A1", "INFORME SEMANAL DE DESEMPEÑO", 1)], 30),
        _row(2, [_cell("A2", f"{row['nombre']}  |  {row['modalidad']}", 2)], 22),
        _row(3, [_cell("A3", sales_period, 3)], 21),
        _row(4, [_cell("A4", f"Zona SisCor: {row['zona']}", 4)], 20),
        _row(6, [_cell("A6", "RESULTADO COMERCIAL ACUMULADO DEL MES", 5)], 21),
        _row(7, [
            _cell("A7", "Objetivo mensual", 6),
            _cell("C7", "Facturacion acumulada", 7),
            _cell("E7", "% de cumplimiento", 8),
            _cell("G7", "Unidades vendidas", 9),
            _cell("I7", "Ticket promedio", 10),
        ], 21),
        _row(8, [
            _cell("A8", float(row["objetivo"]), 11),
            _cell("C8", float(row["total"]), 11),
            _cell("E8", float(row["cumplimiento"]), 12),
            _cell("G8", float(row["unidades"]), 13),
            _cell("I8", float(row["ticket_promedio"]), 11),
        ], 25),
        _row(9, [], 25),
        _row(11, [_cell("A11", f"RENDIMIENTO ESPERADO AL CORTE ({expected_progress:.1%} DEL MES HABIL)", 5)], 21),
        _row(12, [
            _cell("A12", "Indicador", 17),
            _cell("C12", "Resultado real", 17),
            _cell("E12", "Esperado al corte", 17),
            _cell("G12", "Rendimiento", 17),
            _cell("I12", "Estado", 17),
        ], 21),
        _metric_row(13, "Facturacion", float(row["total"]), float(row["facturacion_esperada"]), row["ritmo_ventas"], str(row["estado_ventas"]), money=True),
        _row(15, [_cell("A15", "ACTIVIDAD DEL PERIODO SELECCIONADO", 5)], 21),
        _row(16, [
            _cell("A16", "Indicador", 17),
            _cell("C16", "Resultado real", 17),
            _cell("E16", "Base de comparacion", 17),
            _cell("G16", "Porcentaje", 17),
            _cell("I16", "Estado", 17),
        ], 21),
    ]
    if activity_is_phone:
        rows.extend([
            _metric_row(17, "Llamadas salientes (Anura)", row["llamadas"], row["llamadas_esperadas"], row["ritmo_llamadas"], str(row["estado_llamadas"])),
            _metric_row(18, "Contactos unicos (Clientify)", row["contactos"], "Sin meta definida", None, "NO EVALUABLE"),
        ])
    elif has_itinerary:
        unclassified = pd.to_numeric(row["visitas_sin_clasificar"], errors="coerce")
        unclassified_status = (
            "REVISAR DATOS"
            if pd.notna(unclassified) and float(unclassified) > 0
            else "SIN DIFERENCIAS"
        )
        rows.extend([
            _metric_row(17, "Visitas programadas cumplidas", row["visitas_cumplidas"], row["visitas_programadas"], row["ritmo_visitas"], str(row["estado_visitas"])),
            _metric_row(18, "Total de visitas realizadas", row["visitas"], row["visitas_programadas"], row["ritmo_visitas_totales"], str(row["estado_visitas_totales"])),
            _metric_row(19, "Visitas fuera del itinerario", row["visitas_fuera_itinerario"], row["visitas"], row["porcentaje_fuera_itinerario"], "DATO DE CONTROL"),
            _metric_row(20, "Visitas sin clasificar", row["visitas_sin_clasificar"], "-", "-", unclassified_status),
        ])
    else:
        rows.append(_metric_row(17, "Visitas registradas (Persat)", row["visitas"], "Sin itinerario", None, "NO EVALUABLE"))

    rows.extend([
        _row(21, [_cell("A21", "LECTURA PARA EL VENDEDOR", 5)], 21),
        _row(22, [_cell("A22", _seller_reading(row), 27)], 34),
        _row(23, [_cell("A23", "Criterio: POR ENCIMA >= 105% | EN LINEA 95% a 104,9% | POR DEBAJO < 95%.", 15)], 19),
        _row(25, [_cell("A25", "FUENTES DEL INFORME", 14)], 20),
        _row(26, [_cell("A26", sources, 15)], 27),
        _row(27, [_cell("A27", f"Generado por Bruncas Comercial el {datetime.now():%d/%m/%Y %H:%M}", 16)], 18),
    ])
    merges = [
        "A1:J1", "A2:J2", "A3:J3", "A4:J4", "A6:J6",
        "A7:B7", "A8:B9", "C7:D7", "C8:D9", "E7:F7", "E8:F9",
        "G7:H7", "G8:H9", "I7:J7", "I8:J9", "A11:J11",
        "A12:B12", "C12:D12", "E12:F12", "G12:H12", "I12:J12",
        "A13:B13", "C13:D13", "E13:F13", "G13:H13", "I13:J13",
        "A15:J15", "A16:B16", "C16:D16", "E16:F16", "G16:H16", "I16:J16",
        "A17:B17", "C17:D17", "E17:F17", "G17:H17", "I17:J17",
        "A21:J21", "A22:J22", "A23:J23", "A25:J25", "A26:J26", "A27:J27",
    ]
    if activity_is_phone or has_itinerary:
        merges.extend(["A18:B18", "C18:D18", "E18:F18", "G18:H18", "I18:J18"])
    if not activity_is_phone and has_itinerary:
        merges.extend([
            "A19:B19", "C19:D19", "E19:F19", "G19:H19", "I19:J19",
            "A20:B20", "C20:D20", "E20:F20", "G20:H20", "I20:J20",
        ])
    merge_xml = "".join(f'<mergeCell ref="{item}"/>' for item in merges)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:J27"/>
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
        "16804A", "D97706", "6B5B95", "F4F7FA", "DCFCE7", "DBEAFE", "FEE2E2",
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
        '<font><b/><sz val="10"/><color rgb="FF172033"/><name val="Aptos"/></font>',
        '<font><sz val="10"/><color rgb="FF172033"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FF166534"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FF1D4ED8"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FFB42318"/><name val="Aptos"/></font>',
        '<font><b/><sz val="9"/><color rgb="FF5B677A"/><name val="Aptos"/></font>',
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
        '<xf numFmtId="0" fontId="6" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="11" fillId="11" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="164" fontId="12" fillId="2" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        '<xf numFmtId="3" fontId="12" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        '<xf numFmtId="165" fontId="12" fillId="2" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        '<xf numFmtId="0" fontId="13" fillId="12" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="14" fillId="13" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="15" fillId="14" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="16" fillId="11" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="12" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        '<xf numFmtId="0" fontId="12" fillId="11" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>',
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


def build_workbook(data: pd.DataFrame, cutoff: date, month_start: date, period_start: date) -> bytes:
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
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(row, cutoff, month_start, period_start))
        archive.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Bruncas Comercial</dc:creator><cp:lastModifiedBy>Bruncas Comercial</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified></cp:coreProperties>''')
        archive.writestr("docProps/app.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Bruncas Comercial</Application><TitlesOfParts><vt:vector size="{len(titles)}" baseType="lpstr">{''.join(f'<vt:lpstr>{_xml(title)}</vt:lpstr>' for title in titles)}</vt:vector></TitlesOfParts></Properties>''')
    return buffer.getvalue()
