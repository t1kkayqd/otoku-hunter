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
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
OUT = ROOT / 'data' / 'leads.json'
EXCLUDE = ['投資', '株式投資', 'ローン', '競馬', 'パチンコ', 'カジノ', '酒', 'ワイン', 'ウイスキー', 'ビール', 'たばこ', 'タバコ']
BAD = re.compile('|'.join(map(re.escape, EXCLUDE)))
PURCHASE_REQUIRED = re.compile(
    r'マストバイ|購入者(?:限定|対象)|(?:購入|お買い上げ|お買い物|注文|決済|支払い)で'
    r'|(?:購入|有料(?:会員|登録|契約|プラン|サービス)).{0,12}(?:必須|が条件|限定|が対象)'
    r'|(?:購入|注文)(?:いただいた|された|した)(?:方|人|お客様)'
    r'|購入金額|円以上の(?:購入|お買い上げ|お買い物)|(?:送料|参加費|登録料)(?:が必要|有料)'
    r'|(?:決済|支払い|お買い物|利用金額).{0,12}還元'
)
REWARD = r'(?:進呈|付与|プレゼント|獲得|もらえ|貯ま|たまる|当た|山分け|還元)'
POINT_REWARD = re.compile(
    rf'(楽天ポイント|(?<![a-z])Vポイント).{{0,16}}{REWARD}',
    re.IGNORECASE,
)
SWEEPSTAKES = re.compile(
    r'懸賞|プレゼント(?:キャンペーン|企画).{0,16}(?:開催|実施|応募|開始)'
    r'|(?:抽選で|(?:合計|総勢)?[\d,]+名(?:様)?(?:に|へ)).{0,40}(?:当た|プレゼント|進呈|贈呈)'
    r'|(?:応募|フォロー|リポスト|引用ポスト).{0,16}(?:で|すると).{0,35}(?:当た|プレゼント)'
    r'|(?:当たる|当たります).{0,10}(?:キャンペーン|抽選|プレゼント|応募)'
)


def classify(title):
    title = unicodedata.normalize('NFKC', title)
    if BAD.search(title) or PURCHASE_REQUIRED.search(title):
        return None
    match = POINT_REWARD.search(title)
    if match:
        return '楽天ポイント' if match[1] == '楽天ポイント' else 'Vポイント'
    if SWEEPSTAKES.search(title):
        return '懸賞'
    return None

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
    by_id = {}
    for item in old.get('leads', []):
        category = classify(item['title'])
        if category:
            by_id[item['id']] = {**item, 'category': category}
    successes = 0
    for src in CONFIG['feeds']:
        try:
            req = urllib.request.Request(src['url'], headers={'User-Agent': 'OtokuHunterPersonalRSS/0.1 (RSS headline reader)'})
            with urllib.request.urlopen(req, timeout=20) as r:
                content = r.read(2_000_000)
            for v in parse(content):
                category = classify(v['title'])
                if not category:
                    continue
                ident = hashlib.sha256(v['url'].encode()).hexdigest()[:20]
                if ident not in by_id:
                    by_id[ident] = {'id': ident, **v, 'source': src['name'], 'category': category, 'state': '未確認'}
            successes += 1
            print('OK', src['name'])
        except Exception as e:
            print('FAILED', src['name'], type(e).__name__, str(e)[:120])
    if not successes:
        raise SystemExit('No feeds succeeded; preserving previous data')
    data = sorted(by_id.values(), key=lambda v: v.get('published',''), reverse=True)[:400]
    OUT.write_text(json.dumps({'updated': dt.datetime.now(dt.timezone.utc).isoformat(), 'leads': data}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Candidates',len(data))

if __name__ == '__main__': collect()
