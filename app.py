"""
贵阳市交通拥堵监测系统 - 主应用
"""
# 确保在文件顶部正确导入

import os
import json
import time
from datetime import datetime, timedelta
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # Add this import
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import pandas as pd
import numpy as np

# 导入自定义模块
from utils.data_generator import TrafficDataGenerator
from utils.data_processor import TrafficDataProcessor
from models.predictor import TrafficPredictor
import config

# 创建Flask应用
# 在文件顶部添加（约第21行）
def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    
    # 初始化组件
    with app.app_context():
        global data_generator, data_processor, predictor
        data_generator = TrafficDataGenerator(num_road_segments=config.NUM_ROAD_SEGMENTS)
        data_processor = TrafficDataProcessor()
        predictor = TrafficPredictor()
    
    return app

# 替换原有app初始化（约第26行）
app = create_app()
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['DEBUG'] = config.DEBUG

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# 初始化数据生成器和处理器
data_generator = TrafficDataGenerator(num_road_segments=config.NUM_ROAD_SEGMENTS)
data_processor = TrafficDataProcessor()

# 初始化预测器（如果有保存的模型就加载，否则后续会使用新数据训练）
predictor = TrafficPredictor()
if not predictor.is_trained:
    try:
        # 使用历史数据训练模型
        historical_data = data_generator.historical_data
        if not historical_data.empty:
            predictor.train(historical_data)
            print("模型训练完成")
        else:
            print("没有足够的历史数据用于训练模型")
    except Exception as e:
        print(f"模型训练失败: {e}")

# 全局数据存储
current_traffic_data = pd.DataFrame()
last_update_time = datetime.now()

# 添加线程锁（约第50行）
import threading
data_lock = threading.Lock()

# 添加全局错误处理 - 移到全局作用域
@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_message="服务器内部错误", error_detail=str(e)), 500

@app.route('/')
def dashboard():
    """实时监控仪表板页面"""
    # 获取当前实时数据
    global current_traffic_data
    if current_traffic_data.empty:
        current_traffic_data = data_generator.get_real_time_data()
        print(f"初始化数据: 获取了 {len(current_traffic_data)} 条路段数据")
    
    # 准备地图数据
    map_data = data_processor.prepare_map_data(current_traffic_data)
    # 检查是否为空或有效的JSON
    try:
        map_data_json = json.loads(map_data)
        road_count = 0
        if isinstance(map_data_json, list):
            road_count = len(map_data_json)
        elif isinstance(map_data_json, dict) and 'features' in map_data_json:
            road_count = len(map_data_json['features'])
        print(f"地图数据准备完成: {road_count} 条路段")
    except Exception as e:
        print(f"地图数据解析错误: {str(e)}")
        map_data = '[]'  # 默认空数组
    
    # 准备拥堵路段列表
    # 确保congestion_list包含完整的road对象
    congestion_list = data_processor.prepare_congestion_list(current_traffic_data)
    
    # 准备警报数据
    try:
        alerts = json.loads(data_processor.prepare_alert_data(current_traffic_data))
    except Exception as e:
        print(f"警报数据准备失败: {str(e)}")
        alerts = []
    
    # 准备趋势数据 - 确保变量已初始化
    try:
        trend_data = data_processor.prepare_trend_data([])  # 初始化为空列表
    except Exception as e:
        print(f"趋势数据准备失败: {str(e)}")
        trend_data = json.dumps({'labels': [], 'datasets': []})
    
    # 准备统计数据 - 确保变量已初始化
    try:
        stats_json = data_processor.prepare_statistics(current_traffic_data)
        stats = json.loads(stats_json)
        print(f"统计数据: 路段数={len(current_traffic_data)}, 拥堵指数={stats.get('avg_congestion', 0)}, 车速={stats.get('avg_speed', 0)}")
    except Exception as e:
        print(f"统计数据准备失败: {str(e)}")
        stats = {'avg_congestion': 0, 'avg_speed': 0}

    return render_template('dashboard.html',
                        active_page='dashboard',
                        map_data=map_data,  # 直接传递原始JSON字符串
                        congested_roads=congestion_list,
                        alerts=alerts if alerts else [],  # 确保传递空列表而不是None
                        trend_data=trend_data,  # 已确保初始化
                        current_time=last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                        avg_congestion=round(stats.get('avg_congestion', 0), 2),
                        avg_speed=round(stats.get('avg_speed', 0), 1),
                        road_count=len(current_traffic_data),
                        heavy_congestion_count=len(alerts),
                        center_lat=config.GUIYANG_CENTER[0],
                        center_lng=config.GUIYANG_CENTER[1],
                        zoom=config.DEFAULT_ZOOM,
                        config=config)  # 传递配置到模板

