import importlib
from urllib.parse import urlsplit


def test_socks_proxy_honors_port_and_escapes_credentials(monkeypatch):
    import proxies_list
    with monkeypatch.context() as env:
        for name, value in {'ENABLE_PROXY':'true','WEBSHARE_USERNAME':'test-user-rotate',
                            'WEBSHARE_PASSWORD':'synthetic:p@ss','WEBSHARE_HOST':'p.webshare.io',
                            'WEBSHARE_PORT':'80','WEBSHARE_PROTOCOL':'socks5'}.items():
            env.setenv(name,value)
        importlib.reload(proxies_list)
        proxy=urlsplit(proxies_list.ROTATING_PROXY_URL)
        assert proxy.scheme=='socks5h'
        assert proxy.port==80
        assert proxy.hostname=='p.webshare.io'
        assert proxy.password=='synthetic%3Ap%40ss'
        assert proxies_list.ROTATING_PROXY_DICT['https']==proxies_list.ROTATING_PROXY_URL
    importlib.reload(proxies_list)


def test_http_proxy_does_not_override_configured_port(monkeypatch):
    import proxies_list
    with monkeypatch.context() as env:
        for name,value in {'ENABLE_PROXY':'true','WEBSHARE_USERNAME':'test-user-rotate',
                           'WEBSHARE_PASSWORD':'synthetic','WEBSHARE_HOST':'p.webshare.io',
                           'WEBSHARE_PORT':'80','WEBSHARE_PROTOCOL':'http'}.items():
            env.setenv(name,value)
        importlib.reload(proxies_list)
        assert urlsplit(proxies_list.ROTATING_PROXY_URL).scheme=='http'
        assert urlsplit(proxies_list.ROTATING_PROXY_URL).port==80
    importlib.reload(proxies_list)
