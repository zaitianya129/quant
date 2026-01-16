"""
技术指标计算模块
包含均线(MA)、MACD、RSI、成交量指标
"""
import pandas as pd
import numpy as np


def calc_ma(df: pd.DataFrame, periods: list = [5, 10, 20, 60]) -> pd.DataFrame:
    """
    计算移动平均线

    Args:
        df: 包含 close 列的 DataFrame
        periods: 均线周期列表

    Returns:
        添加了 MA{period} 列的 DataFrame
    """
    df = df.copy()
    for period in periods:
        df[f'MA{period}'] = df['close'].rolling(window=period).mean()
    return df


def calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    计算MACD指标

    Args:
        df: 包含 close 列的 DataFrame
        fast: 快速EMA周期，默认12
        slow: 慢速EMA周期，默认26
        signal: 信号线周期，默认9

    Returns:
        添加了 DIF, DEA, MACD 列的 DataFrame
        - DIF: 快速EMA - 慢速EMA
        - DEA: DIF的EMA (信号线)
        - MACD: (DIF - DEA) * 2 (柱状图)
    """
    df = df.copy()

    # 计算EMA
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()

    # DIF = 快线 - 慢线
    df['DIF'] = ema_fast - ema_slow

    # DEA = DIF的9日EMA
    df['DEA'] = df['DIF'].ewm(span=signal, adjust=False).mean()

    # MACD柱 = (DIF - DEA) * 2
    df['MACD'] = (df['DIF'] - df['DEA']) * 2

    return df


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    计算RSI指标

    Args:
        df: 包含 close 列的 DataFrame
        period: RSI周期，默认14

    Returns:
        添加了 RSI 列的 DataFrame
        RSI < 30: 超卖
        RSI > 70: 超买
    """
    df = df.copy()

    # 计算价格变化
    delta = df['close'].diff()

    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    # 计算平均涨跌幅（使用EMA）
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()

    # 计算RS和RSI
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df


def calc_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """
    计算布林带指标

    Args:
        df: 包含 close 列的 DataFrame
        period: 中轨周期，默认20
        std_dev: 标准差倍数，默认2

    Returns:
        添加了布林带指标的 DataFrame:
        - BOLL_MID: 中轨 (20日均线)
        - BOLL_UP: 上轨 (中轨 + 2倍标准差)
        - BOLL_DOWN: 下轨 (中轨 - 2倍标准差)
        - BOLL_WIDTH: 带宽 (上轨-下轨)/中轨
        - BOLL_POS: 价格在带中的位置 (0-1, 0=下轨, 1=上轨)
    """
    df = df.copy()

    # 中轨 = N日均线
    df['BOLL_MID'] = df['close'].rolling(window=period).mean()

    # 标准差
    rolling_std = df['close'].rolling(window=period).std()

    # 上轨和下轨
    df['BOLL_UP'] = df['BOLL_MID'] + std_dev * rolling_std
    df['BOLL_DOWN'] = df['BOLL_MID'] - std_dev * rolling_std

    # 带宽
    df['BOLL_WIDTH'] = (df['BOLL_UP'] - df['BOLL_DOWN']) / df['BOLL_MID']

    # 价格位置 (0=下轨, 1=上轨)
    df['BOLL_POS'] = (df['close'] - df['BOLL_DOWN']) / (df['BOLL_UP'] - df['BOLL_DOWN'])

    return df


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """
    计算KDJ指标

    Args:
        df: 包含 high, low, close 列的 DataFrame
        n: RSV周期，默认9
        m1: K值平滑周期，默认3
        m2: D值平滑周期，默认3

    Returns:
        添加了KDJ指标的 DataFrame:
        - K: 快速随机指标
        - D: 慢速随机指标
        - J: J值 = 3K - 2D
        K/D < 20: 超卖区
        K/D > 80: 超买区
    """
    df = df.copy()

    # 计算N日内最高价和最低价
    low_n = df['low'].rolling(window=n).min()
    high_n = df['high'].rolling(window=n).max()

    # RSV = (收盘价 - N日最低) / (N日最高 - N日最低) * 100
    rsv = (df['close'] - low_n) / (high_n - low_n) * 100

    # K = RSV的M1日移动平均 (使用EMA平滑)
    # D = K的M2日移动平均
    # 初始值设为50
    k_values = []
    d_values = []
    k_prev = 50
    d_prev = 50

    for i in range(len(df)):
        if pd.isna(rsv.iloc[i]):
            k_values.append(np.nan)
            d_values.append(np.nan)
        else:
            k = (m1 - 1) / m1 * k_prev + 1 / m1 * rsv.iloc[i]
            d = (m2 - 1) / m2 * d_prev + 1 / m2 * k
            k_values.append(k)
            d_values.append(d)
            k_prev = k
            d_prev = d

    df['K'] = k_values
    df['D'] = d_values
    df['J'] = 3 * df['K'] - 2 * df['D']

    return df


