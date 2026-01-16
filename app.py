#!/usr/bin/env python3
"""
A股量化分析系统 - Web应用
基于Flask框架
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
from datetime import datetime, timedelta

from backtest import backtest_stock, calc_score
from data import get_stock_name, get_latest_price
from auth import auth_bp, login_required

app = Flask(__name__)
CORS(app)

# 配置
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JSON_AS_ASCII'] = False  # 支持中文
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # Session有效期24小时

# 注册认证蓝图
app.register_blueprint(auth_bp)


# ==================== 路由 ====================

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/api/analyze/<stock_code>', methods=['GET'])
@login_required
def analyze_stock(stock_code):
    """
    分析单只股票

    GET /api/analyze/000001
    GET /api/analyze/000001?years=3
    """
    try:
        # 标准化股票代码
        from main import normalize_code
        stock_code = normalize_code(stock_code)

        # 获取参数
        years = int(request.args.get('years', 3))

        # 执行回测分析
        result = backtest_stock(stock_code, years=years)

        if not result:
            return jsonify({
                'success': False,
                'message': '无法获取股票数据，请检查代码是否正确'
            }), 404

        # 获取最新价格
        latest = get_latest_price(stock_code)

        # 计算综合评分
        scores = calc_score(result)

        # 构造返回数据
        response = {
            'success': True,
            'data': {
                'ts_code': result['ts_code'],
                'name': result['name'],
                'current_price': latest['close'] if latest else 0,
                'current_date': latest['date'] if latest else '',
                'score': scores,
                'strategies': result['strategies'],
                'current_signals': result['current_signals'],
                'current_pattern': result['current_pattern'],
                'pattern_desc': result['pattern_desc']
            }
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'分析失败: {str(e)}'
        }), 500


@app.route('/api/batch_analyze', methods=['POST'])
@login_required
def batch_analyze():
    """
    批量分析股票

    POST /api/batch_analyze
    Body: {"codes": ["000001", "600000", "601318"]}
    """
    try:
        data = request.get_json()
        stock_codes = data.get('codes', [])

        if not stock_codes:
            return jsonify({
                'success': False,
                'message': '请提供股票代码列表'
            }), 400

        results = []
        for code in stock_codes[:20]:  # 限制最多20只
            try:
                from main import normalize_code
                code = normalize_code(code)

                result = backtest_stock(code, years=3)
                if result:
                    scores = calc_score(result)
                    latest = get_latest_price(code)

                    # 找最佳策略
                    strategies = result.get('strategies', {})
                    valid_strategies = [s for s in strategies.values() if s.get('trade_count', 0) > 0]
                    best_strategy = max(valid_strategies, key=lambda s: s.get('total_return', 0)) if valid_strategies else None

                    results.append({
                        'code': code,
                        'name': result['name'],
                        'price': latest['close'] if latest else 0,
                        'score': scores['total'] if scores else 0,
                        'grade': scores['grade'] if scores else 'N/A',
                        'best_strategy': best_strategy['strategy_name'] if best_strategy else 'N/A',
                        'annual_return': best_strategy['annual_return'] if best_strategy else 0,
                        'win_rate': best_strategy['win_rate'] if best_strategy else 0
                    })
            except Exception as e:
                print(f"分析 {code} 失败: {e}")
                continue

        return jsonify({
            'success': True,
            'data': results
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'批量分析失败: {str(e)}'
        }), 500


@app.route('/api/strategies', methods=['GET'])
def get_strategies():
    """获取可用策略列表"""
    strategies = [
        {'id': 'MA+MACD', 'name': 'MA+MACD', 'description': '均线交叉 + MACD金叉死叉'},
        {'id': 'Bollinger', 'name': '布林带', 'description': '布林带触底反弹和触顶回落'},
        {'id': 'KDJ', 'name': 'KDJ', 'description': 'KDJ超卖超买区金叉死叉'},
        {'id': 'RSI', 'name': 'RSI', 'description': 'RSI超卖超买反弹'},
        {'id': 'Volume', 'name': '成交量突破', 'description': '放量突破前期高点'},
        {'id': 'Combined', 'name': '综合策略', 'description': '多策略加权组合'}
    ]
    return jsonify({
        'success': True,
        'data': strategies
    })


@app.route('/api/search', methods=['GET'])
def search_stock():
    """
    搜索股票（模糊查询）

    GET /api/search?q=平安
    """
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({
            'success': False,
            'message': '请输入搜索关键词'
        }), 400

    # 这里简化处理，实际应该从数据库搜索
    # 可以预先加载股票列表到内存或Redis
    results = []

    # 示例：如果是代码，直接返回
    if query.isdigit():
        from main import normalize_code
        code = normalize_code(query)
        name = get_stock_name(code)
        if name != code:  # 找到了
            results.append({'code': code, 'name': name})

    return jsonify({
        'success': True,
        'data': results
    })


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口（用于监控）"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': '接口不存在'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': '服务器内部错误'
    }), 500


# ==================== 启动 ====================

if __name__ == '__main__':
    # 开发模式运行
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )
