"""
回测引擎模块
基于策略信号进行模拟交易回测
支持：MA+MACD、布林带、KDJ、RSI、成交量突破五种策略
"""
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from config import BACKTEST_PERIODS


# ==================== 辅助计算函数 ====================

def _calculate_annual_return(total_return: float, days: int) -> float:
    """
    计算年化收益率

    Args:
        total_return: 总收益率(%)
        days: 交易天数

    Returns:
        年化收益率(%)
    """
    if days <= 0:
        return 0.0
    return ((1 + total_return / 100) ** (365 / days) - 1) * 100


def _calculate_max_drawdown(equity_curve: list) -> float:
    """
    计算最大回撤

    Args:
        equity_curve: 权益曲线 [(date, value), ...]

    Returns:
        最大回撤(%)
    """
    if not equity_curve:
        return 0.0

    values = [v for _, v in equity_curve]
    max_dd = 0.0
    peak = values[0]

    for value in values:
        if value > peak:
            peak = value
        dd = (peak - value) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return max_dd


def _calculate_sharpe_ratio(equity_curve: list, risk_free_rate: float = 0.03) -> float:
    """
    计算夏普比率

    Args:
        equity_curve: 权益曲线 [(date, value), ...]
        risk_free_rate: 年化无风险利率，默认3%

    Returns:
        夏普比率
    """
    if len(equity_curve) < 2:
        return 0.0

    # 计算日收益率序列
    daily_returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1][1] > 0:
            ret = (equity_curve[i][1] - equity_curve[i-1][1]) / equity_curve[i-1][1]
            daily_returns.append(ret)

    if not daily_returns:
        return 0.0

    mean_return = np.mean(daily_returns)
    std_return = np.std(daily_returns)

    if std_return == 0:
        return 0.0

    # 年化
    daily_rf = risk_free_rate / 252
    sharpe = (mean_return - daily_rf) / std_return * np.sqrt(252)
    return sharpe


# ==================== 核心回测引擎 ====================

def backtest_strategy(
    df: pd.DataFrame,
    signal_column: str,
    strategy_name: str,
    initial_capital: float = 1.0
) -> dict:
    """
    对单个策略进行信号驱动回测

    Args:
        df: 包含信号的DataFrame (必须包含: close, signal_column)
        signal_column: 信号列名 ('signal', 'signal_boll', 'signal_kdj')
        strategy_name: 策略名称
        initial_capital: 初始资金(默认1.0用于计算收益率)

    Returns:
        回测结果字典
    """
    if df.empty or signal_column not in df.columns:
        return _empty_result(strategy_name)

    # 初始化
    capital = initial_capital
    position = 0  # 0=空仓, 1=满仓
    holding_shares = 0
    entry_price = 0
    entry_date = None
    trades = []
    equity_curve = []

    # 遍历数据
    for i in range(len(df)):
        row = df.iloc[i]
        date = df.index[i]
        price = row['close']
        signal = row[signal_column]

        # 计算当前权益
        if position > 0:
            current_value = holding_shares * price
        else:
            current_value = capital
        equity_curve.append((date, current_value))

        # 处理信号
        if signal == 1 and position == 0:
            # 买入信号且空仓 -> 全仓买入
            position = 1
            entry_price = price
            entry_date = date
            holding_shares = capital / price
            capital = 0

        elif signal == -1 and position > 0:
            # 卖出信号且持仓 -> 全仓卖出
            exit_price = price
            exit_date = date
            capital = holding_shares * exit_price

            # 记录交易
            trade = {
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'return': (exit_price - entry_price) / entry_price * 100,
                'return_abs': capital - initial_capital,
                'hold_days': (exit_date - entry_date).days,
                'trade_type': 'long'
            }
            trades.append(trade)

            # 重置持仓
            position = 0
            holding_shares = 0
            entry_price = 0
            entry_date = None

    # 如果回测结束时还持仓，强制平仓
    if position > 0:
        exit_price = df.iloc[-1]['close']
        exit_date = df.index[-1]
        capital = holding_shares * exit_price

        trade = {
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_date': exit_date,
            'exit_price': exit_price,
            'return': (exit_price - entry_price) / entry_price * 100,
            'return_abs': capital - initial_capital,
            'hold_days': (exit_date - entry_date).days,
            'trade_type': 'long'
        }
        trades.append(trade)
        position = 0

    # 计算统计指标
    final_value = capital
    total_return = (final_value - initial_capital) / initial_capital * 100

    # 交易统计
    trade_count = len(trades)
    if trade_count == 0:
        return _empty_result(strategy_name)

    win_trades = [t for t in trades if t['return'] > 0]
    loss_trades = [t for t in trades if t['return'] <= 0]
    win_count = len(win_trades)
    loss_count = len(loss_trades)
    win_rate = win_count / trade_count * 100 if trade_count > 0 else 0

    avg_win = np.mean([t['return'] for t in win_trades]) if win_trades else 0
    avg_loss = np.mean([t['return'] for t in loss_trades]) if loss_trades else 0

    # 盈亏比
    total_win = sum([t['return_abs'] for t in win_trades]) if win_trades else 0
    total_loss = abs(sum([t['return_abs'] for t in loss_trades])) if loss_trades else 0
    profit_factor = total_win / total_loss if total_loss > 0 else 0

    # 时间跨度
    start_date = df.index[0]
    end_date = df.index[-1]
    total_days = (end_date - start_date).days
    trading_days = sum([t['hold_days'] for t in trades])

    # 年化收益
    annual_return = _calculate_annual_return(total_return, total_days)

    # 最大回撤
    max_drawdown = _calculate_max_drawdown(equity_curve)

    # 夏普比率
    sharpe_ratio = _calculate_sharpe_ratio(equity_curve)

    # 平均持仓天数
    avg_hold_days = trading_days / trade_count if trade_count > 0 else 0

    return {
        'strategy_name': strategy_name,
        'signal_column': signal_column,

        # 交易记录
        'trades': trades,
        'trade_count': trade_count,

        # 收益指标
        'total_return': total_return,
        'annual_return': annual_return,
        'final_value': final_value,

        # 胜率指标
        'win_count': win_count,
        'loss_count': loss_count,
        'win_rate': win_rate,

        # 盈亏比
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,

        # 风险指标
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
        'avg_hold_days': avg_hold_days,

        # 时间区间
        'start_date': start_date,
        'end_date': end_date,
        'total_days': total_days,
        'trading_days': trading_days,

        # 权益曲线
        'equity_curve': equity_curve
    }


