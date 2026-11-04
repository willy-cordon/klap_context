"""Optional browser acceptance. Run with Playwright + Chromium installed."""
import json
from pathlib import Path

import pytest

playwright = pytest.importorskip('playwright.sync_api')
from klapcontext.portal import render


def test_local_portal_without_network(tmp_path):
    graph = {'nodes': [{'id': str(i), 'label': f'component_{i}', 'type': 'class' if i % 2 else 'function', 'source_file': f'src/{i}.py'} for i in range(420)],
             'links': [{'source': str(i), 'target': str(i+1), 'relation': 'calls'} for i in range(419)]}
    page_file = tmp_path / 'index.html'
    page_file.write_text(render({'project': {'name': 'Real project'}, 'system_model': {'recent_changes': [{'subject': 'A commit', 'commit': 'abc123'}]}}, '', [], graph=graph).replace('const network = new vis.Network', 'const network = window.testNetwork = new vis.Network'), encoding='utf-8')
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(offline=True, viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.goto(page_file.as_uri())
        page.wait_for_selector('canvas')
        assert page.locator('nav a').all_text_contents() == ['Inicio', 'Git']
        assert 'Vista parcial: 350 de 420' in page.locator('#hint').inner_text()
        assert page.evaluate("testNetwork.body.data.nodes.get('0').font.size") == 0
        page.locator('#search').fill('component_419')
        page.locator('#results button').click()
        assert 'component_419' in page.locator('#selection').inner_text()
        assert 'src/419.py' in page.locator('#selection').inner_text()
        assert page.evaluate("testNetwork.body.data.nodes.get('419').font.size") == 13
        assert page.evaluate('testNetwork.body.data.nodes.getIds().sort()') == ['418', '419']
        assert page.evaluate('testNetwork.body.data.edges.get().map(e => [e.from, e.to])') == [['418', '419']]
        assert page.evaluate('testNetwork.getSelectedNodes()') == ['419']
        page.locator('#focus').click()
        page.wait_for_function('!testNetwork.physics.physicsEnabled')
        page.evaluate("testNetwork.once('animationFinished', () => window.fitFinished = true)")
        page.locator('#fit').click()
        page.wait_for_function('window.fitFinished === true')
        scale = page.evaluate('testNetwork.getScale()')
        page.mouse.move(700, 450)
        page.mouse.wheel(0, -300)
        page.wait_for_timeout(300)
        assert page.evaluate('testNetwork.getScale()') > scale
        position = page.evaluate('testNetwork.getViewPosition()')
        page.mouse.down(); page.mouse.move(750, 480, steps=8); page.mouse.up()
        assert page.evaluate('testNetwork.getViewPosition()') != position
        page.wait_for_timeout(200)  # Allow the pan's final canvas redraw.
        point = page.evaluate("testNetwork.canvasToDOM(testNetwork.getPosition('419'))")
        bounds = page.locator('#graph').bounding_box()
        before = page.evaluate("testNetwork.getPosition('419')")
        page.mouse.move(bounds['x']+point['x'], bounds['y']+point['y'])
        page.wait_for_timeout(100)
        page.mouse.down(); page.mouse.move(bounds['x']+point['x']+40, bounds['y']+point['y']+30, steps=8); page.mouse.up()
        page.wait_for_function("before => JSON.stringify(testNetwork.getPosition('419')) !== JSON.stringify(before)", arg=before)
        page.locator('nav a').filter(has_text='Git').click()
        playwright.expect(page.locator('#historial')).to_be_visible()
        playwright.expect(page.get_by_text('A commit')).to_be_visible()
        page.locator('nav a').filter(has_text='Inicio').click()
        playwright.expect(page.locator('#graph')).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        playwright.expect(page.locator('#hint')).to_be_visible()
        page.locator('#reset').click()
        assert '350 de 420' in page.locator('#hint').inner_text()
        assert not errors
        assert not [url for url in requests if url.startswith(('http:', 'https:'))]
        browser.close()
