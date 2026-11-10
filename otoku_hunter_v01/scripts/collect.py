#!/usr/bin/env python3
"""Collect headline-level leads from explicitly configured RSS feeds.
No logins, form submissions, or scraping of article pages.
"""
import datetime as dt
import email.utils
import hashlib
import json
import pathlib
import re
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
OUT = ROOT / 'data' / 'leads.json'
KEYWORDS = ['無料', 'プレゼント', 'キャンペーン', '懸賞', 'サンプル', '抽選', 'ポイント', 'クーポン', 'モニター', 'ギフト券', '引換券', '応募']
EXCLUDE = ['投資', '株式投資', 'ローン', '競馬', 'パチンコ', 'カジノ', '酒', 'ワイン', 'ウイスキー', 'ビール', 'たばこ', 'タバコ']
RE = re.compile('|'.join(map(re.escape, KEYWORDS)))
BAD = re.compile('|'.join(map(re.escape, EXCLUDE)))

def val(el, tags):
    for t in tags:
        z = el.find(t)
        if z is not None and z.text:
            return z.text.strip()
    return ''

def parse(xml):
    root = ET.fromstring(xml)
    items = root.findall('.//item')
    if not items:
        items = root.findall('.//{http://purl.org/rss/1.0/}item')
    if not items:
        items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
    for item in items:
        title = val(item, ['title', '{http://purl.org/rss/1.0/}title', '{http://www.w3.org/2005/Atom}title'])
        link = val(item, ['link', '{http://purl.org/rss/1.0/}link'])
        if not link:
            link_el = item.find('{http://www.w3.org/2005/Atom}link')
            link = link_el.attrib.get('href', '') if link_el is not None else ''
        date = val(item, ['pubDate', '{http://purl.org/dc/elements/1.1/}date', '{http://www.w3.org/2005/Atom}updated'])
        if not title or not link.startswith('https://'):
            continue
        try:
            date = email.utils.parsedate_to_datetime(date).date().isoformat()
        except Exception:
            date = date[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}.*', date) else ''
        yield {'title': title[:200], 'url': link, 'published': date}

def collect():
    old = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'leads': []}
    by_id = {x['id']: x for x in old.get('leads', [])}
    successes = 0
    for src in CONFIG['feeds']:
        try:
            req = urllib.request.Request(src['url'], headers={'User-Agent': 'OtokuHunterPersonalRSS/0.1 (RSS headline reader)'})
            with urllib.request.urlopen(req, timeout=20) as r:
                content = r.read(2_000_000)
            for v in parse(content):
                if not RE.search(v['title']) or BAD.search(v['title']):
                    continue
                ident = hashlib.sha256(v['url'].encode()).hexdigest()[:20]
                if ident not in by_id:
                    by_id[ident] = {'id': ident, **v, 'source': src['name'], 'category': classify(v['title']), 'state': '未確認'}
            successes += 1
            print('OK', src['name'])
        except Exception as e:
            print('FAILED', src['name'], type(e).__name__, str(e)[:120])
    if not successes:
        raise SystemExit('No feeds succeeded; preserving previous data')
    data = sorted(by_id.values(), key=lambda v: v.get('published',''), reverse=True)[:400]
    OUT.write_text(json.dumps({'updated': dt.datetime.now(dt.timezone.utc).isoformat(), 'leads': data}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Candidates',len(data))

def classify(t):
    if any(x in t for x in ('ポイント', '還元')): return 'ポイント'
    if any(x in t for x in ('サンプル','モニター','引換券')): return '無料サンプル'
    if any(x in t for x in ('懸賞','抽選','プレゼント')): return '懸賞'
    return 'キャンペーン'

if __name__ == '__main__': collect()
