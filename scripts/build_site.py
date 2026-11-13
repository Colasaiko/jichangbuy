from pathlib import Path
import html
import json
import os
import re
import shutil
import urllib.parse
import random
import yaml
import markdown

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'brands'
OUT = ROOT / 'website' / 'dist'

# 品牌排位：同步自 Colasaiko/Home 的推荐机场排行（2026-11-11 FlyV 登顶版）
HOME_ORDER = [
    'feiv', 'weifeng', 'muguang', 'feimao', 'wavenet', 'lingdong',
    'invisible', 'firefly', 'wuyou', 'sogo', 'weitu', 'shanyue',
    'dalao', 'lingmao', 'kuajie', 'bitznet', 'baoyun', 'jiuyun',
    'shenxing', 'xingdaomeng', 'kexin', 'guangsu', 'u1s1', 'jilian',
    'guangnian', 'yifan', 'edge', 'ermao', 'sujie', 'tizi',
    'kuaili', 'nanocloud', 'phantom', 'quanqiuyun', 'yuzhouyun',
]
FEATURED_COUNT = 12

# 样式表版本号：改动 website/dist/style.css 后调高，避免访客读到旧缓存
STYLE_VER = '20261113-rank-faq'

# 线上正式网址（GitHub Pages 从分支根目录部署，站点内容位于 website/dist/）
SITE_URL = 'https://colasaiko.github.io/jichangbuy/website/dist/'
SITE_NAME = '机场买买买！'
DEFAULT_DESC = '稳定机场推荐排行榜：收录 35 家主流机场，按线路（IPLC / IEPL 专线、BGP 中转）、月付与年付价格、设备限制和专属优惠码整理，附选购指南与常见问题。'
INDEX_TITLE = '稳定机场推荐排行榜 · 专线机场选购指南'

e = lambda value: html.escape(str(value or ''), quote=True)

def rich(value):
    """Escape text, then render ~~old price~~ as a struck-through price (used by brand promo copy)."""
    return re.sub(r'~~(.+?)~~', r'<s class="price-was">\1</s>', e(value))


def text(value):
    if isinstance(value, list): return ' · '.join(map(str, value))
    if isinstance(value, dict): return ' · '.join(f'{k}：{v}' for k, v in value.items())
    return str(value or '')

def parse_price_num(price_str):
    nums = re.findall(r'[\d\.]+', str(price_str or ''))
    return float(nums[0]) if nums else None

def load():
    raw_brands = []
    for path in CONTENT.glob('*.md'):
        raw = path.read_text(encoding='utf-8')
        parts = raw.split('---', 2)
        if len(parts) < 3:
            continue
        _, front, body = parts
        item = yaml.safe_load(front)
        item['body'] = body
        aff = item.get('purchase', {}).get('url', item.get('aff', ''))
        if aff.startswith('/go/'):
            aff = aff[4:]
        item['aff'] = aff
        
        # Analyze pricing
        plans = item.get('pricing', [])
        min_month = None
        min_year = None
        min_onetime = None
        for p in plans:
            period = p.get('period', '')
            val = parse_price_num(p.get('originalPrice') or p.get('price'))
            if val is not None:
                if '月' in period and '年' not in period:
                    if min_month is None or val < min_month:
                        min_month = val
                elif '年' in period and '二年' not in period and '三年' not in period:
                    if min_year is None or val < min_year:
                        min_year = val
                elif any(k in period for k in ['一次', '不限时', '长期', '永久']):
                    if min_onetime is None or val < min_onetime:
                        min_onetime = val
        item['min_month'] = min_month
        item['min_year'] = min_year
        item['min_onetime'] = min_onetime
        
        # Line types tags
        lt = item.get('lineType', [])
        if isinstance(lt, str): lt = [lt]
        item['line_types_list'] = lt
        
        raw_brands.append(item)

    # 排序逻辑：与 Colasaiko/Home「推荐机场」页面 (topic/tuijianjichang/brands/) 保持完全一致
    # 前 FEATURED_COUNT 位为站长主力推荐，其余按 Home 资料库顺序排列；未在列表中的新品牌追加到末尾
    brand_map = {b['slug']: b for b in raw_brands}
    all_sorted = []
    for s in HOME_ORDER:
        if s in brand_map:
            b = brand_map.pop(s)
            b['is_featured'] = len(all_sorted) < FEATURED_COUNT
            b['featured_rank'] = len(all_sorted) + 1 if b['is_featured'] else None
            all_sorted.append(b)
    for b in sorted(brand_map.values(), key=lambda x: x['slug']):
        b['is_featured'] = False
        b['featured_rank'] = None
        all_sorted.append(b)
    return all_sorted

def coupon_info(b):
    c = b.get('coupon') or {}
    code = c.get('code', '')
    disc = c.get('discount') or c.get('discountPercent') or ''
    scope = c.get('scope') or ''
    return code, disc, scope

def build_story_sections(b):
    """Optional visual sections from front matter: highlights, nodeRegions, buySteps."""
    hl = b.get('highlights') or []
    highlights_html = ''
    if hl:
        cards = ''.join(f'''
              <div class="highlight-card">
                <i class="fa-solid {e(h.get('icon') or 'fa-star')}"></i>
                <h3>{e(h.get('title'))}</h3>
                <p>{rich(h.get('text'))}</p>
              </div>''' for h in hl)
        highlights_html = f'''
          <section class="highlights-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-gem"></i> 为什么选 {e(b['name'])}</h2>
              <span class="heading-tag">核心卖点</span>
            </div>
            <div class="highlight-grid">{cards}
            </div>
          </section>'''

    regions = b.get('nodeRegions') or []
    nodes_html = ''
    if regions:
        total = sum(int(r.get('count') or 0) for r in regions)
        top = max(int(r.get('count') or 0) for r in regions) or 1
        rows = ''.join(f'''
              <li class="node-row">
                <span class="node-region">{e(r.get('region'))}</span>
                <span class="node-line">{e(r.get('line'))}</span>
                <span class="node-bar"><span style="width: {max(12, round(int(r.get('count') or 0) / top * 100))}%;"></span></span>
                <span class="node-count">{e(r.get('count'))} 个</span>
              </li>''' for r in regions)
        note = b.get('nodeNote') or ''
        nodes_html = f'''
          <section class="nodes-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-earth-asia"></i> 节点分布</h2>
              <span class="heading-tag">{len(regions)} 个地区 · {total} 个节点</span>
            </div>
            <ul class="node-list">{rows}
            </ul>
            {f'<p class="section-tip"><i class="fa-solid fa-circle-info"></i> {rich(note)}</p>' if note else ''}
          </section>'''

    steps = b.get('buySteps') or []
    steps_html = ''
    if steps:
        items = ''.join(f'<li><span class="step-no">{i:02d}</span><p>{rich(s)}</p></li>' for i, s in enumerate(steps, 1))
        steps_html = f'''
          <section class="steps-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-route"></i> 购买与上手流程</h2>
              <span class="heading-tag">{len(steps)} 步完成</span>
            </div>
            <ol class="step-list">{items}</ol>
            <div class="steps-cta">
              <a href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">前往官网注册购买 ↗</a>
            </div>
          </section>'''
    return highlights_html, nodes_html, steps_html


PERIOD_MONTHS = {'月付': 1, '季付': 3, '半年付': 6, '年付': 12, '二年付': 24, '两年付': 24, '三年付': 36}


def short_price(value):
    s = str(value or '').strip()
    m = re.fullmatch(r'(\D*)(\d+\.\d+)(\D*)', s)
    if not m:
        return s
    num = f'{float(m.group(2)):.2f}'.rstrip('0').rstrip('.')
    return f'{m.group(1)}{num}{m.group(3)}'


