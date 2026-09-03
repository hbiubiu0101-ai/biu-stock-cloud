# 六道候选版交易时序：收盘判断、下一可成交日开盘买卖。
# BaoStock行情版：仅前复权日线，其他周期锁定；BaoStock优先，TuShare日线备用。
# 依赖安装：python -m pip install baostock tushare streamlit pandas numpy requests plotly matplotlib akshare
import os
import json
import streamlit as st
import pandas as pd
import numpy as np
import requests
import json as json_lib
import re
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import akshare as ak

TUSHARE_ENABLED = True  # BaoStock失败/无数据时自动尝试TuShare，无须手动开关。

from cloud_backend import CloudError
from cloud_access import cloud_store, login_gate, require_session, secret, render_profile_controls


# 工作台主题：仅显示层，不改变策略、数据源、交易或通知规则。
from streamlit import config as _biu_theme_config
for _biu_key, _biu_value in {
    'theme.base': 'dark', 'theme.primaryColor': '#51b8ff',
    'theme.backgroundColor': '#0b132b', 'theme.secondaryBackgroundColor': '#152344',
    'theme.textColor': '#edf3ff', 'theme.font': 'sans serif',
    'client.showErrorDetails': 'none', 'browser.gatherUsageStats': False
}.items():
    _biu_theme_config.set_option(_biu_key, _biu_value)

st.set_page_config(page_title="Biu · 我的工作台", layout="wide")
login_gate()  # 在所有行情请求、列表读取和通知操作之前验证登录。
st.markdown('<style>\n:root {color-scheme:dark; --biu-bg:#070d21; --biu-panel:#111d3d; --biu-line:rgba(132,157,243,.24); --biu-text:#edf3ff; --biu-muted:#a5b3d3;}\n.stApp {background:radial-gradient(ellipse at 12% 0%,#142f63 0%,transparent 48%),radial-gradient(ellipse at 100% 40%,#29144d 0%,transparent 55%),var(--biu-bg);color:var(--biu-text);}\n[data-testid="stHeader"] {background:rgba(7,13,33,.92);}\n[data-testid="stMainBlockContainer"], .main .block-container {padding-top:2.5rem;padding-bottom:2rem;max-width:1740px;}\n[data-testid="stSidebar"] {background:linear-gradient(170deg,#142958 0%,#101c3b 42%,#17142f 100%);border-right:1px solid var(--biu-line);}\n[data-testid="stSidebarUserContent"] {padding:1.2rem 1rem 2rem;}\nh1,h2,h3,h4,h5,h6 {color:#f3f6ff!important;letter-spacing:.01em;}\nh1 {font-size:2rem!important;font-weight:750!important;}\nh2,h3 {font-size:1.1rem!important;}\n[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:var(--biu-muted)!important;line-height:1.65;}\n.biu-brand {font-size:30px;font-weight:800;letter-spacing:-1px;color:#57baff;margin-bottom:4px;}\n.biu-eyebrow {font-size:11px;letter-spacing:2px;color:#9cafdb;margin:0 0 12px;}\n.biu-nav {display:flex;gap:10px;flex-wrap:wrap;padding:4px 0 16px;}\n.biu-nav a {display:block;padding:9px 18px;border:1px solid var(--biu-line);background:#16284a;border-radius:10px;color:#d3e5ff!important;text-decoration:none!important;font-size:13px;}\n.biu-nav a:hover {background:#234477;border-color:#54b6ff;}\n.biu-nav a:focus-visible {outline:2px solid #79d6ff;outline-offset:3px;}\n.biu-anchor {scroll-margin-top:75px;}\n[data-testid="stForm"], [data-testid="stExpander"], .st-key-biu_kline_panel {border:1px solid var(--biu-line)!important;border-radius:16px!important;background:linear-gradient(115deg,rgba(24,53,100,.64),rgba(39,25,74,.65));box-shadow:0 10px 28px rgba(0,0,0,.1);}\n[data-testid="stForm"] {padding:18px!important;}\n[data-testid="stExpander"] details>summary {background:rgba(39,57,102,.25);border-radius:15px;padding:14px 16px;color:#edf3ff;}\n[data-testid="stExpander"] details>summary:hover {background:rgba(75,99,164,.24);}\n.st-key-biu_kline_panel {padding:16px!important;}\n[data-testid="stMetric"] {border:1px solid var(--biu-line);border-radius:14px;padding:18px 16px;min-height:122px;background:linear-gradient(125deg,rgba(30,81,148,.7),rgba(48,27,96,.75));}\n[data-testid="stMetricLabel"] {color:#b8c9ed;font-size:13px;}\n[data-testid="stMetricValue"] {color:#f1f6ff;font-size:clamp(20px,1.8vw,30px)!important;font-weight:650;font-variant-numeric:tabular-nums;}\n[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) {flex-wrap:wrap;gap:12px;}\n[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) > [data-testid="stColumn"] {flex:1 1 150px;min-width:150px;}\n[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button, [data-testid="stDownloadButton"] button {border:1px solid rgba(120,156,249,.4);background:#20385d;color:#e8f3ff;border-radius:10px;min-height:40px;transition:background .12s,border-color .12s;}\n[data-testid="stFormSubmitButton"] button {background:linear-gradient(100deg,#087bc3,#6d46d7);border-color:#628dff;font-weight:600;}\n[data-testid="stButton"] button:hover, [data-testid="stDownloadButton"] button:hover {background:#304c80;border-color:#77c7ff;color:white;}\nbutton:focus-visible {outline:2px solid #87dcff!important;outline-offset:2px;}\nbutton:disabled {opacity:.46;}\n[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"]>div, [data-baseweb="textarea"] {background:#101b36!important;border-color:#44567b!important;color:#edf3ff!important;border-radius:9px;}\ninput,textarea {color:#edf3ff!important;caret-color:#65ccff;}\ninput::placeholder,textarea::placeholder {color:#879bc1!important;}\n[data-testid="stWidgetLabel"] p {color:#b9c8e7;}\n[data-testid="stDataFrame"] {border:1px solid var(--biu-line);border-radius:10px;overflow:hidden;}\n[data-testid="stAlert"] {border-radius:12px;border:1px solid var(--biu-line);}\n.stock-list-heading {color:#a8bee8!important;}\n.stock-list-cell {color:#e1ebff;}\n[class*="st-key-stock_row_"] {border-bottom:1px solid rgba(129,155,216,.08);}\n[class*="st-key-stock_row_"] button {background:rgba(43,66,111,.4);border-color:rgba(129,155,216,.28);}\n.js-plotly-plot .plotly .modebar {background:transparent!important;}\n.js-plotly-plot .plotly .modebar-btn path {fill:#9bb3de!important;}\nhr {border-color:var(--biu-line)!important;}\n@media(min-width:1100px) {[data-testid="stSidebar"] {min-width:410px!important;max-width:410px!important;}}\n@media(max-width:768px) {\n [data-testid="stMainBlockContainer"],.main .block-container {padding:3rem .8rem 1.5rem!important;}\n h1 {font-size:1.5rem!important;}\n [data-testid="stForm"],.st-key-biu_kline_panel {padding:12px!important;}\n [data-testid="stMetric"] {padding:14px 12px;min-height:105px;}\n [data-testid="stMetricValue"] {font-size:22px!important;}\n [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) > [data-testid="stColumn"] {flex:1 1 calc(50% - 12px);min-width:130px;}\n [data-testid="stSidebar"] {min-width:0!important;max-width:96vw!important;}\n .biu-nav {gap:7px;}\n .biu-nav a {padding:8px 11px;font-size:12px;}\n .st-key-biu_kline_panel {padding:4px!important;}\n}\n@media(prefers-reduced-motion:reduce) {* {transition:none!important;}}\n</style>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="biu-brand">Biu</div><div class="biu-eyebrow">MY STOCK WORKSPACE</div>', unsafe_allow_html=True)

# Display-only preference: session state is isolated per browser session.
light_mode = st.sidebar.checkbox('📱 手机轻量模式', value=True, key='mobile_light_mode',
    help='仅当前浏览器：默认显示最近250根K线，大表格按需加载。完整历史回测不变。')

def _load_display_table(label, key):
    return not light_mode or st.checkbox('加载'+label, key='light_table_'+key)


def _parse_name_suggestions(body, query):
    """Sina's public suggestion response; only accept matching SH/SZ stock records."""
    import unicodedata
    normalized = lambda text: ''.join(unicodedata.normalize('NFKC', text).split()).casefold()
    payload = re.search(r'=\s*"([^"\r\n]*)"', body)
    if not payload: return []
    found = {}
    for record in payload.group(1).split(';'):
        fields = record.split(',')
        if len(fields) < 5: continue
        code, symbol, name = fields[2].strip(), fields[3].strip(), fields[4].strip()
        if not re.fullmatch(r'[0-9]{6}', code) or symbol not in ('sh'+code, 'sz'+code): continue
        if not name or len(name) > 40 or normalized(query) not in normalized(name): continue
        found[code] = {'code': code, 'name': name}
    matches = list(found.values())
    exact = [item for item in matches if normalized(item['name']) == normalized(query)]
    return (exact if exact else matches)[:20]


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def _stock_name_matches(query):
    from urllib.parse import quote
    try:
        response = requests.get('https://suggest3.sinajs.cn/suggest/type=11,12&key='
            + quote(query, safe='') + '&name=suggestvalue',
            headers={'Referer': 'https://finance.sina.com.cn/', 'User-Agent': 'Mozilla/5.0'},
            timeout=(5, 10), allow_redirects=False)
        if response.status_code != 200: raise ValueError()
        # The legacy suggestion endpoint declares GBK/GB18030, not UTF-8.
        response.encoding = 'gb18030'
        return _parse_name_suggestions(response.text, query)
    except (requests.RequestException, ValueError):
        raise ValueError('中文名称查询暂不可用，请稍后重试，或先输入六位股票代码。') from None


def _resolve_stock_input(text):
    import unicodedata
    query = unicodedata.normalize('NFKC', str(text)).strip()
    if re.fullmatch(r'[0-9]{6}', query): return [{'code': query, 'name': query}]
    if not 1 <= len(query) <= 30 or not re.search(r'[\u4e00-\u9fff]', query):
        raise ValueError('请输入六位股票代码或中文股票名称，例如603993或洛阳钼业。')
    matches = _stock_name_matches(query)
    if not matches: raise ValueError('没有找到匹配的沪深股票，请试完整名称或六位代码。')
    return matches


def _add_watch_code(code):
    try:
        cloud_store().add('watchlist', code)
        st.session_state.watchlist = cloud_store().lists()['watchlist']
        st.success('已加入当前名单自选：' + code)
    except CloudError as exc:
        st.error(str(exc) + ' 请刷新确认列表。')



def _find_loading_video():
    from pathlib import Path
    path = Path(__file__).resolve().with_name('bibi_loading.mp4')
    return path if path.is_file() else None


@st.cache_resource(max_entries=2)
def _loading_video_uri(path, mtime_ns, size):
    from pathlib import Path
    if size > 3 * 1024 * 1024:
        return ''  # Prevent an accidentally oversized replacement from stalling phones.
    return 'data:video/mp4;base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')


