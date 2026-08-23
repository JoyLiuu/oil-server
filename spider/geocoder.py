"""
地理编码模块：将经纬度转换为省份和城市
使用中国各省份/城市中心点坐标进行距离计算（纯本地，无第三方调用）
"""

from typing import Optional, Tuple, Dict

from spider.utils import haversine


# 中国各省份中心点坐标（经度, 纬度）
# 数据来源：公开地理数据
PROVINCE_COORDS: Dict[str, Tuple[float, float]] = {
    "北京": (116.405, 39.905),
    "天津": (117.190, 39.125),
    "河北": (114.485, 38.010),
    "山西": (112.549, 37.857),
    "内蒙古": (111.670, 40.818),
    "辽宁": (123.429, 41.796),
    "吉林": (125.324, 43.886),
    "黑龙江": (126.642, 45.756),
    "上海": (121.473, 31.230),
    "江苏": (118.767, 32.041),
    "浙江": (120.153, 30.287),
    "安徽": (117.283, 31.861),
    "福建": (119.306, 26.075),
    "江西": (115.892, 28.676),
    "山东": (117.000, 36.675),
    "河南": (113.665, 34.757),
    "湖北": (114.298, 30.584),
    "湖南": (112.982, 28.194),
    "广东": (113.266, 23.132),
    "广西": (108.320, 22.824),
    "海南": (110.350, 19.020),
    "重庆": (106.504, 29.533),
    "四川": (104.075, 30.675),
    "贵州": (106.713, 26.578),
    "云南": (102.712, 25.040),
    "西藏": (91.117, 29.647),
    "陕西": (108.954, 34.265),
    "甘肃": (103.826, 36.059),
    "青海": (101.778, 36.617),
    "宁夏": (106.278, 38.468),
    "新疆": (87.617, 43.792),
    "香港": (114.173, 22.320),
    "澳门": (113.543, 22.198),
    "台湾": (121.509, 25.044),
}

# 中国主要城市中心点坐标（经度, 纬度）及所属省份
# 用于城市级逆地理编码
CITY_COORDS: Dict[str, Tuple[float, float, str]] = {
    # 直辖市
    "北京市": (116.405, 39.905, "北京"),
    "上海市": (121.473, 31.230, "上海"),
    "天津市": (117.190, 39.125, "天津"),
    "重庆市": (106.504, 29.533, "重庆"),
    # 省会城市
    "石家庄市": (114.515, 38.042, "河北"),
    "太原市": (112.549, 37.857, "山西"),
    "呼和浩特市": (111.670, 40.818, "内蒙古"),
    "沈阳市": (123.429, 41.796, "辽宁"),
    "长春市": (125.324, 43.886, "吉林"),
    "哈尔滨市": (126.642, 45.756, "黑龙江"),
    "南京市": (118.767, 32.041, "江苏"),
    "杭州市": (120.153, 30.287, "浙江"),
    "合肥市": (117.283, 31.861, "安徽"),
    "福州市": (119.306, 26.075, "福建"),
    "南昌市": (115.892, 28.676, "江西"),
    "济南市": (117.000, 36.675, "山东"),
    "郑州市": (113.665, 34.757, "河南"),
    "武汉市": (114.298, 30.584, "湖北"),
    "长沙市": (112.982, 28.194, "湖南"),
    "广州市": (113.266, 23.132, "广东"),
    "南宁市": (108.320, 22.824, "广西"),
    "海口市": (110.350, 19.020, "海南"),
    "成都市": (104.075, 30.675, "四川"),
    "贵阳市": (106.713, 26.578, "贵州"),
    "昆明市": (102.712, 25.040, "云南"),
    "拉萨市": (91.117, 29.647, "西藏"),
    "西安市": (108.954, 34.265, "陕西"),
    "兰州市": (103.826, 36.059, "甘肃"),
    "西宁市": (101.778, 36.617, "青海"),
    "银川市": (106.278, 38.468, "宁夏"),
    "乌鲁木齐市": (87.617, 43.792, "新疆"),
    # 主要非省会城市
    "深圳市": (114.058, 22.543, "广东"),
    "东莞市": (113.746, 23.046, "广东"),
    "佛山市": (113.122, 23.028, "广东"),
    "珠海市": (113.577, 22.271, "广东"),
    "惠州市": (114.413, 23.079, "广东"),
    "中山市": (113.382, 22.521, "广东"),
    "苏州市": (120.620, 31.299, "江苏"),
    "无锡市": (120.302, 31.574, "江苏"),
    "常州市": (119.947, 31.773, "江苏"),
    "南通市": (120.865, 32.016, "江苏"),
    "徐州市": (117.185, 34.262, "江苏"),
    "宁波市": (121.550, 29.868, "浙江"),
    "温州市": (120.672, 28.000, "浙江"),
    "嘉兴市": (120.751, 30.777, "浙江"),
    "绍兴市": (120.582, 30.000, "浙江"),
    "金华市": (119.650, 29.079, "浙江"),
    "青岛市": (120.355, 36.083, "山东"),
    "大连市": (121.615, 38.914, "辽宁"),
    "厦门市": (118.112, 24.490, "福建"),
    "泉州市": (118.590, 24.870, "福建"),
    "洛阳市": (112.434, 34.663, "河南"),
    "株洲市": (113.152, 27.836, "湖南"),
    "绵阳市": (104.742, 31.464, "四川"),
    "宜昌市": (111.290, 30.692, "湖北"),
    "咸阳市": (108.715, 34.330, "陕西"),
    "鞍山市": (122.995, 41.110, "辽宁"),
    "吉林市": (126.553, 43.844, "吉林"),
    "齐齐哈尔市": (123.953, 47.342, "黑龙江"),
    "曲靖市": (103.798, 25.502, "云南"),
    "遵义市": (106.937, 27.706, "贵州"),
    "大同市": (113.295, 40.090, "山西"),
    "柳州市": (109.412, 24.314, "广西"),
    "赣州市": (114.940, 25.851, "江西"),
    "芜湖市": (118.376, 31.326, "安徽"),
    "漳州市": (117.662, 24.510, "福建"),
    "烟台市": (121.391, 37.539, "山东"),
    "潍坊市": (119.107, 36.707, "山东"),
    "临沂市": (118.326, 35.065, "山东"),
    "三亚市": (109.508, 18.248, "海南"),
    "包头市": (109.840, 40.658, "内蒙古"),
    "喀什市": (75.990, 39.468, "新疆"),
    # 特别行政区
    "香港特别行政区": (114.173, 22.320, "香港"),
    "澳门特别行政区": (113.543, 22.198, "澳门"),
}


