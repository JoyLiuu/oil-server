from spider.base import BaseSpider
from spider.eastmoney import EastMoneySpider
from spider.abapi import AbapiSpider
from spider.prediction import fetch_prediction

__all__ = ["BaseSpider", "EastMoneySpider", "AbapiSpider", "fetch_prediction"]