def build_plan_cards(b, plans):
    """Group plans by name + traffic so every billing period of one plan sits in one card."""
    names = [str(p.get('name') or '') for p in plans]
    prefix = ''
    if len(set(names)) > 1:
        common = os.path.commonprefix(names)
        cut = max(common.rfind(' - '), common.rfind(' — '))
        if cut > 0:
            prefix = common[:cut + 3]

    coupon = b.get('coupon') or {}
    code = coupon.get('code') or ''
    eligible_names = set(coupon.get('eligiblePlans') or [])

    groups = {}
    for p in plans:
        name = str(p.get('name') or '')
        key = (name, str(p.get('traffic') or ''))
        groups.setdefault(key, []).append(p)

    cards = []
    for (name, traffic), items in groups.items():
        label = name[len(prefix):] if prefix and name.startswith(prefix) else name
        flags = [p.get('couponEligible') for p in items]
        if eligible_names:
            ok = name in eligible_names
        elif any(f is True for f in flags):
            ok = True
        elif flags and all(f is False for f in flags):
            ok = False
        else:
            ok = None
        if code and ok:
            tag = f'<span class="plan-card-tag is-yes">可用 {e(code)}</span>'
        elif code and ok is False:
            tag = '<span class="plan-card-tag">不参与优惠</span>'
        else:
            tag = ''

        tiles = []
        for p in items:
            period = str(p.get('period') or '')
            orig = short_price(p.get('originalPrice') or p.get('price') or '—')
            disc = short_price(p.get('discountPrice') or '')
            shown = disc if disc and disc != orig else orig
            per_month = ''
            months = PERIOD_MONTHS.get(period)
            val = parse_price_num(shown)
            if months and months > 1 and val:
                per_month = f'<span class="pp-sub">≈ ¥{val / months:.1f}/月</span>'
            elif not months and period:
                per_month = '<span class="pp-sub">用完为止</span>' if any(k in period for k in ('一次', '不限时')) else ''
            strike = f'<s class="pp-orig">{e(orig)}</s>' if disc and disc != orig else ''
            tiles.append(f'<li class="plan-price"><span class="pp-period">{e(period)}</span>'
                         f'<span class="pp-amount">{strike}{e(shown)}</span>{per_month}</li>')

        details = []
        for p in items:
            for k in ('validity', 'deviceLimit', 'peakBandwidth', 'note', 'description'):
                v = str(p.get(k) or '').strip()
                if v and v not in details:
                    details.append(v)
        detail_html = f'<p class="plan-card-note">{e(" · ".join(details))}</p>' if details else ''
        single = ' is-single' if len(tiles) == 1 else ''

        cards.append(f'''
            <article class="plan-card{' is-coupon' if ok and code else ''}">
              <header class="plan-card-head">
                <div>
                  <h3 class="plan-card-name">{e(label)}</h3>
                  {f'<span class="plan-card-traffic"><i class="fa-solid fa-bolt"></i> {e(traffic)}</span>' if traffic else ''}
                </div>
                {tag}
              </header>
              <ul class="plan-price-list{single}">{''.join(tiles)}</ul>
              {detail_html}
              <a class="plan-card-buy" href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">选购此套餐 ↗</a>
            </article>''')
    return ''.join(cards), len(groups)


def extract_chart_items(plans):
    if not plans:
        return []
    name_groups = {}
    for p in plans:
        name = p.get('name', '').strip()
        clean_name = re.sub(r'^[【\[].*?[\]】]', '', name).strip()
        if not clean_name:
            clean_name = name
        traffic_str = p.get('traffic', '')
        t_val = 0
        m = re.search(r'(\d+)\s*(?:GB|G)', traffic_str, re.I)
        if m:
            t_val = int(m.group(1))
        elif 'TB' in traffic_str or 'T' in traffic_str:
            m2 = re.search(r'(\d+(?:\.\d+)?)\s*(?:TB|T)', traffic_str, re.I)
            if m2:
                t_val = int(float(m2.group(1)) * 1024)
        period = p.get('period', '')
        orig_p = p.get('originalPrice') or p.get('price') or ''
        disc_p = p.get('discountPrice') or ''
        if clean_name not in name_groups:
            name_groups[clean_name] = []
        name_groups[clean_name].append({
            'name': clean_name,
            'traffic_str': traffic_str or '标准流量',
            'traffic_val': t_val,
            'period': period or '周期订阅',
            'orig_price': orig_p,
            'disc_price': disc_p
        })
    items = []
    if 2 <= len(name_groups) <= 8:
        for cname, plist in name_groups.items():
            best = None
            for pref in ['月付', '年付', '季付', '半年付', '一次性']:
                matches = [x for x in plist if pref in x['period']]
                if matches:
                    best = matches[0]
                    break
            if not best:
                best = plist[0]
            items.append(best)
    elif len(name_groups) > 8:
        all_sorted = [plist[0] for plist in name_groups.values()]
        all_sorted.sort(key=lambda x: x['traffic_val'])
        step = max(1, len(all_sorted) // 5)
        items = all_sorted[::step][:6]
    else:
        seen_periods = set()
        for p in plans:
            period = p.get('period', '').strip()
            if period and period not in seen_periods:
                seen_periods.add(period)
                traffic_str = p.get('traffic', '')
                t_val = 0
                m = re.search(r'(\d+)\s*(?:GB|G)', traffic_str, re.I)
                if m:
                    t_val = int(m.group(1))
                items.append({
                    'name': f"{p.get('name', '')} ({period})",
                    'traffic_str': traffic_str or '标准流量',
                    'traffic_val': t_val,
                    'period': period,
                    'orig_price': p.get('originalPrice') or p.get('price') or '',
                    'disc_price': p.get('discountPrice') or ''
                })
        items = items[:6]
    return items

FAVICON_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
  <rect width='64' height='64' fill='#141414'/>
  <rect x='6' y='6' width='52' height='52' fill='none' stroke='#A98A56' stroke-width='1'/>
  <text x='32' y='41' text-anchor='middle' font-family='Noto Serif SC, Songti SC, SimSun, serif' font-size='24' font-weight='700' fill='#FAF9F6'>买</text>
  <line x1='22' y1='48' x2='42' y2='48' stroke='#A98A56' stroke-width='1'/>
</svg>"""

FAVICON_DATA_URI = "data:image/svg+xml," + urllib.parse.quote(FAVICON_SVG)

COMMON_JS = """
<script>
function copyCoupon(code) {
    if (!code) return;
    navigator.clipboard.writeText(code).then(() => {
        showToast('优惠码【' + code + '】已复制到剪贴板！');
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = code;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('优惠码【' + code + '】已复制！');
    });
}
function showToast(msg) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast-notification';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}
</script>
"""

INDEX_FILTER_JS = """
<script>
const searchInput = document.getElementById('brand-search-input');
const clearBtn = document.getElementById('search-clear-btn');
const tabs = document.querySelectorAll('.tab-btn');
const cards = document.querySelectorAll('.brand-card');
const counter = document.getElementById('search-counter');
const noResult = document.getElementById('no-result');
let currentFilter = 'all';
const INITIAL_SHOW_COUNT = 12;
let isExpanded = false;

function filterCards() {
    const query = (searchInput.value || '').trim().toLowerCase();
    const isDefaultAll = (currentFilter === 'all') && !query;
    const expandWrap = document.getElementById('expand-brands-wrap');
    const toggleBtn = document.getElementById('btn-toggle-expand');
    
    let visibleCount = 0;
    let matchCount = 0;
    
    cards.forEach(card => {
        const tags = card.dataset.tags || '';
        const name = card.dataset.name || '';
        const slug = card.dataset.slug || '';
        const textContent = card.textContent.toLowerCase();
        
        const matchFilter = (currentFilter === 'all') || tags.split(' ').includes(currentFilter);
        const matchQuery = !query || name.includes(query) || slug.includes(query) || textContent.includes(query);
        
        if (matchFilter && matchQuery) {
            matchCount++;
            if (isDefaultAll && !isExpanded && visibleCount >= INITIAL_SHOW_COUNT) {
                card.style.display = 'none';
            } else {
                card.style.display = '';
                visibleCount++;
            }
        } else {
            card.style.display = 'none';
        }
    });
    
    if (expandWrap) {
        if (isDefaultAll && matchCount > INITIAL_SHOW_COUNT) {
            expandWrap.style.display = 'flex';
            if (toggleBtn) {
                if (isExpanded) {
                    toggleBtn.innerHTML = '<span>收起部分品牌（返回主力推荐 12 家）</span> <i class="fa-solid fa-chevron-up"></i>';
                } else {
                    const remaining = matchCount - INITIAL_SHOW_COUNT;
                    toggleBtn.innerHTML = '<span>展开查看更多品牌（还有 ' + remaining + ' 家入库机场）</span> <i class="fa-solid fa-chevron-down"></i>';
                }
            }
        } else {
            expandWrap.style.display = 'none';
        }
    }
    
    if (counter) {
        if (isDefaultAll && !isExpanded) {
            counter.textContent = '显示前 ' + visibleCount + ' / ' + matchCount + ' 个主推品牌（折叠 26 家）';
        } else {
            counter.textContent = '显示 ' + visibleCount + ' / 35 个品牌';
        }
    }
    if (noResult) noResult.style.display = visibleCount === 0 ? 'block' : 'none';
    if (clearBtn) clearBtn.style.display = query ? 'block' : 'none';
}

function toggleExpandBrands() {
    isExpanded = !isExpanded;
    filterCards();
    if (!isExpanded) {
        const collection = document.getElementById('collection');
        if (collection) {
            collection.scrollIntoView({ behavior: 'smooth' });
        }
    }
}

if (searchInput) {
    searchInput.addEventListener('input', filterCards);
}
if (clearBtn) {
    clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        filterCards();
        searchInput.focus();
    });
}

tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentFilter = tab.dataset.filter;
        filterCards();
    });
});

function resetFilters() {
    if (searchInput) searchInput.value = '';
    currentFilter = 'all';
    tabs.forEach(t => t.classList.remove('active'));
    if (tabs[0]) tabs[0].classList.add('active');
    filterCards();
}

