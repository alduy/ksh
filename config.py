"""
贵阳市交通拥堵监测系统 - 配置文件
"""

import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量（如果存在）
load_dotenv()

# 基本配置
DEBUG = True
SECRET_KEY = os.getenv('SECRET_KEY', 'dev_key_for_traffic_congestion')
PORT = int(os.getenv('PORT', 5000))

# 贵阳市中心坐标
GUIYANG_CENTER = [26.598194, 106.707410]
DEFAULT_ZOOM = 12

# 交通数据模拟配置
SIMULATION_INTERVAL = 5  # 数据更新间隔（秒）
NUM_ROAD_SEGMENTS = 30   # 模拟的路段数量

# 拥堵指数阈值
CONGESTION_THRESHOLDS = {
    'light': 0.4,      # 轻度拥堵
    'moderate': 0.6,   # 中度拥堵
    'heavy': 0.8       # 重度拥堵
}

# 预测模型参数
MODEL_FEATURES = ['hour', 'day_of_week', 'traffic_flow', 'average_speed']
MODEL_UPDATE_INTERVAL = 3600  # 模型更新间隔（秒）

# 数据库配置（如果后期需要添加）
# DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///traffic_data.db')

# 增加地图交互配置
MAP_STYLE = {
    # 主要地图服务
    'tile_url': 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    # 备用地图服务 - 中国大陆区域更容易访问的服务
    'tile_url_backup': 'https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    'attribution': '© OpenStreetMap © CartoDB',
    'marker_color': '#ff4444',
    'marker_size': 12
}