from core.models import Portal
from scrapers.base import BaseScraper
from scrapers.chep import ChepScraper
from scrapers.europool import EuropoolScraper
from scrapers.ifco import IfcoScraper

_SCRAPERS: dict[Portal, type[BaseScraper]] = {
    Portal.EUROPOOL: EuropoolScraper,
    Portal.IFCO: IfcoScraper,
    Portal.CHEP: ChepScraper,
}


def get_scraper(portal: Portal) -> BaseScraper:
    cls = _SCRAPERS.get(portal)
    if cls is None:
        raise ValueError(f"Portal desconocido: {portal}")
    return cls()
