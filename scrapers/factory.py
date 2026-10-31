from config.settings import settings
from core.models import Portal
from scrapers.base import BaseScraper
from scrapers.chep import ChepScraper
from scrapers.europool import EuropoolScraper
from scrapers.europool_api import EuropoolApiDeclarer
from scrapers.ifco import IfcoScraper

_SCRAPERS: dict[Portal, type[BaseScraper]] = {
    Portal.EUROPOOL: EuropoolScraper,
    Portal.IFCO: IfcoScraper,
    Portal.CHEP: ChepScraper,
}


def get_scraper(portal: Portal) -> BaseScraper:
    if portal == Portal.EUROPOOL and settings.europool_modo == "api":
        return EuropoolApiDeclarer()
    cls = _SCRAPERS.get(portal)
    if cls is None:
        raise ValueError(f"Portal desconocido: {portal}")
    return cls()