def _empty_result(strategy_name: str) -> dict:
    """返回空的回测结果"""
    return {
        'strategy_name': strategy_name,
        'signal_column': '',
        'trades': [],
        'trade_count': 0,
        'total_return': 0.0,
        'annual_return': 0.0,
        'final_value': 1.0,
        'win_count': 0,
        'loss_count': 0,
        'win_rate': 0.0,
        'avg_win': 0.0,
        'avg_loss': 0.0,
        'profit_factor': 0.0,
        'max_drawdown': 0.0,
        'sharpe_ratio': 0.0,
        'avg_hold_days': 0.0,
        'start_date': None,
        'end_date': None,
        'total_days': 0,
        'trading_days': 0,
        'equity_curve': []
    }


# ==================== 形态识别（保留用于兼容） ====================

def get_pattern(row) -> dict:
    """
    识别当前技术形态（多维度）
    保留此函数用于 calc_score 兼容性

    返回形态字典：
    - ma: "bull" (MA5>MA20) 或 "bear"
    - macd: "bull" (DIF>DEA) 或 "bear"
    - rsi: "oversold" (<30), "normal" (30-70), "overbought" (>70)
    - volume: "high" (量比>1.5), "normal" (0.7-1.5), "low" (<0.7)
    """
    pattern = {}

    # 均线形态
    if pd.notna(row.get('MA5')) and pd.notna(row.get('MA20')):
        pattern['ma'] = "bull" if row['MA5'] > row['MA20'] else "bear"
    else:
        pattern['ma'] = None

    # MACD形态
    if pd.notna(row.get('DIF')) and pd.notna(row.get('DEA')):
        pattern['macd'] = "bull" if row['DIF'] > row['DEA'] else "bear"
    else:
        pattern['macd'] = None

    # RSI形态
    rsi = row.get('RSI')
    if pd.notna(rsi):
        if rsi < 30:
            pattern['rsi'] = "oversold"
        elif rsi > 70:
            pattern['rsi'] = "overbought"
        else:
            pattern['rsi'] = "normal"
    else:
        pattern['rsi'] = None

    # 成交量形态
    vol_ratio = row.get('VOL_RATIO')
    if pd.notna(vol_ratio):
        if vol_ratio > 1.5:
            pattern['volume'] = "high"
        elif vol_ratio < 0.7:
            pattern['volume'] = "low"
        else:
            pattern['volume'] = "normal"
    else:
        pattern['volume'] = None

    return pattern


