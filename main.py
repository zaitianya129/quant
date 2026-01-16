#!/usr/bin/env python3
"""
A股量化买卖点判断系统
主程序入口
"""
import sys
import argparse
from datetime import datetime

from data import get_stock_data, get_stock_name, get_latest_price
from indicators import calc_all_indicators
from backtest import backtest_stock, calc_score


def normalize_code(code: str) -> str:
    """
    标准化股票代码格式

    支持输入:
    - 000001 -> 000001.SZ
    - 600000 -> 600000.SH
    - 000001.SZ -> 000001.SZ
    """
    code = code.strip().upper()

    # 已经是完整格式
    if '.' in code:
        return code

    # 根据代码前缀判断市场
    if code.startswith('6'):
        return f"{code}.SH"  # 上海
    elif code.startswith(('0', '3')):
        return f"{code}.SZ"  # 深圳
    elif code.startswith('8') or code.startswith('4'):
        return f"{code}.BJ"  # 北交所
    else:
        return f"{code}.SZ"  # 默认深圳


def analyze_stock(ts_code: str, mode='all', selected_strategies=None):
    """分析单只股票并输出结果

    Args:
        ts_code: 股票代码
        mode: 显示模式 'all'(全部) 或 'combined'(仅综合策略) 或 'best'(最佳策略) 或 'selected'(选定策略)
        selected_strategies: 指定显示的策略列表
    """

    ts_code = normalize_code(ts_code)
    name = get_stock_name(ts_code)

    print(f"\n{'='*50}")
    print(f"股票: {ts_code} ({name})")
    print('='*50)

    # 获取数据并计算指标
    print("正在分析...")
    df = get_stock_data(ts_code)

    if df.empty:
        print("错误: 无法获取股票数据，请检查代码是否正确")
        return

    df = calc_all_indicators(df)

    # 当前状态
    latest = get_latest_price(ts_code)
    if latest:
        print(f"\n当前价格: {latest['close']:.2f} 元 ({latest['date']})")

    # 基于形态回测
    result = backtest_stock(ts_code, years=3)

    if result and result.get('strategies'):
        # === 综合策略简洁模式 ===
        if mode == 'combined':
            scores = calc_score(result)
            if scores:
                grade = scores['grade']
                total = scores['total']
                grade_colors = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'E': '🔴'}
                color = grade_colors.get(grade, '')

                print(f"\n综合评分: {color} {total}分 ({grade}级) - {scores['advice']}")

            # 综合策略信号和评分
            current_signals = result.get('current_signals', {})
            combined_signal = current_signals.get('signal_combined', 0)
            combined_score = current_signals.get('score_combined', 0)

            signal_text = {2: '🔥 强烈买入', 1: '🔺 买入', -1: '🔻 卖出', -2: '💀 强烈卖出', 0: '⏸️  观望'}
            print(f"综合策略: {signal_text.get(combined_signal, '未知')}  (信号评分: {combined_score:.0f}/100)")

            # 综合策略回测表现
            strategies = result.get('strategies', {})
            combined_strat = strategies.get('Combined')
            if combined_strat and combined_strat.get('trade_count', 0) > 0:
                print(f"\n历史表现:")
                print(f"  交易次数: {combined_strat['trade_count']} 笔")
                print(f"  总收益: {combined_strat['total_return']:+.2f}%  年化: {combined_strat['annual_return']:+.2f}%")
                print(f"  胜率: {combined_strat['win_rate']:.1f}% ({combined_strat['win_count']}/{combined_strat['trade_count']})")
                print(f"  最大回撤: {combined_strat['max_drawdown']:.2f}%")
                print(f"  夏普比率: {combined_strat['sharpe_ratio']:.2f}")

            print()
            return

        # === 最佳策略模式 ===
        if mode == 'best':
            strategies = result.get('strategies', {})
            valid_strategies = [s for s in strategies.values() if s.get('trade_count', 0) > 0]
            if valid_strategies:
                best_strategy = max(valid_strategies, key=lambda s: s.get('total_return', 0))

                scores = calc_score(result)
                if scores:
                    grade = scores['grade']
                    total = scores['total']
                    grade_colors = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'E': '🔴'}
                    color = grade_colors.get(grade, '')
                    print(f"\n综合评分: {color} {total}分 ({grade}级) - {scores['advice']}")

                print(f"\n最佳策略: 【{best_strategy['strategy_name']}】")
                print(f"  交易次数: {best_strategy['trade_count']} 笔")
                print(f"  总收益: {best_strategy['total_return']:+.2f}%  年化: {best_strategy['annual_return']:+.2f}%")
                print(f"  胜率: {best_strategy['win_rate']:.1f}% ({best_strategy['win_count']}/{best_strategy['trade_count']})")
                print(f"  盈亏比: 盈{best_strategy['avg_win']:+.2f}% / 亏{best_strategy['avg_loss']:.2f}%")
                print(f"  最大回撤: {best_strategy['max_drawdown']:.2f}%")
                print(f"  夏普比率: {best_strategy['sharpe_ratio']:.2f}")

            print()
            return

        # === 选定策略模式 ===
        if mode == 'selected' and selected_strategies:
            scores = calc_score(result)
            if scores:
                grade = scores['grade']
                total = scores['total']
                grade_colors = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'E': '🔴'}
                color = grade_colors.get(grade, '')
                print(f"\n综合评分: {color} {total}分 ({grade}级) - {scores['advice']}")

            # 只显示选定的策略
            strategies = result.get('strategies', {})
            print(f"\n{'─'*50}")
            print(f"选定策略回测对比 (近{result['years']}年)")
            print('─'*50)

            for strategy_name in selected_strategies:
                strat = strategies.get(strategy_name)
                if strat:
                    trade_count = strat.get('trade_count', 0)
                    if trade_count > 0:
                        print(f"\n【{strategy_name}】")
                        print(f"  交易次数: {trade_count} 笔")
                        print(f"  总收益: {strat['total_return']:+.2f}%  年化: {strat['annual_return']:+.2f}%")
                        print(f"  胜率: {strat['win_rate']:.1f}% ({strat['win_count']}/{trade_count})")
                        print(f"  盈亏比: 盈{strat['avg_win']:+.2f}% / 亏{strat['avg_loss']:.2f}%")
                        print(f"  最大回撤: {strat['max_drawdown']:.2f}%")
                        print(f"  夏普比率: {strat['sharpe_ratio']:.2f}")
                        print(f"  平均持仓: {strat['avg_hold_days']:.1f} 天")
                    else:
                        print(f"\n【{strategy_name}】 无有效交易信号")
                else:
                    print(f"\n【{strategy_name}】 策略不存在")

            # 显示这些策略的当前信号
            current_signals = result.get('current_signals', {})
            if current_signals:
                print(f"\n{'─'*50}")
                print("当前信号状态")
                print('─'*50)
                signal_text = {2: '🔥 强烈买入', 1: '🔺 买入', -1: '🔻 卖出', -2: '💀 强烈卖出', 0: '⏸️  观望'}

                strategy_signal_map = {
                    'MA+MACD': 'signal',
                    'Bollinger': 'signal_boll',
                    'KDJ': 'signal_kdj',
                    'RSI': 'signal_rsi',
                    'Volume': 'signal_volume',
                    'Combined': 'signal_combined'
                }

                for strategy_name in selected_strategies:
                    signal_key = strategy_signal_map.get(strategy_name)
                    if signal_key:
                        signal_val = current_signals.get(signal_key, 0)
                        print(f"  {strategy_name:12s}: {signal_text.get(signal_val, '未知')}")

            print()
            return

        # === 完整模式 (默认) ===
        # 计算综合评分
        scores = calc_score(result)

        if scores:
            # 显示综合评分（醒目）
            grade = scores['grade']
            total = scores['total']
            grade_colors = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'E': '🔴'}
            color = grade_colors.get(grade, '')

            print(f"\n{'█'*50}")
            print(f"  综合评分: {color} {total}分 ({grade}级) - {scores['advice']}")
            print(f"{'█'*50}")

            # 评分明细
            print(f"\n评分明细:")
            print(f"  趋势 ({scores['trend']}/30): {scores['trend_text']}")
            print(f"  RSI  ({scores['rsi']}/20): {scores['rsi_text']}")
            print(f"  量能 ({scores['volume']}/10): {scores['volume_text']}")
            print(f"  策略 ({scores.get('strategy_winrate', 0) + scores.get('strategy_return', 0) + scores.get('strategy_sharpe', 0)}/40): {scores.get('strategy_text', '无数据')}")

        # 显示策略回测对比
        strategies = result.get('strategies', {})
        if strategies:
            print(f"\n{'─'*50}")
            print(f"策略回测对比 (近{result['years']}年)")
            print('─'*50)

            for name, strat in strategies.items():
                trade_count = strat.get('trade_count', 0)
                if trade_count > 0:
                    print(f"\n【{name}】")
                    print(f"  交易次数: {trade_count} 笔")
                    print(f"  总收益: {strat['total_return']:+.2f}%  年化: {strat['annual_return']:+.2f}%")
                    print(f"  胜率: {strat['win_rate']:.1f}% ({strat['win_count']}/{trade_count})")
                    print(f"  盈亏比: 盈{strat['avg_win']:+.2f}% / 亏{strat['avg_loss']:.2f}%")
                    print(f"  最大回撤: {strat['max_drawdown']:.2f}%")
                    print(f"  夏普比率: {strat['sharpe_ratio']:.2f}")
                    print(f"  平均持仓: {strat['avg_hold_days']:.1f} 天")
                else:
                    print(f"\n【{name}】 无有效交易信号")

        # 显示当前信号状态
        current_signals = result.get('current_signals', {})
        if current_signals:
            print(f"\n{'─'*50}")
            print("当前信号状态")
            print('─'*50)
            signal_text = {2: '🔥 强烈买入', 1: '🔺 买入', -1: '🔻 卖出', -2: '💀 强烈卖出', 0: '⏸️  观望'}
            print(f"  MA+MACD:  {signal_text.get(current_signals.get('signal', 0), '未知')}")
            print(f"  布林带:   {signal_text.get(current_signals.get('signal_boll', 0), '未知')}")
            print(f"  KDJ:      {signal_text.get(current_signals.get('signal_kdj', 0), '未知')}")
            print(f"  RSI:      {signal_text.get(current_signals.get('signal_rsi', 0), '未知')}")
            print(f"  成交量:   {signal_text.get(current_signals.get('signal_volume', 0), '未知')}")

            # 综合策略 (醒目显示)
            combined_signal = current_signals.get('signal_combined', 0)
            combined_score = current_signals.get('score_combined', 0)
            print(f"\n  {'━'*46}")
            print(f"  【综合策略】 {signal_text.get(combined_signal, '未知')}  (评分: {combined_score:.0f})")
            print(f"  {'━'*46}")

    else:
        print("\n回测数据不足，无法给出建议")

    print()