def get_province_by_coords(
    longitude: float, latitude: float
) -> Tuple[Optional[str], float]:
    """
    根据经纬度获取最近的省份

    Args:
        longitude: 经度
        latitude: 纬度

    Returns:
        (省份名称, 距离(米)) 或 (None, float('inf'))
    """
    if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
        return None, float("inf")

    min_distance = float("inf")
    nearest_province = None

    for province, (lng, lat) in PROVINCE_COORDS.items():
        distance = haversine(longitude, latitude, lng, lat)
        if distance < min_distance:
            min_distance = distance
            nearest_province = province

    return nearest_province, min_distance


def get_city_by_coords(
    longitude: float, latitude: float
) -> Tuple[Optional[str], Optional[str], float]:
    """
    根据经纬度获取最近的城市和所属省份

    Returns:
        (城市名称, 所属省份, 距离(米)) 或 (None, None, float('inf'))
    """
    if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
        return None, None, float("inf")

    min_distance = float("inf")
    nearest_city = None
    nearest_province = None

    for city, (lng, lat, province) in CITY_COORDS.items():
        distance = haversine(longitude, latitude, lng, lat)
        if distance < min_distance:
            min_distance = distance
            nearest_city = city
            nearest_province = province

    return nearest_city, nearest_province, min_distance


def coords_to_province(longitude: float, latitude: float) -> Optional[str]:
    province, distance = get_province_by_coords(longitude, latitude)
    if distance > 500000:
        return None
    return province


def coords_to_city(longitude: float, latitude: float) -> Optional[Dict[str, str]]:
    """
    将经纬度转换为详细位置信息

    Returns:
        {"province": "北京", "city": "北京市", "district": ""} 或 None
    """
    city_name, province_name, distance = get_city_by_coords(longitude, latitude)

    if distance > 500000:
        return None

    if not city_name or not province_name:
        province, prov_distance = get_province_by_coords(longitude, latitude)
        if prov_distance > 500000:
            return None
        return {
            "province": province or "",
            "city": "",
            "district": "",
        }

    return {
        "province": province_name,
        "city": city_name,
        "district": "",
    }


if __name__ == "__main__":
    test_cases = [
        (116.405, 39.905, "北京", "北京市"),
        (121.473, 31.230, "上海", "上海市"),
        (113.266, 23.132, "广东", "广州市"),
        (120.153, 30.287, "浙江", "杭州市"),
        (104.075, 30.675, "四川", "成都市"),
        (114.058, 22.543, "广东", "深圳市"),
    ]

    for lng, lat, expected_prov, expected_city in test_cases:
        result = coords_to_city(lng, lat)
        status = "✓" if result and result["province"] == expected_prov else "✗"
        city_status = "✓" if result and result["city"] == expected_city else "✗"
        print(f"{status}{city_status} ({lng}, {lat}) -> {result} (期望: {expected_prov}/{expected_city})")
