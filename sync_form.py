"""
sync_form.py
구글 스프레드시트 폼 응답을 읽어 index.html에 새 행사를 추가합니다.
구글 Apps Script가 폼 제출 시 즉시 트리거합니다.

환경변수:
  SHEET_ID             구글 스프레드시트 ID
  GITHUB_TOKEN         GitHub Actions 자동 제공 토큰
  GITHUB_REPO          저장소 경로 (예: username/energy-seminar-tracker)
  TELEGRAM_TOKEN       텔레그램 봇 토큰
  TELEGRAM_CHANNEL_ID  발송 채널 ID
"""

import os
import re
import base64
import json
import requests
from datetime import datetime

SHEET_ID   = os.environ["SHEET_ID"]
GH_TOKEN   = os.environ["GITHUB_TOKEN"]
REPO           = os.environ["GITHUB_REPO"]
TG_TOKEN       = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHANNEL     = os.environ.get("TELEGRAM_CHANNEL_ID", "")
DASHBOARD_URL  = os.environ.get("DASHBOARD_URL", "https://energy-seminar.vercel.app")

SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/export?format=csv&gid=1415613594"
)
PROCESSED_FILE = "processed_rows.json"


# ── GitHub API ───────────────────────────────────────────────
def gh_get_file(path: str) -> tuple[str, str]:
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"})
    if r.status_code == 404:
        return "", ""
    r.raise_for_status()
    data = r.json()
    return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]

def gh_put_file(path: str, content: str, sha: str, message: str) -> bool:
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
    if r.status_code not in (200, 201):
        print(f"  GitHub 응답: {r.status_code} {r.text[:200]}")
    return r.status_code in (200, 201)


# ── 유틸 ─────────────────────────────────────────────────────
def parse_month_day(date_str: str) -> tuple:
    if not date_str or date_str.strip() in ("미정", "-", ""):
        return None, None
    # 형식 1: 2026.08.01
    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_str)
    if m:
        return int(m.group(2)), int(m.group(3))
    # 형식 2: 2026. 8. 1 (구글 스프레드시트 자동 변환 형식)
    m2 = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", date_str)
    if m2:
        return int(m2.group(2)), int(m2.group(3))
    # 형식 3: 2026.08 (일 없는 경우)
    m3 = re.search(r"(\d{4})\.(\d{1,2})", date_str)
    if m3:
        return int(m3.group(2)), None
    # 형식 4: 2026/08/01
    m4 = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_str)
    if m4:
        return int(m4.group(2)), int(m4.group(3))
    return None, None

def esc(s: str) -> str:
    return (s or "미정").replace('"', '\\"').strip()


# ── 스프레드시트 읽기 ────────────────────────────────────────
def fetch_rows() -> list[dict]:
    """
    구글폼 컬럼 순서:
    0: 타임스탬프 / 1: 행사명 / 2: 주관기관
    3: 날짜 / 4: 시간 / 5: 장소 / 6: 주요 참석자
    """
    r = requests.get(SHEET_CSV_URL)
    r.raise_for_status()
    # UTF-8 인코딩 명시
    r.encoding = "utf-8"
    lines = r.text.strip().splitlines()

    rows = []
    for i, line in enumerate(lines[1:], start=1):
        cols, current, in_quote = [], "", False
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif ch == "," and not in_quote:
                cols.append(current.strip())
                current = ""
            else:
                current += ch
        cols.append(current.strip())

        # 행사명(B열=index 1)이 비어있으면 건너뜀
        if len(cols) < 2 or not cols[1].strip():
            continue

        rows.append({
            "row_index": i,
            "title":    cols[1] if len(cols) > 1 else "",
            "org":      cols[2] if len(cols) > 2 else "미정",
            "date":     cols[3] if len(cols) > 3 else "미정",
            "time":     cols[4] if len(cols) > 4 else "미정",
            "venue":    cols[5] if len(cols) > 5 else "미정",
            "speakers": cols[6] if len(cols) > 6 else "미정",
        })
    return rows


