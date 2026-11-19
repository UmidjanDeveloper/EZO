"""The analysis as an Excel workbook EZO writes itself: the data, a statistics sheet, a
trend sheet with a native line chart (forecast marked), and group totals with a bar chart."""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Font, PatternFill

from ezo_api.analytics.stats import Analysis
from ezo_api.analytics.table import Table, to_number
from ezo_api.documents.spreadsheet.writer import safe_text

HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="1F4E79")


def _header(ws, values: list[str]) -> None:  # type: ignore[no-untyped-def]
    ws.append(values)
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = HEAD, FILL


def render(table: Table, analysis: Analysis) -> bytes:
    book = Workbook()
    data = book.active
    data.title = "Ma'lumot"
    _header(data, [safe_text(c) for c in table.columns])
    for row in table.rows:
        data.append([n if (n := to_number(v)) is not None else safe_text(str(v)) for v in row])

    stats = book.create_sheet("Statistika")
    _header(
        stats,
        ["Ustun", "Soni", "Bo'sh", "Jami", "O'rtacha", "Mediana", "Eng kam", "Eng ko'p", "Std"],
    )
    for p in analysis.numeric:
        stats.append(
            [p.column, p.count, p.missing, p.total, p.mean, p.median, p.minimum, p.maximum, p.stdev]
        )

    for t_index, trend in enumerate(analysis.trends[:5]):
        ws = book.create_sheet(f"Trend {t_index + 1}")
        _header(ws, ["Davr", trend.column, "Prognoz (taxmin)"])
        for day, value in trend.points:
            ws.append([day.strftime("%Y-%m-%d"), value, None])
        for day, value in trend.forecast:
            ws.append([day.strftime("%Y-%m-%d"), None, value])
        ws.append([])
        ws.append(
            [
                f"O'zgarish: {trend.first:g} → {trend.last:g}"
                + (f" ({trend.change_pct:+g}%)" if trend.change_pct is not None else "")
            ]
        )
        ws.append([f"Chiziqli moslik R² = {trend.r2:g}; prognoz — taxmin, fakt emas."])
        rows = len(trend.points) + len(trend.forecast)
        chart = LineChart()
        chart.title = trend.column
        chart.height, chart.width = 8, 18
        chart.add_data(
            Reference(ws, min_col=2, max_col=3, min_row=1, max_row=rows + 1), titles_from_data=True
        )
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=rows + 1))
        ws.add_chart(chart, "E2")

    for g_index, group in enumerate(analysis.groups[:3]):
        ws = book.create_sheet(f"Guruh {g_index + 1}")
        _header(ws, [group.by, f"{group.column} (jami)", "Qatorlar"])
        for label, total, count in group.totals:
            ws.append([safe_text(label), total, count])
        chart = BarChart()
        chart.title = f"{group.column} — {group.by}"
        chart.height, chart.width = 8, 18
        chart.add_data(
            Reference(ws, min_col=2, min_row=1, max_row=len(group.totals) + 1),
            titles_from_data=True,
        )
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(group.totals) + 1))
        ws.add_chart(chart, "E2")

    if analysis.outliers or analysis.warnings:
        ws = book.create_sheet("Eslatmalar")
        _header(ws, ["Eslatma"])
        for o in analysis.outliers:
            ws.append(
                [f"G'ayrioddiy qiymat: «{o.column}», {o.row}-qator = {o.value:g} — tekshiring."]
            )
        for w in analysis.warnings:
            ws.append([w])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
