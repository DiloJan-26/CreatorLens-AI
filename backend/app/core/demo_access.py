"""Closed-by-default demo boundary. This is not user authentication or a gateway."""
from ipaddress import ip_address
from urllib.parse import urlsplit
from starlette.responses import JSONResponse
from app.core.config import get_settings


def local_demo_enabled(settings):
    return settings.environment in {'local', 'test'} and settings.demo_access_mode == 'local'


def provider_calls_enabled(settings):
    return local_demo_enabled(settings) and settings.demo_allow_provider_calls


class DemoAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        if scope['type'] == 'http' and scope['path'] == '/health' and scope['method'] in {'GET', 'HEAD'}:
            return await JSONResponse({'status': 'ok', 'service': 'creatorlens-api'})(scope, receive, send)
        settings = get_settings()
        host = (scope.get('client') or ('', 0))[0]
        try:
            loopback = ip_address(host).is_loopback
        except ValueError:
            loopback = host == 'testclient' and settings.environment == 'test'
        headers = {key.decode('latin1').lower(): value.decode('latin1') for key, value in scope.get('headers', [])}
        permitted_hosts = {'localhost', '127.0.0.1', '::1'}
        if settings.environment == 'test':
            permitted_hosts.add('testserver')
        try:
            host_allowed = urlsplit('//' + headers.get('host', '')).hostname in permitted_hosts
            origin = headers.get('origin')
            origin_allowed = origin is None or (urlsplit(origin).scheme in {'http', 'https'} and urlsplit(origin).hostname in permitted_hosts)
        except ValueError:
            host_allowed = origin_allowed = False
        allowed = local_demo_enabled(settings) and loopback and host_allowed and origin_allowed
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        if not allowed:
            return await JSONResponse({'detail': 'Interactive demo access is disabled. Use the isolated offline demonstration.'}, status_code=403)(scope, receive, send)
        # POST retrieval/session creation remains useful offline; provider-triggering routes are closed.
        path = scope['path'].rstrip('/')
        provider_route = path.startswith('/health/') and path.endswith(('test', 'stream-test'))
        provider_route = provider_route or '/semantic/' in path or path.endswith(('/ingest', '/ingestion', '/extract', '/extract/youtube', '/extract/instagram', '/extract/facebook', '/index'))
        if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'} and provider_route and not provider_calls_enabled(settings):
            return await JSONResponse({'detail': 'Provider operations are disabled for this demo.'}, status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)


def require_local_worker():
    """Never let a nonlocal demo worker execute pending jobs without a trusted boundary."""
    if get_settings().environment not in {'local', 'test'}:
        from celery.exceptions import Reject
        raise Reject('Cloud demo worker is restricted; keep workers stopped until access approval.', requeue=True)
