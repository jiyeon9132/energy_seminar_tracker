"""
bot.py
텔레그램 봇 서버 — Railway / Render 24시간 실행용

기능:
  /일정    → 양식 한 번에 보여주고 복사해서 채워 보내기
  /목록    → 이번 달 등록 행사 조회
  /도움말  → 사용법 안내

환경변수:
  TELEGRAM_TOKEN      BotFather 봇 토큰
  GITHUB_TOKEN        GitHub Personal Access Token
  GITHUB_REPO         저장소 경로 (예: username/energy-seminar-tracker)
  ALLOWED_USERS       허용 텔레그램 user_id 쉼표 구분 (비워두면 전체 허용)
"""

import os
import re
import base64
import logging
from datetime import datetime

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN       = os.environ["TELEGRAM_TOKEN"]
REPO        = os.environ["GITHUB_REPO"]
GH_TOKEN    = os.environ["GITHUB_TOKEN"]
ALLOWED_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED     = set(x.strip() for x in ALLOWED_RAW.split(",") if x.strip())

TEMPLATE = """\
행사명: 
주관: 
날짜: 
시간: 
장소: 
참석자: """

def is_allowed(user_id: int) -> bool:
    return not ALLOWED or str(user_id) in ALLOWED

# ── GitHub API ───────────────────────────────────────────────
def gh_get_file(path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers={"Authorization": f"token {GH_TOKEN}"})
    r.raise_for_status()
    data = r.json()
    return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]

def gh_put_file(path, content, sha, message):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    r = requests.put(
        url,
        json={"message": message, "content": encoded, "sha": sha},
        headers={"Authorization": f"token {GH_TOKEN}"},
    )
    return r.status_code in (200, 201)

# ── 양식 파싱 ────────────────────────────────────────────────
def parse_form(text: str) -> dict | None:
    """
    행사명: ...
    주관: ...
    날짜: ...
    시간: ...
    장소: ...
    참석자: ...
    """
    fields = {}
    for line in text.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()

    required = ["행사명", "주관", "날짜", "시간", "장소", "참석자"]
    if not all(k in fields for k in required):
        return None
    if not fields.get("행사명"):
        return None
    return fields

def parse_month_day(date_str: str):
    if not date_str or date_str in ("미정", "-", ""):
        return None, None
    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_str)
    if m:
        return int(m.group(2)), int(m.group(3))
    m2 = re.search(r"(\d{4})\.(\d{1,2})", date_str)
    if m2:
        return int(m2.group(2)), None
    return None, None

