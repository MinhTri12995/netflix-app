"""Render the dashboard before parsing scripts, including inline import controls."""
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
import pytest
from tests.conftest import setup_admin_session


def test_dashboard_javascript_compiles(test_app, tmp_path):
    node = shutil.which('node')
    if not node: pytest.skip('Node unavailable; checked by CI')
    response = setup_admin_session(test_app.test_client()).get('/admin/')
    assert response.status_code == 200
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__(); self.inside=False; self.parts=[]; self.scripts=[]
        def handle_starttag(self,tag,attrs):
            if tag=='script': self.inside='src' not in dict(attrs); self.parts=[]
        def handle_data(self,data):
            if self.inside:self.parts.append(data)
        def handle_endtag(self,tag):
            if tag=='script' and self.inside:
                self.scripts.append(''.join(self.parts));self.inside=False
    parser=Scripts();parser.feed(response.data.decode())
    for index,source in enumerate(parser.scripts):
        file=tmp_path/f'inline-{index}.js';file.write_text(source,encoding='utf-8')
        result=subprocess.run([node,'--check',str(file)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    root=Path(__file__).resolve().parents[1]
    for name in ('inventory-jobs.js','admin.js'):
        result=subprocess.run([node,'--check',str(root/'app/static/js'/name)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
