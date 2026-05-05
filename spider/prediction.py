import re
import json
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from config import EASTMONEY_API_URL, REQUEST_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

EASTMONEY_OIL_URL = "https://data.eastmoney.com/cjsj/yjtz/default.html"


def fetch_prediction() -> Optional[Dict]:
    result = {
        "prediction_text": "",
        "change_rate": None,
        "trend": "",
        "predict_gasoline_change": None,
        "predict_diesel_change": None,
        "next_window_date": "",
        "last_adjust_date": "",
        "last_gasoline_price": None,
        "last_diesel_price": None,
        "last_gasoline_change": None,
        "last_diesel_change": None,
        "history": [],
    }

    if not _fetch_prediction_from_page(result):
        logger.warning("[油价预测] 页面预测数据获取失败")

    if not _fetch_history_from_api(result):
        logger.warning("[油价预测] 历史调价数据获取失败")

    if result["history"] and not result["next_window_date"]:
        result["next_window_date"] = _calc_next_window(result["history"])

    return result


def _fetch_prediction_from_page(result: Dict) -> bool:
    try:
        resp = requests.get(
            EASTMONEY_OIL_URL,
            headers={
                **REQUEST_HEADERS,
                "Referer": "https://data.eastmoney.com/",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"

        soup = BeautifulSoup(resp.text, "lxml")

        prediction_div = soup.find("div", class_="predict")
        if not prediction_div:
            all_text = soup.get_text()
            match = re.search(
                r"自上一个窗口调整至今.*?(?:预计|预测).*?(?:持平|上调|下调|上涨|下跌|不调整)",
                all_text,
            )
            if match:
                result["prediction_text"] = match.group(0).strip()
        else:
            result["prediction_text"] = prediction_div.get_text(strip=True)

        full_text = soup.get_text()

        if not result["prediction_text"]:
            patterns = [
                r"自上一个窗口调整至今.*?(?:预计|预测).*?(?:持平|上调|下调|上涨|下跌|不调整)[^。]*",
                r"原油价格变动幅度为[^\。]*?(?:预计|预测)[^。]*",
            ]
            for pattern in patterns:
                match = re.search(pattern, full_text)
                if match:
                    result["prediction_text"] = match.group(0).strip()
                    break

        if result["prediction_text"]:
            rate_match = re.search(r"变动幅度为([+-]?\d+\.?\d*%)", result["prediction_text"])
            if rate_match:
                rate_str = rate_match.group(1).replace("%", "")
                try:
                    result["change_rate"] = float(rate_str)
                except ValueError:
                    pass

            if "上调" in result["prediction_text"] or "上涨" in result["prediction_text"]:
                result["trend"] = "up"
            elif "下调" in result["prediction_text"] or "下跌" in result["prediction_text"]:
                result["trend"] = "down"
            elif "持平" in result["prediction_text"] or "不调整" in result["prediction_text"]:
                result["trend"] = "flat"
            else:
                result["trend"] = "unknown"

        adjust_match = re.search(r"最近一次调整说明[：:](.*?)(?:<|$)", full_text)
        if adjust_match:
            adjust_text = adjust_match.group(1).strip()
            amount_matches = re.findall(r"(\d+)元", adjust_text)
            if len(amount_matches) >= 2:
                try:
                    if "降低" in adjust_text or "下调" in adjust_text:
                        result["predict_gasoline_change"] = -int(amount_matches[0])
                        result["predict_diesel_change"] = -int(amount_matches[1])
                    else:
                        result["predict_gasoline_change"] = int(amount_matches[0])
                        result["predict_diesel_change"] = int(amount_matches[1])
                except (ValueError, IndexError):
                    pass

        return True

    except Exception as e:
        logger.error(f"[油价预测] 页面获取失败: {e}")
        return False


def _fetch_history_from_api(result: Dict) -> bool:
    params = {
        "reportName": "RPTA_WEB_YJ_BD",
        "columns": "ALL",
        "sortColumns": "DIM_DATE",
        "sortTypes": "-1",
        "pageNumber": "1",
        "pageSize": "10",
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
            return False

        rows = data.get("result", {}).get("data", [])
        if not rows:
            return False

        for row in rows:
            dim_date = row.get("DIM_DATE", "")
            match = re.search(r"(\d{4}-\d{2}-\d{2})", str(dim_date))
            date_str = match.group(1) if match else ""

            item = {
                "date": date_str,
                "gasoline_price": row.get("VALUE"),
                "diesel_price": row.get("CY_JG"),
                "gasoline_change": row.get("QY_FD"),
                "diesel_change": row.get("CY_FD"),
            }
            result["history"].append(item)

        if result["history"]:
            latest = result["history"][0]
            result["last_adjust_date"] = latest["date"]
            result["last_gasoline_price"] = latest["gasoline_price"]
            result["last_diesel_price"] = latest["diesel_price"]
            result["last_gasoline_change"] = latest["gasoline_change"]
            result["last_diesel_change"] = latest["diesel_change"]

        return True

    except Exception as e:
        logger.error(f"[油价预测] 历史数据获取失败: {e}")
        return False


def _calc_next_window(history: list) -> str:
    if not history:
        return ""

    last_date_str = history[0].get("date", "")
    if not last_date_str:
        return ""

    try:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
    except ValueError:
        return ""

    year = last_date.year
    windows = _get_adjustment_windows(year)

    for window_date in windows:
        if window_date > last_date_str:
            return window_date

    return ""


def _get_adjustment_windows(year: int) -> list:
    windows = {
        2026: [
            "2026-01-06", "2026-01-20",
            "2026-02-03", "2026-02-24",
            "2026-03-09", "2026-03-23",
            "2026-04-07", "2026-04-21",
            "2026-05-08", "2026-05-21",
            "2026-06-04", "2026-06-18",
            "2026-07-03", "2026-07-17", "2026-07-31",
            "2026-08-14", "2026-08-28",
            "2026-09-11", "2026-09-24",
            "2026-10-15", "2026-10-29",
            "2026-11-12", "2026-11-26",
            "2026-12-10", "2026-12-24",
        ],
    }
    return windows.get(year, [])


def _get_holidays(year: int) -> set:
    holidays = set()
    common = {
        2025: [
            "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
            "2025-02-03", "2025-02-04", "2025-04-04", "2025-05-01", "2025-05-02",
            "2025-05-05", "2025-05-31", "2025-06-02", "2025-10-01", "2025-10-02",
            "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",
        ],
        2026: [
            "2026-01-01", "2026-01-02", "2026-02-16", "2026-02-17", "2026-02-18",
            "2026-02-19", "2026-02-20", "2026-04-06", "2026-05-01", "2026-05-04",
            "2026-05-05", "2026-06-19", "2026-10-01", "2026-10-02", "2026-10-05",
            "2026-10-06", "2026-10-07",
        ],
    }
    return set(common.get(year, []))
