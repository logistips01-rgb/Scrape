"""Impresión automática del PDF resultante."""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

from loguru import logger


def imprimir_pdf(pdf_path: Path, impresora: str | None = None) -> bool:
    """
    Envía el PDF a la impresora. Devuelve True si el comando se lanzó sin error.
    - Windows: usa SumatraPDF si está instalado (silencioso), si no os.startfile
    - Linux/Mac: usa lpr
    """
    if not pdf_path.exists():
        logger.error(f"PDF no encontrado para imprimir: {pdf_path}")
        return False

    sistema = platform.system()
    try:
        if sistema == "Windows":
            return _imprimir_windows(pdf_path, impresora)
        else:
            return _imprimir_unix(pdf_path, impresora)
    except Exception as exc:
        logger.error(f"Error al imprimir {pdf_path.name}: {exc}")
        return False


def _imprimir_windows(pdf_path: Path, impresora: str | None) -> bool:
    # Opción 1: SumatraPDF (silencioso, sin ventana) — recomendado
    sumatra_paths = [
        r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
        r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
        "SumatraPDF.exe",  # si está en PATH
    ]
    for sumatra in sumatra_paths:
        if Path(sumatra).exists() or sumatra == "SumatraPDF.exe":
            cmd = [sumatra, "-print-to-default", "-silent", str(pdf_path)]
            if impresora:
                cmd = [sumatra, "-print-to", impresora, "-silent", str(pdf_path)]
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Imprimiendo con SumatraPDF: {pdf_path.name}")
                return True
            except FileNotFoundError:
                continue

    # Opción 2: PowerShell PrintTo (funciona con cualquier PDF viewer instalado)
    if impresora:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f'Start-Process -FilePath "{pdf_path}" -Verb PrintTo -ArgumentList "{impresora}" -Wait',
        ]
    else:
        # os.startfile con verbo "print" — puede aparecer ventana brevemente
        import os
        os.startfile(str(pdf_path), "print")
        logger.info(f"Imprimiendo con impresora predeterminada: {pdf_path.name}")
        return True

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info(f"Imprimiendo con PowerShell: {pdf_path.name}")
    return True


def _imprimir_unix(pdf_path: Path, impresora: str | None) -> bool:
    cmd = ["lpr", str(pdf_path)]
    if impresora:
        cmd = ["lpr", "-P", impresora, str(pdf_path)]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info(f"Imprimiendo con lpr: {pdf_path.name}")
    return True