def get_pattern_description(pattern: dict) -> list:
    """获取形态的中文描述列表"""
    desc = []

    # 均线+MACD组合
    ma = pattern.get('ma')
    macd = pattern.get('macd')
    if ma == "bull" and macd == "bull":
        desc.append("趋势: 多头 (MA5>MA20, DIF>DEA)")
    elif ma == "bull" and macd == "bear":
        desc.append("趋势: 均线多头 (MA5>MA20, DIF<DEA)")
    elif ma == "bear" and macd == "bull":
        desc.append("趋势: MACD多头 (MA5<MA20, DIF>DEA)")
    elif ma == "bear" and macd == "bear":
        desc.append("趋势: 空头 (MA5<MA20, DIF<DEA)")

    # RSI
    rsi = pattern.get('rsi')
    if rsi == "oversold":
        desc.append("RSI: 超卖区 (<30)")
    elif rsi == "overbought":
        desc.append("RSI: 超买区 (>70)")
    else:
        desc.append("RSI: 正常区间 (30-70)")

    # 成交量
    vol = pattern.get('volume')
    if vol == "high":
        desc.append("成交量: 放量 (量比>1.5)")
    elif vol == "low":
        desc.append("成交量: 缩量 (量比<0.7)")
    else:
        desc.append("成交量: 正常")

    return desc


# ==================== 兼容层 ====================

def _generate_legacy_results(strategies: dict, current_pattern: dict) -> dict:
    """
    生成兼容旧版calc_score的results字段
    使用最佳策略的胜率模拟periods数据
    """
    if not strategies:
        return {
            'match_count': 0,
            'periods': {}
        }

    # 选择收益率最高的策略
    best_strategy = max(strategies.values(), key=lambda s: s.get('total_return', 0))

    trade_count = best_strategy.get('trade_count', 0)
    if trade_count == 0:
        return {
            'match_count': 0,
            'periods': {}
        }

    # 模拟periods数据（用于calc_score）
    # 将策略胜率和平均收益映射到120天周期
    avg_return_per_trade = best_strategy['total_return'] / trade_count if trade_count > 0 else 0

    return {
        'match_count': trade_count,
        'periods': {
            120: {  # 6个月周期
                'win_rate': best_strategy['win_rate'],
                'avg_return': avg_return_per_trade,
                'win_count': best_strategy['win_count'],
                'total_count': trade_count
            }
        }
    }


# ==================== 主回测函数 ====================