@app.route('/analysis')
def analysis():
    """数据分析页面"""
    return render_template('analysis.html', active_page='analysis')

@app.route('/district_analysis')
def district_analysis():
    """区域拥堵分析页面"""
    global current_traffic_data
    
    # 如果没有数据，生成一些数据
    if current_traffic_data.empty:
        with data_lock:
            current_traffic_data = data_generator.get_real_time_data()
    
    # 获取所有区域的概览数据
    stats_json = data_processor.prepare_statistics(current_traffic_data)
    stats = json.loads(stats_json)
    
    # 获取每个区域的交通情况
    district_overviews = []
    
    # 确保district_stats存在且有detailed子属性
    if 'district_stats' in stats and 'detailed' in stats['district_stats']:
        for district, data in stats['district_stats']['detailed'].items():
            # 计算状态比例
            total_roads = data['road_count']
            status_percent = {}
            for status, count in data['status_distribution'].items():
                status_percent[status] = round(count / max(1, total_roads) * 100, 1)
            
            district_overviews.append({
                'name': district,
                'avg_congestion': data['avg_congestion'],
                'avg_speed': data['avg_speed'],
                'road_count': data['road_count'],
                'severe_count': data['severe_count'],
                'moderate_count': data['moderate_count'],
                'free_count': data['free_count'],
                'status_percent': status_percent
            })
    
    # 按拥堵程度排序
    district_overviews.sort(key=lambda x: x['avg_congestion'], reverse=True)
    
    # 获取拥堵预测数据
    future_predictions = []
    if predictor.is_trained and not current_traffic_data.empty:
        try:
            # 添加缺失的预测数据生成
            prediction_df = predictor.predict_future(current_traffic_data, hours_ahead=3)
            
            # 修复缩进问题（原123行附近）
            grouped = prediction_df.groupby(pd.Grouper(key='timestamp', freq='H'))
            
            for group_time, group_data in grouped:  # 确保正确缩进
                hour_data = {
                    'timestamp': group_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'avg_congestion': group_data['congestion_index'].mean(),
                    'congested_count': group_data.loc[group_data['congestion_index'] >= 0.6].shape[0],
                    'status_counts': group_data['status'].value_counts(dropna=False).to_dict()
                }
                future_predictions.append(hour_data)
                
        except Exception as e:
            print(f"预测数据生成失败: {e}")
    
    return render_template(
        'district_analysis.html',
        active_page='district_analysis',
        districts=district_overviews,
        predictions=future_predictions,
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/district/<district_name>')
def district_detail(district_name):
    """显示特定区域的详细信息页面"""
    global current_traffic_data
    
    # 如果没有数据，生成一些数据
    if current_traffic_data.empty:
        with data_lock:
            current_traffic_data = data_generator.get_real_time_data()
    
    # 获取特定区域的详细分析
    district_analysis_json = data_processor.prepare_district_analysis(current_traffic_data, district_name)
    district_data = json.loads(district_analysis_json)
    
    # 准备地图数据
    # 筛选此区域的交通数据
    district_traffic = current_traffic_data[current_traffic_data['district'] == district_name]
    map_data_json = data_processor.prepare_map_data(district_traffic)
    
    # 将地图数据添加到 district_data 字典中（先解析为Python对象）
    district_data['map_data'] = json.loads(map_data_json)
    
    # 添加地图中心点和缩放级别
    district_data['center_lat'] = district_traffic['latitude'].mean() if not district_traffic.empty else 26.598194
    district_data['center_lng'] = district_traffic['longitude'].mean() if not district_traffic.empty else 106.707410
    district_data['zoom_level'] = 13
    
    return render_template(
        'district_detail.html',
        active_page='district_analysis',
        district=district_data,
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/api/district/<district_name>')
def api_district_data(district_name):
    """获取特定区域的交通数据API"""
    try:
        # 获取实时交通数据
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，则生成新数据
        if current_data.empty:
            data_generator.generate_data()
            current_data = data_generator.get_real_time_data()
        
        # 根据区域名称筛选数据并生成区域分析数据
        district_data = data_processor.prepare_district_analysis(current_data, district_name)
        
        return district_data
    except Exception as e:
        print(f"获取区域数据出错: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/district/<district_name>/prediction')
def api_district_prediction(district_name):
    """获取特定区域的拥堵预测数据API"""
    try:
        # 获取实时交通数据
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，则生成新数据
        if current_data.empty:
            data_generator.generate_data()
            current_data = data_generator.get_real_time_data()
        
        # 根据区域名称筛选数据
        district_data = current_data[current_data['district'] == district_name] if district_name != '全市' else current_data
        
        if district_data.empty:
            return jsonify({
                "error": f"未找到区域 '{district_name}' 的数据",
                "time_points": [],
                "predictions": [],
                "current_status": {
                    "status": "数据缺失",
                    "color": "#6c757d",
                    "description": "暂无该区域数据，请选择其他区域"
                },
                "advice": {
                    "best_time": "暂无数据",
                    "worst_roads": [],
                    "alternative_routes": [],
                    "special_notice": "无法获取该区域数据，建议选择其他区域查看"
                }
            }), 404
        
        # 获取当前时间，并计算未来3小时的时间点
        now = datetime.now()
        time_points = []
        predictions = []
        
        # 计算当前平均拥堵指数作为基准
        current_avg_congestion = district_data['congestion_index'].mean()
        time_points.append(now.strftime('%H:%M'))
        predictions.append(float(current_avg_congestion))
        
        # 使用预测模型预测未来几个小时的拥堵情况
        try:
            # 准备预测需要的数据
            prediction_features = []
            for i in range(1, 5):  # 预测未来4个小时
                future_time = now + timedelta(hours=i)
                prediction_features.append({
                    'hour': future_time.hour,
                    'day_of_week': future_time.weekday(),
                    'district': district_name,
                    'current_congestion': current_avg_congestion
                })
            
            # 通过预测模型获取未来拥堵指数
            for i, feature in enumerate(prediction_features):
                future_time = now + timedelta(hours=i+1)
                
                # 应用不同的预测逻辑，根据时间段调整权重
                hour = feature['hour']
                day_of_week = feature['day_of_week']
                
                # 基本预测值
                base_prediction = current_avg_congestion
                
                # 早高峰 (7-9点)
                if 7 <= hour <= 9 and day_of_week < 5:  # 工作日
                    if current_avg_congestion < 0.6:  # 当前不太拥堵
                        prediction = min(0.95, base_prediction + 0.15 + (i * 0.05))
                    else:  # 当前已拥堵
                        prediction = min(0.95, base_prediction + 0.05)
                # 晚高峰 (17-19点)
                elif 17 <= hour <= 19 and day_of_week < 5:  # 工作日
                    if current_avg_congestion < 0.6:  # 当前不太拥堵
                        prediction = min(0.95, base_prediction + 0.2 + (i * 0.05))
                    else:  # 当前已拥堵
                        prediction = min(0.95, base_prediction + 0.1)
                # 中午 (11-14点)
                elif 11 <= hour <= 14:
                    if current_avg_congestion > 0.5:  # 当前拥堵
                        prediction = max(0.2, base_prediction - 0.1 * (i+1))
                    else:
                        prediction = base_prediction + 0.05
                # 夜间 (20-6点)
                elif hour >= 20 or hour <= 6:
                    prediction = max(0.1, base_prediction - 0.15 * (i+1))
                # 其他时段
                else:
                    if current_avg_congestion > 0.7:  # 当前严重拥堵
                        prediction = max(0.3, base_prediction - 0.1 * (i+1))
                    elif current_avg_congestion < 0.3:  # 当前畅通
                        prediction = min(0.5, base_prediction + 0.05 * (i+1))
                    else:
                        prediction = base_prediction + (0.05 * (i % 2) - 0.025)
                
                # 添加少量随机波动
                prediction = max(0.1, min(0.95, prediction + (np.random.random() * 0.1 - 0.05)))
                time_points.append(future_time.strftime('%H:%M'))
                predictions.append(float(prediction))
        
        except Exception as e:
            print(f"预测计算错误: {e}")
            # 如果预测失败，生成模拟数据
            for i in range(1, 5):
                future_time = now + timedelta(hours=i)
                # 根据当前拥堵程度和时间生成随机预测
                if now.hour < 9 or now.hour > 18:
                    prediction = max(0.1, current_avg_congestion - 0.05 * i)
                else:
                    prediction = min(0.95, current_avg_congestion + 0.05 * i)
                time_points.append(future_time.strftime('%H:%M'))
                predictions.append(float(prediction))
        
        # 准备出行建议
        advice = generate_travel_advice(district_name, current_avg_congestion, predictions, district_data)
        
        # 确保所有数据类型正确
        result = {
            "district_name": district_name,
            "time_points": time_points,
            "predictions": [float(p) for p in predictions],  # 确保所有值都是浮点数
            "current_status": get_congestion_status(current_avg_congestion),
            "advice": advice
        }
        
        # 打印返回数据，便于调试
        print(f"向前端返回的预测数据: {result}")
        
        return jsonify(result)
    
    except Exception as e:
        print(f"获取区域预测出错: {e}")
        # 返回错误时也提供空的数据结构，确保前端不会崩溃
        return jsonify({
            "error": str(e),
            "time_points": [],
            "predictions": [],
            "current_status": {
                "status": "数据错误",
                "color": "#dc3545",
                "description": "获取数据时发生错误"
            },
            "advice": {
                "best_time": "暂无数据",
                "worst_roads": [],
                "alternative_routes": [],
                "special_notice": "系统遇到错误，请稍后再试"
            }
        }), 500

def get_congestion_status(congestion_value):
    """根据拥堵指数获取状态描述"""
    if congestion_value >= 0.7:
        return {
            "status": "严重拥堵",
            "color": "#dc3545",
            "description": "该区域当前交通状况非常拥堵，建议避开"
        }
    elif congestion_value >= 0.4:
        return {
            "status": "中度拥堵",
            "color": "#ffc107",
            "description": "该区域当前交通状况较为拥堵，谨慎前往"
        }
    else:
        return {
            "status": "交通畅通",
            "color": "#28a745",
            "description": "该区域当前交通状况良好，可以正常出行"
        }

def generate_travel_advice(district_name, current_congestion, predictions, district_data):
    """根据预测结果生成出行建议"""
    now = datetime.now()
    hour = now.hour
    
    # 确定最佳出行时间
    if hour < 7 or hour > 19:
        best_time = "今日 10:00 - 16:00"
    elif hour >= 7 and hour < 10:
        best_time = "今日 14:00 - 16:00"
    elif hour >= 16 and hour < 19:
        best_time = "今日 20:00 后或明日 10:00 - 16:00"
    else:
        best_time = "当前时段或今日 10:00 - 16:00"
    
    # 获取最拥堵的道路
    worst_roads = []
    if not district_data.empty:
        top_congested = district_data.sort_values('congestion_index', ascending=False).head(3)
        for _, road in top_congested.iterrows():
            worst_roads.append({
                "road_name": road['road_name'],
                "congestion_index": float(road['congestion_index']),
                "status": road['status']
            })
    
    # 生成替代路线建议
    alternative_routes = []
    if district_name == "云岩区":
        alternative_routes.append({"from": "林城西路", "to": "省府路"})
        alternative_routes.append({"from": "中华北路", "to": "太平路"})
    elif district_name == "南明区":
        alternative_routes.append({"from": "解放路", "to": "太慈路"})
        alternative_routes.append({"from": "沙冲路", "to": "市南路"})
    elif district_name == "观山湖区":
        alternative_routes.append({"from": "金朱路", "to": "长岭北路"})
        alternative_routes.append({"from": "观山东路", "to": "石林东路"})
    else:
        alternative_routes.append({"from": "环城高速", "to": "市区道路"})
    
    # 生成特别提醒
    special_notice = ""
    if hour < 7:
        special_notice = f"今日7:00-9:00为早高峰，该区域拥堵指数预计将达到{predictions[1]:.2f}，建议错峰出行。"
    elif hour >= 7 and hour < 10:
        special_notice = "当前处于早高峰时段，拥堵指数较高，建议选择公共交通工具出行。"
    elif hour >= 10 and hour < 16:
        special_notice = f"今日17:00-19:00为晚高峰，该区域拥堵指数预计将升高至{predictions[2]:.2f}，建议提前安排行程。"
    elif hour >= 16 and hour < 20:
        special_notice = "当前处于晚高峰时段，拥堵指数较高，建议选择公共交通工具出行。"
    else:
        special_notice = f"明日7:00-9:00为早高峰，该区域拥堵指数预计将达到0.80，建议早做准备。"
    
    # 根据天气添加相关建议（实际应用中应从API获取天气数据）
    if np.random.random() > 0.5:
        special_notice += " 此外，近期预计有雨，降雨天气可能会加剧道路拥堵情况，请提前规划行程。"
    
    return {
        "best_time": best_time,
        "worst_roads": worst_roads,
        "alternative_routes": alternative_routes,
        "special_notice": special_notice
    }

@app.route('/prediction')
def prediction():
    """拥堵预测页面"""
    global current_traffic_data
    future_predictions = []
    
    if predictor.is_trained and not current_traffic_data.empty:
        try:
            # 添加缺失的预测数据生成
            prediction_df = predictor.predict_future(current_traffic_data, hours_ahead=3)
            
            # 修复缩进问题（原123行附近）
            grouped = prediction_df.groupby(pd.Grouper(key='timestamp', freq='H'))
            
            for group_time, group_data in grouped:  # 确保正确缩进
                hour_data = {
                    'timestamp': group_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'avg_congestion': group_data['congestion_index'].mean(),
                    'congested_count': group_data.loc[group_data['congestion_index'] >= 0.6].shape[0],
                    'status_counts': group_data['status'].value_counts(dropna=False).to_dict()
                }
                future_predictions.append(hour_data)
                
        except Exception as e:
            print(f"预测数据生成失败: {e}")

    # 添加返回语句
    return render_template('prediction.html', 
                        active_page='prediction',
                        predictions=future_predictions)

# 修改数据更新逻辑
def update_traffic_data():
    """正确的后台数据更新函数"""
    global current_traffic_data, last_update_time
    
    while True:
        try:
            # 获取实时数据
            with data_lock:
                df = data_generator.get_real_time_data()
                if not df.empty:
                    # 更新历史数据
                    data_generator.historical_data = pd.concat(
                        [data_generator.historical_data, df], 
                        ignore_index=True
                    )
                    current_traffic_data = df
                    last_update_time = datetime.now()
                    
                    # 准备前端所需的各种数据
                    try:
                        update_data = {
                            'timestamp': last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'map_data': json.loads(data_processor.prepare_map_data(current_traffic_data)),
                            'congestion_list': json.loads(data_processor.prepare_congestion_list(current_traffic_data)),
                            'alerts': json.loads(data_processor.prepare_alert_data(current_traffic_data)),
                            'stats': json.loads(data_processor.prepare_statistics(current_traffic_data))
                        }
                        
                        socketio.emit('traffic_update', update_data)
                        print(f"数据已更新: {last_update_time}")
                    except Exception as e:
                        print(f"数据处理或发送错误: {e}")
        except Exception as e:
            print(f"数据更新主循环错误: {e}")
        
        # 使用time.sleep而不是socketio.sleep，因为这个函数在单独的线程中运行
        time.sleep(config.SIMULATION_INTERVAL)

@app.route('/about')
def about():
    """关于系统页面"""
    return render_template('about.html', active_page='about')

# 新增后台更新线程
# 修复 background_thread 函数缩进
def background_thread():
    """SocketIO专用的后台线程，用于轻量级的实时数据推送"""
    while True:
        try:
            # 获取当前数据
            with data_lock:
                if not current_traffic_data.empty:
                    # 准备数据并检查格式
                    try:
                        map_data = data_processor.prepare_map_data(current_traffic_data)
                        map_data_json = json.loads(map_data)
                        
                        congestion_list = data_processor.prepare_congestion_list(current_traffic_data)
                        congestion_list_json = json.loads(congestion_list)
                        
                        alert_data = data_processor.prepare_alert_data(current_traffic_data)
                        alerts_json = json.loads(alert_data)
                        
                        stats_json = json.loads(data_processor.prepare_statistics(current_traffic_data))
                        
                        # 数据检查和调试输出
                        road_count = 0
                        if isinstance(map_data_json, list):
                            road_count = len(map_data_json)
                        elif isinstance(map_data_json, dict) and 'features' in map_data_json:
                            road_count = len(map_data_json['features'])
                        
                        print(f"WebSocket更新: 发送 {road_count} 条路段数据, " +
                              f"{len(congestion_list_json)} 条拥堵路段, " +
                              f"{len(alerts_json)} 条警报")
                        
                        # 发送更新
                        update_data = {
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'map_data': map_data_json,  # 发送解析后的JSON对象
                            'congestion_list': congestion_list_json,
                            'alerts': alerts_json,
                            'stats': stats_json
                        }
                        socketio.emit('traffic_update', update_data)
                        print(f"SocketIO实时更新已发送: {datetime.now()}")
                    except Exception as e:
                        print(f"准备WebSocket数据时发生错误: {str(e)}")
        except Exception as e:
            print(f"SocketIO后台线程错误: {e}")
            
        # 使用socketio.sleep而不是time.sleep，因为这是socketio的后台任务
        socketio.sleep(30)  # 每30秒推送一次轻量级更新

# 修复 handle_connect 函数缩进
@socketio.on('connect')
def handle_connect():
    socketio.start_background_task(background_thread)
    print('客户端已连接')

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    print('客户端已断开连接')

@socketio.on('get_trend_data')
def handle_get_trend_data():
    """发送历史趋势数据"""
    historical_trend = data_generator.get_historical_trend()
    trend_data = json.loads(data_processor.prepare_trend_data(historical_trend))
    socketio.emit('trend_data', trend_data)

def create_scheduler():
    # 检查变量定义是否完整
    jobstores = {
        'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
    }
    executors = {
        'default': {'type': 'threadpool', 'max_workers': 3}
    }
    
    # 检查参数是否正确
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        timezone='Asia/Shanghai'
    )
    
    try:
        scheduler.add_job(
            func=lambda: socketio.emit('auto_update', {'time': datetime.now().strftime("%H:%M:%S")}),
            trigger='interval',
            seconds=60,
            id='auto_update_job'
        )
        scheduler.start()
    except Exception as e:
        print(f"调度器启动失败: {e}")
    
    return scheduler

# 初始化调度器
scheduler = create_scheduler()

# 添加关闭钩子
@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    if scheduler.running:
        scheduler.shutdown(wait=False)

@app.route('/road/<int:road_id>')
def road_detail(road_id):
    """显示特定路段的详细信息页面"""
    try:
        # 获取当前交通数据
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，使用数据生成器获取一些数据
        if current_data.empty:
            data_lock.acquire()
            try:
                data_generator.refresh_data()
                current_data = data_generator.get_real_time_data()
            finally:
                data_lock.release()
        
        # 查找特定的路段数据
        road_data = current_data[current_data['segment_id'] == road_id]
        
        # 如果找不到指定的路段，创建一个模拟路段数据
        if road_data.empty:
            app.logger.warning(f"路段ID {road_id} 未找到，使用模拟数据")
            # 创建一个模拟数据
            road_data = pd.DataFrame([{
                'segment_id': road_id,
                'road_id': road_id,
                'road_name': f"路段 #{road_id}",
                'district': "未知区域",
                'timestamp': datetime.now(),
                'congestion_index': 0.3,
                'status': "畅通",
                'average_speed': 40,
                'traffic_flow': 200,
                'latitude': 26.598194,
                'longitude': 106.707410
            }])
        
        # 转换为字典以便在模板中使用
        road = road_data.iloc[0].to_dict()
        
        # 确保road_id键存在（防止命名不一致）
        if 'road_id' not in road and 'segment_id' in road:
            road['road_id'] = road['segment_id']
        
        # 获取历史趋势数据
        try:
            trend_data = data_generator.get_road_historical_trend(road_id)
            # 转换为字典列表
            trend_data_list = trend_data.to_dict('records')
        except Exception as e:
            app.logger.error(f"获取历史趋势数据时出错: {str(e)}")
            trend_data_list = []
        
        # 获取相似路段
        try:
            similar_roads = data_generator.get_similar_roads(road_id)
            # 确保相似路段数据中有road_id键
            similar_roads_list = []
            for _, row in similar_roads.iterrows():
                row_dict = row.to_dict()
                if 'road_id' not in row_dict and 'segment_id' in row_dict:
                    row_dict['road_id'] = row_dict['segment_id']
                similar_roads_list.append(row_dict)
        except Exception as e:
            app.logger.error(f"获取相似路段数据时出错: {str(e)}")
            similar_roads_list = []
        
        return render_template('road_detail.html', 
                              road=road, 
                              trend_data=trend_data_list,
                              similar_roads=similar_roads_list)
    
    except Exception as e:
        app.logger.error(f"显示路段 {road_id} 详情时发生错误: {str(e)}")
        return render_template('error.html', 
                              error_title="路段详情页面错误",
                              error_message=f"无法显示路段 #{road_id} 的详情，错误信息: {str(e)}")

if __name__ == '__main__':
    # 启动数据更新后台线程
    update_thread = threading.Thread(target=update_traffic_data)
    update_thread.daemon = True
    update_thread.start()
    
    # 启动Flask应用
    socketio.run(app, host='0.0.0.0', port=config.PORT, debug=config.DEBUG)