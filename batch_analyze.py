#!/usr/bin/env python3
"""
批量股票分析脚本
分析多只股票的最佳策略，筛选出买点机会
"""
import sys
from datetime import datetime
from data import get_stock_data, get_stock_name, get_latest_price
from indicators import calc_all_indicators
from backtest import backtest_stock, calc_score


def analyze_batch(stock_codes):
    """
    批量分析股票

    Args:
        stock_codes: 股票代码列表

    Returns:
        分析结果列表
    """
    results = []

    for i, code in enumerate(stock_codes, 1):
        print(f"\n[{i}/{len(stock_codes)}] 分析 {code}...")

        try:
            # 回测分析
            result = backtest_stock(code, years=3)

            if not result or not result.get('strategies'):
                print(f"  ❌ {code} 数据不足")
                continue

            # 获取最佳策略
            strategies = result.get('strategies', {})
            valid_strategies = [s for s in strategies.values() if s.get('trade_count', 0) > 0]

            if not valid_strategies:
                print(f"  ❌ {code} 无有效策略")
                continue

            best_strategy = max(valid_strategies, key=lambda s: s.get('total_return', 0))

            # 获取当前信号
            current_signals = result.get('current_signals', {})

            # 计算综合评分
            scores = calc_score(result)

            # 获取最新价格
            latest = get_latest_price(code)
            current_price = latest['close'] if latest else 0

            # 判断是否在买点
            is_buy_point = False
            buy_reason = []

            # 判断标准1: 最佳策略当前给出买入信号
            best_strategy_name = best_strategy['strategy_name']
            signal_map = {
                'MA+MACD': 'signal',
                'Bollinger': 'signal_boll',
                'KDJ': 'signal_kdj',
                'RSI': 'signal_rsi',
                'Volume': 'signal_volume',
                'Combined': 'signal_combined'
            }

            best_signal_key = signal_map.get(best_strategy_name)
            if best_signal_key:
                best_signal = current_signals.get(best_signal_key, 0)
                if best_signal >= 1:
                    is_buy_point = True
                    buy_reason.append(f"最佳策略{best_strategy_name}买入信号")

            # 判断标准2: 综合策略买入
            combined_signal = current_signals.get('signal_combined', 0)
            if combined_signal >= 1:
                is_buy_point = True
                buy_reason.append(f"综合策略买入(评分{current_signals.get('score_combined', 0):.0f})")

            # 判断标准3: RSI超卖且RSI策略胜率高
            current_rsi = result.get('current_rsi')
            rsi_strategy = strategies.get('RSI', {})
            if current_rsi and current_rsi < 30 and rsi_strategy.get('win_rate', 0) >= 60:
                is_buy_point = True
                buy_reason.append(f"RSI超卖({current_rsi:.0f}),历史胜率{rsi_strategy['win_rate']:.0f}%")

            # 判断标准4: 综合评分高且接近买点
            if scores and scores['total'] >= 65 and combined_signal == 0:
                # B级以上，虽然没有明确买入信号，但可以关注
                buy_reason.append(f"综合评分{scores['total']}分({scores['grade']}级),可关注")

            results.append({
                'code': code,
                'name': result['name'],
                'price': current_price,
                'best_strategy': best_strategy_name,
                'best_return': best_strategy['annual_return'],
                'best_winrate': best_strategy['win_rate'],
                'best_sharpe': best_strategy['sharpe_ratio'],
                'current_rsi': current_rsi,
                'score': scores['total'] if scores else 0,
                'grade': scores['grade'] if scores else 'N/A',
                'is_buy_point': is_buy_point,
                'buy_reason': ', '.join(buy_reason) if buy_reason else '观望',
                'combined_signal': combined_signal,
                'best_signal': best_signal if best_signal_key else 0
            })

            status = "🔥 买点" if is_buy_point else "⏸️  观望"
            print(f"  {status} | 最佳:{best_strategy_name} | 评分:{scores['total'] if scores else 0}分 | 价格:{current_price:.2f}元")

        except Exception as e:
            print(f"  ❌ {code} 分析失败: {e}")
            continue

    return results