def calc_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算成交量相关指标

    Args:
        df: 包含 vol 列的 DataFrame

    Returns:
        添加了成交量指标的 DataFrame:
        - VOL_MA5: 5日均量
        - VOL_RATIO: 量比（当日成交量/5日均量）
    """
    df = df.copy()

    # 5日均量
    df['VOL_MA5'] = df['vol'].rolling(window=5).mean()

    # 量比
    df['VOL_RATIO'] = df['vol'] / df['VOL_MA5']

    return df


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算所有技术指标

    Args:
        df: 原始K线数据

    Returns:
        包含所有指标的 DataFrame
    """
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_rsi(df)
    df = calc_bollinger(df)
    df = calc_kdj(df)
    df = calc_volume_indicators(df)
    return df


def get_indicator_status(df: pd.DataFrame) -> dict:
    """
    获取最新指标状态

    Args:
        df: 包含指标的 DataFrame

    Returns:
        当前指标状态字典
    """
    if df.empty or len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # 均线状态
    ma5 = latest.get('MA5', np.nan)
    ma20 = latest.get('MA20', np.nan)
    ma5_prev = prev.get('MA5', np.nan)
    ma20_prev = prev.get('MA20', np.nan)

    # 判断均线交叉
    ma_cross = None
    if not (np.isnan(ma5) or np.isnan(ma20) or np.isnan(ma5_prev) or np.isnan(ma20_prev)):
        if ma5_prev <= ma20_prev and ma5 > ma20:
            ma_cross = 'golden'  # 金叉
        elif ma5_prev >= ma20_prev and ma5 < ma20:
            ma_cross = 'dead'  # 死叉

    # MACD状态
    dif = latest.get('DIF', np.nan)
    dea = latest.get('DEA', np.nan)
    dif_prev = prev.get('DIF', np.nan)
    dea_prev = prev.get('DEA', np.nan)

    # 判断MACD交叉
    macd_cross = None
    if not (np.isnan(dif) or np.isnan(dea) or np.isnan(dif_prev) or np.isnan(dea_prev)):
        if dif_prev <= dea_prev and dif > dea:
            macd_cross = 'golden'  # 金叉
        elif dif_prev >= dea_prev and dif < dea:
            macd_cross = 'dead'  # 死叉

    # 布林带状态
    boll_up = latest.get('BOLL_UP', np.nan)
    boll_mid = latest.get('BOLL_MID', np.nan)
    boll_down = latest.get('BOLL_DOWN', np.nan)
    boll_pos = latest.get('BOLL_POS', np.nan)

    boll_status = None
    if not np.isnan(boll_pos):
        if boll_pos <= 0:
            boll_status = 'below_lower'  # 跌破下轨
        elif boll_pos < 0.2:
            boll_status = 'near_lower'   # 接近下轨
        elif boll_pos > 1:
            boll_status = 'above_upper'  # 突破上轨
        elif boll_pos > 0.8:
            boll_status = 'near_upper'   # 接近上轨
        else:
            boll_status = 'middle'       # 中间区域

    # KDJ状态
    k = latest.get('K', np.nan)
    d = latest.get('D', np.nan)
    j = latest.get('J', np.nan)
    k_prev = prev.get('K', np.nan)
    d_prev = prev.get('D', np.nan)

    # KDJ交叉
    kdj_cross = None
    if not (np.isnan(k) or np.isnan(d) or np.isnan(k_prev) or np.isnan(d_prev)):
        if k_prev <= d_prev and k > d:
            kdj_cross = 'golden'  # 金叉
        elif k_prev >= d_prev and k < d:
            kdj_cross = 'dead'    # 死叉

    # KDJ区域
    kdj_zone = None
    if not np.isnan(k):
        if k < 20:
            kdj_zone = 'oversold'    # 超卖
        elif k > 80:
            kdj_zone = 'overbought'  # 超买
        else:
            kdj_zone = 'normal'

    return {
        'close': latest['close'],
        'MA5': ma5,
        'MA10': latest.get('MA10', np.nan),
        'MA20': ma20,
        'MA60': latest.get('MA60', np.nan),
        'DIF': dif,
        'DEA': dea,
        'MACD': latest.get('MACD', np.nan),
        'ma_cross': ma_cross,
        'macd_cross': macd_cross,
        'ma5_above_ma20': ma5 > ma20 if not (np.isnan(ma5) or np.isnan(ma20)) else None,
        'dif_above_dea': dif > dea if not (np.isnan(dif) or np.isnan(dea)) else None,
        # 布林带
        'BOLL_UP': boll_up,
        'BOLL_MID': boll_mid,
        'BOLL_DOWN': boll_down,
        'BOLL_POS': boll_pos,
        'boll_status': boll_status,
        # KDJ
        'K': k,
        'D': d,
        'J': j,
        'kdj_cross': kdj_cross,
        'kdj_zone': kdj_zone,
        'k_above_d': k > d if not (np.isnan(k) or np.isnan(d)) else None
    }


if __name__ == "__main__":
    # 测试
    from data import get_stock_data

    df = get_stock_data("000001.SZ")
    df = calc_all_indicators(df)
    print(df.tail())
    print("\n指标状态:")
    status = get_indicator_status(df)
    for k, v in status.items():
        print(f"  {k}: {v}")