def _show_loading_video(slot):
    if not st.session_state.get('show_loading_animation', True): return
    video = _find_loading_video()
    if video is None: return
    try:
        stat = video.stat()
        uri = _loading_video_uri(str(video), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return
    if not uri: return
    # No visibility:hidden on the application. finally clears the slot; the CSS
    # timeout also removes the overlay if a provider hangs or the connection drops.
    slot.html('''<style>
    #biu-loading-overlay {position:fixed;inset:0;z-index:9999;display:flex;
      align-items:center;justify-content:center;background:rgba(7,13,33,.82);
      pointer-events:none;animation:biu-loading-release .2s linear 25s forwards;}
    #biu-loading-overlay .biu-loading-card {width:min(340px,78vw);overflow:hidden;
      border-radius:18px;box-shadow:0 20px 70px #0008;background:#111d3d;}
    #biu-loading-overlay video {width:100%;aspect-ratio:4/3;display:block;object-fit:contain;}
    #biu-loading-overlay p {margin:0;padding:12px;text-align:center;color:#d3e5ff;font-size:13px;}
    @keyframes biu-loading-release {to {opacity:0;visibility:hidden;}}
    </style><div id="biu-loading-overlay" role="status" aria-label="正在加载">
    <div class="biu-loading-card"><video autoplay muted loop playsinline preload="auto" disablepictureinpicture src="'''
        + uri + '''"></video><p>比比正在陪你加载…</p></div></div>''')


# 使用较新Streamlit；加载完成/发生错误时均由finally移除视频遮罩。
_page_loading = st.empty()
st.sidebar.checkbox('显示比比加载动画', value=True, key='show_loading_animation',
    help='手机轻量模式也可播放。加载很快时可能只闪一下；不强制等待视频播完。')
try:
    _show_loading_video(_page_loading)

    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.title("我的工作台")
        render_profile_controls()
    with col_refresh:
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.session_state['force_query'] = True

    st.caption(f"页面刷新时间（北京时间）：{pd.Timestamp.now(tz='Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')}  ·  行情日期以实际K线为准")


    # ========== 关键函数（完整保留） ==========
    @st.cache_data(ttl=60, show_spinner=False)
    def fetch_stock_quote(code):
        code_str = str(code).strip()
        symbol = f"sh{code_str}" if code_str.startswith(('6', '688', '689')) else f"sz{code_str}"
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        session = requests.Session()
        session.proxies = {"http": None, "https": None}
        session.trust_env = True
        try:
            resp = session.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                match = re.search(r'="(.*?)";', resp.text)
                if match:
                    parts = match.group(1).split(',')
                    if len(parts) >= 10:
                        return {'name': parts[0], 'close': float(parts[3]),
                                'change_pct': (float(parts[3]) - float(parts[2])) / float(parts[2]) * 100,
                                'volume': float(parts[8]), 'amount': float(parts[9]) if parts[9] else 0}
        except Exception:
            pass
        return None


    # ---- 侧边栏：自选股管理 ----
    st.sidebar.markdown("""<style>
    [class*="st-key-stock_row_"], [class*="st-key-stock_header_"] {margin:0!important;padding:0!important;}
    [class*="st-key-stock_row_"] [data-testid="stHorizontalBlock"],
    [class*="st-key-stock_header_"] [data-testid="stHorizontalBlock"] {align-items:center!important;gap:6px!important;flex-wrap:nowrap!important;}
    [class*="st-key-stock_row_"] [data-testid="stColumn"],
    [class*="st-key-stock_header_"] [data-testid="stColumn"] {min-width:0!important;}
    [class*="st-key-stock_row_"] button {
        height:36px!important;min-height:36px!important;width:100%!important;
        padding:0 2px!important;margin:0!important;display:flex!important;
        align-items:center!important;justify-content:center!important;overflow:hidden;}
    [class*="st-key-stock_row_"] button [data-testid="stMarkdownContainer"] {
        display:flex!important;align-items:center!important;justify-content:center!important;min-width:0;max-width:100%;}
    [class*="st-key-stock_row_"] button p {margin:0!important;line-height:1!important;font-size:12px!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .stock-list-cell {height:36px;display:flex;align-items:center;justify-content:center;
        margin:0;padding:0;white-space:nowrap;font-size:12px;font-variant-numeric:tabular-nums;}
    .stock-list-heading {height:24px;display:flex;align-items:center;justify-content:center;
        margin:0;padding:0;white-space:nowrap;font-size:12px;font-weight:600;color:#667085;}
    </style>""", unsafe_allow_html=True)

    if not hasattr(st, 'fragment'):
        st.error('局部刷新需要Streamlit 1.37以上，请执行 python -m pip install -U streamlit')
        st.stop()


    def _remove_watch_stock(code):
        try:
            cloud_store().remove('watchlist', code)
            st.session_state['_holdings_notice'] = '已删除自选 ' + code
        except CloudError as exc:
            st.session_state['_holdings_notice'] = str(exc) + ' 请刷新确认列表。'


    def _select_watch_stock(code):
        # Callback only sets state; do not call rerun from a callback.
        st.session_state['target_code'] = code
        st.session_state['_watch_open_pending'] = True


    def _load_manual_holdings():
        return cloud_store().lists()['holdings']


    def _save_manual_holdings(codes):
        raise CloudError('云端禁止整表覆盖，请使用单只股票的增删按钮。')


    def _add_manual_holding(code):
        try:
            cloud_store().add('holdings', code)
            st.session_state['_holdings_notice'] = '已加入持仓股 ' + code
        except CloudError as exc:
            st.session_state['_holdings_notice'] = str(exc) + ' 请刷新确认列表。'


    def _remove_manual_holding(code):
        try:
            cloud_store().remove('holdings', code)
            st.session_state['_holdings_notice'] = '已移出持仓股 ' + code + '（自选股不受影响）'
        except CloudError as exc:
            st.session_state['_holdings_notice'] = str(exc) + ' 请刷新确认列表。'




    def _china_now():
        return pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)


    def _load_holding_alert_state():
        state = {'schema': 2, 'checked': {}, 'attempted': {}, 'alerts': {}}
        persisted = {}
        for row in cloud_store().alerts():
            code = row['state_key'].removeprefix('signal_v2:')
            data = row.get('state_value')
            if not re.fullmatch(r'[0-9]{6}', code) or not isinstance(data, dict): continue
            checked = data.get('checked')
            if not isinstance(checked, str): continue
            state['checked'][code] = checked
            item = data.get('alert')
            if isinstance(item, dict) and item.get('signal') in ('买入', '卖出', '持仓') and item.get('date') == checked:
                state['alerts'][code] = item
            persisted[code] = data
        st.session_state['_persisted_signals'] = persisted
        return state


    def _save_holding_alert_state(state):
        # Persist only completed checks, one stock at a time. Never replace another phone's full snapshot.
        persisted = st.session_state.setdefault('_persisted_signals', {})
        for code, checked in state.get('checked', {}).items():
            item = state.get('alerts', {}).get(code)
            value = {'checked': checked, 'alert': item}
            if persisted.get(code) == value: continue
            cloud_store().put_state('signal_v2:' + code, value)
            persisted[code] = value


    def _visible_holding_alerts(now=None):
        now = now or _china_now()
        alerts = st.session_state.holding_alert_state['alerts']
        # Opening-time cleanup is display-only; do not erase durable checks from another session.
        if now.time() >= pd.Timestamp('09:30').time():
            return {code: item for code, item in alerts.items() if item.get('date') == now.strftime('%Y-%m-%d')}
        return alerts



    def _feishu_load_config():
        enabled = cloud_store().state('feishu_enabled', False) is True
        return {'enabled': enabled, 'webhook': secret('FEISHU_WEBHOOK'), 'secret': secret('FEISHU_SIGN_SECRET')}

    def _feishu_validate(config):
        import re
        if not re.fullmatch(r'https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9-]+',config['webhook']):
            raise ValueError('请填写飞书机器人的完整HTTPS Webhook地址。')
        if not config['secret']:raise ValueError('请开启机器人签名校验并填写签名密钥。')

    def _feishu_save_config(config):
        cloud_store().put_state('feishu_enabled', config['enabled'] is True)

    def _feishu_send(config,text):
        import time,base64,hmac,hashlib
        require_session()
        _feishu_validate(config)
        timestamp=str(int(time.time()))
        key=(timestamp+'\n'+config['secret']).encode('utf-8')
        signature=base64.b64encode(hmac.new(key,b'',hashlib.sha256).digest()).decode('ascii')
        payload={'timestamp':timestamp,'sign':signature,'msg_type':'text','content':{'text':text}}
        try:
            response=requests.post(config['webhook'],json=payload,timeout=(5,12),allow_redirects=False)
            if response.status_code!=200:return 'unknown','HTTP响应异常，送达状态不确定，请先查看飞书群。'
            data=response.json()
            code=data.get('code',data.get('StatusCode')) if isinstance(data,dict) else None
            if code==0:return 'sent','飞书已接收消息。'
            if isinstance(code,int):return 'failed',f'飞书拒绝消息（错误码{code}），请检查签名、机器人安全设置及电脑时间。'
            return 'unknown','响应格式异常，送达状态不确定，请先查看飞书群。'
        except (requests.RequestException,ValueError):
            return 'unknown','连接或响应异常，送达状态不确定，请先查看飞书群；不会自动重发。'

    def _feishu_db():
        return cloud_store()

    def _feishu_push_alerts(now=None):
        import hashlib
        now = now or _china_now()
        if now.hour < 15: return
        try:
            config = _feishu_load_config()
            if not config['enabled']: return
            _feishu_validate(config)
            today = now.strftime('%Y-%m-%d')
            store = cloud_store()
            for code in st.session_state.manual_holdings:
                item = st.session_state.holding_alert_state['alerts'].get(code, {})
                signal = item.get('signal')
                if item.get('date') != today or signal not in ('买入', '卖出'): continue
                identity = hashlib.sha256((config['webhook']+'|'+today+'|'+code+'|'+signal).encode()).hexdigest()
                # Unique database reservation BEFORE sending; a duplicate or uncertain reservation never sends.
                if not store.reserve_notification(identity, code, today, 'buy' if signal == '买入' else 'sell'): continue
                quote = st.session_state.get('sidebar_quote_snapshots', {}).get(code) or {}
                name = quote.get('name', code)
                profile_name = st.session_state.get('active_profile_name', '默认名单')
                message = (f'股票提醒｜{signal}\n名单：{profile_name}\n股票：{name}（{code}）\n信号日期：{today}\n'
                           '来源：当前策略当日收盘指令\n计划执行：下一可成交交易日开盘\n'
                           '仅为策略模拟信号，非实盘成交；不自动下单。')
                status, detail = _feishu_send(config, message)
                store.finish_notification(identity, status)
                if status != 'sent': st.warning('飞书通知：' + detail)
        except CloudError as exc:
            st.warning(str(exc) + ' 本次推送已停止；如记录为待核对，请查看飞书群，不会自动重发。')
        except ValueError:
            st.warning('飞书 Secrets 尚未正确配置，已停止推送；策略计算不受影响。')

    def _render_feishu_settings():
        with st.expander('📨 飞书通知设置', expanded=False):
            try: config = _feishu_load_config()
            except CloudError as exc:
                st.error(str(exc)); return
            st.caption('仅打开或手动刷新时检查。开启后，将持仓列表的股票代码、名称及当日买卖指令发送到你配置的飞书群；持仓灯不推送，不自动下单。')
            st.caption('只检查当前名单。各名单的开关和发送记录独立，但共用 Secrets 中的飞书机器人；通知会标明名单名称。')
            st.caption('Webhook 和签名密钥只在 Streamlit 的 Secrets 配置，此处不显示也不保存密钥。')
            st.caption('机器人配置：' + ('已填写' if config['webhook'] and config['secret'] else '未完整填写'))
            with st.form('feishu_settings_form'):
                enabled = st.checkbox('启用买卖信号推送到该飞书群', value=config['enabled'])
                save = st.form_submit_button('保存推送开关')
            if save:
                candidate = {**config, 'enabled': enabled}
                try:
                    if enabled: _feishu_validate(candidate)
                    _feishu_save_config(candidate)
                    config = candidate
                    st.success('开关已保存，所有设备共用。实际信号在下次打开或手动刷新时检查。')
                except CloudError as exc: st.error(str(exc))
                except ValueError: st.error('请先在 Secrets 填写正确的 FEISHU_WEBHOOK 和 FEISHU_SIGN_SECRET。')
            if st.button('发送测试消息', key='feishu_test_send'):
                try:
                    status, detail = _feishu_send(config, '股票提醒｜连接测试\n网页与飞书连接测试，不是买卖信号，也不会下单。')
                    (st.success if status == 'sent' else st.warning)(detail)
                except (CloudError, ValueError): st.error('请确认登录有效并已在 Secrets 正确配置飞书。')
            st.caption('同一机器人、股票、日期、指令只尝试一次。超时或程序中断可能已送达，请核对群消息；不自动重发。云端休眠或无人打开时，不会定时推送。')
            if st.button('查看最近发送记录', key='feishu_show_log'):
                try:
                    labels = {'sent': '飞书已接收', 'pending': '发送中／结果待核对', 'failed': '发送失败', 'unknown': '结果待核对'}
                    records = [{'日期': row['signal_date'], '股票': row['stock_code'],
                        '指令': {'buy': '买入', 'sell': '卖出'}.get(row['signal_type'], ''),
                        '状态': labels.get(row['status'], row['status'])} for row in cloud_store().notifications()]
                    if records: st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
                    else: st.caption('暂无信号发送记录；测试消息不计入去重记录。')
                except CloudError as exc: st.error(str(exc))


    def _check_holding_close_signals(now=None):
        now = now or _china_now();
        today = now.strftime('%Y-%m-%d')
        state = st.session_state.holding_alert_state
        # On-demand only: never request today's final daily bar during the session.
        if now.hour < 15: return False
        changed = False
        state.setdefault('checked', {});
        state.setdefault('attempted', {});
        state['schema'] = 2
        for code in st.session_state.manual_holdings:
            if state['checked'].get(code) == today: continue
            changed = True
            state['alerts'].pop(code, None)
            st.session_state.holding_alert_state = state
            try:
                _save_holding_alert_state(state)
            except (OSError, CloudError):
                pass
            try:
                frame = fetch_kline_with_fallback(code, '20180101', today.replace('-', ''), 'day')
                if frame is None or frame.empty or pd.Timestamp(frame['date'].iloc[-1]).strftime(
                    '%Y-%m-%d') != today: continue
                result = cached_backtest_strategy(frame, initial_cash=100000, backtest_start='2019-01-14',
                                                  backtest_end=today,
                                                  buy_threshold=2, sell_threshold=2, signal4_lookback=1,
                                                  signal4_threshold=1.025, cooling_params=None)
                if not result or result.get('信号数据') is None or result['信号数据'].empty: continue
                signal = str(result['信号数据'].iloc[-1].get('收盘指令', ''))
                state['checked'][code] = today
                state['alerts'].pop(code, None)
                if signal not in ['买入', '卖出'] and float(result.get('期末持股数', 0)) > 0: signal = '持仓'
                if signal in ['买入', '卖出', '持仓']: state['alerts'][code] = {'signal': signal, 'date': today}
            except Exception:
                # Failure is not a signal; retry only on the next user-requested refresh.
                continue
        if changed:
            st.session_state.holding_alert_state = state
            try:
                _save_holding_alert_state(state)
            except (OSError, CloudError):
                st.caption('提醒结果已显示，但数据库保存失败；请稍后刷新重试。')
        _feishu_push_alerts(now)
        return changed


    def _sidebar_quote_snapshot(code):
        # Timer rerenders must not trigger quote requests. Explicit refresh invalidates this.
        if 'sidebar_quote_snapshots' not in st.session_state: st.session_state.sidebar_quote_snapshots = {}
        if code not in st.session_state.sidebar_quote_snapshots:
            st.session_state.sidebar_quote_snapshots[code] = fetch_stock_quote(code)
        return st.session_state.sidebar_quote_snapshots[code]


    def _holding_alert_lights(code):
        item = _visible_holding_alerts().get(code)
        signal = item.get('signal') if item else None
        return tuple('🔴' if signal == label else '' for label in ('买入', '卖出', '持仓'))


    def _stock_list_header(kind):
        with st.container(key='stock_header_' + kind):
            widths = [3.1, 1.15, 1.5, .65, .65] if kind == 'watch' else [2.8, 1.05, 1.35, .55, .55, .8, .6]
            labels = ['股票', '价格', '当日涨幅', '', ''] if kind == 'watch' else ['股票', '价格', '当日涨幅', '买',
                                                                                   '卖', '持仓', '']
            columns = st.columns(widths, gap='small', vertical_alignment='center')
            for column, label in zip(columns, labels):
                with column: st.markdown('<div class="stock-list-heading">' + label + '</div>', unsafe_allow_html=True)


    def _stock_list_row(code, kind):
        quote = _sidebar_quote_snapshot(code)
        name = quote.get('name', code) if quote else code
        label = f'{name} ({code})' if name != code else code
        price = f"{quote['close']:.2f}" if quote else '—'
        pct = quote.get('change_pct') if quote else None
        color = '#ff858d' if pct is not None and pct > 0 else '#50d3ad' if pct is not None and pct < 0 else '#a5b3d3'
        change = f'{pct:+.2f}%' if pct is not None else '—'
        with st.container(key='stock_row_' + kind + '_' + code):
            widths = [3.1, 1.15, 1.5, .65, .65] if kind == 'watch' else [2.8, 1.05, 1.35, .55, .55, .8, .6]
            columns = st.columns(widths, gap='small', vertical_alignment='center')
            a, b, c = columns[:3]
            with a:
                st.button(label, key='goto_' + kind + '_' + code, on_click=_select_watch_stock, args=(code,),
                          help=label, use_container_width=True)
            with b:
                st.markdown('<div class="stock-list-cell">' + price + '</div>', unsafe_allow_html=True)
            with c:
                st.markdown(f'<div class="stock-list-cell" style="color:{color}">{change}</div>',
                            unsafe_allow_html=True)
            if kind == 'watch':
                d, e = columns[3:]
                added = code in st.session_state.manual_holdings
                with d:
                    st.button('✓' if added else '+', key='hold_add_' + code, on_click=_add_manual_holding, args=(code,),
                              disabled=added or bool(st.session_state.get('_holdings_load_error')),
                              help='已在持仓股' if added else '加入持仓股（仅记录，不下单）', use_container_width=True)
                with e:
                    st.button('×', key='del_' + code, on_click=_remove_watch_stock, args=(code,),
                              help='删除自选（不会移除持仓股）', use_container_width=True)
            else:
                for column, icon, help_text in zip(columns[3:6], _holding_alert_lights(code),
                                                   ['收盘买入指令，待下一可成交日执行',
                                                    '收盘卖出指令，待下一可成交日执行', '策略继续持仓，无新买卖指令']):
                    with column: st.markdown(
                        f'<div class="stock-list-cell" title="{help_text}" style="font-size:13px">{icon}</div>',
                        unsafe_allow_html=True)
                with columns[6]:
                    st.button('×', key='hold_del_' + code, on_click=_remove_manual_holding, args=(code,),
                              help='移出持仓股（不会卖出股票）', use_container_width=True)


    @st.fragment
    def render_watchlist():
        if st.session_state.pop('_watch_open_pending', False): st.rerun(scope='app')
        try:
            require_session()
            lists = cloud_store().lists()
            st.session_state.watchlist = lists['watchlist']
            st.session_state.manual_holdings = lists['holdings']
            st.session_state.holding_alert_state = _load_holding_alert_state()
            st.session_state.pop('_holdings_load_error', None)
        except CloudError as exc:
            st.error(str(exc))
            st.caption('数据库暂不可用，未显示旧列表，也不会覆盖保存或发送通知。')
            if st.button('重试数据库连接'): st.rerun(scope='app')
            return
        _visible_holding_alerts()
        if st.session_state.pop('_holding_check_on_page_run', False):
            _check_holding_close_signals()
        with st.container(key='stock_lists_panel'):
            with st.expander('📋 自选股管理', expanded=True):
                if st.button('🔄 刷新自选及持仓报价', use_container_width=True, key='refresh_watch_only'):
                    watch_loading = st.empty()
                    _show_loading_video(watch_loading)
                    try:
                        fetch_stock_quote.clear()
                        fetch_kline_with_fallback.clear()
                        st.session_state.sidebar_quote_snapshots = {}
                        st.session_state.holding_alert_state['checked'] = {}
                        _check_holding_close_signals()
                        for code in dict.fromkeys(st.session_state.watchlist + st.session_state.manual_holdings):
                            _sidebar_quote_snapshot(code)
                    finally:
                        watch_loading.empty()
                with st.form('add_watch_form', clear_on_submit=True):
                    a, b = st.columns([3, 1], vertical_alignment='center')
                    with a: new_code = st.text_input('添加股票代码或名称', placeholder='例如：洛阳钼业 / 603993',
                                                     label_visibility='collapsed')
                    with b: add_watch = st.form_submit_button('+', use_container_width=True)
                if add_watch:
                    st.session_state.pop('_watch_name_matches', None)
                    st.session_state.pop('_watch_name_choice', None)
                    try:
                        matches = _resolve_stock_input(new_code)
                        if len(matches) == 1:
                            _add_watch_code(matches[0]['code'])
                        else:
                            st.session_state['_watch_name_matches'] = matches
                    except ValueError as exc: st.error(str(exc))
                if st.session_state.get('_watch_name_matches'):
                    names = {row['code']: row['name'] for row in st.session_state['_watch_name_matches']}
                    st.caption('找到多个结果，请选中股票后再加入。')
                    selected = st.selectbox('选择要加入的股票', list(names),
                        format_func=lambda code: names[code] + '（' + code + '）', key='_watch_name_choice')
                    if st.button('加入当前名单自选', key='confirm_name_add'):
                        _add_watch_code(selected)
                        st.session_state.pop('_watch_name_matches', None)
                if st.session_state.get('_holdings_load_error'): st.error(st.session_state['_holdings_load_error'])
                notice = st.session_state.pop('_holdings_notice', None)
                if notice: st.caption(notice)
                _stock_list_header('watch')
                for code in st.session_state.watchlist[:]: _stock_list_row(code, 'watch')
                if not st.session_state.watchlist: st.caption('暂无自选股')
            st.divider()
            with st.expander('💼 持仓股', expanded=True):
                st.caption(
                    '手动记录列表，非券商实盘。不自动查询；打开网页或手动刷新时检查。当天收盘日线更新后，买／卖／持仓对应列亮🔴，同一时间只亮一灯；无新指令但模拟持股时亮持仓，空仓或数据未更新时全空；开盘后打开或刷新清除旧提醒。信号按本策略自2019-01-14起、初始10万元的模拟持仓计算，不按日涨跌幅判断。')
                _stock_list_header('holding')
                for code in st.session_state.manual_holdings[:]: _stock_list_row(code, 'holding')
                if not st.session_state.manual_holdings: st.caption('点击上方股票右侧的 + 加入持仓股。')
                st.caption('增删及报价刷新仅更新侧栏；点击股票名称再刷新主页面。')
        _render_feishu_settings()


    # ========== 核心计算函数 ==========
    def calc_macd(close, fast=5, slow=30, signal=10):
        ema_f = close.ewm(span=fast, adjust=False).mean()
        ema_s = close.ewm(span=slow, adjust=False).mean()
        diff = ema_f - ema_s
        dea = diff.ewm(span=signal, adjust=False).mean()
        return diff, dea


    def calc_kdj(high, low, close, n=12, m1=5, m2=5):
        low_min = low.rolling(n).min()
        high_max = high.rolling(n).max()
        rsv = ((close - low_min) / (high_max - low_min) * 100).fillna(50)
        K = rsv.ewm(span=m1, adjust=False).mean()
        D = K.ewm(span=m2, adjust=False).mean()
        J = 3 * K - 2 * D
        return K, D, J


    def fetch_intraday_data(code):
        return None  # 分时请求已锁定；只获取日线。
        code_str = str(code).strip()
        symbol = f"sh{code_str}" if code_str.startswith(('6', '688', '689')) else f"sz{code_str}"
        url = "https://quotes.sina.com.cn/api/jsonp_v2.php/var%20_data=/CN_MarketData.getMinuteLineData"
        params = {"symbol": symbol, "scale": "5", "datalen": "240"}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        session = requests.Session()
        session.proxies = {"http": None, "https": None}
        session.trust_env = True
        try:
            resp = session.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                match = re.search(r'\((.*)\)', resp.text)
                if match:
                    data = json_lib.loads(match.group(1))
                    if data and len(data) >= 2:
                        rows = [{'time': i[0], 'price': float(i[1]), 'volume': float(i[2])} for i in data if
                                len(i) >= 3]
                        if rows:
                            df = pd.DataFrame(rows)
                            today = datetime.now().strftime('%Y-%m-%d')
                            df['datetime'] = pd.to_datetime(today + ' ' + df['time'], errors='coerce')
                            return df.dropna(subset=['datetime'])
        except Exception:
            pass
        return None


    def _normalize_tushare_daily(raw, factors, period, start_date, end_date):
        if raw is None or raw.empty: return None
        if factors is None or factors.empty: raise ValueError('缺少复权因子，不能冒充前复权行情')
        df = raw.rename(columns={'trade_date': 'date', 'vol': 'volume'}).copy()
        fac = factors.rename(columns={'trade_date': 'date'}).copy()
        df['date'] = pd.to_datetime(df['date']);
        fac['date'] = pd.to_datetime(fac['date'])
        if df.date.duplicated().any() or fac.date.duplicated().any(): raise ValueError('行情日期重复')
        df = df.merge(fac[['date', 'adj_factor']], on='date', how='left').sort_values('date')
        fields = ['open', 'high', 'low', 'close', 'volume', 'amount', 'adj_factor']
        for col in fields: df[col] = pd.to_numeric(df[col], errors='raise')
        if not np.isfinite(df[fields].to_numpy()).all() or (df.adj_factor <= 0).any(): raise ValueError(
            '复权或行情字段不完整')
        anchor = float(df.adj_factor.iloc[-1])
        for col in ['open', 'high', 'low', 'close']: df[col] = df[col] * df.adj_factor / anchor
        df['amount'] = df['amount'] * 1000.  # TuShare金额千元 -> 元；成交量已经是手。
        df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)
        if now.hour < 15: df = df[df.date < now.normalize()]
        if period in ['week', 'month']:
            groups = df.date.dt.to_period('W-FRI' if period == 'week' else 'M')
            df = df.groupby(groups, sort=True).agg(date=('date', 'last'), open=('open', 'first'), high=('high', 'max'),
                                                   low=('low', 'min'), close=('close', 'last'),
                                                   volume=('volume', 'sum'), amount=('amount', 'sum')).reset_index(
                drop=True)
        df = df[df.date.between(pd.Timestamp(start_date), pd.Timestamp(end_date))].reset_index(drop=True)
        df.attrs.update(source='TuShare', adjustment='qfq', adjustment_anchor=anchor, period=period)
        return df


    def _provider_error(exc):
        # Never render third-party exception bodies: some SDKs include request tokens.
        message = str(exc).lower()
        if any(word in message for word in ('权限', '积分', 'permission')):
            return '数据接口权限不足，请在 TuShare 账户核对权限；Token 有效不代表有接口权限。'
        if any(word in message for word in ('timeout', 'timed out', 'connection', 'proxy')):
            return '行情接口连接失败或超时，请稍后重试。'
        if 'tushare_token' in message:
            return '尚未在 Streamlit Secrets 配置 TUSHARE_TOKEN，备用行情源不可用。'
        return '行情接口暂不可用或返回数据异常，请稍后重试。'


    @st.cache_resource
    def _factor_store():
        import threading
        return {'lock': threading.Lock(), 'values': {}, 'blocked': {}}


    def _get_tushare_factors(pro, token, ts_code, fund, start_date, end_date):
        import hashlib, time
        store = _factor_store()
        account = hashlib.sha256(token.encode()).hexdigest()
        endpoint = 'fund_adj' if fund else 'adj_factor'
        key = (account, endpoint, ts_code, str(start_date), str(end_date))
        limit_key = (account, endpoint)
        with store['lock']:
            now = time.monotonic()
            saved = store['values'].get(key)
            if saved and now - saved[0] < 3600: return saved[1].copy()
            blocked = store['blocked'].get(limit_key, 0)
            if blocked > now:
                raise RuntimeError(f'{endpoint}此前被服务端限流，暂停重试；约{int((blocked - now) / 60) + 1}分钟后再试')
            try:
                func = pro.fund_adj if fund else pro.adj_factor
                factor = func(ts_code=ts_code, start_date=start_date, end_date=end_date)
            except Exception as exc:
                message = _provider_error(exc)
                if any(word in message for word in ['频率', '限流', '每小时', '次/小时', 'rate limit']):
                    store['blocked'][limit_key] = now + 3600
                raise RuntimeError('TuShare ' + endpoint + '：' + message) from None
            if factor is None or factor.empty: raise ValueError('未取得复权因子，不能生成前复权日线')
            store['values'][key] = (time.monotonic(), factor.copy())
            return factor


    def _trade_display_rows(result):
        if not result: return []
        rows = [dict(row) for row in result.get('交易明细', [])]
        open_trade = result.get('未平仓信息')
        if open_trade:
            row = dict(open_trade)
            buys = [f for f in result.get('成交记录', []) if
                    f['side'] == 'BUY' and pd.Timestamp(f['date']) == pd.Timestamp(row['买入日期'])]
            fee = float(buys[-1]['fee']) if buys else float('nan')
            cost = float(row['买入总金额']) + fee
            pnl = float(result['期末浮动盈亏'])
            row.update({'交易模式': '持仓中', '买入费用': fee, '卖出费用': float('nan'),
                        '卖出日期': pd.NaT, '卖出价': float('nan'), '卖出后账户余额': float('nan'),
                        '盈亏金额': pnl, '收益率%': pnl / cost * 100 if cost > 0 else float('nan'),
                        '卖出条件': '尚未卖出（盈亏为期末浮动盈亏）'})
            rows.append(row)
        return rows


    @st.cache_data(ttl=300, show_spinner=False)
    def fetch_kline_tushare(code, start_date, end_date, period='day'):
        if not TUSHARE_ENABLED: return None
        if period != 'day': raise ValueError('仅允许获取日线，其他周期已锁定')
        import tushare as ts
        token = secret('TUSHARE_TOKEN')
        if not token: raise ValueError('请在 Secrets 配置 TUSHARE_TOKEN')
        pro = ts.pro_api(token=token, timeout=15)
        code = str(code).strip()
        if not re.fullmatch(r'\d{6}', code): raise ValueError('证券代码无效')
        ts_code = code + ('.SH' if code.startswith(('5', '6', '9')) else '.SZ')
        fund = code.startswith(('1', '5'))
        daily = pro.fund_daily if fund else pro.daily
        adjustment = pro.fund_adj if fund else pro.adj_factor
        start = pd.Timestamp(start_date) - (pd.Timedelta(days=40) if period != 'day' else pd.Timedelta(0))
        end = pd.Timestamp(end_date)
        if start > end: raise ValueError('开始日期晚于结束日期')
        prices = []
        while start <= end:
            stop = min(start + pd.DateOffset(years=3) - pd.Timedelta(days=1), end)
            args = dict(ts_code=ts_code, start_date=start.strftime('%Y%m%d'), end_date=stop.strftime('%Y%m%d'))
            try:
                chunk = daily(**args)
            except Exception as exc:
                raise RuntimeError(
                    ('TuShare基金日线' if fund else 'TuShare股票日线') + '：' + _provider_error(exc)) from None
            if chunk is not None and not chunk.empty:
                prices.append(chunk)
            start = stop + pd.Timedelta(days=1)
        if not prices: return None
        # Fetch factors once for the entire range, not once per price chunk.
        factors = _get_tushare_factors(pro, token, ts_code, fund, start_date, end_date)
        return _normalize_tushare_daily(pd.concat(prices, ignore_index=True), factors, 'day', start_date, end_date)


    def fetch_kline_tencent(code, count=300):
        code_str = str(code).strip()
        symbol = f"sh{code_str}" if code_str.startswith(('6', '688', '689')) else f"sz{code_str}"
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {"param": f"{symbol},day,,,{count},qfq"}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
        session = requests.Session()
        session.proxies = {"http": None, "https": None}
        session.trust_env = True
        try:
            resp = session.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0 and data.get('data', {}).get(symbol, {}).get('qfqday'):
                    rows = []
                    for line in data['data'][symbol]['qfqday']:
                        p = line.split(',')
                        rows.append({'date': p[0], 'open': float(p[1]), 'close': float(p[2]), 'high': float(p[3]),
                                     'low': float(p[4]), 'volume': float(p[5])})
                    df = pd.DataFrame(rows)
                    df['date'] = pd.to_datetime(df['date'], errors='coerce')
                    return df.dropna(subset=['date'])
        except Exception:
            pass
        return None


    def fetch_kline_sina(code, count=300):
        code_str = str(code).strip()
        symbol = f"sh{code_str}" if code_str.startswith(('6', '688', '689')) else f"sz{code_str}"
        url = "https://quotes.sina.com.cn/api/jsonp_v2.php/var%20_data=/CN_MarketData.getKLineData"
        params = {"symbol": symbol, "scale": "240", "ma": "no", "datalen": str(count)}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        session = requests.Session()
        session.proxies = {"http": None, "https": None}
        session.trust_env = True
        try:
            resp = session.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                match = re.search(r'\((.*)\)', resp.text)
                if match:
                    data = json_lib.loads(match.group(1))
                    if data:
                        df = pd.DataFrame(data)
                        df['date'] = pd.to_datetime(df['day'], errors='coerce')
                        df = df.dropna(subset=['date']).rename(columns={'day': 'date'})
                        for c in ['open', 'high', 'low', 'close', 'volume']:
                            df[c] = df[c].astype(float)
                        return df[['date', 'open', 'high', 'low', 'close', 'volume']]
        except Exception:
            pass
        return None


    @st.cache_resource
    def _baostock_lock():
        import threading
        return threading.Lock()


    def _normalize_bs_kline(rows, fields, period):
        frame = pd.DataFrame(rows, columns=fields)
        if frame.empty:
            return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        if period == '30':
            frame['date'] = pd.to_datetime(frame['time'], format='%Y%m%d%H%M%S%f', errors='raise')
        else:
            frame['date'] = pd.to_datetime(frame['date'], format='%Y-%m-%d', errors='raise')
        for name in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            frame[name] = pd.to_numeric(frame[name], errors='raise')
        if not np.isfinite(frame[['open', 'high', 'low', 'close', 'volume', 'amount']].to_numpy()).all():
            raise ValueError('BaoStock行情含缺失或非有限数值，未进行填充')
        if (frame[['open', 'high', 'low', 'close']] <= 0).any().any() or (frame[['volume', 'amount']] < 0).any().any():
            raise ValueError('BaoStock行情含无效价格或成交量')
        if frame['date'].duplicated().any():
            raise ValueError('BaoStock行情时间重复，未拼接或填充数据')
        # BaoStock成交量单位是股；原应用/CSV及图表使用手，统一除以100。
        frame['volume'] = frame['volume'] / 100.0
        frame = frame[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']].sort_values('date').reset_index(
            drop=True)
        frame.attrs.update(source='BaoStock', period=period, adjust='前复权', volume_unit='手', amount_unit='元')
        return frame


    @st.cache_data(ttl=300, show_spinner=False)
    def fetch_kline_baostock(code, start_date, end_date, period='day'):
        try:
            import baostock as bs
        except ImportError as exc:
            raise RuntimeError('请先安装BaoStock：python -m pip install baostock') from exc
        if period != 'day':
            raise ValueError('仅允许获取日线，其他周期已锁定')
        if not re.fullmatch(r'\d{6}', str(code)):
            raise ValueError('请输入6位股票代码')
        if code.startswith(('5', '6', '9')):
            symbol = 'sh.' + code
        elif code.startswith(('0', '1', '2', '3')):
            symbol = 'sz.' + code
        else:
            raise ValueError('此接口仅接入沪深证券，不支持该代码所属市场')
        start = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end = pd.to_datetime(end_date).strftime('%Y-%m-%d')
        if start > end:
            raise ValueError('开始日期不能晚于结束日期')
        freq = {'day': 'd', '30': '30', 'week': 'w', 'month': 'm'}[period]
        fields = 'date,time,code,open,high,low,close,volume,amount' if period == '30' else 'date,code,open,high,low,close,volume,amount'
        # BaoStock使用共享连接；一次登录、查询、读完结果、退出全过程串行。
        with _baostock_lock():
            login = bs.login()
            if login.error_code != '0':
                raise RuntimeError('BaoStock登录失败：' + str(login.error_msg))
            try:
                result = bs.query_history_k_data_plus(symbol, fields, start_date=start, end_date=end, frequency=freq,
                                                      adjustflag='2')
                if result.error_code != '0':
                    raise RuntimeError('BaoStock查询失败：' + str(result.error_msg))
                rows = []
                while result.next():
                    rows.append(result.get_row_data())
                if result.error_code != '0':
                    raise RuntimeError('BaoStock行情读取不完整：' + str(result.error_msg))
                frame = _normalize_bs_kline(rows, result.fields, period)
            finally:
                bs.logout()
        # 日内未结束K线不展示为完整历史K线；分钟时间为区间结束时间。
        now = pd.Timestamp.now(tz='Asia/Shanghai').tz_localize(None)
        if period == '30':
            frame = frame.loc[frame['date'] <= now].reset_index(drop=True)
        elif period == 'day' and now.time() < pd.Timestamp('15:00').time():
            frame = frame.loc[frame['date'] < now.normalize()].reset_index(drop=True)
        return frame


    @st.cache_data(ttl=300, show_spinner=False)
    def fetch_kline_with_fallback(code, start_date, end_date, period='day'):
        if period != 'day':
            st.error('仅允许日线，已阻止其他周期请求')
            return None
        # Always replace the whole requested series; never splice providers.
        failures = []
        for name, fetch in [('BaoStock', fetch_kline_baostock), ('TuShare', fetch_kline_tushare)]:
            try:
                frame = fetch(code, start_date, end_date, period)
                if frame is None or frame.empty:
                    failures.append(name + '无数据');
                    continue
                frame = frame.copy()
                frame.attrs.update(source=name, adjustment='qfq', period=period, fallback_notes='；'.join(failures))
                return frame
            except Exception as exc:
                # Show actionable provider errors, with all credentials and URLs redacted.
                failures.append(name + '失败：' + _provider_error(exc))
        detail = '；'.join(failures)
        if period == '30': detail += '；30分钟仅使用真实分钟行情，本版TuShare备用只支持日/周/月线'
        st.error(detail)
        return None


    def get_signals_and_kline(code, start_date, end_date, period='day'):
        df = fetch_kline_with_fallback(code, start_date, end_date, period)
        if df is None or len(df) < 10:
            return None, None, None
        return {}, df.iloc[-1]['close'], df


    # ================================================================
    # ========== 回测引擎（统一参数 · 三因子退出） ==========
    # ================================================================
    THREE_COOL_DEFAULT = dict(n1=5, up1=.08, ng1=8, drop1=.10, ns1=5, ups1=.05,
                              ng2=10, dropg2=.15, ns2=6, drops2=.10)
    THREE_COOL_OPTIMIZED = dict(n1=1, up1=.05, ng1=15, drop1=.15, ns1=3, ups1=.05,
                                ng2=5, dropg2=.10, ns2=3, drops2=.05)


    class _ThreeStageCooling:
        def __init__(self, p):
            self.p = dict(p)
            for k in ['n1', 'ng1', 'ns1', 'ng2', 'ns2']:
                if int(p[k]) != p[k] or p[k] < 1: raise ValueError('冷却天数必须为正整数')
            for k in ['up1', 'drop1', 'ups1', 'dropg2', 'drops2']:
                if not 0 < p[k] < 1: raise ValueError('冷却百分比必须在0与1之间')
            self.stage = 0;
            self.start = 0;
            self.sale = 0.;
            self.p1 = 0.;
            self.p2 = 0.;
            self.seen = False;
            self.low = float('inf')

        def begin(self, i, price):
            self.stage = 1;
            self.start = i + 1;
            self.sale = price;
            self.p1 = self.p2 = 0.;
            self.seen = False;
            self.low = float('inf')

        def step(self, i, close, low):
            if not self.stage or i < self.start: return
            days = i - self.start + 1;
            p = self.p
            if self.stage == 1:
                self.seen |= close <= self.sale * (1 - p['drop1'])
                if close >= self.sale * (1 + p['up1']):
                    self.stage = 0
                elif days >= p['n1']:
                    self.p1 = close;
                    self.stage = 2 if self.seen else 3;
                    self.start = i + 1;
                    self.seen = False;
                    self.low = float('inf')
            elif self.stage == 2:
                self.seen |= close <= self.p1 * (1 - p['dropg2'])
                if close > self.p1:
                    self.stage = 0
                elif days >= p['ng1']:
                    self.stage = 4 if self.seen else 0;
                    self.start = i + 1
            elif self.stage == 3:
                self.low = min(self.low, low)
                if close >= self.sale * (1 + p['ups1']):
                    self.stage = 0
                elif days >= p['ns1']:
                    self.p2 = close
                    self.stage = 5 if close <= self.p1 * (1 - p['drops2']) and self.low <= self.p1 * (
                                1 - p['drops2']) else 0
                    self.start = i + 1
            elif self.stage == 4:
                if close > self.p1 or days >= p['ng2']: self.stage = 0
            elif self.stage == 5:
                if close > self.p2 or days >= p['ns2']: self.stage = 0


    class _FixedCoolingD:
        """卖出日T不计入冷却，锁定T+1至T+19；最早T+20开盘买入。"""

        def __init__(self):
            self.stage = 0
            self.start = 0
            self.sale = self.p1 = self.p2 = 0.0

        def begin(self, i, price):
            self.stage = 1
            self.start = i + 1
            self.sale = float(price)
            self.p1 = self.p2 = 0.0

        def step(self, i, close, low):
            if self.stage and i >= self.start and i - self.start + 1 >= 19:
                self.stage = 0


    def backtest_strategy(df, initial_cash=100000, backtest_start=None, backtest_end=None,
                          buy_threshold=3, sell_threshold=2,
                          signal4_lookback=30, signal4_threshold=0.2,
                          long_buy_threshold=None, short_buy_threshold=None,
                          long_sell_threshold=None, short_sell_threshold=None,
                          first_cooling=None, second_cooling=None, third_cooling=None,
                          cooling_params=None):
        """六道候选策略：MA10入场，技术与风控组合；常规持有12日，90日滞涨检查，固定19日冷却。
        旧形参仅为兼容原页面调用，不参与计算；所有股票使用完全相同的参数。
        保留完整输入预热；收盘信号、下一可成交日开盘成交；期末只计价不强平。
        """
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        if df.empty:
            return {}
        if (not df['date'].is_monotonic_increasing or df['date'].duplicated().any()):
            raise ValueError("行情日期必须升序且不能重复")
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='raise')
        if df[['date', 'open', 'high', 'low', 'close', 'volume']].isna().any().any():
            raise ValueError("行情存在缺失值，不能进行可核验回测")
        if initial_cash <= 0:
            raise ValueError("初始资金必须大于0")

        # 先在完整历史上预热，再截取区间。所有股票共享下列固定参数。
        for ma in [5, 10, 20, 30, 39, 40, 42, 50, 60, 120, 250]:
            df[f'MA{ma}'] = df['close'].rolling(ma).mean()
        amount_proxy = df['volume'] * df['close']
        for m in [2, 3, 5, 10, 30, 60, 180, 250]:
            df[f'M{m}'] = amount_proxy.rolling(m).mean()
        df['DIFF'], df['DEA'] = calc_macd(df['close'], fast=3, slow=39, signal=9)
        df['buy_sig1'] = (df['close'] > df['MA10']) & (df['MA10'] > df['MA10'].shift(1))
        # 入场附加过滤：均线偏离上限及成交额活跃度范围。
        df['buy_sig1'] &= df['M10'] < df['M30'] * 1000000.0
        activity = df['M5'] / df['M30']
        df['buy_sig1'] &= (df['MA5'] / df['MA120'] <= 1.8) & (activity >= 0.0) & (activity <= 1000.0)
        # 六道候选：均线入场，成交额和偏离过滤；买入不要求MACD多头。
        buy_activity = df['M2'] / df['M30']
        df['buy_sig1'] &= (buy_activity >= 0.2) & (buy_activity <= 2.2)
        weak = df['DIFF'] < df['DEA']
        df['sell_sig1'] = (df['MA5'] / df['MA120'] >= 1.025) & weak
        df['sell_sig2'] = (df['close'] < df['MA40']) & (df['MA40'] < df['MA40'].shift(1))
        df['sell_sig3'] = (df['M3'] > df['M180'] * 3.9) & weak
        df['卖点信号数'] = df[['sell_sig1', 'sell_sig2', 'sell_sig3']].sum(axis=1)
        mask = df['M250'].notna()
        if backtest_start is not None:
            mask &= df['date'] >= pd.to_datetime(backtest_start)
        if backtest_end is not None:
            mask &= df['date'] <= pd.to_datetime(backtest_end)
        df = df.loc[mask].reset_index(drop=True)
        if df.empty:
            return {}

        def fee(gross, date, is_sell):
            transfer = 0.00002 if date < pd.Timestamp('2022-04-29') else 0.00001
            stamp = 0.001 if date < pd.Timestamp('2023-08-28') else 0.0005
            return max(5.0, gross * 0.0003) + gross * (transfer + (stamp if is_sell else 0))

        cash, position = float(initial_cash), 0
        pending = None
        entry = None
        cooling = _FixedCoolingD()
        trades, fills, daily = [], [], []
        peak, max_dd = float(initial_cash), 0.0
        for i, row in df.iterrows():
            date = row['date']
            filled = ''
            if pending is not None and row['volume'] > 0:
                side = pending['side']
                price = float(row['open']) * (1.001 if side == 'buy' else 0.999)
                if side == 'buy':
                    shares = int(cash // (price * 100)) * 100
                    while shares and shares * price + fee(shares * price, date, False) > cash:
                        shares -= 100
                    if shares:
                        gross = shares * price
                        costs = fee(gross, date, False)
                        cash -= gross + costs
                        position = shares
                        entry = {'index': i, 'date': date, 'signal_date': pending['date'],
                                 'price': price, 'shares': shares, 'gross': gross,
                                 'fee': costs, 'cost': gross + costs}
                        filled = 'buy'
                        fills.append({'date': date, 'signal_date': pending['date'], 'side': 'BUY',
                                      'price': price, 'shares': shares, 'fee': costs,
                                      'cash_change': -gross - costs, 'cash_after': cash})
                else:
                    gross = position * price
                    costs = fee(gross, date, True)
                    net = gross - costs
                    pnl = net - entry['cost']
                    cash += net
                    trades.append({
                        '买入日期': entry['date'], '买入信号日期': entry['signal_date'],
                        '交易模式': '常规卖出',
                        '买入条件': '收盘价>MA10且MA10上行，0.2≤M2/M30≤2.2，MA5/MA120≤1.8',
                        '买入价': entry['price'], '买入股数': entry['shares'],
                        '买入总金额': entry['gross'], '买入费用': entry['fee'],
                        '卖出日期': date, '卖出信号日期': pending['date'],
                        '卖出条件': pending['reason'], '卖出价': price,
                        '卖出总金额': gross, '卖出费用': costs,
                        '收益率%': pnl / entry['cost'] * 100, '盈亏金额': pnl,
                        '买点信号数': 1, '卖点信号数': pending['score']
                    })
                    fills.append({'date': date, 'signal_date': pending['date'], 'side': 'SELL',
                                  'price': price, 'shares': position, 'fee': costs,
                                  'cash_change': net, 'cash_after': cash})
                    position, entry = 0, None
                    cooling.begin(i, price)
                    filled = 'sell'
                pending = None

            decision = ''
            holding_bars = i - entry['index'] + 1 if entry is not None else 0
            score = int(row['卖点信号数'])
            if not position:
                cooling.step(i, float(row['close']), float(row['low']))
            if position:
                # 独立退出不要求凑足常规卖点。涨幅以含滑点的实际买入价格计算。
                price_return = float(row['close']) / entry['price'] - 1.0
                stale_exit = (holding_bars >= 90 and price_return < 0.08
                              and float(row['close']) < float(row['MA42']))
                loss_exit = price_return <= -0.35
                regular_exit = holding_bars >= 12 and score >= 2
                if pending is None and (loss_exit or stale_exit or regular_exit):
                    labels = [label for key, label in [
                        ('sell_sig1', 'MA5/MA120>=1.025且MACD空头'),
                        ('sell_sig2', '跌破MA40且MA40低于1根前'),
                        ('sell_sig3', 'M3>M180×3.9且MACD空头')] if row[key]]
                    decision = '卖出'
                    pending = {'side': 'sell', 'date': date, 'score': score,
                               'reason': ('收盘亏损达到35%' if loss_exit else
                                          '持仓满90日、涨幅不足8%且跌破MA42' if stale_exit else
                                          ' + '.join(labels))}
            elif pending is None and cooling.stage == 0 and row['buy_sig1']:
                decision = '买入'
                pending = {'side': 'buy', 'date': date}
            equity = cash + position * float(row['close'])
            peak = max(peak, equity)
            max_dd = max(max_dd, 1 - equity / peak)
            daily.append({'date': date, '现金': cash, '持股数': position, '账户净值': equity,
                          '持仓K线数': holding_bars, '冷却状态': cooling.stage,
                          '冷却阶段起始索引': cooling.start, '卖出参考价': cooling.sale,
                          '一级结束价P1': cooling.p1, '慢牛1结束价P2': cooling.p2,
                          '当日成交': filled, '收盘指令': decision})

        # 期末按收盘价计价，未平仓不伪造为已实现交易，也不计入已平仓胜率。
        final_equity = cash + position * float(df.iloc[-1]['close'])
        unrealized = position * float(df.iloc[-1]['close']) - entry['cost'] if entry else 0.0
        open_trade = None
        if entry:
            open_trade = {'买入日期': entry['date'], '交易模式': '持仓中',
                          '买入条件': '收盘价>MA10且MA10上行，0.2≤M2/M30≤2.2，MA5/MA120≤1.8',
                          '买入价': entry['price'], '买入股数': position,
                          '买入总金额': entry['gross'], '卖出日期': pd.NaT,
                          '卖出条件': '尚未平仓', '卖出价': float('nan'),
                          '卖出总金额': float('nan')}
        pnls = [t['收益率%'] for t in trades]
        win_rate = sum(t['盈亏金额'] > 0 for t in trades) / len(trades) * 100 if trades else 0.0
        assert abs(float(initial_cash) + sum(f['cash_change'] for f in fills) - cash) < 1e-5
        assert abs(sum(t['盈亏金额'] for t in trades) + unrealized -
                   (final_equity - float(initial_cash))) < 1e-5
        assert all(f['signal_date'] < f['date'] for f in fills)
        sig = df.merge(pd.DataFrame(daily), on='date', how='left')
        return {
            '交易次数': len(trades), '总收益率%': (final_equity / initial_cash - 1) * 100,
            '平均收益率%': sum(pnls) / len(pnls) if pnls else 0.0, '胜率%': win_rate,
            '最大单次收益%': max(pnls) if pnls else 0.0, '最小单次收益%': min(pnls) if pnls else 0.0,
            '最大回撤%': max_dd * 100, '初始资金': initial_cash, '最终资金': final_equity,
            '总盈亏金额': final_equity - initial_cash,
            '长线交易次数': 0, '长线胜率%': 0.0, '短线交易次数': 0, '短线胜率%': 0.0,
            '交易明细': trades, '信号数据': sig, '成交记录': fills,
            '期末持股数': position, '期末浮动盈亏': unrealized, '未平仓信息': open_trade
        }


    # ========== K线绘图（红绿买卖点，含强制平仓原因） ==========
    def plot_kline(df, stock_name, period_name, trade_df=None, display_bars=None):
        df = df.copy()
        for ma in [5, 10, 20, 30, 60, 120, 250]:
            df[f'MA{ma}'] = df['close'].rolling(ma).mean()
        df['chg'] = df['close'].pct_change() * 100
        df['chg'] = df['chg'].fillna(0)
        df['vw'] = df['volume'] / 10000
        # Calculate indicators on the full history BEFORE trimming display rows.
        if display_bars is not None:
            df = df.tail(int(display_bars)).copy()
        cd = df[['vw', 'chg']].values

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])

        # K线
        fig.add_trace(go.Candlestick(
            x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='K线',
            increasing=dict(line=dict(color='red'), fillcolor='red'),
            decreasing=dict(line=dict(color='green'), fillcolor='green'),
            customdata=cd,
            hovertemplate='<b>%{x}</b><br>开:%{open:.2f} 高:%{high:.2f} 低:%{low:.2f} 收:%{close:.2f}<br>量:%{customdata[0]:.2f}万手 幅:%{customdata[1]:.2f}%<extra></extra>'
        ), row=1, col=1)

        # 均线
        colors = ['orange', 'purple', 'blue', 'red', 'green', 'brown', 'pink']
        for i, ma in enumerate([5, 10, 20, 30, 60, 120, 250]):
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[f'MA{ma}'], mode='lines', name=f'MA{ma}',
                line=dict(color=colors[i % 7], width=1.2 if ma in [5, 20, 30] else 1)
            ), row=1, col=1)

        # ---- 买卖点标记 ----
        if trade_df is not None and not trade_df.empty:
            # 买入点（红色▲）
            buy_dates = pd.to_datetime(trade_df['买入日期']).unique()
            buy_df = df[df['date'].isin(buy_dates)]
            if not buy_df.empty:
                fig.add_trace(go.Scatter(
                    x=buy_df['date'], y=buy_df['low'] * 0.96,
                    mode='markers+text', name='买入 (红)',
                    marker=dict(symbol='triangle-up', size=18, color='red'),
                    text='B', textposition='bottom center',
                    textfont=dict(color='red', size=12, family='Arial Black'),
                    hovertemplate='<b>买入</b><br>日期:%{x}<br>价格:%{y:.2f}<extra></extra>'
                ), row=1, col=1)

            # 常规卖出（绿色▼）
            sell_normal = trade_df[trade_df['交易模式'] == '常规卖出']
            if not sell_normal.empty:
                sell_dates = pd.to_datetime(sell_normal['卖出日期']).unique()
                sell_df = df[df['date'].isin(sell_dates)]
                if not sell_df.empty:
                    fig.add_trace(go.Scatter(
                        x=sell_df['date'], y=sell_df['high'] * 1.04,
                        mode='markers+text', name='常规卖出 (绿)',
                        marker=dict(symbol='triangle-down', size=18, color='green'),
                        text='S', textposition='top center',
                        textfont=dict(color='green', size=12, family='Arial Black'),
                        hovertemplate='<b>常规卖出</b><br>日期:%{x}<br>价格:%{y:.2f}<extra></extra>'
                    ), row=1, col=1)

            # 强制平仓（绿色菱形，悬停显示原因）
            sell_force = trade_df[trade_df['交易模式'].str.contains('强制平仓')]
            if not sell_force.empty:
                sell_dates = pd.to_datetime(sell_force['卖出日期']).unique()
                sell_df = df[df['date'].isin(sell_dates)]
                if not sell_df.empty:
                    force_descs = sell_force.groupby('卖出日期')['卖出条件'].apply(
                        lambda x: ' | '.join(x.unique())).to_dict()
                    customdata_list = []
                    for d in sell_df['date']:
                        d_str = d.strftime('%Y-%m-%d') if isinstance(d, pd.Timestamp) else str(d)
                        desc = force_descs.get(d_str, '强制平仓')
                        customdata_list.append(desc)
                    fig.add_trace(go.Scatter(
                        x=sell_df['date'], y=sell_df['high'] * 1.08,
                        mode='markers+text', name='强制平仓 (绿◇)',
                        marker=dict(symbol='diamond', size=18, color='green'),
                        text='S', textposition='top center',
                        textfont=dict(color='green', size=12, family='Arial Black'),
                        customdata=customdata_list,
                        hovertemplate='<b>强制平仓</b><br>日期:%{x}<br>原因:%{customdata}<extra></extra>'
                    ), row=1, col=1)

        # 成交量
        vc = ['red' if c >= o else 'green' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df['date'], y=df['vw'], name='成交量', marker_color=vc), row=2, col=1)

        fig.update_xaxes(type='category', tickformat=("%m-%d %H:%M" if period_name == "30分钟K" else "%Y-%m-%d"),
                         dtick=10, row=1, col=1)
        fig.update_xaxes(type='category', tickformat=("%m-%d %H:%M" if period_name == "30分钟K" else "%Y-%m-%d"),
                         dtick=10, row=2, col=1, showticklabels=False)
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="万手", row=2, col=1)
        fig.update_layout(
            title=f"{stock_name} - {period_name}（BaoStock前复权）", height=900,
            xaxis_rangeslider_visible=False, template='plotly_dark',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        return fig


    def plot_intraday(df, name):
        if df is None or df.empty:
            return None
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig.add_trace(go.Scatter(x=df['datetime'], y=df['price'], mode='lines', name='价格', line=dict(color='blue')),
                      row=1, col=1)
        df['ap'] = df['price'].rolling(5).mean()
        fig.add_trace(go.Scatter(x=df['datetime'], y=df['ap'], mode='lines', name='均价5',
                                 line=dict(color='orange', dash='dash')), row=1, col=1)
        fig.add_trace(go.Bar(x=df['datetime'], y=df['volume'], name='量', marker_color='lightblue'), row=2, col=1)
        fig.update_xaxes(tickformat="%H:%M", type='date')
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="量", row=2, col=1)
        fig.update_layout(title=f"{name} 分时(5min)", height=500, template='plotly_dark')
        return fig


    @st.cache_data(ttl=300, show_spinner=False)
    def fetch_chip_data(code):
        try:
            df = ak.stock_cyq_em(symbol=str(code).strip())
            return df if df is not None and not df.empty else None
        except Exception:
            return None


    def plot_chip_chart(df, name):
        if df is None or df.empty:
            return None
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 8))
        a1.plot(df['日期'], df['平均成本'], 'b--', lw=1.5, label='均成本')
        a1.fill_between(df['日期'], df['90成本-低'], df['90成本-高'], color='gray', alpha=0.3, label='90%区间')
        a1.set_title(f'{name} 筹码分析', fontsize=14)
        a1.legend(loc='upper left')
        a1.grid(True, alpha=0.3)
        a2.bar(df['日期'], df['获利比例'], color='red', alpha=0.5, label='获利比')
        a2.plot(df['日期'], df['90集中度'], 'go-', lw=1.5, label='90集中')
        a2.set_xlabel('日期')
        a2.legend(loc='upper left')
        a2.grid(True, alpha=0.3)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        img = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        return img


    @st.cache_data(max_entries=16, show_spinner=False)
    def cached_backtest_strategy(df, **kwargs):
        # 仅缓存相同数据与相同参数的结果，不改变策略、费用或成交时点。
        return backtest_strategy(df, **kwargs)


    st.session_state._holding_check_on_page_run = True
    with st.sidebar:
        render_watchlist()

    # ========== 主界面 ==========
    if st.session_state.get('target_code'):
        search_default = st.session_state.target_code
        st.session_state.target_code = ''
        st.session_state['search_input'] = search_default
        auto_q = True
    else:
        search_default = st.session_state.get('search_input', '')
        auto_q = False

    st.markdown('<div id="market-query" class="biu-anchor"></div>', unsafe_allow_html=True)
    if st.session_state.get('current_code') or auto_q:
        st.markdown('<nav class="biu-nav" aria-label="工作台分区"><a href="#market-query" target="_self">行情查询</a><a href="#price-chart" target="_self">K线工作区</a><a href="#strategy-backtest" target="_self">策略回测</a><a href="#source-data" target="_self">原始数据</a></nav>', unsafe_allow_html=True)
    st.subheader("行情查询")
    with st.form("market_query_form"):
        sc1, sc2, sc3 = st.columns([3, 1, 1])
        with sc1:
            search_code = st.text_input("股票代码或中文名称", placeholder="洛阳钼业 / 603993", value=search_default,
                                        label_visibility="collapsed", key="search_input")
        with sc2:
            period_choice = '日K'
            st.caption('仅日K（其他周期已锁定）')
        with sc3:
            search_btn = st.form_submit_button("🔍 确认查询", use_container_width=True)

        st.markdown("**📅 时间范围**")
        cd1, cd2 = st.columns(2)
        with cd1:
            start_date = st.date_input("开始", value=datetime(2018, 1, 1), max_value=_china_now().date())
        with cd2:
            end_date = st.date_input("结束", value=_china_now().date(), max_value=_china_now().date())

    if search_btn or st.session_state.get('force_query', False):
        st.session_state.pop('_main_name_matches', None)
        st.session_state.pop('_main_name_choice', None)
        try:
            matches = _resolve_stock_input(search_code)
            if len(matches) == 1:
                search_code = matches[0]['code']
            else:
                st.session_state['_main_name_matches'] = matches
                search_btn = False
                st.session_state['force_query'] = False
        except ValueError as exc:
            st.error(str(exc))
            search_btn = False
            st.session_state['force_query'] = False
    if st.session_state.get('_main_name_matches'):
        names = {row['code']: row['name'] for row in st.session_state['_main_name_matches']}
        st.info('找到多个结果，请选择具体股票；下方若有图表，仍是上次查询结果。')
        chosen = st.selectbox('选择要查询的股票', list(names),
            format_func=lambda code: names[code] + '（' + code + '）', key='_main_name_choice')
        if st.button('查询这只股票', key='confirm_name_query'):
            search_code, search_btn = chosen, True
            st.session_state.pop('_main_name_matches', None)
    search_code = search_code or st.session_state.get('current_code', '')
    period_changed = period_choice != st.session_state.get('current_period')
    qt = search_btn or auto_q or st.session_state.get('force_query', False) or (
                bool(st.session_state.get('current_code')) and st.session_state.get('current_period') != '日K')
    if qt and search_code:
        st.session_state['force_query'] = False
    cc = st.session_state.get('current_code')
    cp = st.session_state.get('current_period')
    cs_ = st.session_state.get('current_start')
    ce = st.session_state.get('current_end')

    if (search_code and qt) or (cc and not qt and not search_btn):
        if qt and search_code:
            ci = search_code.strip()
            ss = start_date.strftime('%Y%m%d')
            es = end_date.strftime('%Y%m%d')
        else:
            ci = cc
            ss = cs_
            es = ce
            start_date = datetime.strptime(ss, '%Y%m%d')
            end_date = datetime.strptime(es, '%Y%m%d')

        if ci and ci.isdigit() and len(ci) == 6:
            quote = fetch_stock_quote(ci)
            if not quote:
                fallback_df = fetch_kline_with_fallback(ci, ss, es,
                                                        {'日K': 'day', '30分钟K': '30', '周K': 'week', '月K': 'month'}[
                                                            period_choice])
                if fallback_df is not None and not fallback_df.empty:
                    last = fallback_df.iloc[-1]
                    prev = float(fallback_df.iloc[-2]['close']) if len(fallback_df) > 1 else float(last['close'])
                    quote = {'name': ci, 'close': float(last['close']),
                             'change_pct': (float(last['close']) / prev - 1) * 100, 'volume': float(last['volume'])}
                    st.caption('实时报价暂不可用，顶部显示所选周期最后一根K线数值。')
            if quote:
                if qt:
                    st.session_state.update({
                        'current_code': ci, 'current_start': ss, 'current_end': es,
                        'current_period': period_choice, 'current_quote': quote
                    })
                c1, c2, c3, c4 = st.columns(4, gap="small")
                with c1:
                    st.metric("📌 名称", f"{quote['name']} ({ci})")
                with c2:
                    st.metric("📌 最新价", f"{quote['close']:.2f}")
                with c3:
                    st.metric("📊 涨跌幅", f"{quote['change_pct']:.2f}%", delta=f"{quote['change_pct']:.2f}%",
                              delta_color="inverse")
                with c4:
                    st.metric("📈 成交量", f"{quote['volume'] / 10000:.2f} 万手")

                if period_choice == '分时':
                    idf = fetch_intraday_data(ci)
                    if idf is not None and not idf.empty:
                        st.subheader("📈 分时图")
                        f = plot_intraday(idf, quote['name'])
                        if f:
                            st.plotly_chart(f, use_container_width=True)
                        else:
                            st.warning("绘制失败")
                    else:
                        st.warning("无分时数据")
                else:
                    pm = {'日K': 'day', '30分钟K': '30', '周K': 'week', '月K': 'month'}
                    sig, price, df_k = get_signals_and_kline(ci, ss, es, pm.get(period_choice, 'day'))
                    if sig is not None and df_k is not None:
                        # 画图、原始表及下载只用本次指定周期的同一份数据。
                        st.session_state['current_df_k'] = df_k
                        st.session_state['current_kline_key'] = (ci, ss, es, period_choice,
                                                                 df_k.attrs.get('source', '未知'), 'qfq')
                        st.caption(
                            f"行情：{df_k.attrs.get('source', '未知')}前复权；成交量：手；成交额：元。换源可能改变回测结果，不混接两家K线。")
                        if df_k.attrs.get('fallback_notes'):
                            st.caption('已启用备用源：' + df_k.attrs['fallback_notes'])

                        kline_panel = st.container(key='biu_kline_panel')
                        result = None
                        if period_choice == '日K':
                            st.markdown('<div id="strategy-backtest" class="biu-anchor"></div>', unsafe_allow_html=True)
                            with st.expander("策略回测 · 六道候选版", expanded=True):
                                buy_thresh, sell_thresh = 2, 2
                                sig4_lookback, sig4_threshold = 1, 1.025
                                cooling_params = None

                                st.markdown("#### 💰 资金 & 回测范围")
                                dmin = df_k['date'].min().date()
                                dmax = df_k['date'].max().date()
                                if 'ic' not in st.session_state:
                                    st.session_state.ic = 100000
                                for state_key, widget_key, default in [('bsd', 'bsd_i', dmin), ('bed', 'bed_i', dmax)]:
                                    current = st.session_state.get(state_key, default)
                                    st.session_state[state_key] = min(max(current, dmin), dmax)
                                    if widget_key in st.session_state:
                                        st.session_state[widget_key] = min(max(st.session_state[widget_key], dmin),
                                                                           dmax)
                                with st.form('backtest_parameters_form'):
                                    draft_ic = st.number_input("初始资金（万元）", min_value=0.1,
                                                               value=float(st.session_state.ic) / 10000, step=1.0,
                                                               key='ic_wan_i') * 10000
                                    bc1, bc2 = st.columns(2)
                                    with bc1:
                                        draft_bsd = st.date_input("回测开始", value=st.session_state.bsd,
                                                                  min_value=dmin, max_value=dmax, key='bsd_i')
                                    with bc2:
                                        draft_bed = st.date_input("回测结束", value=st.session_state.bed,
                                                                  min_value=dmin, max_value=dmax, key='bed_i')
                                    apply_backtest = st.form_submit_button('✅ 确认参数并回测', use_container_width=True)
                                    st.caption('修改数值、点击加减或选择日期不会立即回测；点击确认后统一生效。')
                                if apply_backtest:
                                    if draft_bsd > draft_bed:
                                        st.error('回测开始不能晚于结束，仍显示上次已确认参数的结果。')
                                    else:
                                        st.session_state.update(ic=draft_ic, bsd=draft_bsd, bed=draft_bed)
                                ic, bsd, bed = st.session_state.ic, st.session_state.bsd, st.session_state.bed

                                # 保留调用兼容，旧参数不再参与统一策略计算。
                                result = cached_backtest_strategy(
                                    df_k, initial_cash=ic, backtest_start=bsd, backtest_end=bed,
                                    buy_threshold=buy_thresh, sell_threshold=sell_thresh,
                                    signal4_lookback=sig4_lookback, signal4_threshold=sig4_threshold,
                                    cooling_params=cooling_params
                                )

                                if result:
                                    st.caption(
                                        f"期末持股 {result['期末持股数']} 股；浮动盈亏 "
                                        f"{result['期末浮动盈亏'] / 10000:,.4f} 万元（计入总收益，不计入已平仓胜率）；"
                                        f"最大回撤 {result['最大回撤%']:.2f}%"
                                    )
                                st.markdown("#### 交易明细")
                                display_rows = _trade_display_rows(result)
                                if display_rows:
                                    dt = pd.DataFrame(display_rows)
                                    dt['买入日期'] = pd.to_datetime(dt['买入日期'])
                                    dt['卖出日期'] = pd.to_datetime(dt['卖出日期'])
                                    # 明细以元显示；仅调整展示副本，汇总仍以万元显示。
                                    sell_balances = {pd.Timestamp(f['date']): f['cash_after']
                                                     for f in result['成交记录'] if f['side'] == 'SELL'}
                                    dt['卖出后账户余额'] = dt['卖出日期'].map(sell_balances)
                                    amount_names = {
                                        '买入总金额': '买入成交额（元）',
                                        '买入费用': '买入手续费（元）',
                                        '卖出费用': '卖出手续费（元）',
                                        '卖出后账户余额': '卖出后账户余额（元）',
                                        '盈亏金额': '盈亏金额（元）',
                                    }
                                    dt = dt.rename(columns=amount_names)
                                    dt = dt.rename(columns={'买入价': '买入价（元/股）', '卖出价': '卖出价（元/股）'})
                                    dc = ['买入日期', '交易模式', '买入成交额（元）', '买入价（元/股）',
                                          '买入股数', '卖出价（元/股）', '盈亏金额（元）',
                                          '卖出后账户余额（元）', '收益率%', '卖出日期',
                                          '买入手续费（元）', '卖出手续费（元）', '卖出条件']
                                    ac = [c for c in dc if c in dt.columns]
                                    dt = dt[ac].copy()
                                    if _load_display_table('完整交易明细', 'trades_'+ci):
                                        st.dataframe(dt.style.format({name: '{:,.2f}' for name in amount_names.values()},
                                                                     na_rep='—'), use_container_width=True)
                                    st.caption(
                                        '持仓中行的盈亏及收益率为期末浮动值，不计入已平仓交易次数和胜率；卖出字段留空。明细金额单位：元；股价单位：元/股；外部汇总单位：万元。买入成交额未含手续费。手续费含佣金、过户费及卖出印花税，已计入盈亏；滑点已计入成交价。卖出后账户余额为扣费后到账金额加原有剩余现金。')
                                    td = (bed - bsd).days
                                    cagr = ((result['最终资金'] / result['初始资金']) ** (
                                                1 / (td / 365.25)) - 1) * 100 if td > 0 else 0
                                    s1, s2, s3, s4 = st.columns(4)
                                    s5, s6, s7 = st.columns(3)
                                    with s1:
                                        st.metric("📊 次数", result['交易次数'])
                                    with s2:
                                        st.metric("📈 总收益", f"{result['总收益率%']:.2f}%")
                                    with s3:
                                        st.metric("💰 盈亏（万元）", f"{result['总盈亏金额'] / 10000:,.4f}")
                                    with s4:
                                        st.metric("🏦 终值（万元）", f"{result['最终资金'] / 10000:,.4f}")
                                    with s5:
                                        st.metric("🎯 胜率", f"{result['胜率%']:.2f}%")
                                    with s6:
                                        st.metric("📅 年化", f"{cagr:.2f}%")
                                    with s7:
                                        total_fees = sum(f['fee'] for f in result['成交记录'])
                                        st.metric("🧾 手续费（万元）", f"{total_fees / 10000:,.6f}",
                                                  help='所有已成交买卖的佣金、过户费及卖出印花税之和，包含期末未平仓买入费用；已计入盈亏，不再重复扣除。')
                                    if not light_mode or st.session_state.get('light_table_trades_'+ci,False):
                                        csv = dt.to_csv(index=False).encode('utf-8-sig')
                                        st.download_button("📥 导出CSV", csv, f"{ci}_trades_{ss}_{es}.csv", "text/csv",
                                                           key="dl_t", on_click="ignore")
                                else:
                                    st.info("无交易记录")

                                if result and result['信号数据'] is not None and not result['信号数据'].empty:
                                    with st.expander("📊 信号数据表", expanded=False):
                                        if _load_display_table('完整信号数据', 'signals_'+ci):
                                            sd = result['信号数据'].copy()
                                            sd['date'] = sd['date'].dt.strftime('%Y-%m-%d')
                                            st.dataframe(sd, use_container_width=True)
                                            csv2 = sd.to_csv(index=False).encode('utf-8-sig')
                                            st.download_button("📥 下载信号CSV", csv2, f"{ci}_signals_{ss}_{es}.csv",
                                                               "text/csv", on_click="ignore")

                                with st.expander("📖 当前策略说明", expanded=False):
                                    st.markdown("### 当前策略汇总（六道候选版）\n\n以下说明对应当前程序实际执行的日线规则；所有股票使用同一组固定技术参数。\n\n**指标口径**\n\n- MA表示收盘价均线；M表示“成交量×收盘价”代理成交额的均线，并非直接使用行情接口的成交额字段。\n- MACD参数为(3,39,9)。DIFF＜DEA表示当天处于空头状态，不是必须当天发生死叉，也没有额外保持三天的逻辑。\n\n**买入：全部条件同时满足**\n\n- 空仓、冷却已结束，且没有待执行订单。\n- 收盘价＞MA10，且MA10＞前一根日K线的MA10。\n- 0.2≤M2/M30≤2.2，且MA5/MA120≤1.8。\n- 代码另保留两项宽范围过滤：M10＜M30×1,000,000，0≤M5/M30≤1,000。\n- 买入不要求MACD多头，也不是旧版“五项信号凑两项”的计数方式。\n\n**常规卖出：持仓至少12根日K线，以下三项至少满足两项**\n\n1. MA5/MA120≥1.025，且DIFF＜DEA。\n2. 收盘价＜MA40，且MA40＜前一根日K线的MA40。\n3. M3＞M180×3.9，且DIFF＜DEA。\n\n**独立退出：任意一条触发即可，不要求凑足常规卖点**\n\n- 持仓至少90根日K线、收盘价较实际买入价涨幅不足8%、收盘价＜MA42，三项同时成立。\n- 收盘价较实际买入价亏损达到或超过35%。\n\n持仓根数从买入成交日计为第1根。上述涨跌幅以含滑点的买入成交价为基准，不含手续费。35%只是收盘触发条件，不保证最终亏损不超过35%；当前没有盈利回撤退出。\n\n**冷却与成交**\n\n- 卖出成交日为T日，T+1至T+19禁止买入；第19根结束可检查入场条件，最早T+20开盘买入。没有分支冷却或提前解锁。\n- 收盘确认信号，下一根成交量大于0的日K线按开盘价加减滑点模拟成交；不是信号当天收盘成交。\n- 全仓进出：买入预留费用后按100股整数手尽量买满，卖出全部持股。可能留下不足一手的现金。\n- 这是日线成交模拟，没有单独判断涨跌停封板是否能够成交，不能等同于实盘成交保证。\n\n**费用与收益口径**\n\n- 买入价为开盘价×1.001，卖出价为开盘价×0.999，即每边0.1%滑点。\n- 每笔佣金为成交额的0.03%，最低5元；另按代码计入双边过户费和卖出印花税。\n- 过户费：2022-04-29之前0.002%，当日起0.001%；卖出印花税：2023-08-28之前0.1%，当日起0.05%。\n- 期末账户权益＝现金＋剩余持股按末日收盘价计价；未平仓不强制卖出，浮盈亏计入总收益但不计入已平仓胜率。\n- 回测资金和起止日期以页面实际设置为准；先用完整输入历史计算指标，M250有效且在所选区间内的日K线才参与回测。\n- 手机轻量模式仅减少图表展示根数和按需加载表格，不截短历史回测。\n\n**行情来源与结果说明**\n\n优先使用BaoStock，失败时按现有逻辑尝试TuShare前复权日线。不同来源、复权口径或历史范围可能改变信号和收益，不能直接套用旧CSV的结果。历史回测不保证未来收益。")

                        else:
                            st.info(
                                '当前周期仅用于查看行情；日线策略回测和买卖标记仅在日K模式显示。30分钟K线不能还原14:50信号。')

                        # 绘图
                        trade_df = None
                        if result and result['交易明细']:
                            trade_df = pd.DataFrame(result['交易明细'])
                            trade_df['买入日期'] = pd.to_datetime(trade_df['买入日期'])
                            trade_df['卖出日期'] = pd.to_datetime(trade_df['卖出日期'])
                        # 保留原绘图函数；补入尚未平仓的买入标记，不虚构卖出。
                        if result and result.get('未平仓信息'):
                            open_marker = pd.DataFrame([result['未平仓信息']])
                            trade_df = pd.concat([trade_df, open_marker],
                                                 ignore_index=True) if trade_df is not None else open_marker
                        with kline_panel:
                            st.markdown('<div id="price-chart" class="biu-anchor"></div>', unsafe_allow_html=True)
                            st.subheader('K线工作区')
                            display_bars = None
                            if light_mode:
                                show_all = st.checkbox('显示全部历史K线（加载较慢）', key='light_show_all_kline')
                                display_bars = None if show_all else 250
                            fig = plot_kline(df_k, quote['name'], period_choice, trade_df, display_bars=display_bars)
                            if light_mode:
                                fig.update_layout(height=540, margin=dict(l=25,r=10,t=95,b=25),
                                                  legend=dict(font=dict(size=9)))
                                shown = min(display_bars or len(df_k),len(df_k))
                                st.caption(f'轻量显示：{shown}根K线；回测仍使用原设定的完整历史区间，不受显示根数影响。')
                            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(10,20,47,0.45)',
                                              font=dict(color='#bfd0f0'), height=540 if light_mode else 650,
                                              margin=dict(l=35,r=20,t=95,b=30),
                                              hoverlabel=dict(bgcolor='#17274b',font_color='#edf3ff'))
                            fig.update_xaxes(gridcolor='rgba(134,160,217,.12)',linecolor='rgba(134,160,217,.25)')
                            fig.update_yaxes(gridcolor='rgba(134,160,217,.12)',linecolor='rgba(134,160,217,.25)')
                            st.plotly_chart(fig, use_container_width=True, theme=None)
                            st.caption(f"📊 {min(display_bars or len(df_k),len(df_k))}根{period_choice}K线 | 🔴 ▲ 买入  🟢 ▼ 常规卖出  🟢 ◆ 强制平仓")

                        st.markdown('<div id="source-data" class="biu-anchor"></div>', unsafe_allow_html=True)
                        with st.expander(f"📊 {period_choice}原始数据（{df_k.attrs.get('source', '未知')}）",
                                         expanded=False):
                            if _load_display_table('完整原始K线数据', 'raw_'+ci):
                                st.dataframe(df_k, use_container_width=True)
                                csv3 = df_k.to_csv(index=False).encode('utf-8-sig')
                                st.download_button("📥 下载K线CSV", csv3, f"{ci}_{pm[period_choice]}_kline_{ss}_{es}.csv",
                                                   "text/csv", on_click="ignore")

                        st.subheader("📊 筹码峰")
                        cdf = fetch_chip_data(ci) if (not light_mode or st.checkbox('加载筹码数据', key='load_chip_'+ci)) else None
                        if cdf is not None and not cdf.empty:
                            lc = cdf.iloc[-1]
                            cc1, cc2, cc3, cc4 = st.columns(4)
                            with cc1:
                                st.metric("💰 获利比", f"{lc['获利比例'] * 100:.1f}%")
                            with cc2:
                                st.metric("📊 均成本", f"{lc['平均成本']:.2f}")
                            with cc3:
                                st.metric("📉 90%区间", f"{lc['90成本-低']:.2f}-{lc['90成本-高']:.2f}")
                            with cc4:
                                st.metric("🎯 90集中", f"{lc['90集中度']:.2%}")
                            ib = plot_chip_chart(cdf, quote['name'])
                            if ib:
                                st.image(f"data:image/png;base64,{ib}", use_container_width=True)
                        else:
                            st.info("💡 无筹码数据")
                    else:
                        st.warning("无法获取K线，检查日期范围")
            else:
                st.warning(f"未找到 {ci}")
        elif ci:
            st.warning("请输入6位数字")
        if auto_q:
            st.session_state['auto_query'] = False

    st.divider()
    st.caption("💡 刷新获取最新 | 统一参数策略 | 收盘确认、下一开盘执行 | 期末浮盈亏计入净值")
finally:
    _page_loading.empty()
