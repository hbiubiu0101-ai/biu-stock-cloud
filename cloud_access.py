"""Shared-workspace login and server-only Secrets access."""
import hashlib
import hmac
import threading
import time
from collections import deque
import streamlit as st
from cloud_backend import CloudError, CloudStore


def secret(name):
    try:
        return str(st.secrets.get(name, '')).strip()
    except (FileNotFoundError, KeyError):
        return ''


def _fingerprint():
    return hashlib.sha256((secret('APP_USERNAME') + '\0' + secret('APP_PASSWORD')).encode()).hexdigest()


def authorized():
    return (bool(secret('APP_USERNAME')) and len(secret('APP_PASSWORD')) >= 12
        and hmac.compare_digest(st.session_state.get('_auth_stamp', ''), _fingerprint())
        and time.time() < st.session_state.get('_auth_until', 0))


def require_session():
    if not authorized():
        raise CloudError('登录已过期，请刷新网页重新登录。')


@st.cache_resource
def _login_attempts():
    # Process-wide throttle, not browser-only: reconnecting cannot reset it.
    return threading.Lock(), deque()


def _sign_in(username, password):
    lock, attempts = _login_attempts()
    now = time.monotonic()
    with lock:
        while attempts and now - attempts[0] >= 60:
            attempts.popleft()
        if len(attempts) >= 10:
            return '尝试次数过多，请一分钟后再试。'
        user_ok = hmac.compare_digest(username.encode(), secret('APP_USERNAME').encode())
        pass_ok = hmac.compare_digest(password.encode(), secret('APP_PASSWORD').encode())
        if not (user_ok and pass_ok):
            attempts.append(now)
            return '账号或密码不正确。'
    st.session_state['_auth_stamp'] = _fingerprint()
    st.session_state['_auth_until'] = time.time() + 12 * 3600
    return ''


def _login_submit():
    st.session_state['_login_error'] = _sign_in(
        st.session_state.get('_login_user', ''), st.session_state.get('_login_password', ''))
    st.session_state.pop('_login_password', None)


def _logout():
    for key in list(st.session_state):
        del st.session_state[key]


def login_gate():
    required = ('APP_USERNAME', 'APP_PASSWORD', 'SUPABASE_URL', 'SUPABASE_SECRET_KEY')
    missing = [key for key in required if not secret(key)]
    if missing:
        st.title('Biu · 云端配置')
        st.info('请在 Streamlit → App settings → Secrets 填写：' + '、'.join(missing))
        st.caption('不要把密钥写入 GitHub。配置完成并保存后刷新本页。')
        st.stop()
    if len(secret('APP_PASSWORD')) < 12:
        st.error('请在 Secrets 把 APP_PASSWORD 设置为至少12位的独立强密码。')
        st.stop()
    if not authorized():
        # Remove prior private UI state before showing the login form.
        for key in list(st.session_state):
            if not key.startswith('_login_'):
                del st.session_state[key]
        st.title('Biu · 登录工作台')
        with st.form('cloud_login'):
            st.text_input('账号', key='_login_user')
            st.text_input('密码', type='password', key='_login_password')
            st.form_submit_button('登录', on_click=_login_submit)
        if st.session_state.get('_login_error'):
            st.error(st.session_state['_login_error'])
        st.caption('同一个账号可在多部手机登录，看到同一份自选和持仓。登录有效期12小时。')
        st.stop()
    st.sidebar.button('退出登录', key='cloud_logout', on_click=_logout)
    st.sidebar.caption('云端共享工作台 · 刷新同步各设备的列表')


def cloud_store():
    require_session()
    return CloudStore(secret('SUPABASE_URL'), secret('SUPABASE_SECRET_KEY'), authorize=require_session)
