# 贵阳市交通拥堵监测系统

实时监测贵阳市交通拥堵情况，通过数据模拟和预测分析提供实时可视化。

## 功能特点

- 实时拥堵路段列表显示
- 历史拥堵趋势折线图分析
- 地图可视化显示拥堵路段
- 交通拥堵预测模型
- 实时警报系统

## 技术栈

- 后端: Flask, Socket.IO (实时数据传输)
- 数据处理: NumPy, Pandas
- 机器学习: Scikit-learn (预测模型)
- 可视化: Matplotlib (趋势图), Folium (地图渲染)
- 数据模拟: Faker, 自定义模拟数据生成器

## 项目结构

```
贵阳市交通拥堵监测系统/
├── app.py               # Flask应用主入口
├── config.py            # 配置文件
├── requirements.txt     # 依赖包列表
├── static/              # 静态资源
│   ├── css/             # 样式文件
│   ├── js/              # JavaScript文件
│   └── images/          # 图片资源
├── templates/           # HTML模板
├── models/              # 机器学习模型
│   ├── predictor.py     # 预测模块
│   └── trainer.py       # 模型训练
└── utils/               # 工具函数
    ├── data_generator.py  # 数据模拟生成
    └── data_processor.py  # 数据处理
```

## 安装和运行

1. 安装依赖:
   ```
   pip install -r requirements.txt
   ```

2. 运行应用:
   ```
   python app.py
   ```

3. 在浏览器中访问:
   ```
   http://localhost:5000
   ```

## 数据模拟

系统使用模拟数据生成器创建贵阳市的交通数据，包括:
- 路段信息
- 车流量
- 平均车速
- 拥堵指数

## 预测分析

基于历史数据和当前实时数据，系统使用机器学习模型预测未来交通状况。 