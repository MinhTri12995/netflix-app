"""Extract the current membership plan, never a recommended upgrade."""
import json
import re
import unicodedata
from html.parser import HTMLParser


def normalize_plan(raw):
    if not isinstance(raw, str):
        return None
    raw = re.sub(r'\\[ux]([0-9a-fA-F]{4}|[0-9a-fA-F]{2})', lambda m: chr(int(m[1], 16)), raw)
    text = ''.join(c for c in unicodedata.normalize('NFKD', raw.casefold())
                   if not unicodedata.combining(c))
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text).strip()
    if re.search(r'\b(not|upgrade|offer|switch)\b', text):
        return None
    if re.fullmatch(r'(standard[ _-]*(with[ _-]*)?ads|standard con anuncios|standard z reklamami|standard avec pub|reklam iceren|standar dengan iklan|tieu chuan co quang cao|広告つきスタンダード)', text):
        return 'Standard with Ads'
    aliases = {
        'Premium': ['premium', 'cao cap', 'พรีเมียม', 'プレミアム', 'المميزة', '프리미엄', 'премиум', 'premjum'],
        'Basic': ['basic', 'basico', 'podstawowy', 'co ban', 'temel', 'mobile', 'ベーシック', '베이식', 'พื้นฐาน'],
        'Standard': ['standard', 'estandar', 'standardowy', 'padrao', 'standar', 'tieu chuan', 'スタンダード', 'القياسية', '스탠다드', 'มาตรฐาน'],
    }
    for plan, names in aliases.items():
        for name in names:
            if text == name or text in (name + ' hd', name + ' ultra hd', name + ' 4k', name + ' plan'):
                return plan
    return None


def current_plan(data):
    found = set()
    containers = {'value', 'account', 'user', 'userinfo', 'member', 'membership',
                  'currentplan', 'models', 'data', 'reactcontext', 'json'}
    def walk(obj):
        if not isinstance(obj, dict):
            return
        for key, value in obj.items():
            if key.lower() in ('planname', 'localizedplanname', 'currentplanname'):
                if isinstance(value, dict):
                    value = value.get('value')
                plan = normalize_plan(value)
                if plan:
                    found.add(plan)
            elif key.lower() in containers:
                walk(value)
    walk(data)
    return next(iter(found)) if len(found) == 1 else None


def html_plan(html):
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__(); self.inside = False; self.scripts = []; self.visible = []
        def handle_starttag(self, tag, attrs):
            if tag == 'script': self.inside = True
        def handle_endtag(self, tag):
            if tag == 'script': self.inside = False
        def handle_data(self, data):
            (self.scripts if self.inside else self.visible).append(data)
    parser = Scripts(); parser.feed(html)
    plans = set(); decoder = json.JSONDecoder()
    for script in parser.scripts:
        script = re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', script)
        # Only JSON roots or known current-account assignments. No offer subtrees.
        starts = [0] if script.lstrip().startswith('{') else []
        starts += [m.end() for m in re.finditer(r'(?:netflix\.reactContext|account|userInfo)\s*=\s*', script)]
        for start in starts:
            try:
                data, _ = decoder.raw_decode(script[start:].lstrip())
                plan = current_plan(data)
                if plan: plans.add(plan)
            except (ValueError, TypeError):
                continue
    if len(plans) == 1:
        return next(iter(plans))
    if plans:
        return None
    return None
