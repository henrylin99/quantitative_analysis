import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from loguru import logger

from app.extensions import db
from app.models import FactorValues, MLPredictions, StockBasic


class StockScoringEngine:
    """股票打分引擎"""
    
    def __init__(self):
        self.scoring_methods = {
            'equal_weight': self._equal_weight_scoring,
            'factor_weight': self._factor_weight_scoring,
            'ml_ensemble': self._ml_ensemble_scoring,
            'rank_ic': self._rank_ic_scoring
        }
    
    def calculate_factor_scores(self, trade_date: str, factor_list: List[str] = None,
                               ts_codes: List[str] = None) -> pd.DataFrame:
        """计算因子分数"""
        try:
            # 构建查询
            query = FactorValues.query.filter(FactorValues.trade_date == trade_date)
            
            if factor_list:
                query = query.filter(FactorValues.factor_id.in_(factor_list))
            
            if ts_codes:
                query = query.filter(FactorValues.ts_code.in_(ts_codes))
            
            # 获取因子数据
            factor_data = pd.read_sql(query.statement, db.engine)
            
            if factor_data.empty:
                logger.warning(f"未找到因子数据: {trade_date}")
                return pd.DataFrame()
            
            # 透视表：行为ts_code，列为factor_id
            factor_scores = factor_data.pivot_table(
                index='ts_code',
                columns='factor_id',
                values='z_score',  # 使用标准化后的Z分数
                aggfunc='first'
            ).fillna(0)
            
            logger.info(f"计算因子分数完成: {len(factor_scores)} 只股票, {len(factor_scores.columns)} 个因子")
            return factor_scores
            
        except Exception as e:
            logger.error(f"计算因子分数失败: {trade_date}, 错误: {e}")
            return pd.DataFrame()
    
    def calculate_composite_score(self, factor_scores: pd.DataFrame, weights: Dict[str, float],
                                 method: str = 'equal_weight') -> pd.DataFrame:
        """计算综合分数"""
        try:
            if factor_scores.empty:
                return pd.DataFrame()
            
            # 检查权重
            if method != 'equal_weight' and not weights:
                logger.warning("未提供权重，使用等权重方法")
                method = 'equal_weight'
            
            # 选择评分方法
            if method not in self.scoring_methods:
                logger.warning(f"不支持的评分方法: {method}，使用等权重方法")
                method = 'equal_weight'
            
            scoring_func = self.scoring_methods[method]
            composite_scores = scoring_func(factor_scores, weights)
            
            # 构建结果DataFrame
            result_df = pd.DataFrame({
                'ts_code': composite_scores.index,
                'composite_score': composite_scores.values
            })
            
            # 计算排名
            result_df['rank'] = result_df['composite_score'].rank(ascending=False, method='dense').astype(int)
            
            # 计算百分位排名
            result_df['percentile_rank'] = result_df['composite_score'].rank(pct=True) * 100
            
            logger.info(f"计算综合分数完成: {len(result_df)} 只股票")
            return result_df.sort_values('rank')
            
        except Exception as e:
            logger.error(f"计算综合分数失败: {method}, 错误: {e}")
            return pd.DataFrame()
    
    def _equal_weight_scoring(self, factor_scores: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        """等权重评分"""
        return factor_scores.mean(axis=1)
    
    def _factor_weight_scoring(self, factor_scores: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        """因子权重评分"""
        # 确保权重归一化
        total_weight = sum(weights.values())
        normalized_weights = {k: v / total_weight for k, v in weights.items()}
        
        # 计算加权分数
        weighted_scores = pd.Series(0, index=factor_scores.index)
        
        for factor_id, weight in normalized_weights.items():
            if factor_id in factor_scores.columns:
                weighted_scores += factor_scores[factor_id] * weight
        
        return weighted_scores
    
    def _ml_ensemble_scoring(self, factor_scores: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        """机器学习集成评分"""
        # TODO: 实现基于多个ML模型的集成评分
        # 目前使用等权重作为占位符
        return self._equal_weight_scoring(factor_scores, weights)
    
    def _rank_ic_scoring(self, factor_scores: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        """基于Rank IC的评分"""
        # TODO: 实现基于历史Rank IC的动态权重评分
        # 目前使用等权重作为占位符
        return self._equal_weight_scoring(factor_scores, weights)
    
    def rank_stocks(self, scores: pd.DataFrame, top_n: int = 50, 
                   filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """股票排名选择"""
        try:
            if scores.empty:
                return []
            
            # 应用过滤条件
            filtered_scores = self._apply_filters(scores, filters)
            
            if filtered_scores.empty:
                logger.warning("过滤后无股票数据")
                return []
            
            # 选择前N只股票
            top_stocks = filtered_scores.head(top_n)
            
            # 获取股票基本信息
            ts_codes = top_stocks['ts_code'].tolist()
            stock_info = self._get_stock_info(ts_codes)
            
            # 构建结果
            result = []
            for _, row in top_stocks.iterrows():
                stock_data = {
                    'ts_code': row['ts_code'],
                    'composite_score': float(row['composite_score']),
                    'rank': int(row['rank']),
                    'percentile_rank': float(row['percentile_rank'])
                }
                
                # 添加股票基本信息
                if row['ts_code'] in stock_info:
                    stock_data.update(stock_info[row['ts_code']])
                
                result.append(stock_data)
            
            logger.info(f"股票排名完成: 选出 {len(result)} 只股票")
            return result
            
        except Exception as e:
            logger.error(f"股票排名失败: {e}")
            return []
    
    def _apply_filters(self, scores: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
        """应用过滤条件"""
        try:
            if not filters:
                return scores
            
            filtered_scores = scores.copy()
            
            # 最小分数过滤
            if 'min_score' in filters:
                min_score = filters['min_score']
                filtered_scores = filtered_scores[filtered_scores['composite_score'] >= min_score]
            
            # 最大分数过滤
            if 'max_score' in filters:
                max_score = filters['max_score']
                filtered_scores = filtered_scores[filtered_scores['composite_score'] <= max_score]
            
            # 百分位排名过滤
            if 'min_percentile' in filters:
                min_percentile = filters['min_percentile']
                filtered_scores = filtered_scores[filtered_scores['percentile_rank'] >= min_percentile]
            
            # 行业过滤
            if 'industries' in filters:
                industries = filters['industries']
                stock_info = self._get_stock_info(filtered_scores['ts_code'].tolist())
                valid_codes = [
                    ts_code for ts_code, info in stock_info.items()
                    if info.get('industry') in industries
                ]
                filtered_scores = filtered_scores[filtered_scores['ts_code'].isin(valid_codes)]
            
            # 排除股票
            if 'exclude_codes' in filters:
                exclude_codes = filters['exclude_codes']
                filtered_scores = filtered_scores[~filtered_scores['ts_code'].isin(exclude_codes)]
            
            return filtered_scores
            
        except Exception as e:
            logger.error(f"应用过滤条件失败: {e}")
            return scores
    
    def _get_stock_info(self, ts_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取股票基本信息"""
        try:
            stocks = StockBasic.query.filter(StockBasic.ts_code.in_(ts_codes)).all()
            
            stock_info = {}
            for stock in stocks:
                stock_info[stock.ts_code] = {
                    'symbol': stock.symbol,
                    'name': stock.name,
                    'area': stock.area,
                    'industry': stock.industry,
                    'list_date': stock.list_date.isoformat() if stock.list_date else None
                }
            
            return stock_info
            
        except Exception as e:
            logger.error(f"获取股票信息失败: {e}")
            return {}
    
    def ml_based_selection(self, trade_date: str, model_ids: List[str],
                          top_n: int = 50, ensemble_method: str = 'average') -> List[Dict[str, Any]]:
        """基于机器学习模型的选股"""
        try:
            if not model_ids:
                logger.warning("未提供模型ID")
                return []
            
            # 获取所有模型的预测结果
            all_predictions = []
            
            for model_id in model_ids:
                pred_query = MLPredictions.query.filter(
                    MLPredictions.model_id == model_id,
                    MLPredictions.trade_date == trade_date
                ).order_by(MLPredictions.rank_score)
                
                pred_data = pd.read_sql(pred_query.statement, db.engine)
                
                if not pred_data.empty:
                    pred_data['model_id'] = model_id
                    all_predictions.append(pred_data)
            
            if not all_predictions:
                logger.warning(f"未找到预测数据: {trade_date}")
                return []
            
            # 合并所有预测结果
            combined_predictions = pd.concat(all_predictions, ignore_index=True)
            
            # 集成预测结果
            ensemble_scores = self._ensemble_predictions(combined_predictions, ensemble_method)
            
            # 排名和选择
            ensemble_scores['rank'] = ensemble_scores['ensemble_score'].rank(ascending=False, method='dense').astype(int)
            ensemble_scores['percentile_rank'] = ensemble_scores['ensemble_score'].rank(pct=True) * 100
            
            # 选择前N只股票
            top_stocks = ensemble_scores.head(top_n)
            
            # 获取股票基本信息
            ts_codes = top_stocks['ts_code'].tolist()
            stock_info = self._get_stock_info(ts_codes)
            
            # 构建结果
            result = []
            for _, row in top_stocks.iterrows():
                stock_data = {
                    'ts_code': row['ts_code'],
                    'ensemble_score': float(row['ensemble_score']),
                    'rank': int(row['rank']),
                    'percentile_rank': float(row['percentile_rank']),
                    'model_count': int(row['model_count'])
                }
                
                # 添加股票基本信息
                if row['ts_code'] in stock_info:
                    stock_data.update(stock_info[row['ts_code']])
                
                result.append(stock_data)
            
            logger.info(f"ML选股完成: 使用 {len(model_ids)} 个模型，选出 {len(result)} 只股票")
            return result
            
        except Exception as e:
            logger.error(f"ML选股失败: {trade_date}, 错误: {e}")
            return []
    
    def _ensemble_predictions(self, predictions: pd.DataFrame, method: str) -> pd.DataFrame:
        """集成预测结果"""
        try:
            if method == 'average':
                # 平均集成
                ensemble_result = predictions.groupby('ts_code').agg({
                    'predicted_return': 'mean',
                    'probability_score': 'mean',
                    'rank_score': 'mean',
                    'model_id': 'count'
                }).reset_index()
                
                ensemble_result = ensemble_result.rename(columns={
                    'predicted_return': 'ensemble_score',
                    'model_id': 'model_count'
                })
                
            elif method == 'weighted_average':
                # 加权平均（基于模型历史表现）
                # TODO: 实现基于模型历史表现的加权平均
                ensemble_result = predictions.groupby('ts_code').agg({
                    'predicted_return': 'mean',
                    'probability_score': 'mean',
                    'rank_score': 'mean',
                    'model_id': 'count'
                }).reset_index()
                
                ensemble_result = ensemble_result.rename(columns={
                    'predicted_return': 'ensemble_score',
                    'model_id': 'model_count'
                })
                
            elif method == 'rank_average':
                # 排名平均
                ensemble_result = predictions.groupby('ts_code').agg({
                    'rank_score': 'mean',
                    'predicted_return': 'mean',
                    'probability_score': 'mean',
                    'model_id': 'count'
                }).reset_index()
                
                # 使用排名的倒数作为分数（排名越小分数越高）
                ensemble_result['ensemble_score'] = 1.0 / ensemble_result['rank_score']
                ensemble_result = ensemble_result.rename(columns={'model_id': 'model_count'})
                
            else:
                logger.warning(f"不支持的集成方法: {method}，使用平均方法")
                return self._ensemble_predictions(predictions, 'average')
            
            return ensemble_result.sort_values('ensemble_score', ascending=False)
            
        except Exception as e:
            logger.error(f"集成预测结果失败: {method}, 错误: {e}")
            return pd.DataFrame()
    
    def factor_contribution_analysis(self, ts_code: str, trade_date: str,
                                   factor_list: List[str] = None) -> Dict[str, Any]:
        """因子贡献度分析"""
        try:
            # 获取股票的因子值
            query = FactorValues.query.filter(
                FactorValues.ts_code == ts_code,
                FactorValues.trade_date == trade_date
            )
            
            if factor_list:
                query = query.filter(FactorValues.factor_id.in_(factor_list))
            
            factor_data = pd.read_sql(query.statement, db.engine)
            
            if factor_data.empty:
                return {'error': '未找到因子数据'}
            
            # 获取全市场因子分布
            market_query = FactorValues.query.filter(
                FactorValues.trade_date == trade_date
            )
            
            if factor_list:
                market_query = market_query.filter(FactorValues.factor_id.in_(factor_list))
            
            market_data = pd.read_sql(market_query.statement, db.engine)
            
            # 计算因子贡献度
            contributions = {}
            
            for _, row in factor_data.iterrows():
                factor_id = row['factor_id']
                factor_value = row['factor_value']
                z_score = row['z_score']
                percentile_rank = row['percentile_rank']
                
                # 计算该因子在全市场的分布
                market_factor = market_data[market_data['factor_id'] == factor_id]
                
                if not market_factor.empty:
                    market_mean = market_factor['factor_value'].mean()
                    market_std = market_factor['factor_value'].std()
                    market_median = market_factor['factor_value'].median()
                    
                    contributions[factor_id] = {
                        'factor_value': float(factor_value) if factor_value else None,
                        'z_score': float(z_score) if z_score else None,
                        'percentile_rank': float(percentile_rank) if percentile_rank else None,
                        'market_mean': float(market_mean),
                        'market_std': float(market_std),
                        'market_median': float(market_median),
                        'deviation_from_mean': float(factor_value - market_mean) if factor_value else None,
                        'relative_strength': 'strong' if percentile_rank and percentile_rank > 80 else 
                                           'weak' if percentile_rank and percentile_rank < 20 else 'neutral'
                    }
            
            result = {
                'ts_code': ts_code,
                'trade_date': trade_date,
                'factor_contributions': contributions,
                'total_factors': len(contributions)
            }
            
            logger.info(f"因子贡献度分析完成: {ts_code}, {len(contributions)} 个因子")
            return result
            
        except Exception as e:
            logger.error(f"因子贡献度分析失败: {ts_code}, {trade_date}, 错误: {e}")
            return {'error': str(e)}
    
    def sector_analysis(self, trade_date: str, factor_list: List[str] = None,
                       top_n: int = 10) -> Dict[str, Any]:
        """行业分析"""
        try:
            # 获取因子分数
            factor_scores = self.calculate_factor_scores(trade_date, factor_list)
            
            if factor_scores.empty:
                return {'error': '未找到因子数据'}
            
            # 计算综合分数
            composite_scores = self.calculate_composite_score(factor_scores, {})
            
            if composite_scores.empty:
                return {'error': '计算综合分数失败'}
            
            # 获取股票行业信息
            ts_codes = composite_scores['ts_code'].tolist()
            stock_info = self._get_stock_info(ts_codes)
            
            # 添加行业信息
            composite_scores['industry'] = composite_scores['ts_code'].map(
                lambda x: stock_info.get(x, {}).get('industry', '未知')
            )
            
            # 按行业分组分析
            industry_analysis = composite_scores.groupby('industry').agg({
                'composite_score': ['mean', 'median', 'std', 'count'],
                'percentile_rank': ['mean', 'median']
            }).round(4)
            
            # 展平列名
            industry_analysis.columns = ['_'.join(col).strip() for col in industry_analysis.columns]
            industry_analysis = industry_analysis.reset_index()
            
            # 排序
            industry_analysis = industry_analysis.sort_values('composite_score_mean', ascending=False)
            
            # 选择每个行业的顶级股票
            top_stocks_by_industry = {}
            for industry in industry_analysis['industry'].head(top_n):
                industry_stocks = composite_scores[composite_scores['industry'] == industry].head(5)
                
                top_stocks_by_industry[industry] = []
                for _, stock in industry_stocks.iterrows():
                    stock_data = {
                        'ts_code': stock['ts_code'],
                        'composite_score': float(stock['composite_score']),
                        'rank': int(stock['rank'])
                    }
                    
                    if stock['ts_code'] in stock_info:
                        stock_data.update(stock_info[stock['ts_code']])
                    
                    top_stocks_by_industry[industry].append(stock_data)
            
            result = {
                'trade_date': trade_date,
                'industry_summary': industry_analysis.to_dict('records'),
                'top_stocks_by_industry': top_stocks_by_industry,
                'total_industries': len(industry_analysis),
                'total_stocks': len(composite_scores)
            }
            
            logger.info(f"行业分析完成: {len(industry_analysis)} 个行业")
            return result
            
        except Exception as e:
            logger.error(f"行业分析失败: {trade_date}, 错误: {e}")
            return {'error': str(e)} 