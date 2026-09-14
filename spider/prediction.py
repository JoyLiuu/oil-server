import re
import json
import logging
import threading
from typing import Dict, List, Optional
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

try:
    from chinese_calendar import is_workday as _calendar_is_workday
except ImportError:
    _calendar_is_workday = None

from config import EASTMONEY_API_URL, REQUEST_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

EASTMONEY_OIL_URL = "https://data.eastmoney.com/cjsj/yjtz/default.html"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_CRUDE_SECID = "102.CL00Y"
SINA_FUTURES_KLINE_URL = (
    "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20t=/"
    "GlobalFuturesService.getGlobalFuturesDailyKLine"
)
CHAJIAGE_URL = "https://www.chajiage.com/youjia/tiaozheng.html"

# 国家发改委成品油调价机制：每10个工作日调整一次
ADJUST_INTERVAL_WORKDAYS = 10
# 调价红线：每吨汽柴油调价金额不足50元时不作调整
NDRC_ADJUST_THRESHOLD = 50

# 吨换算升的系数（按各标号汽柴油标准密度估算）：1吨 ≈ N升
LITERS_PER_TON = {
    "oil_89": 1410,
    "oil_92": 1375,
    "oil_95": 1350,
    "oil_98": 1330,
    "oil_0": 1190,
}

# 历史调价实测校准：原油变化率每1%对应约50元/吨（非按零售价比例传导）
CRUDE_RATE_COEFFICIENT = 50

_cache_lock = threading.Lock()
_cache: Dict = {"result": None, "fetched_at": None}
CACHE_TTL = timedelta(minutes=30)

_calendar_warned = False


def fetch_prediction() -> Dict:
    with _cache_lock:
        if (
            _cache["result"] is not None
            and _cache["fetched_at"] is not None
            and datetime.now() - _cache["fetched_at"] < CACHE_TTL
        ):
            return dict(_cache["result"])

    result = {
        "prediction_text": "",
        "change_rate": None,
        "trend": "",
        "predict_gasoline_change": None,
        "predict_diesel_change": None,
        "predict_price_change": None,
        "next_window_date": "",
        "last_adjust_date": "",
        "last_gasoline_price": None,
        "last_diesel_price": None,
        "last_gasoline_change": None,
        "last_diesel_change": None,
        "history": [],
    }

    if not _fetch_history_from_api(result):
        logger.warning("[油价预测] 历史调价数据获取失败")

    if result["history"]:
        result["next_window_date"] = _calc_next_window(result["history"])

    # 优先从查价格网获取准确的调价窗口时间
    if not _fetch_prediction_from_chajiage(result):
        logger.warning("[油价预测] chajiage 调价窗口获取失败")

    # 原油行情推算：获取 trend、预测调幅、prediction_text（使用已校正的 next_window_date）
    closes = _fetch_crude_closes()
    if closes and _compute_from_crude(result, closes):
        pass
    else:
        logger.warning("[油价预测] 原油行情推算失败，回退到东财页面预测文本")
        if not _fetch_prediction_from_page(result):
            logger.warning("[油价预测] 页面预测数据获取失败")

    _normalize_prediction_text(result)

    with _cache_lock:
        _cache["result"] = result
        _cache["fetched_at"] = datetime.now()

    return dict(result)


def _normalize_prediction_text(result: Dict) -> None:
    """把 prediction_text 中过期的窗口日期替换为 next_window_date 的正确日期"""
    text = result.get("prediction_text", "")
    nwd = result.get("next_window_date", "")
    if not text or not nwd:
        return
    nwd_date = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", nwd)
    if not nwd_date:
        return
    target_month, target_day = int(nwd_date.group(2)), int(nwd_date.group(3))
    old_match = re.search(r"(\d{1,2})月(\d{1,2})日\s*(?:24时|24:00)", text)
    if not old_match:
        return
    old_month, old_day = int(old_match.group(1)), int(old_match.group(2))
    if (old_month, old_day) == (target_month, target_day):
        return
    text = re.sub(r"\d{1,2}月\d{1,2}日\s*(?:24时|24:00)",
                  f"{target_month}月{target_day}日24时", text, count=1)
    result["prediction_text"] = text


