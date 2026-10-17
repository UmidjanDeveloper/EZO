# ruff: noqa: E501 - this module is mostly SVG/HTML markup
"""A self-contained web presentation (one HTML file, inline SVG, no external resources).

Keys: ←/→ or space to move, F for fullscreen, N to show speaker notes.
"""

from __future__ import annotations

import math
from html import escape

from ezo_api.documents.render.common import ASCENT, flat, text_lines
from ezo_api.documents.render.primitives import Ellipse, Line, Rect, SlidePlan, TextBox, Wedge
from ezo_api.documents.render.text import BULLET_INDENT


def _arc(cx: float, cy: float, r: float, start: float, end: float, inner: float) -> str:
    def point(radius: float, deg: float) -> tuple[float, float]:
        rad = math.radians(deg)
        return cx + radius * math.cos(rad), cy + radius * math.sin(rad)

    large = 1 if end - start > 180 else 0
    x1, y1 = point(r, start)
    x2, y2 = point(r, end)
    if inner:
        x3, y3 = point(inner, end)
        x4, y4 = point(inner, start)
        return f"M{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} L{x3:.1f},{y3:.1f} A{inner:.1f},{inner:.1f} 0 {large} 0 {x4:.1f},{y4:.1f} Z"
    return f"M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z"


def _svg(plan: SlidePlan) -> str:
    parts = [
        f'<svg viewBox="0 0 {plan.width:g} {plan.height:g}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(plan.title)}">'
    ]
    parts.append(f'<rect width="100%" height="100%" fill="{plan.background}"/>')
    for item in flat(plan):
        if isinstance(item, Rect):
            stroke = (
                f' stroke="{item.line}" stroke-width="{item.line_width:g}"' if item.line else ""
            )
            parts.append(
                f'<rect x="{item.x:.1f}" y="{item.y:.1f}" width="{item.w:.1f}" height="{item.h:.1f}" rx="{item.radius:g}" fill="{item.fill or "none"}"{stroke}/>'
            )
        elif isinstance(item, Ellipse):
            stroke = (
                f' stroke="{item.line}" stroke-width="{item.line_width:g}"' if item.line else ""
            )
            parts.append(
                f'<ellipse cx="{item.x + item.w / 2:.1f}" cy="{item.y + item.h / 2:.1f}" rx="{item.w / 2:.1f}" ry="{item.h / 2:.1f}" fill="{item.fill or "none"}"{stroke}/>'
            )
        elif isinstance(item, Line):
            marker = ' marker-end="url(#arrow)"' if item.arrow else ""
            parts.append(
                f'<line x1="{item.x1:.1f}" y1="{item.y1:.1f}" x2="{item.x2:.1f}" y2="{item.y2:.1f}" stroke="{item.color}" stroke-width="{item.width:g}" color="{item.color}"{marker}/>'
            )
        elif isinstance(item, Wedge):
            parts.append(
                f'<path d="{_arc(item.cx, item.cy, item.r, item.start, item.end, item.inner_r)}" fill="{item.fill}" stroke="{plan.background}" stroke-width="1.5"/>'
            )
        elif isinstance(item, TextBox):
            for x, y, line, size, bold, color, bullet in text_lines(item):
                weight = ' font-weight="700"' if bold else ""
                baseline = y + size * ASCENT
                if bullet:
                    parts.append(
                        f'<text x="{x - size * BULLET_INDENT:.1f}" y="{baseline:.1f}" font-size="{size:g}" fill="{color}">•</text>'
                    )
                parts.append(
                    f'<text x="{x:.1f}" y="{baseline:.1f}" font-size="{size:g}" fill="{color}"{weight} xml:space="preserve">{escape(line)}</text>'
                )
    parts.append("</svg>")
    return "".join(parts)


_STYLE = """
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#111;color:#eee;font-family:"Liberation Sans",Arial,Helvetica,sans-serif}
.deck{height:100%;display:flex;align-items:center;justify-content:center}
.slide{display:none;width:min(100vw,calc(100vh*RATIO));aspect-ratio:RATIO;box-shadow:0 10px 40px #0008}
.slide.on{display:block}.slide svg{width:100%;height:100%;display:block}
.slide svg text{font-family:"Liberation Sans",Arial,Helvetica,sans-serif}
.bar{position:fixed;bottom:10px;left:0;right:0;text-align:center;font-size:13px;opacity:.6}
.notes{position:fixed;left:0;right:0;bottom:36px;margin:auto;max-width:900px;background:#000c;padding:12px 16px;border-radius:10px;white-space:pre-wrap;display:none;font-size:15px;line-height:1.4}
.show-notes .notes.on{display:block}
"""

_SCRIPT = """
const s=[...document.querySelectorAll('.slide')],n=[...document.querySelectorAll('.notes')];let i=0;
const c=document.getElementById('count');
function go(k){i=Math.max(0,Math.min(s.length-1,k));s.forEach((e,j)=>e.classList.toggle('on',j===i));n.forEach((e,j)=>e.classList.toggle('on',j===i));c.textContent=(i+1)+' / '+s.length;}
document.addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' '].includes(e.key))go(i+1);else if(['ArrowLeft','PageUp'].includes(e.key))go(i-1);else if(e.key==='Home')go(0);else if(e.key==='End')go(s.length-1);else if(e.key==='n'||e.key==='N')document.body.classList.toggle('show-notes');else if(e.key==='f'||e.key==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}});
document.addEventListener('click',e=>{go(e.clientX>innerWidth/2?i+1:i-1)});go(0);
"""


def render_deck_html(plans: list[SlidePlan], title: str, language: str) -> bytes:
    ratio = f"{plans[0].width:g}/{plans[0].height:g}" if plans else "16/9"
    defs = '<svg width="0" height="0" style="position:absolute"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs></svg>'
    slides = "".join(f'<section class="slide">{_svg(plan)}</section>' for plan in plans)
    notes = "".join(f'<div class="notes">{escape(plan.notes)}</div>' for plan in plans)
    page = (
        f'<!doctype html><html lang="{escape(language)}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:\">"
        f"<title>{escape(title)}</title><style>{_STYLE.replace('RATIO', ratio)}</style></head>"
        f'<body>{defs}<main class="deck">{slides}</main>{notes}<div class="bar"><span id="count"></span> · ← → · N · F</div>'
        f"<script>{_SCRIPT}</script></body></html>"
    )
    return page.encode("utf-8")
