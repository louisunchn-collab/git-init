"""电商选品数据分析包。

模块结构：
- loaders   : 加载爬虫输出（taobao CSV / 生意参谋 JSON / 自定义 Excel）
- cleaners  : 字段清洗（销量字符串解析、价格带分桶、标题切词）
- analyzers : 业务分析（爆款评分、价格带、关键词热度、店铺集中度）
- forecaster: 销量预测（移动平均 / Prophet 可选）
"""

__all__ = ["loaders", "cleaners", "analyzers", "forecaster"]
