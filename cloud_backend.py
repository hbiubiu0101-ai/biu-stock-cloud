"""Server-only Supabase storage; no local fallback and no credential logging."""
from datetime import datetime, timezone
import re
import requests


class CloudError(RuntimeError):
    pass


class CloudStore:
    def __init__(self, url, key, authorize=lambda: None, transport=None):
        if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co/?", url):
            raise CloudError("SUPABASE_URL 格式不正确，请填写项目的 HTTPS 地址。")
        if not (key.startswith('sb_secret_') or (key.startswith('eyJ') and key.count('.') == 2)):
            raise CloudError("SUPABASE_SECRET_KEY 需要服务器 Secret key 或旧版 service_role key。")
        self._url = url.rstrip('/') + '/rest/v1/'
        self._headers = {'apikey': key, 'Content-Type': 'application/json'}
        # New opaque Secret keys are NOT JWTs. Legacy service_role JWTs use Bearer.
        if key.startswith('eyJ'):
            self._headers['Authorization'] = 'Bearer ' + key
        self._authorize = authorize
        self._transport = transport or requests.request

    def _request(self, method, table, *, params=None, body=None, prefer=None, conflict=False):
        self._authorize()
        headers = dict(self._headers)
        if prefer:
            headers['Prefer'] = prefer
        try:
            response = self._transport(method, self._url + table, headers=headers,
                params=params, json=body, timeout=(5, 15), allow_redirects=False)
        except requests.RequestException:
            raise CloudError("数据库连接失败；请检查网络及 Supabase 项目状态。未切换到本地保存。") from None
        if conflict and response.status_code == 409:
            try:
                if response.json().get('code') == '23505':
                    return False
            except (ValueError, AttributeError):
                pass
        if not 200 <= response.status_code < 300:
            raise CloudError(f"数据库请求失败（HTTP {response.status_code}），请检查项目、密钥及建表权限。")
        if method == 'GET':
            try:
                data = response.json()
                if not isinstance(data, list):
                    raise ValueError()
                return data
            except ValueError:
                raise CloudError("数据库返回格式异常，已停止本次操作。") from None
        return True

    def _rows(self, table, params):
        rows = []
        for offset in range(0, 10000, 500):
            page = self._request('GET', table, params={**params, 'limit': 500, 'offset': offset})
            rows.extend(page)
            if len(page) < 500:
                return rows
        raise CloudError("数据量超过当前读取上限，请联系维护者；未覆盖数据库。")

    def lists(self):
        result = {'watchlist': [], 'holdings': []}
        for row in self._rows('biu_stock_lists', {'select': 'list_type,stock_code', 'order': 'list_type,stock_code'}):
            kind, code = row.get('list_type'), row.get('stock_code')
            self._validate_stock(kind, code)
            result[kind].append(code)
        return result

    @staticmethod
    def _validate_stock(kind, code):
        if kind not in ('watchlist', 'holdings') or not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
            raise CloudError('股票列表或六位代码格式不正确。')

    def add(self, kind, code):
        self._validate_stock(kind, code)
        # One row per mutation: concurrent phones do not replace each other's lists.
        self._request('POST', 'biu_stock_lists', params={'on_conflict': 'list_type,stock_code'},
            body={'list_type': kind, 'stock_code': code}, prefer='resolution=ignore-duplicates,return=minimal')

    def remove(self, kind, code):
        self._validate_stock(kind, code)
        self._request('DELETE', 'biu_stock_lists', params={'list_type': 'eq.' + kind, 'stock_code': 'eq.' + code})

    def state(self, key, default=None):
        rows = self._request('GET', 'biu_app_state', params={'state_key': 'eq.' + key, 'select': 'state_value', 'limit': 1})
        return rows[0]['state_value'] if rows else default

    def put_state(self, key, value):
        self._request('POST', 'biu_app_state', params={'on_conflict': 'state_key'},
            body={'state_key': key, 'state_value': value, 'updated_at': self._now()},
            prefer='resolution=merge-duplicates,return=minimal')

    def alerts(self):
        return self._rows('biu_app_state', {'state_key': 'like.signal_v2:*',
            'select': 'state_key,state_value', 'order': 'state_key'})

    def reserve_notification(self, identity, code, date, signal):
        if signal not in ('buy', 'sell'):
            raise CloudError('无效通知类型。')
        return self._request('POST', 'biu_notifications', body={
            'event_key': identity, 'stock_code': code, 'signal_date': date,
            'signal_type': signal, 'status': 'pending'}, prefer='return=minimal', conflict=True)

    def finish_notification(self, identity, status):
        if status not in ('sent', 'failed', 'unknown'):
            raise CloudError('无效通知状态。')
        self._request('PATCH', 'biu_notifications', params={'event_key': 'eq.' + identity},
            body={'status': status, 'updated_at': self._now()})

    def notifications(self):
        return self._request('GET', 'biu_notifications', params={
            'select': 'signal_date,stock_code,signal_type,status', 'order': 'created_at.desc,event_key', 'limit': 20})

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
