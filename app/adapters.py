"""Shared internal page contract; existing declarative connectors stay readable."""
from dataclasses import dataclass
from app.connectors import Connector, search_json


@dataclass(frozen=True)
class PageRequest:
    query: str
    limit: int
    offset: int = 0
    home: bool = False


class JsonAdapter:
    def __init__(self, config, credential=None):
        self.config = Connector.model_validate(config)
        self.credential = credential

    def search(self, page):
        return search_json(self.config.model_dump(), page.query, page.limit, page.home,
                           offset=page.offset, credential=self.credential, return_page=True)


def native_pagination(config):
    return config.get('kind') == 'json' and config.get('pagination', {}).get('mode', 'prefix') != 'prefix'