def print_report(results):
    """打印分析报告"""

    # 筛选买点股票
    buy_points = [r for r in results if r['is_buy_point']]
    watch_list = [r for r in results if r['score'] >= 65 and not r['is_buy_point']]

    print("\n" + "="*100)
    print(f"批量分析完成 | 总计:{len(results)}只 | 买点:{len(buy_points)}只 | 关注:{len(watch_list)}只")
    print("="*100)

    # 按综合评分排序
    buy_points.sort(key=lambda x: x['score'], reverse=True)
    watch_list.sort(key=lambda x: x['score'], reverse=True)

    if buy_points:
        print(f"\n🔥 买点股票 ({len(buy_points)}只)")
        print("-"*100)
        print(f"{'代码':<12} {'名称':<10} {'价格':<8} {'评分':<6} {'最佳策略':<12} {'年化':<8} {'胜率':<6} {'买入理由':<40}")
        print("-"*100)

        for r in buy_points:
            print(f"{r['code']:<12} {r['name']:<10} {r['price']:>7.2f} "
                  f"{r['score']:>3}分({r['grade']}) {r['best_strategy']:<12} "
                  f"{r['best_return']:>6.1f}% {r['best_winrate']:>5.0f}% "
                  f"{r['buy_reason']:<40}")

    if watch_list:
        print(f"\n👀 高分关注 ({len(watch_list)}只)")
        print("-"*100)
        print(f"{'代码':<12} {'名称':<10} {'价格':<8} {'评分':<6} {'最佳策略':<12} {'年化':<8} {'胜率':<6} {'备注':<40}")
        print("-"*100)

        for r in watch_list:
            print(f"{r['code']:<12} {r['name']:<10} {r['price']:>7.2f} "
                  f"{r['score']:>3}分({r['grade']}) {r['best_strategy']:<12} "
                  f"{r['best_return']:>6.1f}% {r['best_winrate']:>5.0f}% "
                  f"等待买入信号")

    # 输出CSV格式（方便导入Excel）
    print(f"\n\n📊 CSV格式输出（可复制到Excel）:")
    print("-"*100)
    print("代码,名称,价格,评分,等级,最佳策略,年化收益,胜率,夏普,RSI,买点,理由")
    for r in results:
        print(f"{r['code']},{r['name']},{r['price']:.2f},{r['score']},{r['grade']},"
              f"{r['best_strategy']},{r['best_return']:.1f}%,{r['best_winrate']:.0f}%,"
              f"{r['best_sharpe']:.2f},{r['current_rsi'] if r['current_rsi'] else 'N/A'},"
              f"{'是' if r['is_buy_point'] else '否'},{r['buy_reason']}")

    print("\n" + "="*100)


def main():
    """主函数"""
    # 股票列表（已去除港股和重复项）
    stock_codes = [
        '300058.SZ',  # 蓝色光标
        '601360.SH',  # 三六零
        '301159.SZ',  # 三维天地
        '003007.SZ',  # 直真科技
        '002279.SZ',  # 久其软件
        '300520.SZ',  # 科大国创
        '688258.SH',  # 卓易信息
        '600797.SH',  # 浙大网新
        '300725.SZ',  # 药石科技
        '301230.SZ',  # 泓博医药
        '688246.SH',  # 嘉和美康
        '002044.SZ',  # 美年健康
        '603108.SH',  # 润达医疗
        '300253.SZ',  # 卫宁健康
        '834021.BJ',  # 流金科技
        '301396.SZ',  # 宏景科技
        '300634.SZ',  # 彩讯股份
        '600734.SH',  # 实达集团
        '872190.BJ',  # 雷神科技
        '300063.SZ',  # 天龙集团
        '002131.SZ',  # 利欧股份
        '002354.SZ',  # 天娱数科
        '002400.SZ',  # 省广集团
        '000676.SZ',  # 智度股份
        '301171.SZ',  # 易点天下
        '603444.SH',  # 吉比特
        '002555.SZ',  # 三七互娱
        '002602.SZ',  # 世纪华通
        '002624.SZ',  # 完美世界
        '688365.SH',  # 光云科技
        '300448.SZ',  # 浩云科技
        '688060.SH',  # 云涌科技
        '301316.SZ',  # 慧博云通
        '600602.SH',  # 云赛智联
        '002152.SZ',  # 广电运通
        '002739.SZ',  # 万达电影
        '300133.SZ',  # 华策影视
        '601595.SH',  # 上海电影
        '000681.SZ',  # 视觉中国
        '300251.SZ',  # 光线传媒
        '600986.SH',  # 浙文互联
        '600570.SH',  # 恒生电子
        '002657.SZ',  # 中科金财
        '300465.SZ',  # 高伟达
        '603383.SH',  # 顶点软件
        '600446.SH',  # 金证股份
        '000555.SZ',  # 神州信息
        '688111.SH',  # 金山办公
        '688615.SH',  # 合合信息
        '603039.SH',  # 泛微网络
        '688095.SH',  # 福昕软件
        '300170.SZ',  # 汉得信息
    ]

    print(f"\n{'='*100}")
    print(f"批量股票买点分析")
    print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"股票数量: {len(stock_codes)}只（已过滤港股）")
    print(f"{'='*100}")

    # 执行批量分析
    results = analyze_batch(stock_codes)

    # 打印报告
    if results:
        print_report(results)
    else:
        print("\n❌ 没有成功分析任何股票")


if __name__ == "__main__":
    main()
