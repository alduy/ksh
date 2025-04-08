"""
交通数据模拟生成器
用于生成模拟的贵阳市交通数据
"""

import random
import time
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker

# 初始化 Faker 生成器
fake = Faker('zh_CN')

# 贵阳市主要路段和区域
GUIYANG_ROADS = [
    "花果园大街", "南明河滨河路", "沙冲路", "观山大道", "金阳大道", 
    "林城西路", "宝山北路", "乌当大道", "金华园路", "新添大道", 
    "北京路", "未来方舟大道", "贵开大道", "清镇大道", "小河大道",
    "马王庙路", "解放路", "中华中路", "瑞金南路", "中华北路",
    "延安东路", "喷水池路", "遵义路", "人民大道", "都司路",
    "云岩路", "中山东路", "中山西路", "青云路", "新添大道"
]

# 贵阳市各区
GUIYANG_DISTRICTS = [
    "云岩区", "南明区", "花溪区", "乌当区", "白云区", 
    "观山湖区", "清镇市", "开阳县", "修文县", "息烽县"
]

# 贵阳市主要路段基本坐标（近似值，实际应用中应使用精确坐标）
GUIYANG_COORDINATES = {
    "花果园大街": [26.571234, 106.713789],
    "南明河滨河路": [26.567890, 106.723456],
    "观山大道": [26.598765, 106.737891],
    "金阳大道": [26.612345, 106.687654],
    "林城西路": [26.587654, 106.698765],
    # 其他路段可以根据需要添加...
}