def backtest_stock(ts_code: str, years: int = 3) -> dict:
    """
    对单只股票基于信号进行回测

    Args:
        ts_code: 股票代码
        years: 回测年数

    Returns:
        回测结果字典 (兼容calc_score和main.py)
    """
    from data import get_stock_data, get_stock_name
    from indicators import calc_all_indicators
    from strategy import generate_signals

    # 1. 获取数据
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=365 * years + 30)).strftime('%Y%m%d')

    df = get_stock_data(ts_code, start_date, end_date)
    if df.empty:
        return None

    # 2. 计算指标和信号
    df = calc_all_indicators(df)
    df = generate_signals(df)

    # 转换综合策略信号为简单形式 (2,1 -> 1, -2,-1 -> -1, 0 -> 0)
    df['signal_combined_simple'] = 0
    df.loc[df['signal_combined'] >= 1, 'signal_combined_simple'] = 1
    df.loc[df['signal_combined'] <= -1, 'signal_combined_simple'] = -1

    # 3. 回测所有策略
    strategies = {}
    strategy_configs = [
        ('signal', 'MA+MACD'),
        ('signal_boll', 'Bollinger'),
        ('signal_kdj', 'KDJ'),
        ('signal_rsi', 'RSI'),
        ('signal_volume', 'Volume'),
        ('signal_combined_simple', 'Combined')
    ]

    for signal_col, strategy_name in strategy_configs:
        result = backtest_strategy(df, signal_col, strategy_name)
        strategies[strategy_name] = result

    # 4. 获取当前状态（兼容calc_score）
    latest = df.iloc[-1]
    current_pattern = get_pattern(latest)

    # 5. 构造返回结果
    return {
        'ts_code': ts_code,
        'name': get_stock_name(ts_code),
        'years': years,

        # 新增：策略回测结果
        'strategies': strategies,

        # 保留：形态信息（用于calc_score兼容）
        'current_pattern': current_pattern,
        'pattern_desc': get_pattern_description(current_pattern),
        'current_rsi': latest.get('RSI'),
        'current_vol_ratio': latest.get('VOL_RATIO'),

        # 新增：当前信号
        'current_signals': {
            'signal': int(latest.get('signal', 0)),
            'signal_boll': int(latest.get('signal_boll', 0)),
            'signal_kdj': int(latest.get('signal_kdj', 0)),
            'signal_rsi': int(latest.get('signal_rsi', 0)),
            'signal_volume': int(latest.get('signal_volume', 0)),
            'signal_combined': int(latest.get('signal_combined', 0)),
            'score_combined': float(latest.get('score_combined', 0))
        },

        # 兼容旧版：生成模拟的results字段
        'results': _generate_legacy_results(strategies, current_pattern)
    }


# ==================== 评分系统 ====================

