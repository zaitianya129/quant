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

# 验证码存储（内存中，生产环境建议用Redis）
captcha_store = {}

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
    """生成图形验证码"""
    # 生成随机验证码文本（4位字母数字）
    chars = string.ascii_uppercase + string.digits
    # 排除容易混淆的字符
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '').replace('L', '')
    code = ''.join(random.choices(chars, k=4))

    # 生成验证码图片
    image = ImageCaptcha(width=120, height=40)
    data = image.generate(code)

    # 转换为base64
    img_base64 = base64.b64encode(data.getvalue()).decode()

    # 生成唯一ID
    captcha_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    # 存储验证码（5分钟有效）
    captcha_store[captcha_id] = {
        'code': code,
        'expires': datetime.now() + timedelta(minutes=5)
    }

    # 清理过期验证码
    cleanup_expired_captcha()

    return captcha_id, img_base64


def verify_captcha(captcha_id, code):
    """验证验证码"""
    if not captcha_id or not code:
        return False

    captcha_data = captcha_store.get(captcha_id)
    if not captcha_data:
        return False

    # 检查是否过期
    if datetime.now() > captcha_data['expires']:
        del captcha_store[captcha_id]
        return False

    # 验证（不区分大小写）
    is_valid = captcha_data['code'].upper() == code.upper()

    # 用后即销毁
    del captcha_store[captcha_id]

    return is_valid


def cleanup_expired_captcha():
    """清理过期的验证码"""
    now = datetime.now()
    expired_keys = [k for k, v in captcha_store.items() if now > v['expires']]
    for key in expired_keys:
        del captcha_store[key]


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
    captcha_id = data.get('captcha_id', '')
    captcha_code = data.get('captcha_code', '')

    # 验证验证码
    if not verify_captcha(captcha_id, captcha_code):
        return jsonify({
            'success': False,
            'message': '验证码错误或已过期'
        }), 400

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
    captcha_id = data.get('captcha_id', '')
    captcha_code = data.get('captcha_code', '')

    # 验证验证码
    if not verify_captcha(captcha_id, captcha_code):
        return jsonify({
            'success': False,
            'message': '验证码错误或已过期'
        }), 400

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
