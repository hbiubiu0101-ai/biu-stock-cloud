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
        st.caption('同一账号可在多部手机登录；进入后选择各自名单。名单不是独立账号的隐私隔离。登录有效期12小时。')
        st.stop()
    st.sidebar.button('退出登录', key='cloud_logout', on_click=_logout)
    st.sidebar.caption('云端共享工作台 · 每台设备独立选择名单')


def cloud_store():
    require_session()
    return CloudStore(secret('SUPABASE_URL'), secret('SUPABASE_SECRET_KEY'), authorize=require_session,
        profile_id=st.session_state.get('active_profile', 'default'))


def _set_active_profile(identifier, name):
    require_session()
    # Keep only authentication and display preferences. Do not carry holdings,
    # quote widgets, candidates, notification toggles or cached results across lists.
    keep = {'_auth_stamp', '_auth_until', 'mobile_light_mode', 'show_loading_animation'}
    for key in list(st.session_state):
        if key not in keep:
            del st.session_state[key]
    st.session_state['active_profile'] = identifier
    st.session_state['active_profile_name'] = name
    st.session_state['_workspace_choice'] = identifier
    st.session_state['_workspace_notice'] = '当前名单：' + name


def _switch_profile():
    try:
        chosen = st.session_state.get('_workspace_choice', 'default')
        profiles = {item['id']: item['name'] for item in cloud_store().profiles()}
        if chosen not in profiles:
            raise CloudError('名单不存在，请刷新重试。')
        _set_active_profile(chosen, profiles[chosen])
    except CloudError as exc:
        st.session_state['_workspace_error'] = str(exc)


def _create_profile():
    try:
        name = st.session_state.get('_workspace_new_name', '').strip()
        identifier = cloud_store().create_profile(name)
        _set_active_profile(identifier, name)
    except CloudError as exc:
        st.session_state['_workspace_error'] = str(exc)


def render_profile_controls():
    try:
        profiles = {item['id']: item['name'] for item in cloud_store().profiles()}
    except CloudError as exc:
        st.error(str(exc))
        st.stop()
    current = st.session_state.get('active_profile', 'default')
    if current not in profiles:
        st.error('当前名单不可用，请退出后重新登录。原数据未修改。')
        st.stop()
    st.session_state['active_profile_name'] = profiles[current]
    if st.session_state.get('_workspace_choice') not in profiles:
        st.session_state['_workspace_choice'] = current
    left, right = st.columns([4, 1], vertical_alignment='center')
    with left:
        with st.form('profile_switch_form', border=False):
            choice, action = st.columns([4, 1], vertical_alignment='bottom')
            with choice:
                st.selectbox('选择名单', options=list(profiles), format_func=lambda key: profiles[key],
                    key='_workspace_choice', label_visibility='collapsed')
            with action:
                st.form_submit_button('切换', on_click=_switch_profile, use_container_width=True)
    with right:
        with st.popover('＋ 新建', use_container_width=True):
            with st.form('profile_create_form', clear_on_submit=True):
                st.text_input('名单名称', placeholder='例如：小王、小李', max_chars=20, key='_workspace_new_name')
                st.form_submit_button('新建并切换', on_click=_create_profile)
    st.caption('当前：' + profiles[current] + ' · 只切换本设备；同一账号的人可查看和编辑所有名单。')
    if st.session_state.get('_workspace_error'):
        st.error(st.session_state.pop('_workspace_error'))
    if st.session_state.get('_workspace_notice'):
        st.success(st.session_state.pop('_workspace_notice'))