# ── 처리 완료 행 관리 ────────────────────────────────────────
def load_processed() -> set:
    content, _ = gh_get_file(PROCESSED_FILE)
    if not content:
        return set()
    try:
        return set(json.loads(content))
    except Exception:
        return set()

def save_processed(processed: set, sha: str) -> None:
    content = json.dumps(sorted(processed))
    gh_put_file(PROCESSED_FILE, content, sha,
                "[봇] 처리 완료 행 업데이트")


# ── index.html에 행사 추가 ───────────────────────────────────
def add_event_to_html(row: dict) -> tuple[bool, str]:
    try:
        html, sha = gh_get_file("index.html")
    except Exception as e:
        return False, str(e)

    date_str = row.get("date", "미정")
    time_str = row.get("time", "미정")
    month, day = parse_month_day(date_str)
    if month is None:
        month = datetime.now().month

    blank = ("미정", "-", "")
    if date_str not in blank and time_str not in blank:
        display_date = f"{date_str} {time_str}"
    elif date_str not in blank:
        display_date = date_str
    else:
        display_date = f"{datetime.now().year}.{month:02d} (일정 미정)"

    day_val = str(day) if day else "null"
    today   = datetime.now().strftime("%Y.%m.%d")

    new_entry = (
        f'  {{title:"{esc(row["title"])}",'
        f'status:"일정확정",'
        f'prio:"우선",'
        f'day:{day_val},'
        f'date:"{esc(display_date)}",'
        f'org:"{esc(row["org"])}",'
        f'venue:"{esc(row["venue"])}",'
        f'cost:"미정",'
        f'content:"",'
        f'speakers:"{esc(row["speakers"])}",'
        f'src:"팀 직접 등록 ({today})",'
        f'url:""}}'
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
        html = html.replace("const DATA_MAP =",
                            new_array + "const DATA_MAP =")
        html = re.sub(
            r"(const DATA_MAP\s*=\s*\{)([^}]+)(\};)",
            lambda m: (
                f"{m.group(1)}{m.group(2)}, {month}: {d_var}{m.group(3)}"
            ),
            html,
        )

    ok = gh_put_file(
        "index.html", html, sha,
        f"[폼] {month}월 행사 추가: {row['title']}"
    )
    return ok, "" if ok else "GitHub 업데이트 실패"


# ── 텔레그램 알림 ────────────────────────────────────────────
def send_telegram(text: str) -> None:
    if not TG_TOKEN or not TG_CHANNEL:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHANNEL, "text": text},
        )
    except Exception as e:
        print(f"텔레그램 발송 실패: {e}")


# ── 메인 ─────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] 구글폼 응답 확인 시작")

    rows      = fetch_rows()
    processed = load_processed()
    _, proc_sha = gh_get_file(PROCESSED_FILE)

    new_rows = [r for r in rows if r["row_index"] not in processed]

    if not new_rows:
        print("새로운 응답 없음")
        return

    # 디버깅: 날짜 값 확인
    for r in new_rows:
        print(f"  날짜 원본값: [{r.get('date', '')}]")
        month, day = parse_month_day(r.get('date', ''))
        print(f"  파싱 결과: month={month}, day={day}")

    added = []
    for row in new_rows:
        if not row["title"]:
            continue
        print(f"처리 중: {row['title']}")
        ok, err = add_event_to_html(row)
        if ok:
            processed.add(row["row_index"])
            added.append(row)
            print(f"  완료: {row['title']}")
        else:
            print(f"  실패: {err}")

    if added:
        save_processed(processed, proc_sha)
        lines = [f"[행사 등록 알림] {len(added)}건 추가\n"]
        for r in added:
            lines.append(
                f"- {r['title']}\n"
                f"  일시: {r['date']} {r['time']}\n"
                f"  주관: {r['org']}"
            )
        dashboard = DASHBOARD_URL or f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[-1]}"
        lines.append(f"\n대시보드에서 확인하세요.\n{dashboard}")
        send_telegram("\n".join(lines))
        print(f"완료: {len(added)}건 추가")


if __name__ == "__main__":
    main()
