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
import html as htmllib
from datetime import datetime
from urllib.parse import urljoin

GH_TOKEN   = os.environ["GITHUB_TOKEN"]
REPO       = os.environ["GITHUB_REPO"]
TG_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID", "")
FC_KEY     = os.environ.get("FIRECRAWL_API_KEY", "")
DASHBOARD  = os.environ.get("DASHBOARD_URL", "https://energy-seminar.vercel.app")

PROCESSED_FILE = "crawled_items.json"

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


def has_keyword(text):
    has_event = any(kw in text for kw in EVENT_TYPES)
    has_topic = any(kw in text for kw in TOPIC_KEYWORDS)
    return has_event and has_topic


def normalize_text(s: str) -> str:
    """HTML 엔티티 디코딩, 마크다운 기호·보이지 않는 문자 제거, 공백 정리.

    크롤링 원문에 남아있는 &amp; 같은 HTML 엔티티나 zero-width space 등이
    index.html에 그대로 삽입되면 표시가 깨지거나(엔티티) 삽입되는 JS 문자열
    구문이 손상될 수 있어(제어문자) 여기서 한 번에 정리한다.
    """
    s = htmllib.unescape(s or "")
    s = re.sub(r"[\u200b-\u200f\u202a-\u202e\u00a0\u3000\ufeff]", " ", s)
    s = re.sub(r"<[^>]+>", "", s)        # 남은 HTML 태그 제거
    s = re.sub(r"[*_`#>|]+", "", s)      # 마크다운 강조/표 기호 제거
    s = re.sub(r"\s+", " ", s).strip()
    return s


def esc(s):
    # json.dumps로 감싸면 따옴표/역슬래시/제어문자 등 어떤 값이 와도
    # 항상 유효한 JS 문자열 리터럴이 되어, index.html 삽입 시 구문이 깨지지 않는다.
    return json.dumps(normalize_text(s), ensure_ascii=False)


def esc_url(s):
    # URL은 '#'(앵커) 등을 그대로 보존해야 하므로 마크다운 기호 제거는 건너뛴다.
    return json.dumps(htmllib.unescape(s or "").strip(), ensure_ascii=False)