document.addEventListener('DOMContentLoaded', () => {
    filterCards();
    checkTargetHash();
});

function checkTargetHash() {
    if (window.location.hash && window.location.hash.startsWith('#brand-')) {
        const targetSlug = window.location.hash.replace('#brand-', '');
        const targetCard = document.querySelector(`.brand-card[data-slug="${targetSlug}"]`);
        if (targetCard) {
            isExpanded = true;
            filterCards();
            setTimeout(() => {
                targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetCard.classList.add('highlight-brand-target');
            }, 150);
        }
    }
}
window.addEventListener('hashchange', checkTargetHash);
filterCards();
</script>
"""

def shell(title, content, floating, prefix='', is_detail=False, path='', desc=DEFAULT_DESC, jsonld=None):
    url = SITE_URL + path
    full_title = f'{title} · {SITE_NAME}'
    ld = ''.join(f'\n  <script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in (jsonld or []))
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{e(full_title)}</title>
  <meta name="description" content="{e(desc)}">
  <meta name="robots" content="index, follow">
  <meta name="msvalidate.01" content="0033F8E0046B2CEC42304E48CD039F65" />
  <link rel="canonical" href="{e(url)}">
  <meta property="og:type" content="{'product' if is_detail else 'website'}">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:title" content="{e(full_title)}">
  <meta property="og:description" content="{e(desc)}">
  <meta property="og:url" content="{e(url)}">
  <meta property="og:locale" content="zh_CN">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{e(full_title)}">
  <meta name="twitter:description" content="{e(desc)}">{ld}
  <link rel="icon" href="{FAVICON_DATA_URI}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Jost:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=Marcellus&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{prefix}style.css?v={STYLE_VER}">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body>
  <div class="site-bg"></div>
  <header class="site-header">
    <div class="header-inner">
      <a class="wordmark" href="{prefix or './'}">
        <span class="mark platinum-mark">买</span>
        <span class="brand-text">
          <strong class="wordmark-title">机场买买买！</strong>
          <span class="wordmark-sub">机场精选品牌选购馆</span>
        </span>
      </a>
      <nav class="header-nav">
        <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/index.html" target="_blank" rel="noopener" class="nav-home-link" title="推荐机场主推榜：高性价比稳定节点排行榜">
          推荐机场主推榜 ↗
        </a>
        <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/brands/index.html" target="_blank" rel="noopener" class="nav-brands-link" title="全部机场品牌与套餐价格 | 品牌资料库">
          全部品牌资料库 ↗
        </a>
        <a href="{prefix or './'}#collection" class="nav-count">
          全部品牌 <span class="badge">35</span>
        </a>
      </nav>
    </div>
  </header>
  {content}
  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <a class="wordmark" href="{prefix or './'}">
          <span class="mark platinum-mark">买</span>
          <span class="brand-text">
            <strong class="wordmark-title">机场买买买！选购中心</strong>
            <span class="wordmark-sub">机场品牌独立选购馆</span>
          </span>
        </a>
        <p>为配套定制的独立品牌购买中心。每个品牌独立成页，参数透明，直达注册。</p>
      </div>
      <div class="footer-meta">
        <div class="footer-links">
          <a href="{prefix or './'}">返回首页</a>
          <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/index.html" target="_blank" rel="noopener">推荐机场主推榜 ↗</a>
          <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/brands/index.html" target="_blank" rel="noopener">全部品牌资料库 ↗</a>
          <a href="https://github.com/Colasaiko/Home" target="_blank" rel="noopener">开源仓库 ↗</a>
        </div>
        <span class="copyright">© 2026 机场买买买！ · 价格与数据均核验自各大品牌官方结算后台</span>
      </div>
    </div>
  </footer>
  {floating}
  {COMMON_JS}
</body>
</html>'''

def build_brand_subtitles(b):
    name = b.get('name', '')
    is_feat = b.get('is_featured')
    slug = b.get('slug')
    plans = b.get('pricing', [])
    min_m = b.get('min_month')
    min_y = b.get('min_year')
    min_o = b.get('min_onetime')
    
    # 1. 梯队与定位
    if is_feat:
        tier = f"站长主力推荐 {FEATURED_COUNT} 大旗舰品牌之一"
        card_tier = "主力推荐旗舰"
    elif slug == 'feiv':
        tier = "精选高速专线品牌"
        card_tier = "精选高速专线"
    elif b.get('line_types_list') and any('iplc' in str(x).lower() for x in b['line_types_list']):
        tier = "精选全专线独立品牌"
        card_tier = "全专线架构"
    elif b.get('line_types_list') and any('iepl' in str(x).lower() for x in b['line_types_list']):
        tier = "精选高速专线品牌"
        card_tier = "高速专线"
    elif b.get('line_types_list') and any('bgp' in str(x).lower() or '中转' in str(x) for x in b['line_types_list']):
        tier = "精选优质中转品牌"
        card_tier = "优质中转"
    else:
        tier = "精选独立入库品牌"
        card_tier = "精选入库"
        
    # 2. 线路类型描述
    lt_list = b.get('line_types_list', [])
    lt_str = ' · '.join(lt_list) if lt_list else '优质线路'
    
    # 3. 协议描述
    proto = b.get('protocols')
    if isinstance(proto, list):
        proto_clean = [str(p) for p in proto if p]
        proto_text = ' / '.join(proto_clean)
    else:
        proto_text = str(proto or '')
    proto_phrase = f"，采用 {proto_text} 传输协议" if proto_text else ""
    
    # 4. 带宽/限速
    spd = b.get('speedLimit')
    spd_clean = re.sub(r'[（\(].*?[）\)]', '', str(spd or '')).strip()
    spd_phrase = f"，{spd_clean}" if spd_clean else "，晚高峰高速稳定不限速"
    
    # 5. 设备限制
    dev = b.get('deviceLimit')
    dev_clean = re.sub(r'[（\(].*?[）\)]', '', str(dev or '')).strip()
    dev_phrase = f"，{dev_clean}" if dev_clean else "，支持多设备全家共享同时接入"
    
    # 6. 套餐统计与价格
    plans_cnt = len(plans)
    price_parts = []
    if min_m:
        price_parts.append(f"最低月付起步仅 ¥{min_m:.2f}".rstrip('0').rstrip('.'))
    if min_y:
        price_parts.append(f"年付起步 ¥{min_y:.2f}".rstrip('0').rstrip('.'))
    price_str = "（" + "，".join(price_parts) + "）" if price_parts else ""
    
    extra_pkg = "，并配备永久不限时备用流量包" if min_o else ""
    
    # 7. 解锁能力
    ai_list = b.get('aiSupport', [])
    stream_list = b.get('streamingSupport', [])
    if ai_list and stream_list:
        unlock_phrase = "全节点采用原生机房 IP 深度解锁 4K/8K 极清流媒体与全套 AI 生产力应用"
    elif stream_list:
        unlock_phrase = "原生 IP 节点深度解锁全平台 4K/8K 极清流媒体视频"
    elif ai_list:
        unlock_phrase = "原生 IP 节点稳定解锁主流 AI 生产力工具"
    else:
        unlock_phrase = "原生 IP 节点全面适配全球主流网站访问与极清流媒体"
        
    promo = b.get('promo') or {}
    if promo.get('pitch'):
        # 品牌自定义的价格卖点放在最前面，替代默认的“最低月付起步”括号说明
        if promo.get('sub'):
            deep_subtitle = f"{promo['pitch']}{promo['sub']}"
        else:
            deep_subtitle = f"{tier}。{promo['pitch']}基于【{lt_str}】网络架构{proto_phrase}{spd_phrase}{dev_phrase}，全站收录其 {plans_cnt} 款多周期购买方案{extra_pkg}。"
    else:
        deep_subtitle = f"{tier}。基于【{lt_str}】网络架构{proto_phrase}{spd_phrase}{dev_phrase}。全站深度收录其 {plans_cnt} 款多周期购买方案{price_str}{extra_pkg}，{unlock_phrase}，网络通信零丢包、低延迟。"

    # 卡片简要副标题（2行以内，极度凝练有信息量）
    if promo.get('priceLine'):
        card_subtitle = f"{card_tier} · {promo['priceLine']}"
    else:
        card_subtitle = f"{card_tier} · {lt_str} · 收录 {plans_cnt} 款方案"
        if min_m:
            card_subtitle += f" · ¥{min_m:.2f}".rstrip('0').rstrip('.') + "起"
        if min_o:
            card_subtitle += " · 不限时包"

    return deep_subtitle, card_subtitle

def build():
    OUT.mkdir(parents=True, exist_ok=True)
    brands = load()
    page_urls = ['']
    total_brands = len(brands)
    
    cards = []
    
    for i, b in enumerate(brands):
        slug = b['slug']
        target = OUT / 'brands' / slug
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONTENT / f'{slug}.md', target / f'{slug}.md')
        
        code, disc, scope = coupon_info(b)
        deep_subtitle, card_subtitle = build_brand_subtitles(b)
        
        # Tags for filter
        filter_tags = ['all']
        raw_lt = ' '.join(b.get('line_types_list', [])).lower()
        if 'iplc' in raw_lt: filter_tags.append('iplc')
        if 'iepl' in raw_lt: filter_tags.append('iepl')
        if 'bgp' in raw_lt or '中转' in raw_lt: filter_tags.append('bgp')
        if code: filter_tags.append('coupon')
        if b.get('min_onetime'): filter_tags.append('onetime')
        if b.get('min_month') and b.get('min_month') <= 20: filter_tags.append('budget')
        if b.get('is_featured'): filter_tags.append('featured')
        filter_str = ' '.join(filter_tags)
        
        # Features
        features_list = b.get('features', [])[:3]
        features_html = ''.join(f'<li><span class="bullet-dash">—</span> {e(x)}</li>' for x in features_list)
        
        # Price display
        plans = b.get('pricing', [])
        
        month_txt = f"¥{b['min_month']:.2f}".rstrip('0').rstrip('.') + " /月起" if b.get('min_month') else "—"
        year_txt = f"¥{b['min_year']:.2f}".rstrip('0').rstrip('.') + " /年起" if b.get('min_year') else "—"
        promo_box = [(str(x.get('label', '')), str(x.get('value', ''))) for x in ((b.get('promo') or {}).get('priceBox') or [])][:2]
        box = promo_box if len(promo_box) == 2 else [('月付起步', month_txt), ('年付优惠', year_txt)]

        coupon_badge_html = f'''<div class="card-coupon-badge" title="优惠码：{e(code)} {e(disc)}"><span class="coupon-tag-label">优惠码</span> <span class="coupon-code-val">{e(code)}</span> <strong>{e(disc)}</strong></div>''' if code else '<div class="card-coupon-badge no-coupon"><span class="coupon-tag-label">正价</span> 官方正价保障</div>'
        
        line_badge = text(b.get('lineType', [])) or '优质线路'
        
        # 勋章标签：仅 9 大主力显示主力推荐，其余为精选入库
        if b.get('is_featured'):
            ribbon_html = '<div class="card-ribbon top-tier">站长主力推荐</div>'
        else:
            ribbon_html = '<div class="card-ribbon standard-tier">精选入库</div>'
        
        cards.append(f'''
        <article id="brand-{e(slug)}" class="brand-card {'is-top-brand' if b.get('is_featured') else ''}" data-tags="{filter_str}" data-name="{e(b['name'].lower())}" data-slug="{e(slug)}">
          {ribbon_html}
          <div class="card-header">
            <div class="card-symbol-wrap">
              <span class="brand-symbol">{e(b['name'][0])}</span>
              <span class="card-order">第 {i+1:02d} 位</span>
            </div>
            <div class="card-tags">
              <span class="badge-line">{e(line_badge)}</span>
            </div>
          </div>
          
          <div class="card-title-wrap">
            <h3 class="card-name"><a href="brands/{slug}/">{e(b['name'])}</a></h3>
            <p class="card-subtitle">{rich(card_subtitle)}</p>
          </div>
          
          <div class="card-coupon-row">
            {coupon_badge_html}
          </div>
          
          <ul class="card-features">
            {features_html}
          </ul>
          
          <div class="card-pricing-box{' is-promo' if promo_box else ''}">
            <div class="price-item">
              <span class="price-label">{e(box[0][0])}</span>
              <strong class="price-val">{rich(box[0][1])}</strong>
            </div>
            <div class="price-divider"></div>
            <div class="price-item">
              <span class="price-label">{e(box[1][0])}</span>
              <strong class="price-val">{rich(box[1][1])}</strong>
            </div>
          </div>
          
          <div class="card-actions">
            <a class="btn-action btn-direct" href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">
              直达官网 ↗
            </a>
            <a class="btn-action btn-detail" href="brands/{slug}/">
              查看资料 ↗
            </a>
          </div>
        </article>
        ''')
        
        # Build detail page
        plan_cards_html, plan_group_count = build_plan_cards(b, plans)
        highlights_html, nodes_html, steps_html = build_story_sections(b)
        chart_section_html = ''

        facts = ''.join(f'''
        <div class="fact-card">
          <dt><i class="fa-solid fa-circle-dot"></i> {label}</dt>
          <dd>{e(text(b[key]))}</dd>
        </div>''' for key, label in [
            ('lineType','线路类型'),
            ('protocols','支持协议'),
            ('deviceLimit','设备限制'),
            ('speedLimit','速率限制'),
            ('maxBandwidth','最高带宽'),
            ('trafficReset','流量重置'),
            ('aiSupport','AI / ChatGPT 解锁'),
            ('streamingSupport','流媒体解锁'),
            ('paymentMethods','支付通道')
        ] if b.get(key))
        
        coupons = []
        if b.get('coupon', {}).get('code'): coupons.append(b['coupon'])
        coupons.extend(b.get('verifiedCoupons') or [])
        coupons.extend(b.get('temporaryCoupons') or [])
        
        coupon_cards_html = ''
        for c in coupons:
            if not isinstance(c, dict): continue
            ccode = c.get('code')
            if not ccode: continue
            cdisc = c.get('discount') or c.get('label') or c.get('discountPercent') or '专享折扣'
            cscope = c.get('scope') or c.get('eligibilityText') or c.get('description') or '全场套餐通用'
            excluded = '、'.join(c.get('excludedPlans') or [])
            expiry = c.get('expiresAt') or c.get('endDate') or c.get('expiry')
            
            coupon_cards_html += f'''
            <div class="coupon-box">
              <div class="coupon-left">
                <div class="coupon-code-wrap">
                  <span class="coupon-label">优惠码</span>
                  <strong class="coupon-code-text">{e(ccode)}</strong>
                  <button type="button" class="btn-copy-code" onclick="copyCoupon('{e(ccode)}')">
                    <i class="fa-regular fa-copy"></i> 一键复制
                  </button>
                </div>
                <p class="coupon-scope">{e(cscope)}</p>
                {f'<p class="coupon-exclude"><i class="fa-solid fa-circle-exclamation"></i> 排除套餐：{e(excluded)}</p>' if excluded else ''}
                {f'<p class="coupon-expiry"><i class="fa-regular fa-clock"></i> 有效期至：{e(expiry)}</p>' if expiry else ''}
              </div>
              <div class="coupon-right">
                <div class="coupon-discount-tag">{e(cdisc)}</div>
                <a class="btn-coupon-use" href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">去结算 ↗</a>
              </div>
            </div>
            '''
            
        body = re.sub(r'^import .*$', '', b['body'], flags=re.M)
        body = re.sub(r'<[A-Z][^>]*?/>', '', body, flags=re.S)
        body = re.sub(r'\[([^\]]+)\]\(/(?:ai|streaming|dedicated-line|guides)\)', r'\1', body)
        article = markdown.markdown(body, extensions=['tables', 'fenced_code', 'sane_lists'])
        article = re.sub(r'(<table>.*?</table>)', r'<div class="article-table-wrap">\1</div>', article, flags=re.S)
        article = re.sub(r'<a\s+href="([^"]+)"', r'<a href="\1" target="_blank" rel="nofollow sponsored noopener noreferrer"', article)
        
        # Hero coupon box placed directly below the subtitle
        if code:
            hero_coupon_html = f'''
            <div class="hero-coupon-card">
              <div class="hero-coupon-header">
                <span class="hero-coupon-tag"><i class="fa-solid fa-ticket"></i> 专属优惠码</span>
                <span class="hero-coupon-disc">{e(disc)} 特惠</span>
              </div>
              <div class="hero-coupon-body">
                <div class="hero-coupon-code-box">
                  <span class="code-label">专属优惠码：</span>
                  <code class="code-text" id="hero-code-{slug}">{e(code)}</code>
                  <button type="button" class="btn-hero-copy" onclick="copyCoupon('{e(code)}')">
                    <i class="fa-regular fa-copy"></i> 一键复制
                  </button>
                </div>
                <div class="hero-coupon-desc">
                  <span><i class="fa-solid fa-circle-check"></i> 适用范围：{e(scope or "全场所有套餐周期通用，结账输入即享折上折")}</span>
                </div>
              </div>
            </div>
            '''
        else:
            hero_coupon_html = f'''
            <div class="hero-coupon-card no-coupon-card">
              <div class="hero-coupon-header">
                <span class="hero-coupon-tag standard"><i class="fa-solid fa-shield-check"></i> 官方正价保障</span>
                <span class="hero-coupon-disc standard">底价直售</span>
              </div>
              <div class="hero-coupon-body">
                <div class="hero-coupon-desc">
                  <span><i class="fa-solid fa-circle-info"></i> 当前品牌官方实行平价直营策略，全周期套餐已是官方底价，无需输入优惠码，直达官网结算即享正品保障。</span>
                </div>
              </div>
            </div>
            '''
        
        if b.get('is_featured'):
            first_crumb = '<a href="https://colasaiko.github.io/Home/topic/tuijianjichang/index.html" target="_blank" rel="noopener" title="推荐机场主推榜">推荐机场主推榜</a>'
        else:
            first_crumb = '<a href="https://colasaiko.github.io/Home/topic/tuijianjichang/brands/index.html" target="_blank" rel="noopener" title="全部机场品牌与套餐价格 | 品牌资料库">全部品牌资料库</a>'
        
        detail_content = f'''
        <main class="detail-container">
          <div class="detail-top-action-bar">
            <a class="btn-top-big-back floating-back-icon-btn" href="../../#brand-{slug}" onclick="if(window.history.length>1){{window.history.back();return false;}}" title="返回原本位置" aria-label="返回原本位置">
              <span class="floating-icon-arrow"><i class="fa-solid fa-arrow-left"></i></span>
              <span class="floating-icon-text">返回原本位置</span>
            </a>
          </div>
          
          <nav class="breadcrumb-bar" aria-label="Breadcrumbs">
            {first_crumb}
            <span class="sep">/</span>
            <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/brands/{slug}/index.html" target="_blank" rel="noopener" title="{e(b['name'])}套餐价格与资料 | 机场品牌库">{e(b['name'])} 资料库</a>
            <span class="sep">/</span>
            <a href="../../" title="机场买买买！">机场买买买！</a>
            <span class="sep">/</span>
            <span class="current">{e(b['name'])} 专属购买页</span>
          </nav>
          
          <section class="detail-hero-section">
            <div class="detail-hero-main">
              <div class="eyebrow-pill">官方正品注册通道 · 独立落地页</div>
              <h1 class="detail-title">{e(b['name'])}</h1>
              <p class="detail-intro">{rich(deep_subtitle)}</p>
              
              <!-- 专属优惠码放在副标题紧随下方 -->
              {hero_coupon_html}
              
              <div class="detail-hero-cta">
                <a class="btn-primary-buy" href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">
                  直达官网选购 ↗
                </a>
                <a class="btn-secondary-link" href="#plans-table">
                  查看 {len(plans)} 款套餐价格表 ↓
                </a>
              </div>
            </div>
            
            <div class="detail-summary-card">
              <div class="summary-top">
                <span class="brand-symbol lg">{e(b['name'][0])}</span>
                <div>
                  <div class="summary-label">品牌评级推荐</div>
                  <strong>官方核验 · 专线高速节点</strong>
                </div>
              </div>
              <ul class="summary-features">
                {''.join(f'<li><span class="bullet-dash">—</span> {e(x)}</li>' for x in b.get('features',[])[:4])}
              </ul>
              <div class="summary-purchase-btn">
                <a href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">
                  直达官方购买 ↗
                </a>
              </div>
            </div>
          </section>
          
          {highlights_html}

          <section class="specs-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-sliders"></i> 核心服务规格与网络参数</h2>
              <span class="heading-tag">深度核验参数</span>
            </div>
            <dl class="facts-grid">
              {facts}
            </dl>
          </section>

          {nodes_html}

          {f'''
          <section class="coupon-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-ticket"></i> 最新专属优惠码</h2>
              <span class="heading-tag">结账即可抵扣</span>
            </div>
            <div class="coupons-grid">
              {coupon_cards_html}
            </div>
          </section>
          ''' if coupon_cards_html else ''}
          
          {chart_section_html}
          
          <section id="plans-table" class="plans-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-layer-group"></i> 套餐与价格</h2>
              <span class="heading-tag">{plan_group_count} 个套餐 · {len(plans)} 种付款方式</span>
            </div>
            <p class="section-tip"><i class="fa-solid fa-lightbulb"></i> 同一套餐的各付款周期放在同一张卡片里，长周期附每月均价方便比较；价格以官网结算页为准。</p>
            <div class="plan-cards">
              {plan_cards_html}
            </div>
          </section>

          {steps_html}

          <section class="article-section">
            <div class="section-heading">
              <h2><i class="fa-solid fa-file-lines"></i> {e(b['name'])} 深度评测与服务介绍</h2>
            </div>
            <div class="article-content">
              {article}
            </div>
          </section>
          
          <div class="detail-bottom-nav">
            <a class="btn-back" href="../../#collection">
              <i class="fa-solid fa-arrow-left"></i> 返回机场买买买！品牌中心
            </a>
            <a class="btn-download-md" href="{slug}.md" download>
              <i class="fa-solid fa-download"></i> 下载 {e(b['name'])} 原始 Markdown 资料
            </a>
          </div>
        </main>
        '''
        
        detail_floating = f'''
        <aside class="floating-buy-bar" aria-label="快速购买">
          <div class="floating-buy-info">
            <span class="floating-brand">{e(b['name'])}</span>
            <span class="floating-tip">{e(f"券码：{code} ({disc})" if code else "官方正品保障 · 即开即用")}</span>
          </div>
          <a class="btn-floating-cta" href="{e(b['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer">
            <span class="pulse-dot"></span>
            <span>立即购买 / 注册</span>
            <i class="fa-solid fa-arrow-up-right-from-square"></i>
          </a>
        </aside>
        '''
        
        code_d, disc_d, _ = coupon_info(b)
        desc_bits = [f"{b['name']}官网购买入口与{len(b.get('pricing', []))}款套餐价格"]
        if b.get('min_month'): desc_bits.append(f"月付¥{b['min_month']:g}起")
        if b.get('min_year'): desc_bits.append(f"年付¥{b['min_year']:g}起")
        if code_d: desc_bits.append(f"优惠码{code_d}（{disc_d}）")
        lt_d = text(b.get('lineType', []))
        if lt_d: desc_bits.append(f"线路：{lt_d}")
        desc_bits.append('含协议、设备与流媒体解锁参数')
        brand_desc = '，'.join(desc_bits) + '。'
        brand_path = f'brands/{slug}/'
        brand_ld = [{
            '@context': 'https://schema.org', '@type': 'BreadcrumbList',
            'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': SITE_NAME, 'item': SITE_URL},
                {'@type': 'ListItem', 'position': 2, 'name': b['name'], 'item': SITE_URL + brand_path},
            ]}]
        page_urls.append(brand_path)
        (target / 'index.html').write_text(shell(f"{b['name']}套餐购买与优惠码", detail_content, detail_floating, '../../', is_detail=True, path=brand_path, desc=brand_desc, jsonld=brand_ld), encoding='utf-8')
    
    # Build 4-item asymmetric editorial strip for top 4 flagship maisons (weifeng, feimao, muguang, dalao)
    top4 = brands[:4]
    editorial_items_html = []
    for idx_item, b_item in enumerate(top4):
        b_slug = b_item['slug']
        b_name = b_item['name']
        m_price = f"¥{b_item['min_month']:.2f}".rstrip('0').rstrip('.') + " /月起" if b_item.get('min_month') else "按量计费"
        y_price = f"¥{b_item['min_year']:.2f}".rstrip('0').rstrip('.') + " /年起" if b_item.get('min_year') else ""
        price_line = f"{m_price} · {y_price}" if y_price else m_price
        b_promo = b_item.get('promo') or {}
        price_line = b_promo.get('priceLine') or price_line
        b_desc = b_promo.get('pitch') or text(b_item.get('features', [])[:2])
        b_line = text(b_item.get('lineType', [])) or '专线线路'
        
        editorial_items_html.append(f'''
        <article class="editorial-card editorial-item-{idx_item+1}">
          <div class="editorial-tag">第 0{idx_item+1} 位 · {e(b_line)}</div>
          <div class="editorial-visual">
            <span class="editorial-monogram">{e(b_name[0])}</span>
          </div>
          <div class="editorial-body">
            <h3 class="editorial-name"><a href="brands/{b_slug}/">{e(b_name)}</a></h3>
            <p class="editorial-desc">{rich(b_desc)}</p>
            <div class="editorial-price{' is-promo' if b_promo.get('priceLine') else ''}">{rich(price_line)}</div>
            <div class="editorial-actions">
              <a href="brands/{b_slug}/" class="editorial-link">查看详情 →</a>
              <a href="{e(b_item['aff'])}" target="_blank" rel="nofollow sponsored noopener noreferrer" class="editorial-aff">直达选购 ↗</a>
            </div>
          </div>
        </article>
        ''')
        
    editorial_strip_html = f'''
    <section class="editorial-strip-section">
      <div class="section-meta-header">
        <span class="meta-eyebrow">站长主力推荐四大家 · 优质专线</span>
        <span class="meta-caption">精选主力品牌</span>
      </div>
      <div class="editorial-grid">
        {''.join(editorial_items_html)}
      </div>
    </section>
    '''
    
    concierge_band_html = '''
    <section class="concierge-reservation-band">
      <div class="concierge-inner">
        <div class="concierge-content">
          <span class="concierge-eyebrow">站长专属礼宾服务 · 购买前后必读</span>
          <h3 class="concierge-title">节点咨询、网络测速与安全核验</h3>
          <p class="concierge-subtitle">节点部署咨询 · 大额年付专属优惠券 · 独立防泄漏安全核验报告</p>
        </div>
        <div class="concierge-action">
          <a href="https://colasaiko.github.io/Home/topic/cybersecurity/index.html" target="_blank" rel="noopener" class="btn-concierge-gold">
            网络安全与防泄漏指南 ↗
          </a>
        </div>
      </div>
    </section>
    '''
    
    # Coupon range from data (e.g. 7 折 ~ 9 折)
    def _disc_val(t):
        m = re.search(r'(\d+(?:\.\d+)?)\s*折', str(t or ''))
        if not m:
            return None
        v = float(m.group(1))
        return v / 10 if v >= 10 else v
    _vals = sorted({v for v in (_disc_val((x.get('coupon') or {}).get('discount')) for x in brands) if v})
    coupon_range = f"{_vals[0]:g} 折 ~ {_vals[-1]:g} 折" if len(_vals) > 1 else (f"{_vals[0]:g} 折" if _vals else "以各品牌为准")

    # Crawlable ranking table for the featured brands
    rank_rows = []
    for i, x in enumerate([y for y in brands if y.get('is_featured')], 1):
        xp = x.get('promo') or {}
        if xp.get('priceLine'):
            price_cell = rich(xp['priceLine'])
        else:
            mm = f"¥{x['min_month']:g}/月起" if x.get('min_month') else ''
            yy = f"¥{x['min_year']:g}/年起" if x.get('min_year') else ''
            price_cell = e(' · '.join(t for t in (mm, yy) if t) or '见品牌页')
        xc, xd, _ = coupon_info(x)
        coupon_cell = f'<code>{e(xc)}</code> {e(xd)}' if xc else '—'
        rank_rows.append(f'''
              <tr>
                <td class="rank-no">{i:02d}</td>
                <th scope="row"><a href="brands/{x['slug']}/">{e(x['name'])}</a></th>
                <td>{e(text(x.get('lineType', [])) or '—')}</td>
                <td>{price_cell}</td>
                <td>{coupon_cell}</td>
              </tr>''')
    ranking_table_html = f'''
      <section class="rank-section" aria-labelledby="rank-title">
        <div class="section-heading">
          <h2 id="rank-title"><i class="fa-solid fa-ranking-star"></i> 稳定机场推荐排行榜 · 主力推荐 {len(rank_rows)} 家</h2>
          <span class="heading-tag">线路 · 价格 · 优惠码</span>
        </div>
        <div class="rank-table-wrap">
          <table class="rank-table">
            <thead><tr><th>排名</th><th>机场</th><th>线路类型</th><th>价格</th><th>专属优惠码</th></tr></thead>
            <tbody>{''.join(rank_rows)}
            </tbody>
          </table>
        </div>
        <p class="section-tip"><i class="fa-solid fa-circle-info"></i> 排名为站长推荐顺序，与 Cola 的全栈导航「推荐机场主推榜」同步，不代表测速成绩；价格与优惠以各品牌官网结算页为准。</p>
      </section>'''

    faq_items = [
        ('什么样的机场才算稳定机场？',
         '主要看四点：线路类型（IPLC / IEPL 专线不经过公网跨境，晚高峰通常比普通中转更稳定）、计费倍率是否为 1×、晚高峰（20:00—23:00）的实际表现，以及是否有长期运营记录和正规售后渠道。本排行榜按线路、价格、设备限制和优惠整理，方便横向比较。'),
        ('这个稳定机场推荐排行榜是怎么排序的？',
         f'前 {sum(1 for y in brands if y.get("is_featured"))} 家为站长主力推荐，排序与 Cola 的全栈导航「推荐机场主推榜」保持同步；其余品牌按品牌资料库顺序收录。排名代表推荐顺序，不代表某一次测速的成绩。'),
        ('IPLC、IEPL 专线和 BGP 中转有什么区别？',
         'IPLC / IEPL 是国际专线，数据走运营商的跨境专用链路，延迟和晚高峰稳定性通常更好，价格也更高；BGP 中转经由国内多线机房转发后再出境，成本较低，适合日常轻度使用。可以在下方选购大厅用「全专线架构」「中转线路」标签筛选。'),
        ('第一次买机场，应该选月付还是年付？',
         '建议先买月付或最小的套餐，在自己所在的运营商（电信 / 联通 / 移动）晚高峰实际用几天，确认速度、稳定性和客户端都合适，再考虑季付、年付等长周期套餐。'),
        ('优惠码怎么用？通过本站购买会更贵吗？',
         f'在品牌页复制优惠码，到机场官网结算页的优惠码栏填写即可，本站收录的专属优惠码约为 {coupon_range}。各品牌规则不同（例如部分仅限新用户首单），实付以结算页为准。通过本站链接购买，价格不会增加。'),
        ('买完机场之后还需要注意什么？',
         '订阅链接或账号相当于访问凭据，不要公开分享；连接成功后，建议检查 WebRTC 与 DNS 是否泄露真实 IP。可以参考 Cola 的全栈导航里的在线隐私检测与网络安全专题。'),
    ]
    faq_blocks = []
    for n, (q, a) in enumerate(faq_items):
        faq_blocks.append('\n          <details class="faq-item"' + (' open' if n == 0 else '') + '>'
                          + '<summary>' + e(q) + '</summary><p>' + e(a) + '</p></details>')
    faq_html = f'''
      <section class="faq-section" aria-labelledby="faq-title">
        <div class="section-heading">
          <h2 id="faq-title"><i class="fa-solid fa-circle-question"></i> 稳定机场推荐 · 常见问题</h2>
          <span class="heading-tag">{len(faq_items)} 个问题</span>
        </div>
        <div class="faq-list">{''.join(faq_blocks)}
        </div>
      </section>'''

    # Build Main Index Page
    index_content = f'''
    <main class="index-container">
      <!-- 流量核心 Hero 区域 -->
      <section class="hero-banner">
        <div class="hero-left">
          <div class="hero-eyebrow">
            全网 35 家主流机场档案 · 专线与价格对比 · 独立选购大厅
          </div>
          <h1 class="hero-title">
            <span class="hero-sub-title">稳定机场推荐排行榜</span>
            <span class="hero-sub">专线机场选购指南与价格对比</span>
          </h1>
          <p class="hero-desc">
            这份稳定机场推荐排行榜按线路类型、晚高峰稳定性、价格与设备限制整理 35 家主流机场：IPLC / IEPL 专线与 BGP 中转分开比较，月付、年付与不限时流量包一目了然，每个品牌都有独立页面和专属优惠码。
          </p>
          <div class="hero-actions">
            <a href="#collection" class="btn-ghost">
              直达 35 个品牌选购大厅 ↓
            </a>
            <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/index.html" target="_blank" rel="noopener" class="btn-gold-outline" title="推荐机场主推榜">
              推荐机场主推榜 ↗
            </a>
            <a href="https://colasaiko.github.io/Home/topic/tuijianjichang/brands/index.html" target="_blank" rel="noopener" class="btn-ghost" title="全部机场品牌与套餐价格 | 品牌资料库">
              全部品牌资料库 ↗
            </a>
          </div>
        </div>
        
        <aside class="hero-stats-card">
          <div class="stat-badge">实测收录</div>
          <div class="stat-number">35<span class="stat-unit">家机场</span></div>
          <p class="stat-desc">
            精选 12 家主力推荐旗舰品牌，全量收录 35 家精品机场，价格透明，参数真实核验。
          </p>
          <div class="stat-pills">
            <span>高速专线</span>
            <span>不限时流量包</span>
            <span>多客户端适配</span>
            <span>原生解锁 AI</span>
          </div>
        </aside>
      </section>

      <!-- 4 Items Asymmetric Editorial Product Strip -->
      {editorial_strip_html}

      <!-- 可抓取的排行榜表格（SEO 主关键词：稳定机场推荐排行榜） -->
      {ranking_table_html}

      <!-- Concierge Reservation Band (Dark #141414 Strip) -->
      {concierge_band_html}

      <!-- 核心 SEO 转化硬核指南区 (Why / How / 好处与坏处 / 30秒科普 / 温馨提示) -->
      <section class="seo-guide-section">
        <!-- 1. Why 为什么要知道 -->
        <div class="guide-box why-box">
          <div class="guide-box-header">
            <span class="guide-pill">核心价值与初衷</span>
            <h2>为什么你需要一份客观透明的稳定机场推荐？</h2>
          </div>
          <div class="guide-grid-3">
            <div class="guide-col-item">
              <div class="col-num">01</div>
              <h3>打破信息差，拒绝跑路坑</h3>
              <p>翻墙圈内推广鱼龙混杂，充斥大量套壳圈钱的月抛廉价直连机场。本站建立客观档案，实时监控结算后台，让真实节点与价格一览无余。</p>
            </div>
            <div class="guide-col-item">
              <div class="col-num">02</div>
              <h3>识破“虚标带宽与偷跑倍率”</h3>
              <p>很多机场号称 10Gbps 峰值带宽，实际晚高峰严重限流，甚至暗中设置 3x-5x 高倍率。我们只推荐真实 1x 倍率与标称专线的大厂。</p>
            </div>
            <div class="guide-col-item">
              <div class="col-num">03</div>
              <h3>专属优惠码直接抵扣</h3>
              <p>官方渠道原价昂贵，我们与各大品牌沟通拿到专属优惠码（{coupon_range}），在独立落地页一键复制，让每一分预算都花在刀刃上。</p>
            </div>
          </div>
        </div>

        <!-- 2. How 如何科学选购 -->
        <div class="guide-box how-box">
          <div class="guide-box-header">
            <span class="guide-pill">科学选购指南</span>
            <h2>四步挑选最适合你的科学上网与加速工具</h2>
          </div>
          <div class="how-steps">
            <div class="step-card">
              <div class="step-num">01</div>
              <h4>按实际业务场景定线路</h4>
              <p>重度流媒体 4K、跨境电商、ChatGPT/Claude 生产力，请认准 <strong>全 IPLC/IEPL 国际专线</strong>；日常查资料轻度使用可选优质 <strong>BGP 中转</strong>。</p>
            </div>
            <div class="step-card">
              <div class="step-num">02</div>
              <h4>按手中设备匹配客户端</h4>
              <p>Windows 选 Clash Verge / v2rayN；Mac 选 Clash Meta / Surge；iOS 认准 Shadowrocket（小火箭）；安卓选 Clash / v2rayNG。</p>
            </div>
            <div class="step-card">
              <div class="step-num">03</div>
              <h4>务必坚持“先月付试水”</h4>
              <p>切勿为了所谓的“三年付骨折价”冲动充值！先买一个月，在晚高峰（20:00~23:00）实测你所在运营商（电信/联通/移动）的表现。</p>
            </div>
            <div class="step-card">
              <div class="step-num">04</div>
              <h4>结账激活独家优惠码</h4>
              <p>进入本站每个品牌的独立落地页，复制对应优惠码（如 <code>fly20</code>、<code>weifeng90</code>），在机场结算页填写即可抵扣，具体规则以结算页为准。</p>
            </div>
          </div>
        </div>

        <!-- 3. 好处与坏处 (Pros & Cons) -->
        <div class="guide-box pros-cons-box">
          <div class="guide-box-header">
            <span class="guide-pill">客观对比与理性预期</span>
            <h2>购买专线机场的好处，以及你必须提前了解的“客观坏处”</h2>
          </div>
          <div class="pros-cons-grid">
            <div class="pro-card">
              <h3 class="pro-title">优势 · 购买优质专线机场的好处</h3>
              <ul>
                <li><strong>晚高峰不卡顿：</strong>内网专线不经过公网 GFW 过滤防火墙，敏感时期依然能保持超低延迟与 4K 秒开。</li>
                <li><strong>原生 IP 完美解锁：</strong>解除 Netflix、Disney+ 等版权限制，告别访问 ChatGPT 时常见的“Access Denied”报错。</li>
                <li><strong>不限制设备接入：</strong>前排主流大厂大多支持多台手机、电脑、软路由同时在线，一人购买全家共享。</li>
              </ul>
            </div>
            <div class="con-card">
              <h3 class="con-title">须知 · 必须理解的“客观坏处与物理不可抗力”</h3>
              <ul>
                <li><strong>物理海底光缆故障：</strong>亚太地区地震、海啸或渔船拖网意外切断跨国海缆时，国际出口会整体拥堵，任何神仙机场也无法避免。</li>
                <li><strong>特殊敏感期防火墙严查：</strong>逢年过节或重大会议期间，国内入口中转机可能遭遇临时查封断流，需等待大厂切换备用入口。</li>
                <li><strong>同行恶性黑客 DDoS：</strong>翻墙圈竞争白热化，头部大厂可能偶遇恶性流量轰炸导致服务震荡，因此<strong>常备一家不限时备用包至关重要</strong>。</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 4. 30秒科普：为什么非高峰也会用不了 -->
        <div class="guide-box science-box">
          <div class="science-header">
            <span class="guide-pill">硬核科普 · 30 秒读懂网络原理</span>
            <h2>为什么有时候明明不是晚高峰，节点却依然无法使用？</h2>
          </div>
          <p class="science-intro">很多用户以为节点变慢或失联一定是因为“网络拥挤”，但在非高峰期断流，通常是由于以下三大底层原因触发了安全风控或路由阻断：</p>
          <div class="science-grid">
            <div class="science-item">
              <div class="science-item-num">A</div>
              <h4>国内中转入口被 GFW 精准单向污染</h4>
              <p>并不是海外节点宕机，而是你本地通向国内机房入口的公网连接被墙阻断。大厂通常在 10~30 分钟内完成入口 IP 自动漂移切换。</p>
            </div>
            <div class="science-item">
              <div class="science-item-num">B</div>
              <h4>目标网站流媒体 / Cloudflare 触发高风险风控</h4>
              <p>你访问的网站（如 OpenAI、银行网银、部分流媒体）将该落地节点标记为机房代理 IP 并临时拦截。此时只需在客户端切换同品牌的其他国家或备用节点即可秒解。</p>
            </div>
            <div class="science-item">
              <div class="science-item-num">C</div>
              <h4>本地客户端分流规则与 DNS 污染冲突</h4>
              <p>Clash 等客户端的分流规则库过旧，或者本地网卡未配置 Fake-IP，导致目标域名的解析流量没有走节点通道而是被本地运营商拦截。</p>
            </div>
          </div>
        </div>

        <!-- 5. 温馨小提示 (维持网站运行与网络安全研究指引) -->
        <div class="guide-box notice-box">
          <div class="notice-header">
            <span class="guide-pill">站长温馨提示</span>
            <h3>网站运营机制与购买前后安全必读</h3>
            <p>透明告知维护来源，并为您筑牢网络安全与隐私防线</p>
          </div>
          <div class="notice-content">
            <div class="notice-section">
              <h4>维持网站运营的小费用说明</h4>
              <p>
                本站坚持完全中立、透明的真实数据整理。通过本站链接前往注册，机场官方会向站长返还一笔极其微薄的推荐（Affiliate）佣金。<strong>这笔小费用将全部用于维持本站测速探针服务器、日常维护与定期更新；您的购买价格绝不会因此增加任何一分钱</strong>，相反，您还能免费使用本站争取来的专属优惠码（{coupon_range}）！感谢大家的支持！
              </p>
            </div>
            <div class="notice-section">
              <h4>购买前参考与购买后必做的安全检查</h4>
              <p>
                在任何机场选购前，请仔细核对套餐价格、设备限制与重置时间。<strong>购买并成功连接后，切勿直接裸奔！</strong>请务必前往学习站长的硬核安全专题：
                <a href="https://colasaiko.github.io/Home/topic/cybersecurity/index.html" target="_blank" rel="noopener" class="notice-safe-link">
                  网络安全研究 | Cola 站长 ↗
                </a>
              </p>
              <div class="safe-links-grid">
                <a href="https://colasaiko.github.io/Home/api.html" target="_blank" rel="noopener" class="safe-card-pill">
                  <span><strong>在线隐私防泄漏检测</strong>检查 WebRTC 与真实 IP 暴露 ↗</span>
                </a>
                <a href="https://colasaiko.github.io/Home/topic/cybersecurity/privacy.html" target="_blank" rel="noopener" class="safe-card-pill">
                  <span><strong>机场审计与隐私揭秘</strong>保护订阅链接与邮箱安全 ↗</span>
                </a>
                <a href="https://colasaiko.github.io/Home/topic/cybersecurity/protocols.html" target="_blank" rel="noopener" class="safe-card-pill">
                  <span><strong>协议大乱斗与 GFW 攻防</strong>搞懂 VLESS / Shadowsocks 加密 ↗</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      {faq_html}

      <!-- 品牌选购大厅 -->
      <section id="collection" class="collection-section">
        <div class="collection-toolbar">
          <div class="toolbar-header">
            <div>
              <div class="toolbar-eyebrow">独立品牌选购大厅</div>
              <h2 class="toolbar-title">探索全部机场品牌（各品牌独立成页，分开放置）</h2>
            </div>
            <div id="search-counter" class="toolbar-count">显示 35 / 35 个品牌</div>
          </div>
          
          <div class="toolbar-controls">
            <div class="search-input-box">
              <input type="text" id="brand-search-input" placeholder="输入品牌名、协议（如 VLESS）、线路（如 IPLC）实时检索..." autocomplete="off">
              <button type="button" id="search-clear-btn" class="search-clear" style="display:none;"><i class="fa-solid fa-xmark"></i></button>
            </div>
            
            <div class="filter-tabs" id="filter-tabs">
              <button type="button" class="tab-btn active" data-filter="all">全部品牌 (35)</button>
              <button type="button" class="tab-btn" data-filter="featured">站长主力推荐 (12家)</button>
              <button type="button" class="tab-btn" data-filter="iplc">全专线架构</button>
              <button type="button" class="tab-btn" data-filter="iepl">专线线路</button>
              <button type="button" class="tab-btn" data-filter="bgp">中转线路</button>
              <button type="button" class="tab-btn" data-filter="coupon">有专属优惠券</button>
              <button type="button" class="tab-btn" data-filter="budget">高性价比 (≤20元/月)</button>
              <button type="button" class="tab-btn" data-filter="onetime">不限时流量包</button>
            </div>
          </div>
        </div>
        
        <div class="brand-grid" id="brand-cards-grid">
          {''.join(cards)}
        </div>
        
        <div class="expand-brands-wrap" id="expand-brands-wrap">
          <button type="button" class="btn-expand-brands" id="btn-toggle-expand" onclick="toggleExpandBrands()">
            <span>展开查看更多品牌 (26 家)</span>
            <i class="fa-solid fa-chevron-down"></i>
          </button>
        </div>
        
        <div id="no-result" class="no-result-box" style="display: none;">
          <h3>未找到匹配的机场品牌</h3>
          <p>请尝试搜索其他关键字，或切换分类筛选标签。</p>
          <button type="button" class="btn-reset-search" onclick="resetFilters()">重置所有筛选条件</button>
        </div>
      </section>
    </main>
    {INDEX_FILTER_JS}
    '''
    
    index_floating = '''
    <a class="floating-quick-btn" href="#collection" title="浏览全部品牌">
      <span class="floating-btn-text">选购大厅 ↓</span>
    </a>
    '''
    
    index_ld = [
        {'@context': 'https://schema.org', '@type': 'WebSite', 'name': SITE_NAME, 'url': SITE_URL,
         'description': DEFAULT_DESC, 'inLanguage': 'zh-CN',
         'isPartOf': {'@type': 'WebSite', 'name': 'Cola的全栈导航', 'url': 'https://colasaiko.github.io/Home/'}},
        {'@context': 'https://schema.org', '@type': 'FAQPage',
         'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faq_items]},
        {'@context': 'https://schema.org', '@type': 'ItemList', 'name': '稳定机场推荐排行榜',
         'itemListOrder': 'https://schema.org/ItemListOrderAscending', 'numberOfItems': len(brands),
         'itemListElement': [{'@type': 'ListItem', 'position': i, 'name': x['name'], 'url': f"{SITE_URL}brands/{x['slug']}/"}
                             for i, x in enumerate(brands, 1)]},
    ]
    (OUT / 'index.html').write_text(shell(INDEX_TITLE, index_content, index_floating, desc=DEFAULT_DESC, jsonld=index_ld), encoding='utf-8')

    # 联盟链接检查：所有指向品牌推广链接的 <a> 都必须带 sponsored + nofollow + noopener
    aff_urls = {html.escape(str(x.get('aff') or ''), quote=True) for x in brands if x.get('aff')}
    bad_aff = []
    for page in OUT.rglob('*.html'):
        for tag in re.findall(r'<a\b[^>]*>', page.read_text(encoding='utf-8')):
            m_href = re.search(r'href="([^"]+)"', tag)
            if m_href and m_href.group(1) in aff_urls:
                rel = set((re.search(r'rel="([^"]*)"', tag) or [None, ''])[1].split())
                if not {'sponsored', 'nofollow', 'noopener'} <= rel:
                    bad_aff.append(f'{page.relative_to(OUT)}: {tag[:120]}')
    if bad_aff:
        raise SystemExit('联盟链接缺少 rel="sponsored nofollow noopener"：\n' + '\n'.join(bad_aff[:20]))

    from datetime import date
    today = date.today().isoformat()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in page_urls:
        sm.append(f'  <url><loc>{SITE_URL}{u}</loc><lastmod>{today}</lastmod><priority>{"1.0" if not u else "0.8"}</priority></url>')
    sm.append('</urlset>')
    (OUT / 'sitemap.xml').write_text(chr(10).join(sm) + chr(10), encoding='utf-8')
    (OUT / 'robots.txt').write_text(f'User-agent: *{chr(10)}Allow: /{chr(10)}{chr(10)}Sitemap: {SITE_URL}sitemap.xml{chr(10)}', encoding='utf-8')
    
    # Generate Enhanced BRAND-INDEX.md with Full Purchase Data
    index_md = f'''# 🛒 机场买买买！稳定机场推荐排行榜与品牌购买全景指南

> **项目说明**：本文件专为 **[Colasaiko/Home](https://github.com/Colasaiko/Home)** 仓库打造。全网收录 **{total_brands}** 个主流翻墙机场品牌，前 12 名为主推核心品牌，各品牌独立落地页分开放置，提供月付/年付价格、独家优惠券与安全防漏指引。

---

## 📊 35 个机场品牌核心购买决策矩阵（前 9 名为主力力荐）

| # | 品牌名称 | 推荐梯队 | 线路架构 | 支持协议 | 最低月付 | 最低年付 | 不限时包 | 独家优惠码 | 独立购买页 | 官方购买通道 |
|---|---|---|---|---|---|---|---|---|---|---|
'''
    
    for idx, b in enumerate(brands, 1):
        slug = b['slug']
        name = b['name']
        line_t = text(b.get('lineType', [])) or '优质线路'
        proto = text(b.get('protocols', [])) or '常见协议'
        m_price = f"¥{b['min_month']:.2f}".rstrip('0').rstrip('.') if b.get('min_month') else "—"
        y_price = f"¥{b['min_year']:.2f}".rstrip('0').rstrip('.') if b.get('min_year') else "—"
        onetime = "✅ 支持" if b.get('min_onetime') else "—"
        
        tier = "👑 站长主力" if (b.get('featured_rank') and b['featured_rank'] <= FEATURED_COUNT) else "标准收录"
        
        code, disc, _ = coupon_info(b)
        coupon_str = f"`{code}` ({disc})" if code else "官方正价"
        
        detail_link = f"[查看独立落地页](website/dist/brands/{slug}/index.html)"
        aff_link = f"[直达购买 / 注册 ↗]({b['aff']})"
        
        index_md += f"| {idx:02d} | **{name}** | {tier} | {line_t} | {proto} | {m_price} | {y_price} | {onetime} | {coupon_str} | {detail_link} | {aff_link} |\n"
        
    top_lines = []
    for b in [x for x in brands if x.get('is_featured')]:
        code, disc, _ = coupon_info(b)
        line_t = text(b.get('lineType', [])) or '优质线路'
        coupon_part = f"，优惠码 `{code}`（{disc}）" if code else ""
        m = f"，月付 ¥{b['min_month']:g} 起" if b.get('min_month') else ""
        y = f"，年付 ¥{b['min_year']:g} 起" if b.get('min_year') else ""
        top_lines.append(f"{b['featured_rank']}. **{b['name']}**：{line_t}{coupon_part}{m}{y}。")
    top_names = '、'.join(x['name'] for x in brands if x.get('is_featured'))
    top_list_md = chr(10).join(top_lines)
    index_md += f'''
---

## 🎯 站长核心主推 {FEATURED_COUNT} 大品牌推荐榜（{top_names}）

{top_list_md}


---

## 🛡️ 网络安全与购买后隐私检测必读

购买机场节点后，请务必前往站长的安全专题进行安全防漏核验：
- **安全研究专区**：[网络安全研究 | Cola 站长](https://colasaiko.github.io/Home/topic/cybersecurity/index.html)
- **在线防泄漏检测**：[在线隐私防泄露检测工具](https://colasaiko.github.io/Home/api.html)（核验 WebRTC 与真实 IP 暴露）
- **机场审计揭秘**：[机场审计规则与隐私揭秘](https://colasaiko.github.io/Home/topic/cybersecurity/privacy.html)（保护个人邮箱与订阅安全）
- **协议深度解析**：[翻墙协议大乱斗与 GFW 攻防](https://colasaiko.github.io/Home/topic/cybersecurity/protocols.html)
'''
    (ROOT / 'BRAND-INDEX.md').write_text(index_md, encoding='utf-8')
    
    print(json.dumps({
        'total_brands': total_brands,
        'plans_count': sum(len(b.get('pricing', [])) for b in brands),
        'html_pages': len(list(OUT.rglob('*.html')))
    }, ensure_ascii=False))

if __name__ == '__main__':
    build()
