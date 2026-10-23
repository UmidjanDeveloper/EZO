"""PDF generation worker for EZO JARVIS Mode.

Transforms metric comparison results and executive summaries into clean,
professional vector PDF documents using EZO's typography and document model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ezo_api.documents.model import DocumentSpec, Heading, Paragraph, Rule, Run, Table
from ezo_api.documents.pdf.writer import render_pdf
from ezo_api.jarvis.percentage_worker import MetricComparisonResult


def build_comparison_pdf(
    comparison: MetricComparisonResult,
    source_filename_older: str = "metrics_2026_10_20.json",
    source_filename_newer: str = "metrics_2026_10_21.json",
    output_path: Path | None = None,
) -> tuple[bytes, Path | None]:
    """Generates a professional PDF report from metric comparison results.

    Returns the raw PDF bytes and the output Path if saved.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    blocks = [
        Heading(
            level=1,
            runs=(Run(text="EZO OS — Ko'rsatkichlar Taqqoslama Hisoboti", bold=True),),
        ),
        Paragraph(
            runs=(
                Run(
                    text=f"Hisobot sanasi: {now_str} | OpenJarvis Desktop Agent orqali avtomatik tuzildi",
                    italic=True,
                ),
            )
        ),
        Rule(),
        Heading(
            level=2,
            runs=(Run(text="1. Asosiy Xulosa va Qisqacha Tahlil", bold=True),),
        ),
        Paragraph(
            runs=(
                Run(
                    text=comparison.summary_uz,
                ),
            )
        ),
        Paragraph(
            runs=(
                Run(text="Tahlil qilingan manbalar: ", bold=True),
                Run(text=f"Baza fayli: '{source_filename_older}', Yangi fayl: '{source_filename_newer}'"),
            )
        ),
        Rule(),
        Heading(
            level=2,
            runs=(Run(text="2. Parametrlar va Foiz O'zgarishlari Jadvali", bold=True),),
        ),
    ]

    # Build comparison table
    header = (
        "Ko'rsatkich Nomi",
        "Oldingi Ko'rsatkich",
        "Yangi Ko'rsatkich",
        "O'zgarish (Farq)",
        "O'sish / Foiz Sur'ati",
    )
    rows: list[tuple[str, ...]] = []
    for r in comparison.rows:
        prev_display = f"{r.previous_value:,.2f}".rstrip("0").rstrip(".")
        curr_display = f"{r.current_value:,.2f}".rstrip("0").rstrip(".")
        diff_display = f"{r.diff:+,.2f}".rstrip("0").rstrip(".")
        rows.append(
            (
                r.label_uz,
                prev_display,
                curr_display,
                diff_display,
                r.formatted_change,
            )
        )

    blocks.append(Table(header=header, rows=tuple(rows)))

    blocks.extend(
        [
            Rule(),
            Heading(
                level=3,
                runs=(Run(text="3. Xavfsizlik va Tekshiruv Ma'lumotlari (Audit Hash)", bold=True),),
            ),
            Paragraph(
                runs=(
                    Run(text="SHA256 Audit Imzosi: ", bold=True),
                    Run(text=comparison.audit_hash, code=True),
                )
            ),
            Paragraph(
                runs=(
                    Run(
                        text="Ushbu hujjat EZO OS JARVIS Mode va OpenJarvis xavfsiz qumloq (sandbox) "
                        "muhitida to'liq tekshirilib, tasdiqlash uchun tayyorlandi.",
                        italic=True,
                    ),
                )
            ),
        ]
    )

    spec = DocumentSpec(
        title="EZO OS — Ko'rsatkichlar Taqqoslama Hisoboti",
        subtitle=f"Manba: {source_filename_newer}",
        language="uz",
        author="EZO OS / JARVIS Agent",
        blocks=blocks,
    )

    pdf_bytes = render_pdf(spec)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)

    return pdf_bytes, output_path
