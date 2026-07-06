"""
seminar_data.py
세미나 데이터 보관 및 텔레그램 메시지 생성
매월 업데이트 시 SEMINARS 리스트만 수정하면 됩니다.
"""

from datetime import datetime

SEMINARS = [
    {
        "title":    "전력망 확충 국회토론회 (HVDC·에너지고속도로)",
        "status":   "일정확정",
        "priority": "최우선",
        "date":     "2026.06.10 (화) 13:30",
        "org":      "이언주 의원실 (더불어민주당)",
        "venue":    "국회의원회관 제1세미나실",
        "cost":     "무료",
        "speakers": [
            "이언주 의원 (더불어민주당)",
            "문양택 전력산업정책관 (기후에너지환경부)",
            "서성태 전력망정책과장 (기후에너지환경부)",
            "이성학 계통정책기획실장 (한국전력공사)",
        ],
        "source": "ampos.nanet.go.kr (2026.06 공지)",
    },
    {
        "title":    "태양광 RPS 고정가격계약 입찰 설명회 (마지막 RPS 입찰)",
        "status":   "일정조율중",
        "priority": "최우선",
        "date":     "2026.06 초~중순 (공고 예정)",
        "org":      "한국에너지공단 신재생에너지센터",
        "venue":    "온라인 또는 에너지공단 강당",
        "cost":     "무료",
        "speakers": [
            "최재관 이사장 (한국에너지공단)",
            "강부영 청정전력전환과장 (기후에너지환경부)",
        ],
        "source": "blog.haezoom.com (2026.05.27 보도)",
    },
    {
        "title":    "제1차 재생에너지 기본계획 후속 공청회",
        "status":   "일정조율중",
        "priority": "최우선",
        "date":     "2026.06 중순 (일정 TBD)",
        "org":      "기후에너지환경부 재생에너지정책관실",
        "venue":    "대한상공회의소 또는 정부세종청사",
        "cost":     "무료",
        "speakers": [
            "윤정원 재생에너지정책과장 (기후에너지환경부)",
            "박영진 분산에너지과장 (기후에너지환경부)",
            "최재관 이사장 (한국에너지공단)",
        ],
        "source": "mcee.go.kr (2026.05 에너지위원회 발표)",
    },
    {
        "title":    "배전망 연계형 ESS 구축지원사업 설명회 (1,171억 규모)",
        "status":   "일정조율중",
        "priority": "최우선",
        "date":     "2026.06 중순 (최종선정 前)",
        "org":      "한국에너지공단",
        "venue":    "에너지공단 또는 온라인",
        "cost":     "무료",
        "speakers": [
            "최재관 이사장 (한국에너지공단)",
            "박영진 분산에너지과장 (기후에너지환경부)",
        ],
        "source": "electimes.com (2026.03.20 보도)",
    },
    {
        "title":    "분산형 전력망 정례 정책 포럼",
        "status":   "일정조율중",
        "priority": "최우선",
        "date":     "2026.06 (격월 정례)",
        "org":      "기후에너지환경부 / 한국에너지공단",
        "venue":    "서울 (장소 추후 공지)",
        "cost":     "무료",
        "speakers": [
            "서성태 전력망정책과장 (기후에너지환경부)",
            "김성진 이사장 (한국전력거래소)",
            "최재관 이사장 (한국에너지공단)",
        ],
        "source": "electimes.com / mcee.go.kr (2026.03 기사)",
    },
    {
        "title":    "ESS 입찰시장·VPP 수익모델 전략 세미나 [미래기술교육연구원]",
        "status":   "일정조율중",
        "priority": "우선",
        "date":     "2026.06 중순 (일정 미정)",
        "org":      "한국미래기술교육연구원",
        "venue":    "서울 여의도 FKI타워 사파이어홀",
        "cost":     "유료 (40~70만원 추정)",
        "speakers": ["전력거래소 시장운영처 담당자 (연사 미확정)"],
        "source": "ekn.kr (과거 개최 패턴)",
    },
    {
        "title":    "전력시장·에너지 대응 전략 세미나 [세미나허브]",
        "status":   "일정조율중",
        "priority": "우선",
        "date":     "2026.06 둘째~셋째주 (미정)",
        "org":      "세미나허브",
        "venue":    "서울 여의도 FKI타워 컨퍼런스센터",
        "cost":     "유료 (40~60만원 추정)",
        "speakers": ["전력거래소 시장운영처 관계자 (연사 미확정)"],
        "source": "seminarhub.co.kr (과거 개최 패턴)",
    },
    {
        "title":    "RE100·직접PPA 실무 전략 세미나",
        "status":   "개최추정",
        "priority": "우선",
        "date":     "2026.06 하순 (추정)",
        "org":      "세미나허브 또는 한국미래기술교육연구원",
        "venue":    "서울 여의도 FKI타워",
        "cost":     "유료 (40~70만원 추정)",
        "speakers": ["기후에너지환경부 재생에너지 담당 과장 (연사 미확정)"],
        "source": "electimes.com (2026.04.28 RE100컨퍼런스 1차 기반 추정)",
    },
    {
        "title":    "전기차·충전인프라 구축 실무 세미나 [산업교육연구소]",
        "status":   "개최추정",
        "priority": "우선",
        "date":     "2026.06 (분기별 추정)",
        "org":      "산업교육연구소",
        "venue":    "서울 여의도 전경련회관",
        "cost":     "유료 (35~55만원 추정)",
        "speakers": [
            "박판규 탈탄소녹색수송혁신과장 (기후에너지환경부)",
            "전력거래소 V2G 담당자 (미확정)",
        ],
        "source": "kiet.co.kr (과거 개최 이력)",
    },
    {
        "title":    "전력거래소 전력시장 운영 제도 설명회",
        "status":   "개최추정",
        "priority": "참고용",
        "date":     "2026.06 (분기별 추정)",
        "org":      "전력거래소 (KPX)",
        "venue":    "전력거래소 나주 또는 서울 사무소",
        "cost":     "무료",
        "speakers": [
            "김성진 이사장 (한국전력거래소)",
            "시장운영처장 / 계통운영처 담당자",
        ],
        "source": "kpx.or.kr (분기별 설명회 패턴)",
    },
    {
        "title":    "한전 재생에너지 계통 접속 현황 설명회 (사업자 대상)",
        "status":   "개최추정",
        "priority": "최우선",
        "date":     "2026.06 (반기별 추정)",
        "org":      "한국전력공사 (KEPCO)",
        "venue":    "한전 본사(나주) 또는 서울 사무소",
        "cost":     "무료",
        "speakers": [
            "김동철 사장 (한국전력공사)",
            "이성학 계통정책기획실장 (한국전력공사)",
        ],
        "source": "kepco.co.kr / skenews.kr (2026.03.21 기사)",
    },
]


