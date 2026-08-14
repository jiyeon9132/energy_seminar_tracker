"""
crawl_seminars.py
에너지 관련 세미나 정보를 자동 수집하여 index.html에 추가합니다.
매주 월요일 10:00 KST 자동 실행
"""

import os
import re
import base64
import json
import requests
from datetime import datetime

GH_TOKEN   = os.environ["GITHUB_TOKEN"]
REPO       = os.environ["GITHUB_REPO"]
TG_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID", "")
FC_KEY     = os.environ.get("FIRECRAWL_API_KEY", "")
DASHBOARD  = os.environ.get("DASHBOARD_URL", "https://energy-seminar.vercel.app")

PROCESSED_FILE = "crawled_items.json"

# ── 키워드 필터 ─────────────────────────────────────────────
EVENT_TYPES = [
    "세미나", "포럼", "토론회", "공청회",
    "컨퍼런스", "설명회", "간담회",
]

TOPIC_KEYWORDS = [
    "재생에너지", "태양광", "풍력", "RE100",
    "ESS", "에너지저장", "BESS",
    "전기차", "충전", "V2G",
    "전력망", "계통", "HVDC", "송전", "배전",
    "수소", "연료전지", "수전해",
    "배터리", "이차전지", "전고체",
    "CCUS", "탄소포집",
    "VPP", "가상발전소",
    "분산에너지", "분산전원", "마이크로그리드",
    "PPA", "전력구매계약",
]

def has_keyword(text: str) -> bool:
    has_event = any(kw in text for kw in EVENT_TYPES)
    has_topic = any(kw in text for kw in TOPIC_KEYWORDS)
    return has_event and has_topic

def is_future(text: str) -> bool:
    now = datetime.now()
    year = now.year
    months_ahead = [f"{year}.{m:02d}" for m in range(now.month, 13)]
    months_ahead += [f"{year+1}.{m:02d}" for m in range(1, 13)]
    return any(m in text for m in months_ahead) or str(year) in text


# ── GitHub API ───────────────────────────────────────────────
def gh_get_file(path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"})
    if r.status_code == 404:
        return "", ""
    r.raise_for_status()
    data = r.json()
    return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]

def gh_put_file(path, content, sha, message):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, json=payload,
                     headers={
                         "Authorization": f"token {GH_TOKEN}",
                         "Accept": "application/vnd.github.v3+json",
                     })
    return r.status_code in (200, 201)


# ── 처리 완료 항목 관리 ──────────────────────────────────────
def load_processed():
    content, _ = gh_get_file(PROCESSED_FILE)
    if not content:
        return set()
    try:
        return set(json.loads(content))
    except Exception:
        return set()

def save_processed(processed, sha):
    content = json.dumps(sorted(processed))
    gh_put_file(PROCESSED_FILE, content, sha, "[크롤러] 처리 완료 항목 업데이트")


# ── requests 크롤링 ──────────────────────────────────────────
def crawl_with_requests(url):
    try:
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = "utf-8"
        return r.text
    except Exception as e:
        print(f"  requests 실패 ({url}): {e}")
        return ""

def extract_items_from_html(html, source_name, source_url):
    items = []
    pattern = r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>([^<]{10,100})</a>'
    for match in re.finditer(pattern, html):
        href, text = match.group(1), match.group(2).strip()
        text = re.sub(r'\s+', ' ', text)
        if has_keyword(text) and len(text) > 10:
            full_url = href if href.startswith("http") else source_url.rstrip("/") + "/" + href.lstrip("/")
            items.append({
                "title": text,
                "url": full_url,
                "source": source_name,
            })
    return items


# ── Firecrawl 크롤링 ─────────────────────────────────────────
def crawl_with_firecrawl(url, source_name):
    if not FC_KEY:
        print(f"  Firecrawl API 키 없음 — {source_name} 건너뜀")
        return []
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {FC_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": ["markdown"]},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  Firecrawl 실패 ({source_name}): {r.status_code}")
            return []

        markdown = r.json().get("data", {}).get("markdown", "")
        items = []

        for line in markdown.splitlines():
            line = line.strip()
            m = re.search(r'\[([^\]]{10,100})\]\((https?://[^\)]+)\)', line)
            if m:
                text, link = m.group(1).strip(), m.group(2)
                if has_keyword(text):
                    items.append({"title": text, "url": link, "source": source_name})
            elif has_keyword(line) and len(line) > 15:
                items.append({"title": line[:80], "url": url, "source": source_name})
        return items

    except Exception as e:
        print(f"  Firecrawl 예외 ({source_name}): {e}")
        return []


# ── URL 정제 ─────────────────────────────────────────────────
def clean_url(url):
    if not url:
        return ""
    for sep in ['/menu.es', '/main.es', '/sub.es']:
        if sep in url:
            url = url.split(sep)[0]
    if '?' in url:
        base, query = url.split('?', 1)
        query = query.split('/http')[0].split('//')[0]
        url = f"{base}?{query}"
    return url.strip()

def esc(s):
    return (s or "").replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').strip()


