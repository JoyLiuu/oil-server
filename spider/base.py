from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseSpider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def fetch_oil_prices(self) -> Optional[List[Dict]]:
        pass

    @abstractmethod
    def get_update_time(self) -> Optional[str]:
        pass
