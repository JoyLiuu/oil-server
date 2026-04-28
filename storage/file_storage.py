import os
import json
import csv
import logging
from typing import List, Dict
from datetime import datetime

from config import DATA_DIR

logger = logging.getLogger(__name__)


class FileStorage:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)

    def save_json(self, data: List[Dict], filename: str = None) -> str:
        if filename is None:
            filename = f"oil_prices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(DATA_DIR, filename)

        output = {
            "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(data),
            "data": data,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON数据已保存至: {filepath}")
        return filepath

    def save_csv(self, data: List[Dict], filename: str = None) -> str:
        if filename is None:
            filename = f"oil_prices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(DATA_DIR, filename)

        if not data:
            logger.warning("无数据可保存")
            return ""

        fieldnames = list(data[0].keys())
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"CSV数据已保存至: {filepath}")
        return filepath

    def load_latest_json(self) -> List[Dict]:
        json_files = [
            f for f in os.listdir(DATA_DIR) if f.startswith("oil_prices_") and f.endswith(".json")
        ]
        if not json_files:
            return []

        json_files.sort(reverse=True)
        filepath = os.path.join(DATA_DIR, json_files[0])

        with open(filepath, "r", encoding="utf-8") as f:
            content = json.load(f)

        return content.get("data", [])
