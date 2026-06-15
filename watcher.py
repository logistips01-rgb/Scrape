"""
Vigilante de carpeta (Hot Folder Watcher).

Monitoriza la carpeta INPUT_DIR esperando ficheros CSV del ERP.
Cuando detecta uno nuevo lo procesa automáticamente:
  1. Declara los envases en Europool / IFCO / CHEP
  2. Genera el PDF de declaración
  3. Fusiona con el PDF del albarán si existe
  4. Imprime el PDF combinado en la impresora predeterminada
  5. Mueve el CSV a la carpeta de procesados (o errores si falla)

Uso:
    python watcher.py             # arranca el vigilante
    python watcher.py --ayuda     # muestra esta ayuda
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from loguru import logger
from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config.settings import settings
from core.database import guardar_declaracion, init_db, ya_declarado
from core.erp_parser import albaranes_from_xls
from core.models import DeclarationStatus, albaranes_from_csv
from documents.declaration import generar_declaracion_pdf
from documents.merger import fusionar_pdfs
from documents.printer import imprimir_pdf
from scrapers.factory import get_scraper

# ---------------------------------------------------------------------------
# Carpetas de trabajo
# ---------------------------------------------------------------------------
DIR_PENDIENTES = settings.input_dir / "pendientes"
DIR_PROCESANDO = settings.input_dir / "procesando"
DIR_PROCESADOS = settings.input_dir / "procesados"
DIR_ERRORES = settings.input_dir / "errores"
DIR_COMPLETADOS = settings.output_dir / "completados"

for _d in (DIR_PENDIENTES, DIR_PROCESANDO, DIR_PROCESADOS, DIR_ERRORES, DIR_COMPLETADOS):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger.remove()
settings.output_dir.mkdir(parents=True, exist_ok=True)
logger.add(settings.output_dir / "logs" / "watcher.log", rotation="10 MB", level="DEBUG")
logger.add(sys.stdout, level="INFO", colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


# ---------------------------------------------------------------------------
# Procesado de un fichero CSV
# ---------------------------------------------------------------------------

def procesar_csv(csv_path: Path) -> None:
    """Procesa un CSV completo: scraping + PDF + impresión."""
    logger.info(f"Procesando: {csv_path.name}")

    # Mover a "procesando" para evitar doble procesado
    en_proceso = DIR_PROCESANDO / csv_path.name
    csv_path.rename(en_proceso)

    errores = []
    try:
        init_db()
        if en_proceso.suffix.lower() in (".xls", ".xlsx"):
            albaranes = albaranes_from_xls(en_proceso)
        else:
            albaranes = albaranes_from_csv(en_proceso)
        logger.info(f"  {len(albaranes)} albarán(es) encontrados en el fichero")

        for albaran in albaranes:
            if ya_declarado(albaran.num_albaran, albaran.portal.value):
                logger.warning(f"  [{albaran.num_albaran}] Ya declarado. Omitiendo.")
                continue

            logger.info(f"  → [{albaran.portal.value}] {albaran.num_albaran} | {albaran.cliente_nombre}")

            scraper = get_scraper(albaran.portal)
            result = scraper.declarar(albaran)

            if result.status != DeclarationStatus.ERROR:
                # Usar el PDF oficial del portal si fue descargado,
                # o generar uno propio como fallback
                if albaran.pdf_declaracion_oficial and albaran.pdf_declaracion_oficial.exists():
                    result.declaration_pdf_path = albaran.pdf_declaracion_oficial
                    logger.info("  Usando PDF oficial del portal")
                else:
                    result.declaration_pdf_path = generar_declaracion_pdf(albaran, result)

                result.merged_pdf_path = fusionar_pdfs(
                    result.declaration_pdf_path,
                    albaran.pdf_path,
                    albaran.num_albaran,
                )

                # Copiar PDF a completados
                dest = DIR_COMPLETADOS / result.merged_pdf_path.name
                dest.write_bytes(result.merged_pdf_path.read_bytes())

                # Imprimir automáticamente
                if settings.auto_print:
                    ok = imprimir_pdf(dest, settings.printer_name or None)
                    logger.info(f"  PDF enviado a impresora: {ok}")
                else:
                    logger.info(f"  PDF listo en: {dest}")

            else:
                logger.error(f"  ERROR en {albaran.num_albaran}: {result.error_message}")
                errores.append(albaran.num_albaran)

            guardar_declaracion(
                num_albaran=albaran.num_albaran,
                portal=albaran.portal.value,
                status=result.status.value,
                confirmation_num=result.confirmation_number,
                declaration_pdf=str(result.declaration_pdf_path) if result.declaration_pdf_path else None,
                merged_pdf=str(result.merged_pdf_path) if result.merged_pdf_path else None,
                error_message=result.error_message,
            )

    except Exception as exc:
        logger.exception(f"Error crítico procesando {csv_path.name}: {exc}")
        errores.append("*")

    # Mover CSV a procesados o errores según resultado
    if errores:
        destino = DIR_ERRORES / en_proceso.name
        logger.warning(f"  Fichero movido a ERRORES: {destino.name}")
    else:
        destino = DIR_PROCESADOS / en_proceso.name
        logger.success(f"  Fichero procesado OK → {destino.name}")

    en_proceso.rename(destino)


# ---------------------------------------------------------------------------
# Handler del watchdog
# ---------------------------------------------------------------------------

class CsvHandler(FileSystemEventHandler):
    _EXTENSIONES = {".csv", ".xls", ".xlsx"}

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        self._handle(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        self._handle(Path(event.dest_path))

    def _handle(self, path: Path) -> None:
        if path.suffix.lower() not in self._EXTENSIONES:
            return
        # Esperar a que el ERP termine de escribir el fichero
        time.sleep(2)
        if path.exists():
            procesar_csv(path)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("  DECLARADOR DE ENVASES — Vigilante de carpeta activo")
    logger.info(f"  Monitorizando: {DIR_PENDIENTES.resolve()}")
    logger.info(f"  Completados:   {DIR_COMPLETADOS.resolve()}")
    logger.info(f"  Impresión:     {'SÍ' if settings.auto_print else 'NO'}")
    logger.info("=" * 60)

    # Procesar ficheros que ya estuvieran esperando
    for csv_file in DIR_PENDIENTES.glob("*.csv"):
        logger.info(f"Fichero pendiente encontrado al arrancar: {csv_file.name}")
        procesar_csv(csv_file)

    observer = Observer()
    observer.schedule(CsvHandler(), str(DIR_PENDIENTES), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Vigilante detenido.")
    observer.join()


if __name__ == "__main__":
    main()
