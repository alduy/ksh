"""
交通数据处理工具
用于处理交通数据并为可视化和分析做准备
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import random

class TrafficDataProcessor:
    """交通数据处理类"""
    
    def __init__(self):
        """初始化数据处理器"""
        pass
    
    def prepare_map_data(self, df):
        """准备地图数据，确保所有值都是JSON可序列化的"""
        try:
            if df.empty:
                return self.safe_json_dumps([])
            
            # 选择需要的列，避免不必要的数据传输
            columns = ['road_id', 'road_name', 'longitude', 'latitude', 'congestion_index', 'status']
            available_columns = [col for col in columns if col in df.columns]
            
            # 如果缺少关键列，则尝试找替代
            if 'road_id' not in available_columns and 'segment_id' in df.columns:
                df['road_id'] = df['segment_id']
                available_columns.append('road_id')
            
            if 'longitude' not in available_columns and 'lng' in df.columns:
                df['longitude'] = df['lng']
                available_columns.append('longitude')
            
            if 'latitude' not in available_columns and 'lat' in df.columns:
                df['latitude'] = df['lat']
                available_columns.append('latitude')
            
            # 选择可用列
            map_data = df[available_columns].copy()
            
            # 确保数据类型正确
            for col in map_data.columns:
                if col in ['longitude', 'latitude', 'congestion_index']:
                    # 转换为float
                    map_data[col] = pd.to_numeric(map_data[col], errors='coerce')
                    # 替换NaN值
                    if col == 'congestion_index':
                        map_data[col].fillna(1.0, inplace=True)
                    else:
                        # 经纬度的NaN值会在前端被过滤
                        pass
            
            # 转换为记录列表，确保所有值都是JSON可序列化的
            records = []
            for _, row in map_data.iterrows():
                record = {}
                for col, value in row.items():
                    # 处理 pandas Timestamp 对象
                    if pd.api.types.is_datetime64_any_dtype(type(value)):
                        record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                    # 处理 numpy 类型
                    elif isinstance(value, (np.integer, np.floating)):
                        record[col] = float(value) if isinstance(value, np.floating) else int(value)
                    # 处理 NaN 值
                    elif pd.isna(value):
                        if col in ['longitude', 'latitude']:
                            # 对于经纬度，使用None以便前端过滤
                            record[col] = None
                        elif col == 'congestion_index':
                            # 对于拥堵指数，使用默认值
                            record[col] = 1.0
                        else:
                            record[col] = None
                    else:
                        record[col] = value
                records.append(record)
            
            return self.safe_json_dumps(records)
        except Exception as e:
            print(f"准备地图数据时出错: {e}")
            # 返回一个空列表作为后备
            return self.safe_json_dumps([])

    def prepare_congestion_list(self, df):
        """准备拥堵路段列表"""
        try:
            # 如果DataFrame为空，返回空列表
            if df.empty:
                print("警告: 路段数据为空")
                return self.safe_json_dumps([])
                
            # 确保段ID字段一致性
            if 'segment_id' in df.columns and 'road_id' not in df.columns:
                df['road_id'] = df['segment_id']
            elif 'road_id' in df.columns and 'segment_id' not in df.columns:
                df['segment_id'] = df['road_id']
                
            # 按拥堵指数降序排序
            sorted_df = df.sort_values('congestion_index', ascending=False)
            
            # 确保返回必要的字段，且包含完整信息
            required_columns = [
                'segment_id', 'road_id', 'road_name', 'congestion_index', 
                'status', 'district', 'average_speed', 'latitude', 'longitude'
            ]
            
            # 选取可用列
            available_columns = [col for col in required_columns if col in df.columns]
            
            # 如果某些字段不存在，记录警告但不中断处理
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                print(f"警告: 路段数据缺少以下字段: {', '.join(missing_columns)}")
            
            # 转换为字典列表
            roads_list = sorted_df[available_columns].to_dict(orient='records')
            
            # 确保每条记录都有必要的ID字段
            for i, road in enumerate(roads_list):
                # 确保路段有segment_id字段
                if 'segment_id' not in road:
                    road['segment_id'] = road.get('road_id', f"segment_{i}")
                    
                # 确保路段有road_id字段 (与前端代码对应)
                if 'road_id' not in road:
                    road['road_id'] = road.get('segment_id', f"road_{i}")
                
                # 确保前端使用的id字段存在
                if 'id' not in road:
                    road['id'] = road.get('road_id', road.get('segment_id', f"road_{i}"))
                
                # 确保其他必要字段都有值
                road['road_name'] = road.get('road_name', f"未命名路段_{i}")
                road['district'] = road.get('district', '未知区域')
                road['congestion_index'] = float(road.get('congestion_index', 0))
                road['average_speed'] = float(road.get('average_speed', 30))
                
                # 如果status不存在，则根据拥堵指数设置
                if 'status' not in road:
                    congestion = road['congestion_index']
                    if congestion >= 0.7:
                        road['status'] = '严重拥堵'
                    elif congestion >= 0.4:
                        road['status'] = '中度拥堵'
                    else:
                        road['status'] = '畅通'
            
            # 打印调试信息
            print(f"准备了 {len(roads_list)} 条路段数据，样例: {roads_list[0] if roads_list else 'None'}")
            
            # 确保所有数值都是JSON可序列化的
            return self.safe_json_dumps(roads_list, ensure_ascii=False)
            
        except Exception as e:
            print(f"准备拥堵路段列表时出错: {e}")
            # 出错时返回一个空数组
            return self.safe_json_dumps([], ensure_ascii=False)

    def prepare_alert_data(self, df):
        """准备警报数据"""
        alerts = df[df['congestion_index'] >= 0.7]
        return self.safe_json_dumps(alerts[['road_name', 'congestion_index']].to_dict(orient='records'))

    def prepare_statistics(self, df):
        """生成基础统计数据"""
        # 添加字段存在性检查
        required_columns = ['congestion_index', 'average_speed', 'status']
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"缺失必要数据列: {', '.join(missing)}")

        # 计算各状态数量
        status_counts = df['status'].value_counts()
        
        stats = {
            'avg_congestion': round(float(df['congestion_index'].mean()), 4),
            'avg_speed': round(float(df['average_speed'].mean()), 2),
            'total_roads': len(df),
            'free_count': int(status_counts.get('畅通', 0)),
            'moderate_count': int(status_counts.get('中度拥堵', 0)),
            'severe_count': int(status_counts.get('严重拥堵', 0)),
            'district_stats': {
                'detailed': df.groupby('district').apply(
                    lambda x: {
                        'road_count': len(x),
                        'avg_congestion': round(x['congestion_index'].mean(), 4),
                        'avg_speed': round(x['average_speed'].mean(), 2),
                        'status_distribution': x['status'].value_counts().to_dict()
                    }
                ).to_dict()
            }
        }
        return self.safe_json_dumps(stats, ensure_ascii=False)

    def get_trend_data(self):
        """生成24小时趋势数据（模拟数据）"""
        return [{
            'time': (datetime.now() - timedelta(hours=24-i)).strftime("%H:%M"),
            'value': round(0.3 + random.uniform(-0.1, 0.2), 2)
        } for i in range(24)]

    def get_district_stats(self):
        """生成区域统计模拟数据"""
        districts = ["云岩区", "南明区", "花溪区", "乌当区", "白云区", "观山湖区"]
        return [{'name': d, 'value': round(0.2 + i*0.1, 2)} for i, d in enumerate(districts)]
    
    # 添加区域分析方法
    def prepare_district_analysis(self, df, district_name):
        """准备区域分析数据"""
        try:
            # 过滤出特定区域的数据
            if df.empty:
                # 如果数据为空，返回空结果
                print(f"警告: 区域 {district_name} 的数据为空")
                return self.safe_json_dumps({
                    "district": district_name,
                    "stats": {},
                    "roads": [],
                    "prediction": {}
                }, ensure_ascii=False)
            
            district_data = df[df['district'] == district_name] if 'district' in df.columns else df
            
            if district_data.empty:
                # 如果该区域没有数据，返回空结果
                print(f"警告: 找不到区域 {district_name} 的数据")
                return self.safe_json_dumps({
                    "district": district_name,
                    "stats": {},
                    "roads": [],
                    "prediction": {}
                }, ensure_ascii=False)
            
            # 计算基本统计信息
            avg_congestion = round(float(district_data['congestion_index'].mean()), 4)
            avg_speed = round(float(district_data['average_speed'].mean() if 'average_speed' in district_data.columns else 0), 2)
            
            # 路段状态统计
            status_counts = district_data['status'].value_counts().to_dict() if 'status' in district_data.columns else {}
            
            # 准备道路数据
            roads = district_data.sort_values('congestion_index', ascending=False)
            road_list = []
            
            for _, road in roads.iterrows():
                road_data = {}
                for col, val in road.items():
                    # 转换特殊类型为JSON可序列化类型
                    if pd.api.types.is_datetime64_any_dtype(type(val)):
                        road_data[col] = val.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(val, (np.integer, np.floating)):
                        road_data[col] = float(val) if isinstance(val, np.floating) else int(val)
                    elif pd.isna(val):
                        road_data[col] = None
                    else:
                        road_data[col] = val
                road_list.append(road_data)
            
            # 生成分析结果
            analysis = {
                "district": district_name,
                "stats": {
                    "avg_congestion": avg_congestion,
                    "avg_speed": avg_speed,
                    "total_roads": len(district_data),
                    "status_distribution": status_counts
                },
                "roads": road_list[:20],  # 限制返回路段数量
                "prediction": {}  # 预测数据会由其他API填充
            }
            
            return self.safe_json_dumps(analysis, ensure_ascii=False)
            
        except Exception as e:
            print(f"准备区域分析数据时出错: {e}")
            # 返回一个基本结构作为后备
            return self.safe_json_dumps({
                "district": district_name,
                "stats": {},
                "roads": [],
                "prediction": {},
                "error": str(e)
            }, ensure_ascii=False)

    def prepare_trend_data(self, historical_data):
        """准备趋势数据以供图表显示"""
        if historical_data.empty:
            # 如果没有历史数据，返回一些模拟数据
            time_points = [(datetime.now() - timedelta(hours=i)).strftime('%H:%M') for i in range(24, -1, -1)]
            return self.safe_json_dumps({
                "times": time_points,
                "congestion_indices": [random.uniform(1.0, 2.0) for _ in range(25)],
            })
        
        # 确保时间列是datetime类型
        if 'timestamp' in historical_data.columns:
            time_col = 'timestamp'
        elif 'time' in historical_data.columns:
            time_col = 'time'
        else:
            # 如果没有时间列，创建一个时间序列
            historical_data['timestamp'] = pd.date_range(
                end=datetime.now(), 
                periods=len(historical_data), 
                freq='H'
            )
            time_col = 'timestamp'
        
        # 确保时间列为datetime类型
        if not pd.api.types.is_datetime64_any_dtype(historical_data[time_col]):
            try:
                historical_data[time_col] = pd.to_datetime(historical_data[time_col])
            except:
                # 如果转换失败，创建一个新的时间列
                historical_data['timestamp'] = pd.date_range(
                    end=datetime.now(), 
                    periods=len(historical_data), 
                    freq='H'
                )
                time_col = 'timestamp'
        
        # 如果有多个记录，按时间排序并选择最近24小时
        historical_data = historical_data.sort_values(by=time_col)
        if len(historical_data) > 24:
            historical_data = historical_data.iloc[-24:]
        
        # 提取时间和拥堵指数
        times = [t.strftime('%H:%M') for t in historical_data[time_col]]
        
        # 确保 congestion_index 列存在
        if 'congestion_index' not in historical_data.columns and 'congestion' in historical_data.columns:
            historical_data['congestion_index'] = historical_data['congestion']
        elif 'congestion_index' not in historical_data.columns:
            # 创建一个随机的拥堵指数
            historical_data['congestion_index'] = [random.uniform(1.0, 2.0) for _ in range(len(historical_data))]
        
        congestion_indices = historical_data['congestion_index'].tolist()
        
        # 确保所有值都是可序列化的
        congestion_indices = [float(c) if not pd.isna(c) else 1.0 for c in congestion_indices]
        
        return self.safe_json_dumps({
            "times": times,
            "congestion_indices": congestion_indices,
        })

    def safe_json_dumps(self, data, ensure_ascii=True, **kwargs):
        """安全的JSON序列化方法，处理pandas和numpy类型"""
        try:
            # 尝试直接序列化
            return json.dumps(data, ensure_ascii=ensure_ascii, cls=self.CustomJSONEncoder, **kwargs)
        except (TypeError, OverflowError) as e:
            # 如果失败，尝试将数据转换为普通Python类型
            print(f"JSON序列化警告: {e}")
            
            if isinstance(data, dict):
                cleaned_data = {}
                for k, v in data.items():
                    cleaned_data[k] = self._convert_to_serializable(v)
                return json.dumps(cleaned_data, ensure_ascii=ensure_ascii, **kwargs)
            
            elif isinstance(data, list):
                cleaned_data = [self._convert_to_serializable(item) for item in data]
                return json.dumps(cleaned_data, ensure_ascii=ensure_ascii, **kwargs)
            
            else:
                # 单个值
                return json.dumps(self._convert_to_serializable(data), ensure_ascii=ensure_ascii, **kwargs)
    
    def _convert_to_serializable(self, obj):
        """将对象转换为JSON可序列化类型"""
        if isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list) or isinstance(obj, tuple):
            return [self._convert_to_serializable(item) for item in obj]
        elif pd.api.types.is_datetime64_any_dtype(type(obj)) or isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return self._convert_to_serializable(obj.tolist())
        elif pd.isna(obj):
            return None
        else:
            return obj
            
    class CustomJSONEncoder(json.JSONEncoder):
        """自定义JSON编码器，处理特殊类型"""
        def default(self, obj):
            # 处理 pandas Timestamp
            if pd.api.types.is_datetime64_any_dtype(type(obj)):
                return obj.strftime('%Y-%m-%d %H:%M:%S')
            # 处理 Python datetime
            elif isinstance(obj, datetime):
                return obj.strftime('%Y-%m-%d %H:%M:%S')
            # 处理 numpy int
            elif isinstance(obj, (np.integer, np.int64)):
                return int(obj)
            # 处理 numpy float
            elif isinstance(obj, (np.floating, np.float64)):
                return float(obj)
            # 处理 numpy array
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            # 处理 pandas NaT, None 等
            elif pd.isna(obj):
                return None
            # 默认行为
            return super().default(obj)