# ── index.html에 신규 행사 추가 ──────────────────────────────
def add_to_html(item):
    try:
        html, sha = gh_get_file("index.html")
    except Exception as e:
        return False, str(e)

    now = datetime.now()
    month = now.month
    today = now.strftime("%Y.%m.%d")
    item_url = clean_url(item.get("url", ""))

    new_entry = (
        f'  {{title:"{esc(item["title"])}",'
        f'status:"개최추정",'
        f'prio:"우선",'
        f'day:null,'
        f'date:"{now.year}.{month:02d} (크롤링 수집)",'
        f'org:"{esc(item["source"])}",'
        f'venue:"미정",'
        f'cost:"미정",'
        f'content:"",'
        f'speakers:"미정",'
        f'src:"{esc(item["source"])} — 자동 수집 ({today})",'
        f'url:"{esc(item_url)}"}}'
    )

    d_var = f"D{month}"
    if f"const {d_var}=[" in html:
        pattern = rf"(const {d_var}=\[)([\s\S]*?)(\];)"
        def replacer(m):
            existing = m.group(2).rstrip()
            sep = ",\n" if existing.strip() else "\n"
            return f"{m.group(1)}{existing}{sep}{new_entry}\n{m.group(3)}"
        html = re.sub(pattern, replacer, html)
    else:
        new_array = f"const {d_var}=[\n{new_entry}\n];\n\n"
        html = html.replace("const DATA_MAP =", new_array + "const DATA_MAP =")
        html = re.sub(
            r"(const DATA_MAP\s*=\s*\{)([^}]+)(\};)",
            lambda m: f"{m.group(1)}{m.group(2)}, {month}: {d_var}{m.group(3)}",
            html,
        )

    ok = gh_put_file("index.html", html, sha,
                     f"[크롤러] {month}월 행사 추가: {item['title'][:30]}")
    return ok, "" if ok else "GitHub 업데이트 실패"


# ── 텔레그램 발송 ────────────────────────────────────────────
def send_telegram(text):
    if not TG_TOKEN or not TG_CHANNEL:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHANNEL, "text": text},
        )
    except Exception as e:
        print(f"텔레그램 발송 실패: {e}")


# ── 크롤링 대상 사이트 ───────────────────────────────────────
SITES_REQUESTS = [
    ("기후에너지환경부",   "https://www.mcee.go.kr/home/web/index.do?menuId=10598"),
    ("산업통상부",         "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c"),
    ("한국에너지공단",     "https://www.energy.or.kr/web/kem_home_new/notice.asp"),
    ("한국전력거래소",     "https://www.kpx.or.kr/board.es?mid=a10301000000&bid=0003"),
    ("한국전력공사",       "https://home.kepco.co.kr/kepco/PR/A/htmlView/PREAAHP00202.do"),
    ("KHARN",              "https://www.kharn.kr/news/section.html?sec_no=3"),
    ("전기신문",           "https://www.electimes.com/news/articleList.html?sc_section_code=S1N4"),
]

SITES_FIRECRAWL = [
    ("에너지전환포럼",     "https://www.energytransitionkorea.org/event"),
    ("스마트그리드협회",   "https://www.ksg.or.kr/bbs/board.php?bo_table=notice"),
    ("산업교육연구소",     "https://www.kiei.com/education/schedule?t=schedule_01"),
    ("국회도서관 세미나",  "https://ampos.nanet.go.kr/seminarList.do"),
    ("에너지미래포럼",     "https://www.energyfuture.kr/"),
]


# ── 메인 ────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] 크롤링 시작")

    processed = load_processed()
    _, proc_sha = gh_get_file(PROCESSED_FILE)

    all_items = []

    for name, url in SITES_REQUESTS:
        print(f"크롤링 중: {name}")
        html = crawl_with_requests(url)
        if html:
            items = extract_items_from_html(html, name, url)
            print(f"  {len(items)}개 항목 감지")
            all_items.extend(items)

    for name, url in SITES_FIRECRAWL:
        print(f"크롤링 중 (Firecrawl): {name}")
        items = crawl_with_firecrawl(url, name)
        print(f"  {len(items)}개 항목 감지")
        all_items.extend(items)

    new_items = []
    seen_titles = set()
    for item in all_items:
        key = item["title"][:50]
        if key not in processed and key not in seen_titles:
            seen_titles.add(key)
            new_items.append(item)

    print(f"\n신규 항목: {len(new_items)}개")

    if not new_items:
        send_telegram(
            f"[에너지 세미나 주간 업데이트]\n"
            f"업데이트: {datetime.now().strftime('%Y.%m.%d')}\n\n"
            f"이번 주 신규 감지 행사 없음\n\n"
            f"대시보드: {DASHBOARD}"
        )
        print("신규 항목 없음 — 텔레그램 알림 발송 완료")
        return

    added = []
    for item in new_items:
        ok, err = add_to_html(item)
        if ok:
            processed.add(item["title"][:50])
            added.append(item)
            print(f"  추가 완료: {item['title'][:40]}")
        else:
            print(f"  추가 실패: {err}")

    if added:
        save_processed(processed, proc_sha)

    lines = [
        f"[에너지 세미나 주간 업데이트]",
        f"업데이트: {datetime.now().strftime('%Y.%m.%d')}",
        "",
    ]
    if added:
        lines.append(f"신규 감지 행사 {len(added)}건")
        lines.append("-" * 28)
        for i, item in enumerate(added[:5], 1):
            lines.append(f"{i}. {item['title'][:40]}")
            lines.append(f"   출처: {item['source']}")
            lines.append("")
        if len(added) > 5:
            lines.append(f"외 {len(added)-5}건 추가 — 대시보드에서 확인")
            lines.append("")
    lines += [
        "=" * 28,
        "자동 수집 데이터는 반드시 직접 확인 후 참석 결정하세요.",
        "",
        f"대시보드: {DASHBOARD}",
    ]
    send_telegram("\n".join(lines))
    print("완료")


if __name__ == "__main__":
    main()
