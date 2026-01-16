#!/usr/bin/env python3
"""
用户认证模块
- 用户注册/登录
- 图形验证码生成
- Session管理
"""
import os
import sqlite3
import random
import string
import io
import base64
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from captcha.image import ImageCaptcha

# 创建蓝图
auth_bp = Blueprint('auth', __name__)

# 配置
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
USER_DB_PATH = os.path.join(CACHE_DIR, 'users.db')

# 验证码存储路径（使用SQLite，解决多进程问题）
CAPTCHA_DB_PATH = os.path.join(CACHE_DIR, 'captcha.db')


def get_captcha_db():
    """获取验证码数据库连接"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(CAPTCHA_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_captcha_db():
    """初始化验证码数据库"""
    conn = get_captcha_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS captchas (
            captcha_id VARCHAR(32) PRIMARY KEY,
            code VARCHAR(10) NOT NULL,
            expires_at DATETIME NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# ==================== 数据库操作 ====================

def get_db():
    """获取数据库连接"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化用户数据库"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME,
            login_attempts INTEGER DEFAULT 0,
            locked_until DATETIME
        )
    ''')

    conn.commit()
    conn.close()


def get_user_by_username(username):
    """根据用户名获取用户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user


def create_user(username, password):
    """创建新用户"""
    conn = get_db()
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)

    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            (username, password_hash)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_login_attempts(username, attempts, locked_until=None):
    """更新登录失败次数"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET login_attempts = ?, locked_until = ? WHERE username = ?',
        (attempts, locked_until, username)
    )
    conn.commit()
    conn.close()


def update_last_login(username):
    """更新最后登录时间"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET last_login = ?, login_attempts = 0, locked_until = NULL WHERE username = ?',
        (datetime.now(), username)
    )
    conn.commit()
    conn.close()


# ==================== 验证码 ====================

def generate_captcha():
    """生成数字验证码"""
    # 生成4位数字验证码
    code = ''.join(random.choices(string.digits, k=4))

    # 生成验证码图片
    image = ImageCaptcha(width=120, height=40)
    data = image.generate(code)

    # 转换为base64
    img_base64 = base64.b64encode(data.getvalue()).decode()

    # 生成唯一ID
    captcha_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    # 存储到数据库（5分钟有效）
    expires_at = datetime.now() + timedelta(minutes=5)
    conn = get_captcha_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO captchas (captcha_id, code, expires_at) VALUES (?, ?, ?)',
        (captcha_id, code, expires_at.isoformat())
    )
    conn.commit()
    conn.close()

    # 清理过期验证码
    cleanup_expired_captcha()

    return captcha_id, img_base64


def verify_captcha(captcha_id, code):
    """验证验证码"""
    if not captcha_id or not code:
        return False

    conn = get_captcha_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM captchas WHERE captcha_id = ?', (captcha_id,))
    captcha_data = cursor.fetchone()

    if not captcha_data:
        conn.close()
        return False

    # 检查是否过期
    expires_at = datetime.fromisoformat(captcha_data['expires_at'])
    if datetime.now() > expires_at:
        cursor.execute('DELETE FROM captchas WHERE captcha_id = ?', (captcha_id,))
        conn.commit()
        conn.close()
        return False

    # 验证
    is_valid = captcha_data['code'] == code

    # 用后即销毁
    cursor.execute('DELETE FROM captchas WHERE captcha_id = ?', (captcha_id,))
    conn.commit()
    conn.close()

    return is_valid


def cleanup_expired_captcha():
    """清理过期的验证码"""
    conn = get_captcha_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM captchas WHERE expires_at < ?', (datetime.now().isoformat(),))
    conn.commit()
    conn.close()


# ==================== 登录状态检查 ====================

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'message': '请先登录',
                'code': 'UNAUTHORIZED'
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """获取当前登录用户"""
    if 'user_id' not in session:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, created_at, last_login FROM users WHERE id = ?',
                   (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return user


# ==================== API 路由 ====================

@auth_bp.route('/api/auth/captcha', methods=['GET'])
def get_captcha():
    """获取图形验证码"""
    captcha_id, img_base64 = generate_captcha()

    return jsonify({
        'success': True,
        'data': {
            'captcha_id': captcha_id,
            'image': f'data:image/png;base64,{img_base64}'
        }
    })


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()

    username = data.get('username', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    # 验证用户名
    if not username or len(username) < 3 or len(username) > 20:
        return jsonify({
            'success': False,
            'message': '用户名长度应为3-20个字符'
        }), 400

    if not username.isalnum():
        return jsonify({
            'success': False,
            'message': '用户名只能包含字母和数字'
        }), 400

    # 验证密码
    if len(password) < 8:
        return jsonify({
            'success': False,
            'message': '密码长度至少8位'
        }), 400

    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return jsonify({
            'success': False,
            'message': '密码必须包含字母和数字'
        }), 400

    if password != confirm_password:
        return jsonify({
            'success': False,
            'message': '两次密码输入不一致'
        }), 400

    # 检查用户名是否已存在
    if get_user_by_username(username):
        return jsonify({
            'success': False,
            'message': '用户名已被注册'
        }), 400

    # 创建用户
    if create_user(username, password):
        return jsonify({
            'success': True,
            'message': '注册成功，请登录'
        })
    else:
        return jsonify({
            'success': False,
            'message': '注册失败，请稍后重试'
        }), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()

    username = data.get('username', '').strip()
    password = data.get('password', '')

    # 获取用户
    user = get_user_by_username(username)

    if not user:
        return jsonify({
            'success': False,
            'message': '用户名或密码错误'
        }), 401

    # 检查是否被锁定
    if user['locked_until']:
        locked_until = datetime.fromisoformat(user['locked_until'])
        if datetime.now() < locked_until:
            remaining = int((locked_until - datetime.now()).total_seconds() / 60) + 1
            return jsonify({
                'success': False,
                'message': f'账户已锁定，请{remaining}分钟后再试'
            }), 403

    # 验证密码
    if not check_password_hash(user['password_hash'], password):
        # 增加失败次数
        attempts = user['login_attempts'] + 1

        if attempts >= 5:
            # 锁定15分钟
            locked_until = datetime.now() + timedelta(minutes=15)
            update_login_attempts(username, attempts, locked_until.isoformat())
            return jsonify({
                'success': False,
                'message': '密码错误次数过多，账户已锁定15分钟'
            }), 403
        else:
            update_login_attempts(username, attempts)
            return jsonify({
                'success': False,
                'message': f'用户名或密码错误，还剩{5 - attempts}次机会'
            }), 401

    # 登录成功
    session.clear()
    session['user_id'] = user['id']
    session['username'] = user['username']
    session.permanent = True

    update_last_login(username)

    return jsonify({
        'success': True,
        'message': '登录成功',
        'data': {
            'username': user['username']
        }
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({
        'success': True,
        'message': '已退出登录'
    })


@auth_bp.route('/api/auth/status', methods=['GET'])
def auth_status():
    """检查登录状态"""
    user = get_current_user()

    if user:
        return jsonify({
            'success': True,
            'data': {
                'logged_in': True,
                'username': user['username']
            }
        })
    else:
        return jsonify({
            'success': True,
            'data': {
                'logged_in': False
            }
        })


# ==================== 页面路由 ====================

@auth_bp.route('/login')
def login_page():
    """登录页面"""
    return render_template('login.html')


@auth_bp.route('/register')
def register_page():
    """注册页面"""
    return render_template('register.html')


# 初始化数据库
init_db()
init_captcha_db()
