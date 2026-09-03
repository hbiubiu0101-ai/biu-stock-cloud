"""Shared-workspace login and server-only Secrets access."""
import hashlib
import hmac
import threading
import time
import secrets
import re
from collections import deque
import streamlit as st
from cloud_backend import CloudError, CloudStore

REMEMBER_SECONDS = 7 * 24 * 3600


def _remember_store():
    return CloudStore(secret('SUPABASE_URL'), secret('SUPABASE_SECRET_KEY'))


def _token_mac(payload):
    # Server-only signing material. Password changes invalidate all saved tokens.
    key = hmac.new(secret('SUPABASE_SECRET_KEY').encode(),
                   ('biu-remember-v1:' + _fingerprint()).encode(), hashlib.sha256).digest()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def _token_expiry(token):
    if not isinstance(token, str) or not re.fullmatch(r'[0-9]{10}\.[a-f0-9]{64}\.[a-f0-9]{64}', token):
        return 0
    payload, signature = token.rsplit('.', 1)
    expiry = int(payload.split('.')[0])
    if not hmac.compare_digest(signature, _token_mac(payload)):
        return 0
    return expiry if time.time() < expiry <= time.time() + REMEMBER_SECONDS + 60 else 0


def _token_key(token):
    return 'login_session:' + hashlib.sha256(token.encode()).hexdigest()


def _issue_remember_token():
    require_session()
    expiry = int(time.time()) + REMEMBER_SECONDS
    payload = str(expiry) + '.' + secrets.token_hex(32)
    token = payload + '.' + _token_mac(payload)
    _remember_store().put_state(_token_key(token), {'expires': expiry,
        'profile': st.session_state.get('active_profile', 'default')})
    st.session_state['_remember_token'] = token
    st.session_state['_remember_verified_at'] = time.time()
    st.session_state['_auth_until'] = expiry
    st.session_state['_remember_command'] = {'id': secrets.token_hex(8), 'action': 'write',
                                            'token': token, 'expires': expiry}


def _resume_remember_token(token):
    expiry = _token_expiry(token)
    if not expiry:
        return False
    row = _remember_store().state(_token_key(token))
    if not isinstance(row, dict) or row.get('expires') != expiry:
        return False
    profile = row.get('profile', 'default')
    if profile != 'default' and not re.fullmatch(r'[a-f0-9]{24}', str(profile)):
        profile = 'default'
    st.session_state['_auth_stamp'] = _fingerprint()
    st.session_state['_auth_until'] = expiry
    st.session_state['_remember_token'] = token
    st.session_state['_remember_verified_at'] = time.time()
    st.session_state['active_profile'] = profile
    return True


def _remember_browser():
    # Fixed trusted JS only; no interpolation, third-party scripts or credentials.
    bridge = _remember_component()
    command = st.session_state.get('_remember_command', {'id': 'read', 'action': 'read'})
    return bridge(data=command, key='_remember_bridge', on_result_change=lambda: None).result


@st.cache_resource
def _remember_component():
    from streamlit.components.v2 import component
    return component('biu_remember_device', js=r'''
export default function({data, parentElement, setStateValue}) {
  if (parentElement._biuRememberOp === data.id) return;
  parentElement._biuRememberOp = data.id;
  const name = '__Host-biu_remember_v1';
  const backup = 'biu_remember_v1';
  const read = () => (document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(name+'=')) || '').slice(name.length+1);
  const readBackup = () => {
    try {
      const item = JSON.parse(localStorage.getItem(backup) || 'null');
      if (item && typeof item.token === 'string' && item.expires > Math.floor(Date.now()/1000)) return item.token;
      localStorage.removeItem(backup);
    } catch (_) {}
    return '';
  };
  let ok = true, token = '';
  try {
    if (data.action === 'write') {
      if (location.protocol !== 'https:') throw new Error('HTTPS required');
      const age = Math.max(0, Math.min(604800, data.expires - Math.floor(Date.now()/1000)));
      let cookieOK = false, backupOK = false;
      try {
        document.cookie = name+'='+data.token+'; Path=/; Max-Age='+age+'; Secure; SameSite=Strict';
        cookieOK = read() === data.token;
      } catch (_) {}
      try {
        localStorage.setItem(backup, JSON.stringify({token:data.token, expires:data.expires}));
        backupOK = readBackup() === data.token;
      } catch (_) {}
      ok = cookieOK || backupOK;
    } else if (data.action === 'clear') {
      try { document.cookie = name+'=; Path=/; Max-Age=0; Secure; SameSite=Strict'; } catch (_) {}
      try { localStorage.removeItem(backup); } catch (_) {}
      ok = !read() && !readBackup();
    } else { token = read() || readBackup(); }
  } catch (_) { ok = false; }
  setStateValue('result', {id:data.id, ok, token});
}
''')


