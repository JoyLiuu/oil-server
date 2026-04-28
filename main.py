import argparse
import logging
import sys
from typing import List, Dict, Optional

from spider.eastmoney import EastMoneySpider
from spider.abapi import AbapiSpider
from storage.file_storage import FileStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SPIDERS = [
    EastMoneySpider,
    AbapiSpider,
]


def fetch_oil_prices(source: str = "all") -> Optional[List[Dict]]:
    if source == "all":
        spider_classes = SPIDERS
    elif source == "eastmoney":
        spider_classes = [EastMoneySpider]
    elif source == "abapi":
        spider_classes = [AbapiSpider]
    else:
        logger.error(f"未知数据源: {source}")
        return None

    for spider_cls in spider_classes:
        spider = spider_cls()
        logger.info(f"正在从 [{spider.name}] 获取油价数据...")
        result = spider.fetch_oil_prices()
        if result:
            update_time = spider.get_update_time()
            if update_time:
                logger.info(f"数据更新时间: {update_time}")
            return result
        logger.warning(f"[{spider.name}] 获取失败，尝试下一个数据源...")

    logger.error("所有数据源均获取失败")
    return None


def _fmt_price(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "-"


def _fmt_change(val) -> str:
    if val is None:
        return "-"
    try:
        v = float(val)
        return f"+{v:.2f}" if v > 0 else f"{v:.2f}"
    except (ValueError, TypeError):
        return "-"


def display_prices(prices: List[Dict], province: str = None):
    if not prices:
        print("\n暂无油价数据")
        return

    if province:
        prices = [p for p in prices if province in p.get("province", "")]
        if not prices:
            print(f"\n未找到 [{province}] 的油价数据")
            return

    has_change = any("change_92" in p for p in prices)

    print("\n" + "=" * 70)
    print("全国最新油价 (单位: 元/升)")
    print("=" * 70)
    header = f"{'地区':<8}{'92#汽油':<10}{'95#汽油':<10}{'98#汽油':<10}{'0#柴油':<10}"
    if has_change:
        header += f"{'92#涨跌':<10}{'95#涨跌':<10}{'0#涨跌':<10}"
    print(header)
    print("-" * 70)

    for item in prices:
        line = f"{item.get('province', ''):<8}"
        line += f"{_fmt_price(item.get('oil_92')):<10}"
        line += f"{_fmt_price(item.get('oil_95')):<10}"
        line += f"{_fmt_price(item.get('oil_98')):<10}"
        line += f"{_fmt_price(item.get('oil_0')):<10}"

        if has_change:
            line += f"{_fmt_change(item.get('change_92')):<10}"
            line += f"{_fmt_change(item.get('change_95')):<10}"
            line += f"{_fmt_change(item.get('change_0')):<10}"

        print(line)

    print("=" * 70)
    print(f"共 {len(prices)} 个地区")


def main():
    parser = argparse.ArgumentParser(description="全国最新油价查询工具")
    parser.add_argument(
        "-s", "--source",
        choices=["all", "eastmoney", "abapi"],
        default="all",
        help="数据源选择 (默认: all，依次尝试所有数据源)",
    )
    parser.add_argument(
        "-p", "--province",
        type=str,
        default=None,
        help="查询指定省份油价 (如: 北京、广东)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "csv", "both"],
        default="json",
        help="保存格式 (默认: json)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="是否将数据保存到文件",
    )
    args = parser.parse_args()

    prices = fetch_oil_prices(source=args.source)
    if not prices:
        sys.exit(1)

    display_prices(prices, province=args.province)

    if args.save:
        storage = FileStorage()
        if args.format in ("json", "both"):
            storage.save_json(prices)
        if args.format in ("csv", "both"):
            storage.save_csv(prices)


if __name__ == "__main__":
    main()
