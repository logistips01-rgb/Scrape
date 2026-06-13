"""Genera el PDF de declaración de envases."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config.settings import settings
from core.models import Albaran, DeclaracionResult

STYLES = getSampleStyleSheet()


def generar_declaracion_pdf(albaran: Albaran, result: DeclaracionResult) -> Path:
    """Genera el PDF de declaración y lo guarda en output/pdfs/. Devuelve la ruta."""
    out_dir = settings.output_dir / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"declaracion_{albaran.portal.value}_{albaran.num_albaran}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []

    # Cabecera
    story.append(Paragraph(
        f"<b>DECLARACIÓN DE ENVASES — {albaran.portal.value.upper()}</b>",
        STYLES["Title"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    # Datos del albarán
    datos = [
        ["Nº Albarán:", albaran.num_albaran],
        ["Nº Pedido:", albaran.num_pedido],
        ["Fecha entrega:", albaran.fecha_entrega.strftime("%d/%m/%Y")],
        ["Cliente:", f"{albaran.cliente_codigo} — {albaran.cliente_nombre}"],
        ["Portal:", albaran.portal.value.upper()],
    ]
    if result.confirmation_number:
        datos.append(["Nº Confirmación:", result.confirmation_number])

    info_table = Table(datos, colWidths=[5 * cm, 12 * cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.8 * cm))

    # Tabla de envases
    story.append(Paragraph("<b>Detalle de envases declarados</b>", STYLES["Heading2"]))
    story.append(Spacer(1, 0.3 * cm))

    headers = ["Tipo de envase", "Cantidad"]
    rows = [[l.tipo, str(l.cantidad)] for l in albaran.lineas]
    rows.append(["TOTAL", str(albaran.total_envases)])

    envases_table = Table(
        [headers] + rows,
        colWidths=[12 * cm, 5 * cm],
    )
    envases_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5f8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f0f7")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f5f5")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(envases_table)
    story.append(Spacer(1, 1 * cm))

    # Estado
    estado_color = "#28a745" if result.confirmation_number else "#dc3545"
    estado_texto = "DECLARACIÓN ENVIADA CORRECTAMENTE" if result.confirmation_number else "PENDIENTE DE CONFIRMACIÓN"
    story.append(Paragraph(
        f'<font color="{estado_color}"><b>{estado_texto}</b></font>',
        STYLES["Normal"],
    ))

    doc.build(story)
    return pdf_path