# ── index.html 행사 추가 ─────────────────────────────────────
def add_event_to_html(fields: dict) -> tuple[bool, str]:
    try:
        html, sha = gh_get_file("index.html")
    except Exception as e:
        return False, f"GitHub 파일 읽기 실패: {e}"

    date_str = fields.get("날짜", "미정")
    time_str = fields.get("시간", "미정")
    month, day = parse_month_day(date_str)
    if month is None:
        month = datetime.now().month

    if date_str not in ("미정", "-", "") and time_str not in ("미정", "-", ""):
        display_date = f"{date_str} {time_str}"
    elif date_str not in ("미정", "-", ""):
        display_date = date_str
    else:
        display_date = f"{datetime.now().year}.{month:02d} (일정 미정)"

    day_val = str(day) if day else "null"
    today   = datetime.now().strftime("%Y.%m.%d")

    def esc(s):
        return (s or "미정").replace('"', '\\"')

    new_entry = (
        f'  {{title:"{esc(fields["행사명"])}",'
        f'status:"일정확정",'
        f'prio:"우선",'
        f'day:{day_val},'
        f'date:"{esc(display_date)}",'
        f'org:"{esc(fields["주관"])}",'
        f'venue:"{esc(fields["장소"])}",'
        f'cost:"미정",'
        f'content:"",'
        f'speakers:"{esc(fields["참석자"])}",'
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
        html = html.replace("const DATA_MAP =", new_array + "const DATA_MAP =")
        html = re.sub(
            r"(const DATA_MAP\s*=\s*\{)([^}]+)(\};)",
            lambda m: f"{m.group(1)}{m.group(2)}, {month}: {d_var}{m.group(3)}",
            html,
        )

    ok = gh_put_file(
        "index.html", html, sha,
        f"[봇] {month}월 행사 추가: {fields['행사명']}"
    )
    return ok, "" if ok else "GitHub 파일 업데이트 실패"

def format_preview(fields: dict) -> str:
    return (
        f"아래 내용으로 등록할까요?\n\n"
        f"행사명: {fields['행사명']}\n"
        f"주관:   {fields['주관']}\n"
        f"날짜:   {fields['날짜']}\n"
        f"시간:   {fields['시간']}\n"
        f"장소:   {fields['장소']}\n"
        f"참석자: {fields['참석자']}"
    )

# ── /일정 ────────────────────────────────────────────────────
async def cmd_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("권한이 없습니다.")
        return

    await update.message.reply_text(
        "아래 양식을 복사해서 내용을 채워 보내주세요.\n"
        "미정인 항목은 그대로 비워두거나 '미정'으로 입력하세요.\n\n"
        f"{TEMPLATE}"
    )

# ── 양식 응답 수신 ───────────────────────────────────────────
async def receive_form(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # 양식 형식인지 확인 (행사명: 포함 여부)
    if "행사명:" not in text:
        return  # 일반 메시지는 무시

    fields = parse_form(text)
    if not fields:
        await update.message.reply_text(
            "양식이 올바르지 않습니다.\n"
            "/일정 을 다시 입력해 양식을 받아주세요."
        )
        return

    ctx.user_data["pending"] = fields
    keyboard = [[
        InlineKeyboardButton("등록",    callback_data="confirm"),
        InlineKeyboardButton("다시 입력", callback_data="retry"),
        InlineKeyboardButton("취소",    callback_data="cancel"),
    ]]
    await update.message.reply_text(
        format_preview(fields),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ── 버튼 콜백 ────────────────────────────────────────────────
async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        ctx.user_data.clear()
        await query.edit_message_text("등록을 취소했습니다.")
        return

    if query.data == "retry":
        ctx.user_data.clear()
        await query.edit_message_text(
            f"양식을 다시 복사해서 채워 보내주세요.\n\n{TEMPLATE}"
        )
        return

    fields = ctx.user_data.get("pending")
    if not fields:
        await query.edit_message_text("등록 정보가 없습니다. /일정 을 다시 입력해 주세요.")
        return

    await query.edit_message_text("대시보드에 반영 중...")
    ok, err = add_event_to_html(fields)

    if ok:
        await query.edit_message_text(
            f"등록 완료\n\n"
            f"행사명: {fields['행사명']}\n"
            f"날짜:   {fields['날짜']}\n\n"
            f"대시보드에서 확인하세요."
        )
    else:
        await query.edit_message_text(
            f"등록 실패: {err}\n잠시 후 /일정 으로 다시 시도해 주세요."
        )
    ctx.user_data.clear()

# ── /목록 ────────────────────────────────────────────────────
async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("권한이 없습니다.")
        return
    try:
        html, _ = gh_get_file("index.html")
    except Exception:
        await update.message.reply_text("데이터를 불러올 수 없습니다.")
        return

    m     = datetime.now().month
    match = re.search(rf"const D{m}=\[([\s\S]*?)\];", html)
    if not match:
        await update.message.reply_text(f"{m}월 등록된 행사가 없습니다.")
        return

    titles = re.findall(r'title:"([^"]+)"', match.group(1))
    dates  = re.findall(r'date:"([^"]+)"',  match.group(1))

    if not titles:
        await update.message.reply_text(f"{m}월 등록된 행사가 없습니다.")
        return

    lines = [f"[{m}월 행사 목록] {len(titles)}건\n"]
    for i, (t, d) in enumerate(zip(titles, dates), 1):
        lines.append(f"{i}. {t}\n   {d}")
    await update.message.reply_text("\n".join(lines))

# ── /도움말 ──────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "[에너지 세미나 봇 사용법]\n\n"
        "/일정\n"
        "  양식을 보내드립니다. 복사해서 내용을 채워 보내주세요.\n"
        "  미정인 항목은 비워두거나 '미정' 입력.\n\n"
        "/목록\n"
        "  이번 달 등록된 행사 조회\n\n"
        "/도움말\n"
        "  이 메시지"
    )

# ── 메인 ────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("일정",   cmd_schedule))
    app.add_handler(CommandHandler("목록",   cmd_list))
    app.add_handler(CommandHandler("도움말", cmd_help))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_form))
    logger.info("봇 시작")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
