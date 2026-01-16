"""
数据获取和本地缓存模块
使用 tushare 获取A股日线数据，SQLite 缓存避免重复请求
"""
import os
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import tushare as ts
from config import TUSHARE_TOKEN, CACHE_DIR, DB_PATH

# 初始化 tushare
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def init_db():
    """初始化数据库表"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 日线数据表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_data (
            ts_code TEXT,
            trade_date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            vol REAL,
            amount REAL,
            PRIMARY KEY (ts_code, trade_date)
        )
    """)

    # 股票基本信息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_info (
            ts_code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            list_date TEXT
        )
    """)

    # 缓存元数据表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache_meta (
            ts_code TEXT PRIMARY KEY,
            last_update TEXT,
            start_date TEXT,
            end_date TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_stock_name(ts_code: str) -> str:
    """获取股票名称"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM stock_info WHERE ts_code = ?", (ts_code,))
    result = cursor.fetchone()

    if result:
        conn.close()
        return result[0]

    # 从 tushare 获取
    try:
        df = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,list_date')
        if not df.empty:
            row = df.iloc[0]
            cursor.execute(
                "INSERT OR REPLACE INTO stock_info VALUES (?, ?, ?, ?)",
                (row['ts_code'], row['name'], row.get('industry', ''), row.get('list_date', ''))
            )
            conn.commit()
            conn.close()
            return row['name']
    except Exception as e:
        print(f"获取股票信息失败: {e}")

    conn.close()
    return ts_code


def get_stock_data(ts_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    获取股票日线数据(后复权)

    Args:
        ts_code: 股票代码，如 '000001.SZ'
        start_date: 开始日期 YYYYMMDD，默认3年前
        end_date: 结束日期 YYYYMMDD，默认今天

    Returns:
        DataFrame: 包含 trade_date, open, high, low, close, vol 等列
    """
    init_db()

    # 默认日期范围：3年
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365*3+30)).strftime('%Y%m%d')

    # 检查缓存
    conn = sqlite3.connect(DB_PATH)

    # 查询缓存的数据范围
    cursor = conn.cursor()
    cursor.execute("SELECT start_date, end_date, last_update FROM cache_meta WHERE ts_code = ?", (ts_code,))
    meta = cursor.fetchone()

    need_update = True
    if meta:
        cached_start, cached_end, last_update = meta
        last_update_date = datetime.strptime(last_update, '%Y%m%d')
        # 如果缓存覆盖请求范围且今天已更新，直接用缓存
        if cached_start <= start_date and cached_end >= end_date:
            if last_update == datetime.now().strftime('%Y%m%d'):
                need_update = False

    if need_update:
        print(f"从 tushare 获取 {ts_code} 数据...")
        try:
            # 获取前复权日线数据（最新价=实际价格）
            df = ts.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                adj='qfq'  # 前复权
            )

            if df is not None and not df.empty:
                # 存入数据库
                for _, row in df.iterrows():
                    cursor.execute("""
                        INSERT OR REPLACE INTO daily_data
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row['ts_code'], row['trade_date'],
                        row['open'], row['high'], row['low'], row['close'],
                        row['vol'], row['amount']
                    ))

                # 更新缓存元数据
                cursor.execute("""
                    INSERT OR REPLACE INTO cache_meta VALUES (?, ?, ?, ?)
                """, (ts_code, datetime.now().strftime('%Y%m%d'), start_date, end_date))

                conn.commit()
                print(f"已缓存 {len(df)} 条数据")
        except Exception as e:
            print(f"获取数据失败: {e}")

    # 从缓存读取
    query = """
        SELECT trade_date, open, high, low, close, vol, amount
        FROM daily_data
        WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ?
        ORDER BY trade_date ASC
    """
    df = pd.read_sql_query(query, conn, params=(ts_code, start_date, end_date))
    conn.close()

    if df.empty:
        print(f"警告: {ts_code} 无数据")
        return df

    # 转换日期格式
    df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
    df.set_index('trade_date', inplace=True)

    return df


def get_latest_price(ts_code: str) -> dict:
    """获取最新实际价格（不复权）"""
    try:
        # 获取不复权的实际价格
        df = pro.daily(ts_code=ts_code, limit=1)
        if df is not None and not df.empty:
            row = df.iloc[0]
            return {
                'date': f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}",
                'close': row['close'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'vol': row['vol']
            }
    except Exception as e:
        print(f"获取最新价格失败: {e}")

    # 备用：从缓存获取（后复权价格）
    df = get_stock_data(ts_code)
    if df.empty:
        return None
    latest = df.iloc[-1]
    return {
        'date': df.index[-1].strftime('%Y-%m-%d'),
        'close': latest['close'],
        'open': latest['open'],
        'high': latest['high'],
        'low': latest['low'],
        'vol': latest['vol']
    }


if __name__ == "__main__":
    # 测试
    df = get_stock_data("000001.SZ")
    print(df.tail())
    print(f"\n股票名称: {get_stock_name('000001.SZ')}")
