"""
交通拥堵预测模型训练器
用于管理模型训练和验证流程
"""

import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from datetime import datetime

from predictor import TrafficPredictor

class ModelTrainer:
    """模型训练器类"""
    
    def __init__(self, model_dir='./saved_models'):
        """
        初始化训练器
        
        参数:
            model_dir: 模型保存目录
        """
        self.model_dir = model_dir
        
        # 确保模型目录存在
        os.makedirs(model_dir, exist_ok=True)
    
    def train_and_evaluate(self, data, test_size=0.2, random_state=42):
        """
        训练并评估模型
        
        参数:
            data: 训练数据
            test_size: 测试集比例
            random_state: 随机种子
            
        返回:
            训练好的预测器和评估指标
        """
        # 数据分割
        train_data, test_data = train_test_split(data, test_size=test_size, random_state=random_state)
        
        print(f"训练集样本数: {len(train_data)}")
        print(f"测试集样本数: {len(test_data)}")
        
        # 创建并训练预测器
        predictor = TrafficPredictor()
        predictor.train(train_data)
        
        # 评估模型
        X_test = test_data.copy()
        y_true = X_test['congestion_index'].values
        
        # 预测测试集
        y_pred = predictor.predict(X_test)
        
        # 计算评估指标
        metrics = {
            'mse': mean_squared_error(y_true, y_pred),
            'rmse': np.sqrt(mean_squared_error(y_true, y_pred)),
            'mae': mean_absolute_error(y_true, y_pred),
            'r2': r2_score(y_true, y_pred)
        }
        
        # 打印评估指标
        print("\n模型评估指标:")
        print(f"均方误差 (MSE): {metrics['mse']:.4f}")
        print(f"均方根误差 (RMSE): {metrics['rmse']:.4f}")
        print(f"平均绝对误差 (MAE): {metrics['mae']:.4f}")
        print(f"决定系数 (R²): {metrics['r2']:.4f}")
        
        return predictor, metrics
    
    def save_model(self, predictor, metrics=None, model_name=None):
        """
        保存模型和评估指标
        
        参数:
            predictor: 训练好的预测器
            metrics: 评估指标字典
            model_name: 模型名称（如果为None，则使用时间戳）
            
        返回:
            模型文件路径
        """
        # 生成模型文件名
        if model_name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            model_name = f"traffic_model_{timestamp}"
        
        # 模型文件路径
        model_path = os.path.join(self.model_dir, f"{model_name}.joblib")
        
        # 保存模型
        predictor.save_model(model_path)
        
        # 如果有评估指标，保存到对应的文本文件
        if metrics:
            metrics_path = os.path.join(self.model_dir, f"{model_name}_metrics.txt")
            
            with open(metrics_path, 'w') as f:
                f.write(f"模型名称: {model_name}\n")
                f.write(f"保存时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("评估指标:\n")
                for metric_name, metric_value in metrics.items():
                    f.write(f"{metric_name}: {metric_value:.4f}\n")
        
        return model_path
    
    def train_and_save(self, data, model_name=None):
        """
        训练并保存模型的便捷方法
        
        参数:
            data: 训练数据
            model_name: 模型名称
            
        返回:
            保存的模型路径
        """
        # 训练并评估模型
        predictor, metrics = self.train_and_evaluate(data)
        
        # 保存模型和指标
        model_path = self.save_model(predictor, metrics, model_name)
        
        return model_path

# 测试代码
if __name__ == "__main__":
    import sys
    import os
    
    # 添加上级目录到路径
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.data_generator import TrafficDataGenerator
    
    # 创建数据生成器
    generator = TrafficDataGenerator(num_road_segments=20)
    
    # 获取历史数据
    historical_data = generator.historical_data
    
    # 创建训练器
    trainer = ModelTrainer(model_dir='./saved_models')
    
    # 训练并保存模型
    model_path = trainer.train_and_save(historical_data)
    
    print(f"\n模型已保存到: {model_path}") 