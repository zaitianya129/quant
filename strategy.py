"""
买卖信号策略模块
策略: 均线交叉 + MACD + 布林带 + KDJ 组合
"""
import pandas as pd
import numpy as np


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成买卖信号

    策略逻辑:
    原有策略:
    - 买入信号(1): MA5上穿MA20 且 MACD金叉(DIF上穿DEA)
    - 卖出信号(-1): MA5下穿MA20 或 MACD死叉

    布林带策略:
    - 买入信号(1): 价格触及下轨后回升 (BOLL_POS从<0.1回到>0.1)
    - 卖出信号(-1): 价格触及上轨后回落 (BOLL_POS从>0.9回到<0.9)

    KDJ策略:
    - 买入信号(1): K上穿D 且 K<30 (超卖区金叉)
    - 卖出信号(-1): K下穿D 且 K>70 (超买区死叉)

    RSI策略:
    - 买入信号(1): RSI<30超卖且开始反弹
    - 卖出信号(-1): RSI>70超买且开始回落

    成交量突破策略:
    - 买入信号(1): 价格突破20日最高 + 量比>2(放量突破)
    - 卖出信号(-1): 价格跌破20日最低 或 缩量

    Args:
        df: 包含技术指标的 DataFrame

    Returns:
        添加了 signal, signal_boll, signal_kdj, signal_rsi, signal_volume 列的 DataFrame
    """
    df = df.copy()

    # 初始化信号列
    df['signal'] = 0         # 原有MA+MACD策略
    df['signal_boll'] = 0    # 布林带策略
    df['signal_kdj'] = 0     # KDJ策略
    df['signal_rsi'] = 0     # RSI策略
    df['signal_volume'] = 0  # 成交量突破策略
    df['signal_combined'] = 0  # 综合策略

    # 确保有足够的数据
    if len(df) < 2:
        return df

    # ========== 原有 MA + MACD 策略 ==========
    df['ma5_above'] = df['MA5'] > df['MA20']
    ma5_above_prev = df['ma5_above'].shift(1).astype(bool).fillna(False)
    df['ma5_cross_up'] = df['ma5_above'] & ~ma5_above_prev
    df['ma5_cross_down'] = ~df['ma5_above'] & ma5_above_prev

    df['dif_above'] = df['DIF'] > df['DEA']
    dif_above_prev = df['dif_above'].shift(1).astype(bool).fillna(False)
    df['dif_cross_up'] = df['dif_above'] & ~dif_above_prev
    df['dif_cross_down'] = ~df['dif_above'] & dif_above_prev

    # ========== 布林带策略 ==========
    df['boll_pos_prev'] = df['BOLL_POS'].shift(1)
    # 触底反弹: 前一天在下轨以下或接近下轨，今天回到带内
    df['boll_bounce_up'] = (df['boll_pos_prev'] < 0.1) & (df['BOLL_POS'] >= 0.1) & (df['BOLL_POS'] < 0.5)
    # 触顶回落: 前一天在上轨以上或接近上轨，今天回落
    df['boll_bounce_down'] = (df['boll_pos_prev'] > 0.9) & (df['BOLL_POS'] <= 0.9) & (df['BOLL_POS'] > 0.5)

    # ========== KDJ策略 ==========
    df['k_above_d'] = df['K'] > df['D']
    k_above_prev = df['k_above_d'].shift(1).astype(bool).fillna(False)
    df['kdj_cross_up'] = df['k_above_d'] & ~k_above_prev
    df['kdj_cross_down'] = ~df['k_above_d'] & k_above_prev

    # ========== RSI策略 ==========
    df['rsi_prev'] = df['RSI'].shift(1)
    df['rsi_oversold'] = df['RSI'] < 30  # 超卖区
    df['rsi_overbought'] = df['RSI'] > 70  # 超买区
    df['rsi_bounce_up'] = (df['rsi_prev'] < df['RSI']) & df['rsi_oversold']  # 超卖区反弹
    df['rsi_bounce_down'] = (df['rsi_prev'] > df['RSI']) & df['rsi_overbought']  # 超买区回落

    # ========== 成交量突破策略 ==========
    # 计算20日最高价和最低价
    df['high_20'] = df['high'].rolling(window=20).max()
    df['low_20'] = df['low'].rolling(window=20).min()
    df['high_20_prev'] = df['high_20'].shift(1)
    df['low_20_prev'] = df['low_20'].shift(1)

    # 突破判断
    df['breakout_high'] = df['close'] > df['high_20_prev']  # 突破前期高点
    df['breakout_low'] = df['close'] < df['low_20_prev']    # 跌破前期低点
    df['volume_surge'] = df['VOL_RATIO'] > 2.0               # 放量
    df['volume_shrink'] = df['VOL_RATIO'] < 0.5              # 缩量

    for i in range(1, len(df)):
        # ===== 原有策略信号 =====
        if df['ma5_cross_up'].iloc[i] and df['dif_above'].iloc[i]:
            df.iloc[i, df.columns.get_loc('signal')] = 1
        elif df['dif_cross_up'].iloc[i] and df['ma5_above'].iloc[i]:
            df.iloc[i, df.columns.get_loc('signal')] = 1
        elif df['ma5_cross_down'].iloc[i] or df['dif_cross_down'].iloc[i]:
            df.iloc[i, df.columns.get_loc('signal')] = -1

        # ===== 布林带策略信号 =====
        if df['boll_bounce_up'].iloc[i]:
            df.iloc[i, df.columns.get_loc('signal_boll')] = 1
        elif df['boll_bounce_down'].iloc[i]:
            df.iloc[i, df.columns.get_loc('signal_boll')] = -1

        # ===== KDJ策略信号 =====
        k_val = df['K'].iloc[i]
        if df['kdj_cross_up'].iloc[i] and k_val < 30:
            df.iloc[i, df.columns.get_loc('signal_kdj')] = 1
        elif df['kdj_cross_up'].iloc[i] and k_val < 50:
            # 中位金叉，弱买入信号
            df.iloc[i, df.columns.get_loc('signal_kdj')] = 1
        elif df['kdj_cross_down'].iloc[i] and k_val > 70:
            df.iloc[i, df.columns.get_loc('signal_kdj')] = -1
        elif df['kdj_cross_down'].iloc[i] and k_val > 50:
            # 中位死叉，弱卖出信号
            df.iloc[i, df.columns.get_loc('signal_kdj')] = -1

        # ===== RSI策略信号 =====
        if df['rsi_bounce_up'].iloc[i]:
            # RSI超卖区反弹
            df.iloc[i, df.columns.get_loc('signal_rsi')] = 1
        elif df['rsi_bounce_down'].iloc[i]:
            # RSI超买区回落
            df.iloc[i, df.columns.get_loc('signal_rsi')] = -1

        # ===== 成交量突破策略信号 =====
        if df['breakout_high'].iloc[i] and df['volume_surge'].iloc[i]:
            # 放量突破
            df.iloc[i, df.columns.get_loc('signal_volume')] = 1
        elif df['breakout_low'].iloc[i] or df['volume_shrink'].iloc[i]:
            # 跌破低点或缩量
            df.iloc[i, df.columns.get_loc('signal_volume')] = -1

    # 清理临时列
    temp_cols = ['ma5_above', 'ma5_cross_up', 'ma5_cross_down',
                 'dif_above', 'dif_cross_up', 'dif_cross_down',
                 'boll_pos_prev', 'boll_bounce_up', 'boll_bounce_down',
                 'k_above_d', 'kdj_cross_up', 'kdj_cross_down',
                 'rsi_prev', 'rsi_oversold', 'rsi_overbought', 'rsi_bounce_up', 'rsi_bounce_down',
                 'high_20', 'low_20', 'high_20_prev', 'low_20_prev',
                 'breakout_high', 'breakout_low', 'volume_surge', 'volume_shrink']
    df.drop(temp_cols, axis=1, inplace=True)

    # ========== 综合策略 (加权评分) ==========
    # 权重分配：MA+MACD(30) + 布林带(20) + 成交量(20) + KDJ(15) + RSI(15) = 100
    df['score_combined'] = (
        df['signal'] * 30 +         # MA+MACD
        df['signal_boll'] * 20 +    # 布林带
        df['signal_volume'] * 20 +  # 成交量突破
        df['signal_kdj'] * 15 +     # KDJ
        df['signal_rsi'] * 15       # RSI
    )

    # 根据总分生成综合信号
    # 强买入(2): >= 60, 买入(1): >= 40, 观望(0): -40~40, 卖出(-1): <= -40, 强卖出(-2): <= -60
    df['signal_combined'] = 0
    df.loc[df['score_combined'] >= 60, 'signal_combined'] = 2
    df.loc[(df['score_combined'] >= 40) & (df['score_combined'] < 60), 'signal_combined'] = 1
    df.loc[(df['score_combined'] > -40) & (df['score_combined'] < 40), 'signal_combined'] = 0
    df.loc[(df['score_combined'] <= -40) & (df['score_combined'] > -60), 'signal_combined'] = -1
    df.loc[df['score_combined'] <= -60, 'signal_combined'] = -2

    return df


def get_current_signal(df: pd.DataFrame) -> dict:
    """
    获取当前交易日的信号判断

    Args:
        df: 包含信号的 DataFrame

    Returns:
        当前信号详情，包括三个策略的独立信号
    """
    if df.empty or len(df) < 2:
        return {'signal': 0, 'signal_text': '数据不足', 'reasons': []}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = latest.get('signal', 0)
    signal_boll = latest.get('signal_boll', 0)
    signal_kdj = latest.get('signal_kdj', 0)
    signal_rsi = latest.get('signal_rsi', 0)
    signal_volume = latest.get('signal_volume', 0)
    signal_combined = latest.get('signal_combined', 0)
    score_combined = latest.get('score_combined', 0)
    reasons = []

    # 分析信号原因
    ma5 = latest.get('MA5', np.nan)
    ma20 = latest.get('MA20', np.nan)
    ma5_prev = prev.get('MA5', np.nan)
    ma20_prev = prev.get('MA20', np.nan)

    dif = latest.get('DIF', np.nan)
    dea = latest.get('DEA', np.nan)
    dif_prev = prev.get('DIF', np.nan)
    dea_prev = prev.get('DEA', np.nan)

    # 检查均线交叉
    if not np.isnan(ma5) and not np.isnan(ma20):
        if ma5_prev <= ma20_prev and ma5 > ma20:
            reasons.append(f"MA5({ma5:.2f}) 上穿 MA20({ma20:.2f})")
        elif ma5_prev >= ma20_prev and ma5 < ma20:
            reasons.append(f"MA5({ma5:.2f}) 下穿 MA20({ma20:.2f})")
        elif ma5 > ma20:
            reasons.append(f"MA5({ma5:.2f}) 在 MA20({ma20:.2f}) 上方")
        else:
            reasons.append(f"MA5({ma5:.2f}) 在 MA20({ma20:.2f}) 下方")

    # 检查MACD交叉
    if not np.isnan(dif) and not np.isnan(dea):
        if dif_prev <= dea_prev and dif > dea:
            reasons.append(f"MACD金叉: DIF({dif:.4f}) 上穿 DEA({dea:.4f})")
        elif dif_prev >= dea_prev and dif < dea:
            reasons.append(f"MACD死叉: DIF({dif:.4f}) 下穿 DEA({dea:.4f})")
        elif dif > dea:
            reasons.append(f"DIF({dif:.4f}) > DEA({dea:.4f})")
        else:
            reasons.append(f"DIF({dif:.4f}) < DEA({dea:.4f})")

    # 布林带分析
    boll_reasons = []
    boll_up = latest.get('BOLL_UP', np.nan)
    boll_mid = latest.get('BOLL_MID', np.nan)
    boll_down = latest.get('BOLL_DOWN', np.nan)
    boll_pos = latest.get('BOLL_POS', np.nan)
    boll_pos_prev = prev.get('BOLL_POS', np.nan)

    if not np.isnan(boll_pos):
        if boll_pos < 0:
            boll_reasons.append(f"价格跌破下轨({boll_down:.2f})")
        elif boll_pos < 0.2:
            boll_reasons.append(f"价格接近下轨({boll_down:.2f})，位置{boll_pos*100:.0f}%")
        elif boll_pos > 1:
            boll_reasons.append(f"价格突破上轨({boll_up:.2f})")
        elif boll_pos > 0.8:
            boll_reasons.append(f"价格接近上轨({boll_up:.2f})，位置{boll_pos*100:.0f}%")
        else:
            boll_reasons.append(f"价格在布林带中间，位置{boll_pos*100:.0f}%")

        # 触底反弹/触顶回落
        if not np.isnan(boll_pos_prev):
            if boll_pos_prev < 0.1 and boll_pos >= 0.1:
                boll_reasons.append("触底反弹信号")
            elif boll_pos_prev > 0.9 and boll_pos <= 0.9:
                boll_reasons.append("触顶回落信号")

    # KDJ分析
    kdj_reasons = []
    k = latest.get('K', np.nan)
    d = latest.get('D', np.nan)
    j = latest.get('J', np.nan)
    k_prev = prev.get('K', np.nan)
    d_prev = prev.get('D', np.nan)

    if not np.isnan(k) and not np.isnan(d):
        # KDJ交叉
        if k_prev <= d_prev and k > d:
            if k < 30:
                kdj_reasons.append(f"KDJ超卖区金叉 K({k:.1f}) D({d:.1f})")
            else:
                kdj_reasons.append(f"KDJ金叉 K({k:.1f}) D({d:.1f})")
        elif k_prev >= d_prev and k < d:
            if k > 70:
                kdj_reasons.append(f"KDJ超买区死叉 K({k:.1f}) D({d:.1f})")
            else:
                kdj_reasons.append(f"KDJ死叉 K({k:.1f}) D({d:.1f})")
        else:
            # 显示当前KDJ状态
            if k < 20:
                kdj_reasons.append(f"KDJ超卖 K({k:.1f}) D({d:.1f}) J({j:.1f})")
            elif k > 80:
                kdj_reasons.append(f"KDJ超买 K({k:.1f}) D({d:.1f}) J({j:.1f})")
            else:
                kdj_reasons.append(f"KDJ正常 K({k:.1f}) D({d:.1f}) J({j:.1f})")

    # 信号文本
    signal_text_map = {
        2: "强烈买入",
        1: "买入信号",
        -1: "卖出信号",
        -2: "强烈卖出",
        0: "无信号"
    }

    return {
        'signal': signal,
        'signal_text': signal_text_map.get(signal, "未知"),
        'signal_boll': signal_boll,
        'signal_boll_text': signal_text_map.get(signal_boll, "未知"),
        'signal_kdj': signal_kdj,
        'signal_kdj_text': signal_text_map.get(signal_kdj, "未知"),
        'signal_rsi': signal_rsi,
        'signal_rsi_text': signal_text_map.get(signal_rsi, "未知"),
        'signal_volume': signal_volume,
        'signal_volume_text': signal_text_map.get(signal_volume, "未知"),
        'signal_combined': signal_combined,
        'signal_combined_text': signal_text_map.get(signal_combined, "未知"),
        'score_combined': score_combined,
        'reasons': reasons,
        'boll_reasons': boll_reasons,
        'kdj_reasons': kdj_reasons,
        'close': latest['close'],
        'date': df.index[-1].strftime('%Y-%m-%d')
    }


if __name__ == "__main__":
    # 测试
    from data import get_stock_data
    from indicators import calc_all_indicators

    df = get_stock_data("000001.SZ")
    df = calc_all_indicators(df)
    df = generate_signals(df)

    # 统计信号数量
    print("=" * 50)
    print("信号统计")
    print("=" * 50)

    print("\n【MA+MACD策略】")
    buy_signals = (df['signal'] == 1).sum()
    sell_signals = (df['signal'] == -1).sum()
    print(f"  买入信号: {buy_signals} 次")
    print(f"  卖出信号: {sell_signals} 次")

    print("\n【布林带策略】")
    buy_boll = (df['signal_boll'] == 1).sum()
    sell_boll = (df['signal_boll'] == -1).sum()
    print(f"  买入信号: {buy_boll} 次")
    print(f"  卖出信号: {sell_boll} 次")

    print("\n【KDJ策略】")
    buy_kdj = (df['signal_kdj'] == 1).sum()
    sell_kdj = (df['signal_kdj'] == -1).sum()
    print(f"  买入信号: {buy_kdj} 次")
    print(f"  卖出信号: {sell_kdj} 次")

    print("\n【RSI策略】")
    buy_rsi = (df['signal_rsi'] == 1).sum()
    sell_rsi = (df['signal_rsi'] == -1).sum()
    print(f"  买入信号: {buy_rsi} 次")
    print(f"  卖出信号: {sell_rsi} 次")

    print("\n【成交量突破策略】")
    buy_volume = (df['signal_volume'] == 1).sum()
    sell_volume = (df['signal_volume'] == -1).sum()
    print(f"  买入信号: {buy_volume} 次")
    print(f"  卖出信号: {sell_volume} 次")

    print("\n【综合策略】")
    strong_buy = (df['signal_combined'] == 2).sum()
    buy_combined = (df['signal_combined'] == 1).sum()
    sell_combined = (df['signal_combined'] == -1).sum()
    strong_sell = (df['signal_combined'] == -2).sum()
    print(f"  强烈买入: {strong_buy} 次")
    print(f"  买入信号: {buy_combined} 次")
    print(f"  卖出信号: {sell_combined} 次")
    print(f"  强烈卖出: {strong_sell} 次")

    # 当前信号
    print("\n" + "=" * 50)
    print("当前信号分析")
    print("=" * 50)
    current = get_current_signal(df)

    print(f"\n日期: {current['date']}")
    print(f"收盘价: {current['close']:.2f}")

    print(f"\n【MA+MACD】{current['signal_text']}")
    for reason in current['reasons']:
        print(f"  - {reason}")

    print(f"\n【布林带】{current['signal_boll_text']}")
    for reason in current['boll_reasons']:
        print(f"  - {reason}")

    print(f"\n【KDJ】{current['signal_kdj_text']}")
    for reason in current['kdj_reasons']:
        print(f"  - {reason}")

    print(f"\n【RSI】{current['signal_rsi_text']}")
    rsi_val = df.iloc[-1].get('RSI')
    if pd.notna(rsi_val):
        if rsi_val < 30:
            print(f"  - RSI超卖区({rsi_val:.1f})，可能反弹")
        elif rsi_val > 70:
            print(f"  - RSI超买区({rsi_val:.1f})，可能回调")
        else:
            print(f"  - RSI正常区({rsi_val:.1f})")

    print(f"\n【成交量突破】{current['signal_volume_text']}")
    vol_ratio = df.iloc[-1].get('VOL_RATIO')
    if pd.notna(vol_ratio):
        if vol_ratio > 2:
            print(f"  - 放量突破(量比{vol_ratio:.1f})")
        elif vol_ratio < 0.5:
            print(f"  - 缩量(量比{vol_ratio:.1f})")
        else:
            print(f"  - 量能正常(量比{vol_ratio:.1f})")

    print(f"\n{'='*50}")
    print(f"【综合策略】{current['signal_combined_text']}")
    print(f"  综合评分: {current['score_combined']:.0f} 分")
    print(f"  信号构成:")
    print(f"    MA+MACD:  {current['signal']} × 30 = {current['signal']*30}")
    print(f"    布林带:   {current['signal_boll']} × 20 = {current['signal_boll']*20}")
    print(f"    成交量:   {current['signal_volume']} × 20 = {current['signal_volume']*20}")
    print(f"    KDJ:      {current['signal_kdj']} × 15 = {current['signal_kdj']*15}")
    print(f"    RSI:      {current['signal_rsi']} × 15 = {current['signal_rsi']*15}")
    print('='*50)