def main():
    """主函数"""
    # 策略名称映射（支持别名）
    STRATEGY_MAP = {
        'macd': 'MA+MACD',
        'ma': 'MA+MACD',
        'boll': 'Bollinger',
        'bollinger': 'Bollinger',
        'kdj': 'KDJ',
        'rsi': 'RSI',
        'volume': 'Volume',
        'vol': 'Volume',
        'combined': 'Combined',
        'combo': 'Combined'
    }

    AVAILABLE_STRATEGIES = ['MA+MACD', 'Bollinger', 'KDJ', 'RSI', 'Volume', 'Combined']

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='A股量化买卖点判断系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  基本使用:
    python main.py 000001                    # 显示所有策略详情
    python main.py 000001 600000             # 分析多只股票

  简洁模式:
    python main.py 000001 -c                 # 只显示综合策略
    python main.py 000001 -b                 # 只显示最佳策略

  指定策略:
    python main.py 000001 -s macd            # 只显示MA+MACD策略
    python main.py 000001 -s kdj,rsi         # 显示KDJ和RSI策略
    python main.py 000001 -s boll,combined   # 显示布林带和综合策略
    python main.py 000001 300450 -s combined # 多股票+综合策略

  策略别名:
    macd, ma      -> MA+MACD
    boll          -> Bollinger
    kdj           -> KDJ
    rsi           -> RSI
    vol, volume   -> Volume
    combo         -> Combined

  列出所有策略:
    python main.py --list                    # 显示所有可用策略
        '''
    )
    parser.add_argument('codes', nargs='*', help='股票代码 (如: 000001, 600000.SH)')
    parser.add_argument('-c', '--combined', action='store_true', help='只显示综合策略(简洁模式)')
    parser.add_argument('-b', '--best', action='store_true', help='只显示最佳策略')
    parser.add_argument('-s', '--strategy', type=str, help='指定策略 (逗号分隔多个策略，如: macd,kdj,rsi)')
    parser.add_argument('--list', action='store_true', help='列出所有可用策略')

    args = parser.parse_args()

    # 列出策略
    if args.list:
        print("\n可用策略列表:")
        print("="*50)
        for i, strategy in enumerate(AVAILABLE_STRATEGIES, 1):
            print(f"{i}. {strategy}")

        print("\n策略别名:")
        print("="*50)
        alias_groups = {
            'MA+MACD': ['macd', 'ma'],
            'Bollinger': ['boll', 'bollinger'],
            'KDJ': ['kdj'],
            'RSI': ['rsi'],
            'Volume': ['vol', 'volume'],
            'Combined': ['combined', 'combo']
        }
        for strategy, aliases in alias_groups.items():
            print(f"{strategy:12s} -> {', '.join(aliases)}")
        print()
        return

    # 确定显示模式和策略选择
    selected_strategies = None
    if args.strategy:
        mode = 'selected'
        # 解析策略列表
        strategy_inputs = [s.strip().lower() for s in args.strategy.split(',')]
        selected_strategies = []
        for s_input in strategy_inputs:
            strategy_name = STRATEGY_MAP.get(s_input)
            if strategy_name:
                selected_strategies.append(strategy_name)
            else:
                print(f"警告: 未知策略 '{s_input}'，使用 --list 查看可用策略")

        if not selected_strategies:
            print("错误: 未指定有效策略")
            return
    elif args.combined:
        mode = 'combined'
    elif args.best:
        mode = 'best'
    else:
        mode = 'all'

    print("\n" + "="*50)
    print("  A股量化买卖点判断系统")
    if mode == 'combined':
        print("  模式: 综合策略")
    elif mode == 'best':
        print("  模式: 最佳策略")
    elif mode == 'selected':
        print(f"  模式: 指定策略 ({', '.join(selected_strategies)})")
    else:
        print("  策略: 均线交叉 + MACD")
    print("="*50)

    # 检查命令行参数
    if args.codes:
        for code in args.codes:
            analyze_stock(code, mode, selected_strategies)
        return

    # 交互模式
    print("\n输入股票代码进行分析 (如: 000001 或 600000.SH)")
    print("输入 q 退出\n")

    while True:
        try:
            code = input("请输入股票代码: ").strip()

            if code.lower() in ('q', 'quit', 'exit'):
                print("再见!")
                break

            if not code:
                continue

            # 支持多个代码，空格分隔
            codes = code.split()
            for c in codes:
                analyze_stock(c, mode, selected_strategies)

        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            print(f"错误: {e}")


if __name__ == "__main__":
    main()