def _is_workday(d: date) -> bool:
    global _calendar_warned
    if _calendar_is_workday is not None:
        try:
            return bool(_calendar_is_workday(d))
        except (NotImplementedError, ValueError):
            if not _calendar_warned:
                logger.warning(
                    f"[油价预测] chinese-calendar 缺少 {d.year} 年节假日数据，"
                    "退化为仅跳过周末推算，结果可能偏差1-2天"
                )
                _calendar_warned = True
    return d.weekday() < 5


def _fetch_prediction_from_chajiage(result: Dict) -> bool:
    """从查价格网获取准确的调价窗口时间（实时更新）"""
    try:
        resp = requests.get(CHAJIAGE_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        raw = resp.text

        # 提取 "下一轮油价调整窗口时间：XXXX年X月X日24时"
        match = re.search(
            r"下一轮油价调整窗口时间[：:]\s*(\d{4}年)?(\d{1,2})月(\d{1,2})日\s*24时",
            raw,
        )
        if not match:
            logger.warning("[油价预测] chajiage 页面未找到下一轮调价窗口时间")
            return False

        month, day = int(match.group(2)), int(match.group(3))
        today = datetime.now().date()
        try:
            window_date = date(today.year, month, day)
        except ValueError:
            return False

        if window_date >= today:
            result["next_window_date"] = window_date.strftime("%Y-%m-%d") + " 24:00"
            logger.info(f"[油价预测] chajiage 下次调价窗口: {result['next_window_date']}")
            return True

        logger.warning(f"[油价预测] chajiage 窗口日期已过: {window_date}")
        return False

    except Exception as e:
        logger.error(f"[油价预测] chajiage 爬取失败: {e}")
        return False


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
                re.S,
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
                match = re.search(pattern, full_text, re.S)
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


def _fetch_crude_closes() -> Dict[str, float]:
    for fetcher in (_crude_closes_from_sina, _crude_closes_from_eastmoney):
        try:
            data = fetcher()
            if data:
                logger.info(f"[油价预测] 国际原油收盘价来源: {fetcher.__name__}（{len(data)}个交易日）")
                return data
        except Exception as e:
            logger.warning(f"[油价预测] {fetcher.__name__} 获取失败: {e}")
    return {}


def _crude_closes_from_sina() -> Dict[str, float]:
    resp = requests.get(
        SINA_FUTURES_KLINE_URL,
        params={"symbol": "OIL"},
        headers={
            **REQUEST_HEADERS,
            "Referer": "https://finance.sina.com.cn",
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    text = resp.content.decode("gbk", errors="ignore")

    match = re.search(r"\((.*)\)", text, re.S)
    if not match:
        return {}

    rows = json.loads(match.group(1))
    closes: Dict[str, float] = {}
    for row in rows:
        day = str(row.get("date", ""))
        close = row.get("close")
        if not day or close is None:
            continue
        try:
            closes[day] = float(close)
        except (TypeError, ValueError):
            continue
    return closes


def _crude_closes_from_eastmoney() -> Dict[str, float]:
    begin = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    resp = requests.get(
        EASTMONEY_KLINE_URL,
        params={
            "secid": EM_CRUDE_SECID,
            "fields1": "f1,f2,f3",
            "fields2": "f51,f53",
            "klt": "101",
            "fqt": "0",
            "beg": begin,
            "end": "20500101",
        },
        headers={
            **REQUEST_HEADERS,
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()

    klines = ((resp.json().get("data") or {}).get("klines")) or []
    closes: Dict[str, float] = {}
    for line in klines:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            closes[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return closes


def _compute_from_crude(result: Dict, closes: Dict[str, float]) -> bool:
    last_adjust_date = result.get("last_adjust_date") or ""
    gasoline_price = result.get("last_gasoline_price")
    diesel_price = result.get("last_diesel_price")

    if not last_adjust_date or gasoline_price is None or diesel_price is None:
        return False

    try:
        last_adj = datetime.strptime(last_adjust_date, "%Y-%m-%d").date()
    except ValueError:
        return False

    today = datetime.now().date()

    prev_days: List[date] = []
    cur = last_adj
    while len(prev_days) < ADJUST_INTERVAL_WORKDAYS:
        cur -= timedelta(days=1)
        if _is_workday(cur):
            prev_days.append(cur)

    cur_first = last_adj
    while True:
        cur_first += timedelta(days=1)
        if _is_workday(cur_first):
            break

    prev_closes = [
        closes[d.isoformat()] for d in sorted(prev_days) if d.isoformat() in closes
    ]
    cur_closes = []
    d = cur_first
    while d <= today:
        key = d.isoformat()
        if key in closes:
            cur_closes.append(closes[key])
        d += timedelta(days=1)

    if len(prev_closes) < ADJUST_INTERVAL_WORKDAYS // 2 or len(cur_closes) < 2:
        logger.info(
            f"[油价预测] 样本不足：上轮{len(prev_closes)}天/本轮{len(cur_closes)}天，暂不推算"
        )
        return False

    avg_prev = sum(prev_closes) / len(prev_closes)
    avg_cur = sum(cur_closes) / len(cur_closes)
    if avg_prev <= 0:
        return False

    rate = (avg_cur / avg_prev - 1) * 100

    est_ton = int(round(rate * CRUDE_RATE_COEFFICIENT / 5) * 5)
    est_gasoline = est_ton
    est_diesel = est_ton

    window_date = str(result.get("next_window_date") or "").split(" ")[0] or cur_first.isoformat()

    if max(abs(est_gasoline), abs(est_diesel)) < NDRC_ADJUST_THRESHOLD:
        trend = "flat"
        est_gasoline = 0
        est_diesel = 0
        prediction_text = (
            f"上一调价窗口以来国际原油均价变动{rate:+.2f}%，"
            f"折算调价幅度不足50元/吨，预计{window_date} 24时调价搁浅、零售限价持平"
        )
    elif rate > 0:
        trend = "up"
        prediction_text = (
            f"上一调价窗口以来国际原油均价上涨{rate:.2f}%，"
            f"预计{window_date} 24时汽柴油最高零售限价上调约{est_gasoline}元/吨，"
            f"折合92号每升约{est_gasoline / LITERS_PER_TON['oil_92']:.2f}元"
        )
    else:
        trend = "down"
        prediction_text = (
            f"上一调价窗口以来国际原油均价下跌{abs(rate):.2f}%，"
            f"预计{window_date} 24时汽柴油最高零售限价下调约{abs(est_gasoline)}元/吨，"
            f"折合92号每升约{abs(est_gasoline) / LITERS_PER_TON['oil_92']:.2f}元"
        )

    result["change_rate"] = round(rate, 2)
    result["trend"] = trend
    result["predict_gasoline_change"] = est_gasoline
    result["predict_diesel_change"] = est_diesel
    result["predict_price_change"] = {
        field: round((est_diesel if field == "oil_0" else est_gasoline) / liters, 2)
        for field, liters in LITERS_PER_TON.items()
    }
    result["prediction_text"] = prediction_text
    return True


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

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    while next_date <= today:
        next_date = _add_workdays(next_date, ADJUST_INTERVAL_WORKDAYS)
        if not next_date:
            return ""

    return next_date.strftime("%Y-%m-%d") + " 24:00"


def _add_workdays(start_date: datetime, days: int) -> Optional[datetime]:
    """返回 start_date 之后第 days 个工作日，自动跳过周末和法定节假日（含调休）"""
    cur = start_date
    count = 0
    while count < days:
        cur += timedelta(days=1)
        if _is_workday(cur.date()):
            count += 1
    return cur