@st.cache_resource
def _loading_component():
    from streamlit.components.v2 import component
    return component('biu_modal_loading', js=r'''
export default function({data}) {
  const shield = document.createElement('dialog');
  shield.className = 'biu-loading-shield';
  shield.setAttribute('aria-label', '正在加载，请稍候');
  shield.setAttribute('aria-modal', 'true');
  shield.style.cssText = 'position:fixed;inset:0;z-index:2147483647;margin:0;border:0;padding:0;max-width:none;max-height:none;width:100vw;height:100dvh;background:rgba(7,13,33,.88);color:#d3e5ff;align-items:center;justify-content:center;overflow:hidden;';
  const card = document.createElement('div');
  card.style.cssText = 'width:min(340px,78vw);border-radius:18px;overflow:hidden;background:#111d3d;text-align:center;padding-bottom:12px;';
  if (data.uri) {
    const video = document.createElement('video');
    video.src = data.uri;
    video.autoplay = true; video.muted = true; video.loop = true; video.playsInline = true;
    video.setAttribute('muted', ''); video.setAttribute('playsinline', '');
    video.style.cssText = 'width:100%;aspect-ratio:4/3;display:block;object-fit:contain;';
    card.appendChild(video);
    video.play().catch(() => {});
  }
  const label = document.createElement('p');
  label.textContent = data.uri ? '比比正在陪你加载…' : '正在加载，请稍候…';
  card.appendChild(label);
  const retry = document.createElement('button');
  retry.textContent = '加载较久，重新打开页面';
  retry.style.cssText = 'display:none;padding:10px;border:1px solid #7191c9;border-radius:8px;background:#20385d;color:white;';
  retry.onclick = () => location.reload();
  card.appendChild(retry); shield.appendChild(card); document.body.appendChild(shield);
  const preventCancel = event => event.preventDefault();
  shield.addEventListener('cancel', preventCancel);
  if (shield.showModal) shield.showModal();
  shield.style.display = 'flex';
  // Native modal top layer covers existing dropdowns and traps keyboard focus.
  // Capture guard is also used for browsers with incomplete dialog support.
  const guard = event => {
    if (!event.target.closest?.('.biu-loading-shield')) {
      event.preventDefault(); event.stopImmediatePropagation();
    }
  };
  const events = ['pointerdown', 'click', 'touchstart', 'keydown', 'wheel'];
  events.forEach(name => document.addEventListener(name, guard, {capture:true, passive:false}));
  const timer = setTimeout(() => {retry.style.display = 'inline-block';}, 30000);
  return () => {
    clearTimeout(timer);
    events.forEach(name => document.removeEventListener(name, guard, true));
    shield.removeEventListener('cancel', preventCancel);
    if (shield.open && shield.close) shield.close();
    shield.remove();
  };
}
''')


def render_loading(slot, uri):
    with slot.container():
        _loading_component()(data={'uri': uri}, key='loading_' + slot._get_delta_path_str())


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
    token = st.session_state.get('_remember_token')
    if token and time.time() - st.session_state.get('_remember_verified_at', 0) > 60:
        row = _remember_store().state(_token_key(token))
        if not _token_expiry(token) or not isinstance(row, dict) or row.get('expires') != _token_expiry(token):
            st.session_state.pop('_auth_stamp', None)
            raise CloudError('登录凭证已撤销或过期，请重新登录。')
        st.session_state['_remember_verified_at'] = time.time()


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
    if not st.session_state['_login_error']:
        st.session_state['_remember_checked'] = True
        st.session_state.pop('_remember_token', None)
        st.session_state.pop('_remember_verified_at', None)
        if st.session_state.get('_login_remember', False):
            try:
                _issue_remember_token()
            except CloudError:
                st.session_state['_remember_warning'] = '已登录，但7天登录凭证保存失败；本次仅保持当前会话。'
        else:
            st.session_state['_remember_command'] = {'id': secrets.token_hex(8), 'action': 'clear'}


