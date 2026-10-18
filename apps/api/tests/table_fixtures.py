"""PDFs and images with a known table."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from tests.ocr_fixtures import FONT

ROWS = [
    ("Viloyat", "Aholi", "O'sish %"),
    ("Toshkent shahri", "3 040 000", "2.1"),
    ("Samarqand", "4 200 000", "1.8"),
    ("Farg'ona", "3 900 000", "1.6"),
    ("Xorazm", "1 950 000", "1.4"),
]


def table_pdf() -> bytes:
    if "EzoTableFont" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("EzoTableFont", str(FONT)))
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.setFont("EzoTableFont", 11)
    page.drawString(60, 780, "Hisobot: viloyatlar bo'yicha aholi")
    y = 740
    for name, people, growth in ROWS:
        page.drawString(60, y, name)
        page.drawRightString(330, y, people)
        page.drawRightString(450, y, growth)
        y -= 20
    page.drawString(60, y - 30, "Izoh: ma'lumotlar taxminiy.")
    page.save()
    return buffer.getvalue()


def table_image() -> Image.Image:
    font = ImageFont.truetype(str(FONT), 34)
    image = Image.new("L", (1700, 520), 255)
    draw = ImageDraw.Draw(image)
    draw.text((80, 40), "Hisobot: viloyatlar bo'yicha aholi", font=font, fill=0)
    y = 140
    for name, people, growth in ROWS:
        draw.text((80, y), name, font=font, fill=0)
        width = draw.textlength(people, font=font)
        draw.text((900 - width, y), people, font=font, fill=0)
        width = draw.textlength(growth, font=font)
        draw.text((1300 - width, y), growth, font=font, fill=0)
        y += 60
    return image
