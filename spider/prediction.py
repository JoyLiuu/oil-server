import re
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

try:
    from chinese_calendar import is_workday
except ImportError:
    is_workday = None

from config import EASTMONEY_API_URL, REQUEST_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

EASTMONEY_OIL_URL = "https://data.eastmoney.com/cjsj/yjtz/default.html"

# 国家发改委成品油调价机制：每10个工作日调整一次
ADJUST_INTERVAL_WORKDAYS = 10

_calendar_warned = False


def fetch_prediction() -> Dict:
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
        "pageSize": "12",
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
    """根据最近一次调价日期推算下次调价窗口：上次调价日 + 10个工作日"""
    if not history:
        return ""

    last_date_str = history[0].get("date", "")
    if not last_date_str:
        return ""

    try:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
    except ValueError:
        return ""

    next_date = _add_workdays(last_date, ADJUST_INTERVAL_WORKDAYS)
    if not next_date:
        return ""

    return next_date.strftime("%Y-%m-%d") + " 24:00"


def _add_workdays(start_date: datetime, days: int) -> Optional[datetime]:
    """返回 start_date 之后第 days 个工作日，自动跳过周末和法定节假日（含调休）"""
    global _calendar_warned

    cur = start_date
    count = 0
    while count < days:
        cur += timedelta(days=1)
        try:
            if is_workday is not None:
                workday = bool(is_workday(cur))
            else:
                raise NotImplementedError
        except NotImplementedError:
            if not _calendar_warned:
                logger.warning(
                    f"[油价预测] chinese-calendar 缺少 {cur.year} 年节假日数据，"
                    "退化为仅跳过周末推算，结果可能偏差1-2天"
                )
                _calendar_warned = True
            workday = cur.weekday() < 5

        if workday:
            count += 1
    return cur