def clean_url(url):
    if not url:
        return ""
    for sep in ["/menu.es", "/main.es", "/sub.es"]:
        if sep in url:
            url = url.split(sep)[0]
    if "?" in url:
        base, query = url.split("?", 1)
        query = query.split("/http")[0].split("//")[0]
        url = f"{base}?{query}"
    return url.strip()


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
    r = requests.put(
        url,
        json=payload,
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    return r.status_code in (200, 201)


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


def crawl_with_requests(url):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = "utf-8"
        return r.text
    except Exception as e:
        print(f"  requests 실패 ({url}): {e}")
        return ""


def extract_items_from_html(html, source_name, source_url):
    items = []
    # 앵커 안에 <p>제목</p>처럼 한 겹 감싸진 카드형 목록도 잡을 수 있도록
    # </a> 직전까지는 중첩 태그를 허용하고, normalize_text가 태그를 벗겨낸다.
    pattern = r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>((?:(?!</a>).){10,300})</a>'
    for match in re.finditer(pattern, html, re.DOTALL):
        # href의 &amp; 등 HTML 엔티티를 여기서 바로 풀어야, 이후 상세페이지
        # 크롤링(fetch_event_detail)에 온전한 URL이 전달된다.
        href, text = htmllib.unescape(match.group(1)), normalize_text(match.group(2))
        if has_keyword(text) and len(text) > 10:
            full_url = href if href.startswith("http") else urljoin(source_url, href)
            items.append({"title": text, "url": full_url, "source": source_name})
    return items


def extract_ksga_events(html, source_name):
    """한국스마트그리드협회(ksga.org) '외부 행사안내' 게시판 전용 파서.

    이 게시판은 항목 링크가 <a href="javascript:;" onclick="pf_DetailMove('7841')">
    형태라 실제 href가 없고, 대신 JS로 폼을 만들어 /web/Board/{id}/detailView.do 로
    이동한다. 그 URL 패턴이 GET으로도 그대로 열리는 것을 확인했으므로, onclick에서
    게시글 번호만 추출해 상세페이지 URL을 직접 구성한다.
    """
    items = []
    pattern = r'<a[^>]*onclick="pf_DetailMove\(\'(\d+)\'\)"[^>]*>((?:(?!</a>).){5,200})</a>'
    for match in re.finditer(pattern, html, re.DOTALL):
        bn_id, text = match.group(1), normalize_text(match.group(2))
        if has_keyword(text) and len(text) > 10:
            url = f"https://ksga.org/web/Board/{bn_id}/detailView.do?pageIndex=1"
            items.append({"title": text, "url": url, "source": source_name})
    return items


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
        for raw_line in markdown.splitlines():
            line = normalize_text(raw_line)
            if not line:
                continue
            # 마크다운 링크: [텍스트](url) — normalize_text는 대괄호를 건드리지 않으므로
            # 정리된 line에 대해 그대로 매칭 가능
            m = re.search(r"\[([^\]]{10,100})\]\((https?://[^\)]+)\)", line)
            if m:
                text, link = m.group(1).strip(), m.group(2)
                if has_keyword(text):
                    items.append({"title": text, "url": link, "source": source_name})
            # 링크 없이 목록 텍스트만으로 항목을 만들면(과거 elif 분기) 표 형태로
            # 여러 줄에 걸쳐 잘린 문자열("| 6 | - [ESS 대전환..." 등)이 그대로
            # 제목이 되어버려 실제 페이지와 무관한 데이터가 들어갔다.
            # 개별 상세 링크를 확실히 잡은 항목만 신뢰할 수 있으므로 이 fallback은 두지 않는다.
        return items
    except Exception as e:
        print(f"  Firecrawl 예외 ({source_name}): {e}")
        return []


def fetch_event_detail(url):
    """상세 페이지에서 실제 제목·일시·장소·참가비·연사/프로그램을 추출한다.

    목록 페이지 텍스트만으로는 실제 개최일을 알 수 없어 크롤링 실행 시점의
    월로 잘못 분류되고(day도 항상 null) 캘린더에 반영되지 않는 문제가 있었다.
    실패 시 None을 반환해 호출부가 기존 placeholder를 그대로 쓰도록 한다.
    """
    if not FC_KEY or not url or not url.startswith("http"):
        return None
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
            return None
        md = r.json().get("data", {}).get("markdown", "")
        if not md:
            return None
    except Exception as e:
        print(f"  상세 페이지 크롤링 예외 ({url}): {e}")
        return None

    detail = {}

    # 제목: 첫 markdown 헤딩 또는 굵은 글씨 첫 줄
    m = re.search(r"^#{1,3}\s+(.{5,120})$", md, re.MULTILINE)
    if not m:
        m = re.search(r"\*\*(.{5,120})\*\*", md)
    if m:
        title = normalize_text(m.group(1))
        if len(title) > 8:
            detail["title"] = title

    # 날짜: YYYY-MM-DD 또는 YYYY.MM.DD (범위 포함)
    m = re.search(
        r"(\d{4})[.\-](\d{2})[.\-](\d{2})(?:\s*[~\-]\s*(\d{4})[.\-](\d{2})[.\-](\d{2}))?",
        md,
    )
    if m:
        y1, mo1, d1, y2, mo2, d2 = m.groups()
        start = f"{y1}.{mo1}.{d1}"
        if y2 and (y2, mo2, d2) != (y1, mo1, d1):
            if y2 == y1 and mo2 == mo1:
                end = d2
            elif y2 == y1:
                end = f"{mo2}.{d2}"
            else:
                end = f"{y2}.{mo2}.{d2}"
            detail["date"] = f"{start}~{end}"
        else:
            detail["date"] = start
        detail["day"] = int(d1)
        month_num = int(mo1)
        if 1 <= month_num <= 12:
            detail["month"] = month_num

    # 장소
    m = re.search(r"장소[\s:*|]*\n?\s*([^\n]{2,60})", md)
    if m:
        venue = normalize_text(m.group(1))
        if venue and "장소" not in venue:
            detail["venue"] = venue

    # 참가비
    m = re.search(r"참가(?:료|비)[\s:*|]*\n?\s*([^\n]{1,40})", md)
    if m:
        cost = normalize_text(m.group(1))
        if cost:
            detail["cost"] = cost

    # 연사/강사
    m = re.search(r"(?:연사|강사)[\s:*|]*\n?\s*([^\n]{2,120})", md)
    if m:
        speakers = normalize_text(m.group(1))
        if speakers:
            detail["speakers"] = speakers

    # 프로그램/교육내용
    m = re.search(r"(?:교육내용|커리큘럼|프로그램)[\s:*|]*\n((?:.{1,200}\n?){1,6})", md)
    if m:
        content = normalize_text(m.group(1))[:200]
        if content:
            detail["content"] = content

    # 일부 사이트(KIEI, ksga.org 등)는 연사·프로그램 정보를 텍스트가 아니라
    # 포스터 이미지로만 제공한다(파일 확장자 없는 동적 다운로드 URL도 있음).
    # 이 경우 텍스트 정규식으로는 절대 추출할 수 없으므로, 조용히 빈 값으로
    # 두는 대신 이미지로 제공된다는 사실을 명시해 원문 링크 확인을 유도한다.
    if "speakers" not in detail and "content" not in detail:
        img_urls = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
        content_images = [
            u for u in img_urls
            if not re.search(r"(logo|loading|/common/images/|/resources/img/)", u, re.IGNORECASE)
        ]
        if content_images:
            detail["content"] = "프로그램·연사 정보는 이미지로 제공되어 자동 추출 불가 — 원문 링크에서 확인"

    return detail or None


def add_to_html(item):
    try:
        html, sha = gh_get_file("index.html")
    except Exception as e:
        return False, str(e)

    now = datetime.now()
    today = now.strftime("%Y.%m.%d")
    item_url = clean_url(item.get("url", ""))
    source_name = item.get("source", "")
    src_text = f"{source_name} — 자동 수집 ({today})"

    # 상세 페이지에서 실제 개최월을 얻었으면 그 달에 배치한다.
    # (목록 페이지만 봐서는 실제 날짜를 몰라, 예전엔 크롤링 실행월에 무조건
    #  넣어버려 9월 세미나가 8월 탭에 들어가는 식의 오배치가 있었다.)
    month = item.get("month") or now.month
    date_str = item.get("date") or f"{now.year}.{month:02d} (크롤링 수집)"
    day_val = item.get("day")
    day_js = str(int(day_val)) if day_val else "null"
    venue = item.get("venue") or "미정"
    cost = item.get("cost") or "미정"
    speakers = item.get("speakers") or "미정"
    content = item.get("content") or ""

    new_entry = (
        f'  {{title:{esc(item.get("title", ""))},'
        f'status:"개최추정",'
        f'prio:"우선",'
        f'day:{day_js},'
        f'date:{esc(date_str)},'
        f'org:{esc(source_name)},'
        f'venue:{esc(venue)},'
        f'cost:{esc(cost)},'
        f'content:{esc(content)},'
        f'speakers:{esc(speakers)},'
        f'src:{esc(src_text)},'
        f'url:{esc_url(item_url)}}}'
    )

    d_var = f"D{month}"
    if f"const {d_var}=[" in html:
        pattern = rf"(const {d_var}=\[)([\s\S]*?)(\];)"

        def replacer(m):
            existing = m.group(2).rstrip()
            if existing.endswith(","):
                existing = existing[:-1]
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

    # 업데이트 날짜 갱신 (대시보드 상단에 실제 데이터 갱신일 표시)
    html = update_last_updated(html, today)

    ok = gh_put_file(
        "index.html",
        html,
        sha,
        f"[크롤러] {month}월 행사 추가: {item.get('title', '')[:30]}",
    )
    return ok, "" if ok else "GitHub 업데이트 실패"


def update_last_updated(html, today):
    if re.search(r'const LAST_UPDATED="[^"]*";', html):
        return re.sub(
            r'const LAST_UPDATED="[^"]*";',
            f'const LAST_UPDATED="{today}";',
            html,
        )
    # LAST_UPDATED 선언이 없으면 새로 추가 (하위 호환)
    return re.sub(
        r"(const DATA_MAP\s*=)",
        f'const LAST_UPDATED="{today}";\n\\1',
        html,
        count=1,
    )


def count_month_stats(html, month):
    """index.html의 D{month} 배열을 파싱해 현재 누적 현황 집계"""
    match = re.search(rf"const D{month}=\[([\s\S]*?)\];", html)
    if not match:
        return {"total": 0, "conf": 0, "plan": 0, "est": 0, "high": 0}
    body = match.group(1)
    statuses = re.findall(r'status:"([^"]*)"', body)
    prios = re.findall(r'prio:"([^"]*)"', body)
    return {
        "total": len(statuses),
        "conf": statuses.count("일정확정"),
        "plan": statuses.count("일정조율중"),
        "est": statuses.count("개최추정"),
        "high": prios.count("최우선"),
    }


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


SITES_REQUESTS = [
    ("기후에너지환경부", "https://www.mcee.go.kr/home/web/index.do?menuId=10598"),
    ("산업통상부",       "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c"),
    ("한국에너지공단",   "https://www.energy.or.kr/web/kem_home_new/notice.asp"),
    ("한국전력거래소",   "https://www.kpx.or.kr/board.es?mid=a10301000000&bid=0003"),
    ("한국전력공사",     "https://home.kepco.co.kr/kepco/PR/A/htmlView/PREAAHP00202.do"),
    ("세미나허브",       "https://seminarhub.co.kr/product/list.php?st=ing"),
]

SITES_FIRECRAWL = [
    ("에너지전환포럼",    "https://www.energytransitionkorea.org/event"),
    ("산업교육연구소",    "https://www.kiei.com/education/schedule?t=schedule_01"),
    ("국회도서관 세미나", "https://ampos.nanet.go.kr/seminarList.do"),
    ("KHARN",             "https://www.kharn.kr/news/section.html?sec_no=3"),
    ("전기신문",          "https://www.electimes.com/news/articleList.html?sc_section_code=S1N4"),
]

# ksga.org(한국스마트그리드협회)는 목록 링크가 JS onclick 기반이라
# 전용 파서(extract_ksga_events)로 별도 처리한다.
SITE_KSGA = ("한국스마트그리드협회", "https://ksga.org/web/notice/event_out.do")


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

    ksga_name, ksga_url = SITE_KSGA
    print(f"크롤링 중: {ksga_name}")
    ksga_html = crawl_with_requests(ksga_url)
    if ksga_html:
        ksga_items = extract_ksga_events(ksga_html, ksga_name)
        print(f"  {len(ksga_items)}개 항목 감지")
        all_items.extend(ksga_items)

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

    added = []
    for item in new_items:
        # 중복 방지 키는 상세 페이지 보강 전(원래 목록에서 긁은) 제목 기준으로
        # 고정해야 다음 주 재크롤링 시에도 같은 키가 나와 중복 등록을 막을 수 있다.
        dedup_key = item["title"][:50]
        if FC_KEY:
            detail = fetch_event_detail(item.get("url", ""))
            if detail:
                item.update(detail)
        ok, err = add_to_html(item)
        if ok:
            processed.add(dedup_key)
            added.append(item)
            print(f"  추가 완료: {item['title'][:40]}")
        else:
            print(f"  추가 실패: {err}")

    if added:
        save_processed(processed, proc_sha)

    # 최신 index.html 기준으로 이번 달 누적 현황 집계 (하드코딩 없이 실데이터 기반)
    now = datetime.now()
    html, _ = gh_get_file("index.html")
    stats = count_month_stats(html, now.month)

    week = (now.day - 1) // 7 + 1
    lines = [
        f"[에너지 세미나 주간 업데이트 | {now.month}월 {week}주차]",
        f"업데이트: {now.strftime('%Y.%m.%d')}",
        "",
        f"이번 달 누적 현황: 전체 {stats['total']}건 | "
        f"확정 {stats['conf']} | 조율중 {stats['plan']} | "
        f"추정 {stats['est']} | 최우선 {stats['high']}",
        "",
    ]
    if added:
        lines.append(f"-- 이번 주 신규 감지 행사 {len(added)}건 --")
        for i, item in enumerate(added[:5], 1):
            lines.append(f"{i}. {item['title'][:40]}")
            lines.append(f"   출처: {item['source']}")
            lines.append("")
        if len(added) > 5:
            lines.append(f"외 {len(added)-5}건 — 대시보드에서 확인")
            lines.append("")
    else:
        lines.append("-- 이번 주 신규 감지 행사 없음 --")
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