def calc_score(result: dict) -> dict:
    """
    计算综合买入评分 (0-100)

    新评分维度：
    - 趋势分 (30分): MA+MACD形态
    - RSI分 (20分): RSI位置
    - 成交量分 (10分): 量比状态
    - 策略胜率 (20分): 最佳策略的历史胜率
    - 策略收益 (10分): 最佳策略的年化收益
    - 夏普比率 (10分): 最佳策略的风险调整收益

    Returns:
        包含各维度分数和总分的字典
    """
    if result is None:
        return None

    pattern = result.get('current_pattern', {})
    rsi = result.get('current_rsi')
    vol_ratio = result.get('current_vol_ratio')
    strategies = result.get('strategies', {})

    scores = {}

    # 1. 趋势分 (30分)
    ma = pattern.get('ma')
    macd = pattern.get('macd')
    if ma == 'bull' and macd == 'bull':
        scores['trend'] = 30
        scores['trend_text'] = "多头趋势"
    elif ma == 'bull' and macd == 'bear':
        scores['trend'] = 20
        scores['trend_text'] = "均线多头"
    elif ma == 'bear' and macd == 'bull':
        scores['trend'] = 15
        scores['trend_text'] = "MACD多头"
    else:
        scores['trend'] = 5
        scores['trend_text'] = "空头趋势"

    # 2. RSI分 (20分)
    if rsi is not None:
        if rsi < 30:
            scores['rsi'] = 16
            scores['rsi_text'] = f"超卖({rsi:.0f})"
        elif rsi < 50:
            scores['rsi'] = 20
            scores['rsi_text'] = f"低位({rsi:.0f})"
        elif rsi < 70:
            scores['rsi'] = 14
            scores['rsi_text'] = f"中位({rsi:.0f})"
        else:
            scores['rsi'] = 6
            scores['rsi_text'] = f"超买({rsi:.0f})"
    else:
        scores['rsi'] = 10
        scores['rsi_text'] = "无数据"

    # 3. 成交量分 (10分)
    if vol_ratio is not None:
        if vol_ratio < 0.7:
            scores['volume'] = 5
            scores['volume_text'] = f"缩量({vol_ratio:.1f})"
        elif vol_ratio < 1.5:
            scores['volume'] = 10
            scores['volume_text'] = f"正常({vol_ratio:.1f})"
        elif vol_ratio < 2.5:
            scores['volume'] = 8
            scores['volume_text'] = f"放量({vol_ratio:.1f})"
        else:
            scores['volume'] = 4
            scores['volume_text'] = f"异常({vol_ratio:.1f})"
    else:
        scores['volume'] = 5
        scores['volume_text'] = "无数据"

    # 4. 策略表现分 (40分)
    if strategies:
        # 选择表现最好的策略（按总收益）
        valid_strategies = [s for s in strategies.values() if s.get('trade_count', 0) > 0]

        if valid_strategies:
            best_strategy = max(valid_strategies, key=lambda s: s.get('total_return', 0))

            # 4.1 胜率分 (20分)
            win_rate = best_strategy.get('win_rate', 0)
            if win_rate >= 65:
                scores['strategy_winrate'] = 20
            elif win_rate >= 55:
                scores['strategy_winrate'] = 16
            elif win_rate >= 50:
                scores['strategy_winrate'] = 12
            elif win_rate >= 40:
                scores['strategy_winrate'] = 8
            else:
                scores['strategy_winrate'] = 4

            # 4.2 收益率分 (10分)
            annual_return = best_strategy.get('annual_return', 0)
            if annual_return > 30:
                scores['strategy_return'] = 10
            elif annual_return > 15:
                scores['strategy_return'] = 8
            elif annual_return > 5:
                scores['strategy_return'] = 6
            elif annual_return > 0:
                scores['strategy_return'] = 4
            else:
                scores['strategy_return'] = 0

            # 4.3 夏普比率分 (10分)
            sharpe = best_strategy.get('sharpe_ratio', 0)
            if sharpe > 2:
                scores['strategy_sharpe'] = 10
            elif sharpe > 1:
                scores['strategy_sharpe'] = 8
            elif sharpe > 0.5:
                scores['strategy_sharpe'] = 6
            elif sharpe > 0:
                scores['strategy_sharpe'] = 4
            else:
                scores['strategy_sharpe'] = 0

            scores['strategy_text'] = f"{best_strategy['strategy_name']}: 胜率{win_rate:.0f}%/年化{annual_return:+.1f}%/SR{sharpe:.1f}"
            scores['best_strategy'] = best_strategy['strategy_name']
        else:
            scores['strategy_winrate'] = 0
            scores['strategy_return'] = 0
            scores['strategy_sharpe'] = 0
            scores['strategy_text'] = "无有效交易"
            scores['best_strategy'] = None
    else:
        scores['strategy_winrate'] = 0
        scores['strategy_return'] = 0
        scores['strategy_sharpe'] = 0
        scores['strategy_text'] = "无回测数据"
        scores['best_strategy'] = None

    # 总分
    scores['total'] = (scores['trend'] + scores['rsi'] + scores['volume'] +
                       scores.get('strategy_winrate', 0) +
                       scores.get('strategy_return', 0) +
                       scores.get('strategy_sharpe', 0))

    # 评级
    total = scores['total']
    if total >= 80:
        scores['grade'] = 'A'
        scores['advice'] = '强烈推荐买入'
        scores['action'] = 'buy'
    elif total >= 65:
        scores['grade'] = 'B'
        scores['advice'] = '可以买入'
        scores['action'] = 'buy'
    elif total >= 50:
        scores['grade'] = 'C'
        scores['advice'] = '谨慎买入，控制仓位'
        scores['action'] = 'hold'
    elif total >= 35:
        scores['grade'] = 'D'
        scores['advice'] = '观望为主'
        scores['action'] = 'wait'
    else:
        scores['grade'] = 'E'
        scores['advice'] = '不建议买入'
        scores['action'] = 'avoid'

    return scores


if __name__ == "__main__":
    print("回测 000001.SZ...")
    result = backtest_stock("000001.SZ", years=3)
    if result:
        print(f"\n股票: {result['name']} ({result['ts_code']})")
        print(f"形态: {result['pattern_desc']}")

        print(f"\n{'='*50}")
        print("策略回测对比")
        print('='*50)

        for name, strat in result['strategies'].items():
            print(f"\n【{name}】")
            print(f"  交易次数: {strat['trade_count']} 笔")
            print(f"  总收益: {strat['total_return']:+.2f}%  年化: {strat['annual_return']:+.2f}%")
            print(f"  胜率: {strat['win_rate']:.1f}% ({strat['win_count']}/{strat['trade_count']})")
            print(f"  最大回撤: {strat['max_drawdown']:.2f}%")
            print(f"  夏普比率: {strat['sharpe_ratio']:.2f}")

        scores = calc_score(result)
        if scores:
            print(f"\n{'='*50}")
            print(f"综合评分: {scores['total']}分 ({scores['grade']}级)")
            print(f"建议: {scores['advice']}")
            print('='*50)