defbuild_message() -> str:
    now = datetime.now().strftime("%Y.%m.%d")
    total = len(SEMINARS)
    conf  = sum(1 for s in SEMINARS if s["status"] == "일정확정")
    plan  = sum(1 for s in SEMINARS if s["status"] == "일정조율중")
    est   = sum(1 for s in SEMINARS if s["status"] == "개최추정")
    high  = sum(1 for s in SEMINARS if s["priority"] == "최우선")
    free  = sum(1 for s in SEMINARS if s["cost"] == "무료")

    lines = [
        "📋 에너지·전력 세미나 주간 브리핑",
        f"업데이트: {now}",
        f"전체 {total}건  |  확정 {conf}  |  조율중 {plan}  |  추정 {est}",
        f"최우선 {high}건  |  무료 {free}건",
        "",
    ]

    STATUS_LABEL = {
        "일정확정":   "🔵 일정확정",
        "일정조율중": "🟡 일정조율중",
        "개최추정":   "⚪ 개최추정",
    }
    PRIO_LABEL = {
        "최우선": "최우선",
        "우선":   "우선",
        "참고용": "참고용",
    }

    for status in ["일정확정", "일정조율중", "개최추정"]:
        group = [s for s in SEMINARS if s["status"] == status]
        if not group:
            continue

        lines.append(f"{'━' * 20}")
        lines.append(f"{STATUS_LABEL[status]}  ({len(group)}건)")
        lines.append("")

        for i, s in enumerate(group, 1):
            prio = PRIO_LABEL[s["priority"]]
            lines.append(f"{i}. [{prio}] {s['title']}")
            lines.append(f"   일시 | {s['date']}")
            lines.append(f"   주관 | {s['org']}")
            lines.append(f"   장소 | {s['venue']}")
            lines.append(f"   비용 | {s['cost']}")
            lines.append(f"   연사 | {s['speakers'][0]}")
            lines.append(f"   출처 | {s['source']}")
            lines.append("")

    lines += [
        f"{'━' * 20}",
        "개최추정 행사는 반드시 직접 확인 후 참석 결정하세요.",
        "모니터링: energy.or.kr / mcee.go.kr / kpx.or.kr / ampos.nanet.go.kr",
    ]
    return "\n".join(lines)
