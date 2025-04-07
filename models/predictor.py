"""
交通拥堵预测模型
基于历史数据预测未来交通状况
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
import joblib
import os

class TrafficPredictor:
    """交通拥堵预测器"""
    
    def __init__(self, model_path=None):
        """
        初始化预测器
        
        参数:
            model_path: 预训练模型的路径（如果有）
        """
        self.model = None
        self.scaler = StandardScaler()
        self.model_path = model_path
        self.is_trained = False
        
        # 如果提供了模型路径，尝试加载预训练模型
        if model_path and os.path.exists(model_path):
            try:
                self.load_model(model_path)
                self.is_trained = True
            except Exception as e:
                print(f"加载模型失败: {e}")
    
    def _prepare_features(self, data):
        """
        准备模型特征
        
        参数:
            data: 原始数据DataFrame
            
        返回:
            处理后的特征矩阵
        """
        # 确保数据中包含必要的特征
        required_features = ['hour', 'day_of_week', 'traffic_flow', 'average_speed']
        for feature in required_features:
            if feature not in data.columns:
                raise ValueError(f"数据中缺少必要特征: {feature}")
        
        # 提取模型特征
        features = data[required_features].copy()
        
        # 创建时间特征
        features['hour_sin'] = np.sin(2 * np.pi * features['hour'] / 24)
        features['hour_cos'] = np.cos(2 * np.pi * features['hour'] / 24)
        features['day_sin'] = np.sin(2 * np.pi * features['day_of_week'] / 7)
        features['day_cos'] = np.cos(2 * np.pi * features['day_of_week'] / 7)
        
        # 删除原始时间特征
        features.drop(['hour', 'day_of_week'], axis=1, inplace=True)
        
        return features
    
    def train(self, historical_data):
        """
        训练模型
        
        参数:
            historical_data: 包含训练数据的DataFrame
            
        返回:
            训练后的模型
        """
        if historical_data.empty:
            raise ValueError("训练数据为空")
        
        # 准备特征和目标
        X = self._prepare_features(historical_data)
        y = historical_data['congestion_index'].values
        
        # 特征标准化
        X_scaled = self.scaler.fit_transform(X)
        
        # 训练随机森林模型
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        
        self.model.fit(X_scaled, y)
        self.is_trained = True
        
        return self.model
    
    def predict(self, input_data):
        """
        预测拥堵指数
        
        参数:
            input_data: 输入数据DataFrame
            
        返回:
            拥堵指数预测结果
        """
        if not self.is_trained:
            raise ValueError("模型未训练，请先训练模型")
        
        # 准备特征
        X = self._prepare_features(input_data)
        
        # 特征标准化
        X_scaled = self.scaler.transform(X)
        
        # 预测拥堵指数
        predictions = self.model.predict(X_scaled)
        
        # 确保预测结果在有效范围内 (0-1)
        predictions = np.clip(predictions, 0, 1)
        
        return predictions
    
    def predict_future(self, current_data, hours_ahead=3):
        """
        预测未来几小时的交通状况
        
        参数:
            current_data: 当前交通数据
            hours_ahead: 预测未来的小时数
            
        返回:
            包含未来预测的DataFrame
        """
        if not self.is_trained:
            raise ValueError("模型未训练，请先训练模型")
        
        # 创建预测结果列表
        future_predictions = []
        
        # 获取当前时间
        current_time = datetime.now()
        
        # 为每条路段进行预测
        for segment_id in current_data['segment_id'].unique():
            # 提取特定路段的数据
            segment_data = current_data[current_data['segment_id'] == segment_id].iloc[0].to_dict()
            
            # 预测未来几小时
            for hour in range(1, hours_ahead + 1):
                # 计算未来时间点
                future_time = current_time + timedelta(hours=hour)
                
                # 创建预测数据点
                prediction_point = segment_data.copy()
                prediction_point['timestamp'] = future_time
                prediction_point['hour'] = future_time.hour
                prediction_point['day_of_week'] = future_time.weekday()
                
                # 创建特征DataFrame
                pred_df = pd.DataFrame([prediction_point])
                
                # 预测拥堵指数
                pred_congestion = self.predict(pred_df)[0]
                
                # 更新预测点
                prediction_point['congestion_index'] = pred_congestion
                prediction_point['predicted'] = True
                
                # 根据预测的拥堵指数更新状态
                if pred_congestion < 0.4:
                    prediction_point['status'] = '畅通'
                elif pred_congestion < 0.6:
                    prediction_point['status'] = '轻度拥堵'
                elif pred_congestion < 0.8:
                    prediction_point['status'] = '中度拥堵'
                else:
                    prediction_point['status'] = '严重拥堵'
                
                # 添加到预测列表
                future_predictions.append(prediction_point)
        
        # 转换为DataFrame
        if future_predictions:
            predictions_df = pd.DataFrame(future_predictions)
            return predictions_df
        
        return pd.DataFrame()
    
    def save_model(self, model_path=None):
        """
        保存模型到文件
        
        参数:
            model_path: 模型保存路径
        """
        if not self.is_trained:
            raise ValueError("模型未训练，无法保存")
        
        path = model_path or self.model_path or "traffic_model.joblib"
        
        # 创建包含模型和缩放器的字典
        model_data = {
            'model': self.model,
            'scaler': self.scaler
        }
        
        # 保存模型
        joblib.dump(model_data, path)
        print(f"模型已保存到 {path}")
    
    def load_model(self, model_path=None):
        """
        从文件加载模型
        
        参数:
            model_path: 模型文件路径
        """
        path = model_path or self.model_path
        if not path:
            raise ValueError("未提供模型路径")
        
        # 加载模型
        model_data = joblib.load(path)
        
        # 提取模型和缩放器
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.is_trained = True
        print(f"模型已从 {path} 加载")

# 测试代码
if __name__ == "__main__":
    # 导入数据生成器用于测试
    import sys
    import os
    
    # 添加上级目录到路径，以便导入utils
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.data_generator import TrafficDataGenerator
    
    # 创建数据生成器和预测器
    generator = TrafficDataGenerator(num_road_segments=5)
    predictor = TrafficPredictor()
    
    # 获取历史数据进行训练
    historical_data = generator.historical_data
    print(f"训练数据样本数: {len(historical_data)}")
    
    # 训练模型
    predictor.train(historical_data)
    
    # 获取当前数据
    current_data = generator.get_real_time_data()
    
    # 预测未来3小时
    future_predictions = predictor.predict_future(current_data, hours_ahead=3)
    
    # 显示预测结果
    print("\n未来预测结果:")
    print(future_predictions[['road_name', 'timestamp', 'congestion_index', 'status']].head(10)) 