def _logout():
    token = st.session_state.get('_remember_token')
    failed = False
    if token:
        try:
            _remember_store()._request('DELETE', 'biu_app_state',
                params={'state_key': 'eq.' + _token_key(token)})
        except CloudError:
            failed = True
    for key in list(st.session_state):
        del st.session_state[key]
    st.session_state['_remember_checked'] = True
    st.session_state['_remember_command'] = {'id': secrets.token_hex(8), 'action': 'clear'}
    if failed:
        st.session_state['_remember_warning'] = '已退出本页面，但服务器凭证撤销失败。请清除此网站数据；如设备遗失，请修改登录密码使旧凭证失效。'


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
    # Streamlit exposes cookies from the initial browser connection. Restoring
    # here also works before the asynchronous component has rendered.
    if not authorized() and not st.session_state.get('_remember_checked'):
        try:
            cookie_token = st.context.cookies.get('__Host-biu_remember_v1', '')
            if cookie_token and _resume_remember_token(cookie_token):
                st.session_state['_remember_checked'] = True
        except CloudError:
            pass  # Component restoration/manual login remain available.
    result = _remember_browser()
    command = st.session_state.get('_remember_command', {})
    # Mount/acknowledge the persistence component before expensive market loading.
    # Otherwise a login rerun can begin loading before the browser receives its token.
    if authorized() and command.get('action') == 'write' and (
            not isinstance(result, dict) or result.get('id') != command.get('id')):
        st.info('正在保存本设备的7天登录状态…')
        if st.button('跳过保存，先进入工作台', key='_remember_skip'):
            st.session_state['_remember_command'] = {'id': secrets.token_hex(8), 'action': 'read'}
            st.rerun()
        st.stop()
    if isinstance(result, dict):
        if not result.get('ok', False):
            st.warning('本设备未能保存登录状态，下次可能需要重新登录。请使用同一浏览器、同一应用网址，并关闭无痕模式。')
        if not authorized() and not st.session_state.get('_remember_checked') and result.get('id') == 'read':
            try:
                _resume_remember_token(result.get('token', ''))
            except CloudError:
                st.session_state['_remember_warning'] = '自动登录验证暂不可用，请手动登录。'
            st.session_state['_remember_checked'] = True
    if st.session_state.get('_remember_warning'):
        st.warning(st.session_state.pop('_remember_warning'))
    if not authorized():
        # Remove prior private UI state before showing the login form.
        for key in list(st.session_state):
            if not key.startswith(('_login_', '_remember_')):
                del st.session_state[key]
        st.title('Biu · 登录工作台')
        with st.form('cloud_login'):
            st.text_input('账号', key='_login_user')
            st.text_input('密码', type='password', key='_login_password')
            st.checkbox('记住登录7天（仅限自己的设备）', key='_login_remember', value=False)
            st.form_submit_button('登录', on_click=_login_submit)
        if st.session_state.get('_login_error'):
            st.error(st.session_state['_login_error'])
        st.caption('不勾选：当前会话12小时。勾选：本浏览器最多7天；清除网站数据或使用无痕模式后需重新登录。')
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
        if key not in keep and not key.startswith('_remember_'):
            del st.session_state[key]
    st.session_state['active_profile'] = identifier
    st.session_state['active_profile_name'] = name
    st.session_state['_workspace_choice'] = identifier
    st.session_state['_workspace_notice'] = '当前名单：' + name
    token = st.session_state.get('_remember_token')
    if token and _token_expiry(token):
        try:
            # PATCH only: a stale tab must never recreate a revoked session row.
            _remember_store()._request('PATCH', 'biu_app_state',
                params={'state_key': 'eq.' + _token_key(token)},
                body={'state_value': {'expires': _token_expiry(token), 'profile': identifier}})
        except CloudError:
            st.session_state['_remember_warning'] = '工作台已切换，但下次打开时的默认工作台未保存。'


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