class TrafficDataGenerator:
    """交通数据生成器类"""
    
    def __init__(self, num_road_segments=30):
        """
        初始化交通数据生成器
        
        参数:
            num_road_segments: 生成的路段数量
        """
        self.num_road_segments = num_road_segments
        self.road_segments = self._generate_road_segments()
        self.historical_data = pd.DataFrame()
        self._generate_initial_historical_data()
    
    def _generate_road_segments(self):
        """生成基本的路段信息"""
        road_segments = []
        
        for i in range(self.num_road_segments):
            # 随机选择道路名称，如果不够可以重复使用
            road_name = GUIYANG_ROADS[i % len(GUIYANG_ROADS)]
            district = random.choice(GUIYANG_DISTRICTS)
            
            # 如果有预设坐标就使用，否则随机生成附近坐标
            if road_name in GUIYANG_COORDINATES:
                base_lat, base_lng = GUIYANG_COORDINATES[road_name]
            else:
                # 贵阳市中心附近随机生成坐标
                base_lat = 26.598194 + random.uniform(-0.05, 0.05)
                base_lng = 106.707410 + random.uniform(-0.05, 0.05)
            
            # 路段长度 (500米 - 3公里)
            length = round(random.uniform(0.5, 3.0), 2)
            
            # 计算路段终点（简化处理，实际应用需考虑道路走向）
            angle = random.uniform(0, 2 * math.pi)
            end_lat = base_lat + (length / 111) * math.sin(angle)  # 约111公里/度
            end_lng = base_lng + (length / 85) * math.cos(angle)   # 贵阳纬度下约85公里/度
            
            # 道路类型
            road_type = random.choice(['主干道', '次干道', '支路', '快速路'])
            
            # 车道数量
            lanes = random.randint(2, 8)
            
            road_segments.append({
                'id': i + 1,
                'name': road_name,
                'district': district,
                'type': road_type,
                'lanes': lanes,
                'length': length,
                'start_lat': base_lat,
                'start_lng': base_lng,
                'end_lat': end_lat,
                'end_lng': end_lng,
                'capacity': lanes * 500  # 简化的容量计算
            })
        
        return road_segments
    
    def _generate_initial_historical_data(self):
        """生成初始的历史数据（过去7天）"""
        data = []
        now = datetime.now()
        
        # 过去7天的数据
        for day_offset in range(7, 0, -1):
            start_date = now - timedelta(days=day_offset)
            
            # 每天生成24小时的数据
            for hour in range(24):
                timestamp = start_date.replace(hour=hour, minute=0, second=0)
                
                for segment in self.road_segments:
                    # 添加时间因素影响，早晚高峰拥堵程度更高
                    time_factor = self._get_time_factor(hour)
                    
                    # 生成交通数据
                    traffic_data = self._generate_traffic_data(segment, time_factor, timestamp)
                    data.append(traffic_data)
        
        self.historical_data = pd.DataFrame(data)
    
    def _get_time_factor(self, hour):
        """根据一天中的时间生成交通因子，模拟早晚高峰"""
        if 7 <= hour <= 9:  # 早高峰
            return random.uniform(0.7, 1.0)
        elif 17 <= hour <= 19:  # 晚高峰
            return random.uniform(0.6, 0.9)
        elif 10 <= hour <= 16:  # 工作时间
            return random.uniform(0.3, 0.6)
        else:  # 夜间和凌晨
            return random.uniform(0.1, 0.3)
    
    def _generate_traffic_data(self, segment, time_factor, timestamp=None):
        """为特定路段生成交通数据"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # 基本容量
        capacity = segment['capacity']
        
        # 车流量 (受时间因子影响)
        traffic_flow = int(capacity * time_factor * random.uniform(0.8, 1.2))
        
        # 平均车速 (km/h)，随交通流量增加而减少
        max_speed = 60 if segment['type'] == '快速路' else 40
        average_speed = max(5, max_speed * (1 - 0.8 * (traffic_flow / capacity)))
        
        # 拥堵指数 (0-1)
        congestion_index = min(1.0, (traffic_flow / capacity) * random.uniform(0.8, 1.2))
        
        # 路段状态
        if congestion_index < 0.4:
            status = '畅通'
        elif congestion_index < 0.6:
            status = '轻度拥堵'
        elif congestion_index < 0.8:
            status = '中度拥堵'
        else:
            status = '严重拥堵'
        
        return {
            'timestamp': timestamp,
            'segment_id': segment['id'],
            'road_name': segment['name'],
            'district': segment['district'],
            'traffic_flow': traffic_flow,
            'average_speed': round(average_speed, 1),
            'congestion_index': round(congestion_index, 2),
            'status': status,
            'hour': timestamp.hour,
            'day_of_week': timestamp.weekday(),
            'latitude': segment['start_lat'],
            'longitude': segment['start_lng']
        }
    
    def get_real_time_data(self):
        """生成并返回所有路段的实时数据"""
        current_time = datetime.now()
        
        # 获取当前时间因子
        current_hour = current_time.hour
        time_factor = self._get_time_factor(current_hour)
        
        # 确保道路段定义正确
        if not self.road_segments or len(self.road_segments) == 0:
            print("警告: 没有定义的路段，重新生成路段定义")
            self.road_segments = self._generate_road_segments()
            if not self.road_segments:
                print("错误: 无法生成路段定义")
                # 返回空DataFrame但确保列存在
                return pd.DataFrame({
                    'segment_id': [], 'road_name': [], 'district': [], 
                    'traffic_flow': [], 'average_speed': [], 'congestion_index': [],
                    'status': [], 'timestamp': [], 'latitude': [], 'longitude': []
                })
        
        print(f"开始生成实时数据，共 {len(self.road_segments)} 个路段")
        
        # 为每个路段生成数据
        real_time_data = []
        for segment in self.road_segments:
            data = self._generate_traffic_data(segment, time_factor, current_time)
            
            # 确保没有NaN值
            for key, value in data.items():
                if pd.isna(value):
                    # 根据字段类型设置默认值
                    if key == 'congestion_index':
                        data[key] = 0.3
                    elif key == 'average_speed':
                        data[key] = 40.0
                    elif key == 'traffic_flow':
                        data[key] = 200
                    elif key == 'latitude' or key == 'longitude':
                        data[key] = 0.0
                    elif key == 'status':
                        data[key] = '畅通'
                    elif key == 'road_name':
                        data[key] = f"路段 #{segment['id']}"
                    elif key == 'district':
                        data[key] = "未知区域"
                    elif isinstance(value, (int, float)):
                        data[key] = 0
                    elif isinstance(value, str):
                        data[key] = ""
                    else:
                        data[key] = None
            
            real_time_data.append(data)
        
        # 转换为DataFrame
        df = pd.DataFrame(real_time_data)
        
        # 再次检查并清理任何NaN值
        for col in df.columns:
            if df[col].isna().any():
                count_nan = df[col].isna().sum()
                print(f"警告: 列 {col} 包含 {count_nan} 个NaN值，进行修复")
                
                if col == 'congestion_index':
                    df[col] = df[col].fillna(0.3)
                elif col == 'average_speed':
                    df[col] = df[col].fillna(40.0)
                elif col == 'traffic_flow':
                    df[col] = df[col].fillna(200)
                elif col == 'status':
                    df[col] = df[col].fillna('畅通')
                elif col in ['latitude', 'longitude']:
                    # 如果坐标缺失，设置为贵阳市中心
                    df[col] = df[col].fillna(26.598194 if col == 'latitude' else 106.707410)
                elif df[col].dtype in [np.int64, np.float64]:
                    df[col] = df[col].fillna(0)
                else:
                    df[col] = df[col].fillna('')
        
        # 添加到历史数据（可选，视内存使用情况而定）
        if len(df) > 0:
            self.historical_data = pd.concat([self.historical_data, df], ignore_index=True)
        
        # 打印一条调试信息，确认数据是否正常
        print(f"生成了 {len(df)} 条路段数据，监控路段数: {df['segment_id'].nunique()}")
        
        # 额外的数据检查
        if len(df) == 0:
            print("警告: 生成的数据为空!")
        
        # 打印一些示例数据
        if not df.empty:
            print("示例数据:")
            sample = df.head(1).to_dict('records')[0]
            for key, value in sample.items():
                print(f"  {key}: {value}")
        
        return df
    
    def get_historical_trend(self, hours=24):
        """生成历史趋势数据（确保返回字典列表）"""
        trend_data = []
        base_time = datetime.now() - timedelta(hours=hours)
        
        for i in range(hours):
            entry = {
                'timestamp': (base_time + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S'),
                'avg_congestion': random.uniform(0.3, 0.8)
            }
            trend_data.append(entry)
        
        print(f"[DEBUG] 生成历史趋势数据样例: {trend_data[:2]}")  # 调试输出
        return trend_data
        
    def get_historical_trend(self, segment_id=None, days=7):
        """获取历史趋势数据"""
        if not self.historical_data.empty:
            data = self.historical_data.copy()
            
            # 过滤特定路段
            if segment_id is not None:
                data = data[data['segment_id'] == segment_id]
            
            # 按小时聚合
            data['hour_group'] = data['timestamp'].dt.floor('H')
            hourly_data = data.groupby(['hour_group']).agg({
                'congestion_index': 'mean',
                'traffic_flow': 'mean',
                'average_speed': 'mean'
            }).reset_index()
            
            return hourly_data
        
        return pd.DataFrame()
    
    def get_congested_segments(self, threshold=0.6):
        """获取当前拥堵路段"""
        real_time_data = self.get_real_time_data()
        congested = real_time_data[real_time_data['congestion_index'] >= threshold]
        return congested.sort_values('congestion_index', ascending=False)

    def get_all_road_data(self):
        """获取所有路段数据，包括历史记录"""
        if self.historical_data.empty:
            # 如果没有历史数据，返回当前实时数据
            return self.get_real_time_data()
        else:
            # 返回所有历史数据
            return self.historical_data

    def get_road_historical_trend(self, road_id, hours=24):
        """获取特定路段的历史趋势数据"""
        if self.historical_data.empty:
            # 如果没有历史数据，生成模拟数据
            road_name = f"路段 #{road_id}"
            district = "未知区域"
            
            trend_data = []
            now = datetime.now()
            
            for i in range(hours):
                time_point = now - timedelta(hours=hours-i)
                # 生成波动的拥堵指数，白天高、夜间低
                hour = time_point.hour
                base_congestion = 0.3  # 基础拥堵指数
                
                # 早晚高峰拥堵系数
                if 7 <= hour <= 9:  # 早高峰
                    congestion_factor = 0.3 + random.uniform(0.1, 0.5)
                elif 17 <= hour <= 19:  # 晚高峰
                    congestion_factor = 0.4 + random.uniform(0.1, 0.5)
                elif 12 <= hour <= 14:  # 午间高峰
                    congestion_factor = 0.2 + random.uniform(0.1, 0.3)
                elif 22 <= hour or hour <= 5:  # 夜间
                    congestion_factor = random.uniform(0, 0.2)
                else:  # 其他时段
                    congestion_factor = 0.1 + random.uniform(0.1, 0.3)
                
                congestion_index = min(0.95, base_congestion + congestion_factor)
                
                # 确定交通状态
                if congestion_index < 0.4:
                    status = "畅通"
                elif congestion_index < 0.6:
                    status = "轻度拥堵"
                elif congestion_index < 0.8:
                    status = "中度拥堵"
                else:
                    status = "严重拥堵"
                    
                # 计算平均速度（与拥堵指数成反比）
                avg_speed = max(5, int(60 * (1 - congestion_index) + random.uniform(-5, 5)))
                
                # 生成交通流量
                traffic_flow = int(200 + 300 * congestion_index + random.uniform(-50, 50))
                
                trend_data.append({
                    'road_id': road_id,
                    'road_name': road_name,
                    'district': district,
                    'timestamp': time_point,
                    'congestion_index': congestion_index,
                    'status': status,
                    'average_speed': avg_speed,
                    'traffic_flow': traffic_flow
                })
                
            return pd.DataFrame(trend_data)
        else:
            # 从历史数据中筛选该路段的数据
            road_data = self.historical_data[self.historical_data['id'] == road_id]
            if road_data.empty:
                # 如果没有找到该路段数据，调用模拟生成
                return self.get_road_historical_trend(road_id, hours)
            
            # 按时间排序
            road_data = road_data.sort_values('timestamp')
            
            # 只保留最近几小时的数据
            now = datetime.now()
            cutoff_time = now - timedelta(hours=hours)
            recent_data = road_data[road_data['timestamp'] >= cutoff_time]
            
            if recent_data.empty:
                # 如果没有最近数据，返回全部历史数据
                return road_data
            else:
                return recent_data

    def get_similar_roads(self, road_id, limit=5):
        """获取与给定路段相似的其他路段
        
        相似性基于：
        1. 地理距离
        2. 路段类型
        3. 交通模式相似度
        """
        # 获取当前所有路段数据
        all_roads = self.get_real_time_data()
        
        if all_roads.empty:
            # 没有数据，返回空DataFrame
            return pd.DataFrame()
        
        # 查找目标路段
        target_road = all_roads[all_roads['id'] == road_id]
        if target_road.empty:
            # 如果没找到目标路段，随机返回几条路段数据
            if len(all_roads) <= limit:
                return all_roads
            else:
                return all_roads.sample(limit)
        
        # 获取目标路段信息
        target_lat = target_road.iloc[0]['latitude']
        target_lng = target_road.iloc[0]['longitude']
        target_district = target_road.iloc[0]['district']
        
        # 排除目标路段自身
        other_roads = all_roads[all_roads['id'] != road_id].copy()
        
        if other_roads.empty:
            return pd.DataFrame()
        
        # 计算地理距离
        def haversine_distance(lat1, lng1, lat2, lng2):
            """计算两点之间的距离（单位：公里）"""
            # 地球半径（公里）
            R = 6371.0
            
            # 将经纬度转换为弧度
            lat1_rad = math.radians(lat1)
            lng1_rad = math.radians(lng1)
            lat2_rad = math.radians(lat2)
            lng2_rad = math.radians(lng2)
            
            # 经纬度差值
            dlat = lat2_rad - lat1_rad
            dlng = lng2_rad - lng1_rad
            
            # Haversine公式
            a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            
            return distance
        
        # 计算每条路段与目标路段的距离
        other_roads['distance'] = other_roads.apply(
            lambda row: haversine_distance(target_lat, target_lng, row['latitude'], row['longitude']),
            axis=1
        )
        
        # 计算相似性分数
        # 1. 地理距离因素：距离越近得分越高
        max_distance = other_roads['distance'].max() or 1
        other_roads['distance_score'] = 1 - (other_roads['distance'] / max_distance)
        
        # 2. 区域因素：同一区域得分更高
        other_roads['district_score'] = other_roads['district'].apply(
            lambda d: 1.0 if d == target_district else 0.5
        )
        
        # 3. 交通状态相似度
        target_congestion = target_road.iloc[0]['congestion_index']
        max_congestion_diff = 1.0
        other_roads['congestion_diff'] = abs(other_roads['congestion_index'] - target_congestion)
        other_roads['congestion_score'] = 1 - (other_roads['congestion_diff'] / max_congestion_diff)
        
        # 计算总相似度分数
        other_roads['similarity_score'] = (
            other_roads['distance_score'] * 0.4 +
            other_roads['district_score'] * 0.3 +
            other_roads['congestion_score'] * 0.3
        )
        
        # 按相似度分数排序
        similar_roads = other_roads.sort_values('similarity_score', ascending=False).head(limit)
        
        # 移除辅助列
        columns_to_drop = ['distance', 'distance_score', 'district_score', 
                          'congestion_diff', 'congestion_score', 'similarity_score']
        
        return similar_roads.drop(columns=columns_to_drop, errors='ignore')

# 测试代码
if __name__ == "__main__":
    generator = TrafficDataGenerator(num_road_segments=10)
    
    # 获取实时数据
    real_time_data = generator.get_real_time_data()
    print("实时交通数据:")
    print(real_time_data[['road_name', 'traffic_flow', 'average_speed', 'congestion_index', 'status']].head())
    
    # 获取拥堵路段
    congested = generator.get_congested_segments(threshold=0.6)
    print("\n拥堵路段:")
    if not congested.empty:
        print(congested[['road_name', 'district', 'congestion_index', 'status']].head())
    else:
        print("当前没有拥堵路段")

# 在_get_base_congestion方法中强制设置不同值
def _get_base_congestion(self, road_type):
    # 测试用强制返回值
    if "主干道" in road_type: 
        return 0.75  # 红色
    elif "次干道" in road_type:
        return 0.55  # 橙色
    else:
        return 0.35  # 绿色

# 在DataGenerator类中添加
def refresh_data(self):
    """强制生成新数据集"""
    self.current_data = self._generate_new_data()
    self.last_update = time.time()
    return self.current_data