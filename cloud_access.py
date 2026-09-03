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


def _switch_profile(identifier=None):
    try:
        chosen = identifier or st.session_state.get('_workspace_choice', 'default')
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


def _request_profile_delete(identifier):
    require_session()
    st.session_state['_workspace_delete_target'] = identifier
    st.session_state.pop('_workspace_delete_name', None)


def _cancel_profile_delete():
    st.session_state.pop('_workspace_delete_target', None)
    st.session_state.pop('_workspace_delete_name', None)


def _delete_profile():
    try:
        store = cloud_store()
        profiles = {p['id']: p['name'] for p in store.profiles()}
        current = st.session_state.get('_workspace_delete_target')
        if current not in profiles:
            raise CloudError('目标工作台不存在，请重新选择。')
        if st.session_state.get('_workspace_delete_name', '').strip() != profiles.get(current):
            raise CloudError('请输入当前工作台的完整名称确认删除。')
        store.set_profile_deleted(current, True)
        if store.profile_id == current:
            _set_active_profile('default', '默认名单（原有数据）')
        else:
            _cancel_profile_delete()
        st.session_state['_workspace_notice'] = '已移入回收区，数据保留，可在“＋”中恢复。'
    except CloudError as exc:
        st.session_state['_workspace_error'] = str(exc)


def _restore_profile():
    try:
        store = cloud_store()
        identifier = st.session_state.get('_workspace_restore_id', '')
        items = {p['id']: p for p in store.profiles(include_deleted=True) if p.get('deleted')}
        if identifier not in items:
            raise CloudError('该工作台已恢复或不存在，请刷新。')
        store.set_profile_deleted(identifier, False)
        _set_active_profile(identifier, items[identifier]['name'])
    except CloudError as exc:
        st.session_state['_workspace_error'] = str(exc)


def render_profile_controls():
    try:
        all_profiles = cloud_store().profiles(include_deleted=True)
        profiles = {item['id']: item['name'] for item in all_profiles if not item.get('deleted')}
    except CloudError as exc:
        st.error(str(exc))
        st.stop()
    current = st.session_state.get('active_profile', 'default')
    if current not in profiles:
        _set_active_profile('default', profiles['default'])
        st.session_state['_workspace_notice'] = '原工作台已移入回收区，已切回默认名单。'
        current = 'default'
    st.session_state['active_profile_name'] = profiles[current]
    if st.session_state.get('_workspace_choice') not in profiles:
        st.session_state['_workspace_choice'] = current
    st.html('''<style>
.st-key-profile_toolbar {max-width:304px!important;width:100%!important;}
.st-key-profile_toolbar [data-testid="stHorizontalBlock"] {gap:6px!important;flex-wrap:nowrap!important;}
.st-key-profile_toolbar [data-testid="stColumn"] {min-width:0!important;}
.st-key-profile_toolbar [data-testid="stColumn"]:first-child {flex:1 1 260px!important;}
.st-key-profile_toolbar [data-testid="stColumn"]:last-child {flex:0 0 38px!important;}
.st-key-profile_toolbar button {min-height:32px!important;padding:3px 7px!important;}
.st-key-profile_toolbar button p {font-size:12px!important;white-space:nowrap;}
.st-key-profile_add [data-testid="stPopoverButton"] svg {display:none;}
.st-key-profile_menu [data-testid="stHorizontalBlock"] {flex-wrap:nowrap!important;gap:6px!important;}
.st-key-profile_menu [data-testid="stColumn"] {min-width:0!important;}
.st-key-profile_menu [data-testid="stColumn"]:first-child {flex:1 1 0!important;}
.st-key-profile_menu [data-testid="stColumn"]:last-child {flex:0 0 34px!important;}
</style>''')
    with st.container(key='profile_toolbar'):
        selector, create = st.columns([7, 1], gap='small')
        with selector.popover(profiles[current], width='stretch'):
            with st.container(key='profile_menu'):
                for identifier, name in profiles.items():
                    entry, remove = st.columns([7, 1], gap='small')
                    entry.button(name, key='profile_select_' + identifier,
                        on_click=_switch_profile, args=(identifier,), width='stretch',
                        type='primary' if identifier == current else 'secondary')
                    remove.button('×', key='profile_remove_' + identifier,
                        help='默认名单不能删除' if identifier == 'default' else '删除 ' + name,
                        disabled=identifier == 'default', on_click=_request_profile_delete,
                        args=(identifier,), width='stretch')
                target = st.session_state.get('_workspace_delete_target')
                if target in profiles and target != 'default':
                    st.warning('确认删除：' + profiles[target])
                    st.caption('移入回收区，所有设备均不再显示；可从“＋”恢复。')
                    with st.form('profile_delete_form'):
                        st.text_input('输入目标工作台名称确认', key='_workspace_delete_name')
                        st.form_submit_button('确认删除', on_click=_delete_profile)
                    st.button('取消', on_click=_cancel_profile_delete)
        with create.container(key='profile_add'), st.popover('＋', help='新建工作台 / 恢复', width='stretch'):
            with st.form('profile_create_form', clear_on_submit=True):
                st.text_input('名单名称', placeholder='例如：小王、小李', max_chars=20, key='_workspace_new_name')
                st.form_submit_button('新建并切换', on_click=_create_profile)
            deleted = {p['id']: p['name'] for p in all_profiles if p.get('deleted')}
            if deleted:
                st.caption('回收区：恢复后保留原有持仓、自选和设置。')
                st.selectbox('恢复工作台', options=list(deleted), format_func=lambda k: deleted[k], key='_workspace_restore_id')
                st.button('恢复并切换', on_click=_restore_profile)
    st.caption('当前：' + profiles[current] + ' · 本设备独立切换 · 同账号共享名单')
    if st.session_state.get('_workspace_error'):
        st.error(st.session_state.pop('_workspace_error'))
    if st.session_state.get('_workspace_notice'):
        st.toast(st.session_state.pop('_workspace_notice'))
