import re
import logging
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

from spider.base import BaseSpider
from config import ABAPI_URL, REQUEST_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class AbapiSpider(BaseSpider):
    def __init__(self):
        super().__init__("今日油价网(abapi)")
        self._update_time = None

    def fetch_oil_prices(self) -> Optional[List[Dict]]:
        try:
            resp = requests.get(
                ABAPI_URL,
                headers=REQUEST_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"

            soup = BeautifulSoup(resp.text, "lxml")

            update_time_text = soup.find(string=re.compile(r"更新时间"))
            if update_time_text:
                match = re.search(r"(\d{4}-\d{2}-\d{2})", str(update_time_text))
                if match:
                    self._update_time = match.group(1)

            table = soup.find("table")
            if not table:
                logger.warning(f"[{self.name}] 未找到油价表格")
                return None

            prices = []
            rows = table.find_all("tr")
            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) < 5:
                    continue

                province = cols[0].get_text(strip=True)
                if not province or province in ("地区", "📍 全国各地今日油价"):
                    continue

                item = {
                    "province": province,
                    "oil_92": self._parse_float(cols[1].get_text(strip=True)),
                    "oil_95": self._parse_float(cols[2].get_text(strip=True)),
                    "oil_98": self._parse_float(cols[3].get_text(strip=True)),
                    "oil_0": self._parse_float(cols[4].get_text(strip=True)),
                }
                prices.append(item)

            logger.info(f"[{self.name}] 成功获取 {len(prices)} 个地区油价数据")
            return prices

        except requests.RequestException as e:
            logger.error(f"[{self.name}] 请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[{self.name}] 解析失败: {e}")
            return None

    def get_update_time(self) -> Optional[str]:
        return self._update_time

    @staticmethod
    def _parse_float(value: str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
