import re
import json
import logging
from typing import List, Dict, Optional

import requests

from spider.base import BaseSpider
from config import EASTMONEY_API_URL, REQUEST_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class EastMoneySpider(BaseSpider):
    def __init__(self):
        super().__init__("东方财富网")
        self._update_time = None

    def fetch_oil_prices(self) -> Optional[List[Dict]]:
        latest_date = self._fetch_latest_date()
        if not latest_date:
            logger.warning(f"[{self.name}] 无法获取最新调价日期")
            return None

        self._update_time = latest_date
        return self._fetch_prices_by_date(latest_date)

    def _fetch_latest_date(self) -> Optional[str]:
        params = {
            "reportName": "RPTA_WEB_YJ_RQ",
            "columns": "ALL",
            "sortColumns": "DIM_DATE",
            "sortTypes": "-1",
            "pageNumber": "1",
            "pageSize": "1",
            "source": "WEB",
        }

        try:
            resp = requests.get(
                EASTMONEY_API_URL,
                params=params,
                headers={
                    **REQUEST_HEADERS,
                    "Referer": "https://data.eastmoney.com/",
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                return None

            rows = data.get("result", {}).get("data", [])
            if not rows:
                return None

            dim_date = rows[0].get("DIM_DATE", "")
            match = re.search(r"(\d{4}-\d{2}-\d{2})", str(dim_date))
            return match.group(1) if match else None

        except Exception as e:
            logger.error(f"[{self.name}] 获取日期失败: {e}")
            return None

    def _fetch_prices_by_date(self, date: str) -> Optional[List[Dict]]:
        params = {
            "reportName": "RPTA_WEB_YJ_JH",
            "columns": "ALL",
            "filter": f"(DIM_DATE='{date}')",
            "sortColumns": "FIRST_LETTER",
            "sortTypes": "1",
            "pageNumber": "1",
            "pageSize": "100",
            "source": "WEB",
        }

        try:
            resp = requests.get(
                EASTMONEY_API_URL,
                params=params,
                headers={
                    **REQUEST_HEADERS,
                    "Referer": "https://data.eastmoney.com/",
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.warning(f"[{self.name}] 接口返回错误: {data.get('message')}")
                return None

            rows = data.get("result", {}).get("data", [])
            if not rows:
                logger.warning(f"[{self.name}] 无油价数据")
                return None

            prices = []
            for row in rows:
                item = {
                    "province": row.get("CITYNAME", ""),
                    "oil_89": row.get("V89"),
                    "oil_92": row.get("V92"),
                    "oil_95": row.get("V95"),
                    "oil_0": row.get("V0"),
                    "change_89": row.get("ZDE89"),
                    "change_92": row.get("ZDE92"),
                    "change_95": row.get("ZDE95"),
                    "change_0": row.get("ZDE0"),
                    "adjust_date": date,
                }
                if item["province"]:
                    prices.append(item)

            logger.info(f"[{self.name}] 成功获取 {len(prices)} 个地区油价数据 (调整日期: {date})")
            return prices

        except requests.RequestException as e:
            logger.error(f"[{self.name}] 请求失败: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[{self.name}] 数据解析失败: {e}")
            return None

    def get_update_time(self) -> Optional[str]:
        return self._update_time
