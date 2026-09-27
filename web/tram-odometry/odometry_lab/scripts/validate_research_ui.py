"""Actual Chromium smoke of the research page, with disclosed synthetic inputs."""
from pathlib import Path
import argparse
import json
import shutil
import sys
import tempfile
import pytest
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
parser.add_argument('--chromium', help='Path to a locally installed Chromium executable')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
chromium = args.chromium or shutil.which('chromium') or shutil.which('chromium-browser')
if not chromium:
    parser.error('Provide --chromium with the local browser executable path')
sys.path[:0] = [str(root/'src'), str(root/'tests')]
from test_research_integration import fixture_service,route_doc
from tram_lab.hack_adapter import profile
from fastapi.responses import FileResponse
with tempfile.TemporaryDirectory() as temp:
    monkeypatch=pytest.MonkeyPatch()
    settings,records,client,captured=fixture_service.__wrapped__(Path(temp),monkeypatch)
    app=client.app
    @app.get('/api/v1/dataset')
    def data():return {'bags':records}
    @app.get('/api/v1/runs')
    def runs():
        rows=[]
        for identity in ('base','candidate'):
            config=json.loads((settings.runs/identity/'config.json').read_text())
            if identity=='base':config['estimator']['core']=profile('hack_v8')['config']
            rows.append({'id':identity,'config':config,'metrics':{'bags':[{'id':r['id']} for r in records]}})
        return rows
    @app.get('/api/v1/download')
    def download(run:str,file:str):
        from tram_lab.web.research_api import inside
        return FileResponse(inside(inside(settings.runs,run),file),filename=file)
    errors=[];checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=chromium,headless=True,args=['--no-sandbox'])
            browser_version=browser.version
            page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            def fixture_fetch(path, options=None):
                options=options or {}
                response=client.request(options.get('method','GET'),path,content=options.get('body'),headers=options.get('headers',{}))
                return {'status':response.status_code,'body':response.text,'headers':dict(response.headers)}
            page.expose_function('__fixture_fetch',fixture_fetch)
            html=(root/'src/tram_lab/web/research_page.html').read_text()
            html=html.replace('<script defer src="/api/v1/research/page.js"></script>','')
            page.set_content(html)
            page.evaluate('''() => { window.fetch = async (path, options) => {
                const r = await window.__fixture_fetch(path, options);
                return new Response(r.body, {status:r.status,headers:r.headers});
            }; }''')
            page.add_script_tag(content=(root/'src/tram_lab/web/research_page.js').read_text())
            page.wait_for_function("document.querySelector('#status').textContent.startsWith('Готово')")
            assert page.locator('#localize').is_disabled();checks.append('localization_disabled_without_external_route')
            assert page.locator('#bags input').count()==1;checks.append('30618_scope_default')
            page.locator('#all-bags').click();page.locator('#fault-kind').select_option('dropout');page.locator('#enqueue').click()
            page.wait_for_function("document.querySelector('#queue-result').textContent.includes('synthetic-test-job')")
            assert captured[-1][1]['faults'][0]['kind']=='drop'
            assert len(captured[-1][1]['faults'][0]['topics'])==2;checks.append('queue_pair_and_correct_native_fault_schema')
            page.locator('#compare').click()
            page.wait_for_function("document.querySelector('#compare-result').textContent.includes('Group-macro')")
            assert page.locator('#compare-result').inner_text().count('30618')>=1;checks.append('paired_scope_table_rendered')
            page.locator('#vehicle').select_option('30639');assert page.locator('#bags input').count()==1;checks.append('30639_diagnostic_scope')
            page.locator('#vehicle').select_option('30618')
            page.locator('#compare').click()
            page.wait_for_function("document.querySelector('#compare-result').textContent.includes('Group-macro')")
            route=Path(temp)/'synthetic-route.json';route.write_text(json.dumps(route_doc()))
            page.locator('#route-file').set_input_files(str(route))
            page.wait_for_function("!document.querySelector('#localize').disabled")
            page.locator('#period').fill('1');page.locator('#localize').click()
            page.wait_for_function("document.querySelector('#localize-result').textContent.includes('Полный JSON')")
            assert page.locator('#localize-result svg').count()==2;checks.append('two_actual_svg_plots')
            assert page.locator('#localize-result').inner_text().find('corrected')>=0;checks.append('gnss_correction_journal')
            link=page.locator('#localize-result a').get_attribute('href')
            response=client.get(link);assert response.status_code==200
            dest=output/'SYNTHETIC_BROWSER_RESULT.json'
            dest.write_bytes(response.content)
            result=response.json();assert len(result['points'])==100 and result['official_xyz_score'] is None
            checks.append('artifact_link_and_ASGI_download_response_not_browser_HTTP')
            # Banner explicitly labels screenshot's fixtures.
            page.locator('#status').evaluate("e => {e.textContent='СИНТЕТИЧЕСКАЯ ПРОВЕРКА ИНТЕРФЕЙСА · не реальные поездки и не результаты хакатона';e.className='notice';}")
            page.evaluate("document.documentElement.dataset.theme='dark'")
            page.screenshot(path=str(output/'research_ui_dark.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            checks.append('desktop_no_horizontal_overflow')
            page.set_viewport_size({'width':760,'height':950})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            checks.append('narrow_no_horizontal_overflow')
            page.evaluate("document.documentElement.dataset.theme='light'")
            assert page.evaluate("document.documentElement.dataset.theme")=='light';checks.append('light_theme')
            assert not errors,errors
            browser.close()
        (output/'browser_check.json').write_text(json.dumps({'status':'PASS','browser_executable':str(chromium),'browser_version':browser_version,'data':'SYNTHETIC fixtures, not real bag','scope':'Actual research HTML/JS rendered with Chromium; requests routed explicitly to in-process ASGI synthetic fixture, with no browser HTTP. Not full React shell, worker, real data, or network end-to-end.','checks':checks,'page_errors':errors},indent=2,ensure_ascii=False)+'\n')
        print(json.dumps({'checks':checks,'page_errors':errors},indent=2))
    finally:
        monkeypatch.undo()
