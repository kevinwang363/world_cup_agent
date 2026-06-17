import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests
from langchain_core.tools import tool

DATA_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
BEIJING_TZ = timezone(timedelta(hours=8))
TEAM_ALIASES = {
    "葡萄牙": "Portugal",
    "刚果民主共和国": "DR Congo",
    "刚果金": "DR Congo",
    "刚果": "DR Congo",
    "乌兹别克斯坦": "Uzbekistan",
    "哥伦比亚": "Colombia",
    "英格兰": "England",
    "克罗地亚": "Croatia",
    "加纳": "Ghana",
    "巴拿马": "Panama",
    "墨西哥": "Mexico",
    "韩国": "South Korea",
    "南非": "South Africa",
    "加拿大": "Canada",
    "卡塔尔": "Qatar",
    "瑞士": "Switzerland",
    "巴西": "Brazil",
    "摩洛哥": "Morocco",
    "阿根廷": "Argentina",
    "法国": "France",
    "德国": "Germany",
    "西班牙": "Spain",
    "塞内加尔": "Senegal",
    "挪威": "Norway",
    "伊拉克": "Iraq",
    "阿尔及利亚": "Algeria",
    "奥地利": "Austria",
    "约旦": "Jordan",
    "佛得角": "Cape Verde",
    "沙特": "Saudi Arabia",
    "沙特阿拉伯": "Saudi Arabia",
    "乌拉圭": "Uruguay",
    "日本": "Japan",
    "荷兰": "Netherlands",
    "比利时": "Belgium",
    "意大利": "Italy",
    "美国": "USA",
    "澳大利亚": "Australia",
}


def _today_label() -> str:
    return _now_beijing().strftime("%Y-%m-%d")


def _now_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


def _load_worldcup_data() -> Dict[str, Any]:
    response = requests.get(DATA_URL, timeout=20)
    response.raise_for_status()
    return response.json()


def _match_id(match: Dict[str, Any]) -> str:
    team1 = match.get("team1", "").lower().replace(" ", "-")
    team2 = match.get("team2", "").lower().replace(" ", "-")
    return f"{match.get('date')}-{team1}-vs-{team2}"


def _kickoff_beijing(match: Dict[str, Any]) -> datetime:
    match_time = match.get("time", "00:00 UTC+0")
    match_time_pattern = re.match(r"(\d{1,2}):(\d{2}) UTC([+-]\d+)", match_time)
    if not match_time_pattern:
        local_time = datetime.strptime(f"{match['date']} 00:00", "%Y-%m-%d %H:%M")
        return local_time.replace(tzinfo=timezone.utc).astimezone(BEIJING_TZ)

    hour = int(match_time_pattern.group(1))
    minute = int(match_time_pattern.group(2))
    offset_hours = int(match_time_pattern.group(3))
    local_tz = timezone(timedelta(hours=offset_hours))
    local_time = datetime.strptime(f"{match['date']} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
    return local_time.replace(tzinfo=local_tz).astimezone(BEIJING_TZ)


def _normalize(text: str) -> str:
    return "".join(char.lower() for char in text if char.isalnum())


def _extract_teams_from_query(query: str) -> List[str]:
    teams: List[str] = []
    for local_name, english_name in sorted(TEAM_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if local_name in query and english_name not in teams:
            teams.append(english_name)

    normalized_query = _normalize(query)
    for english_name in TEAM_ALIASES.values():
        if _normalize(english_name) in normalized_query and english_name not in teams:
            teams.append(english_name)
    return teams


def _query_variants(query: str) -> List[str]:
    expanded = query
    for local_name, english_name in TEAM_ALIASES.items():
        expanded = expanded.replace(local_name, f" {english_name} ")

    variants = [query]
    if expanded != query:
        variants.append(expanded)
    for team in _extract_teams_from_query(query):
        variants.append(team)
    return variants


def _query_terms(query: str) -> List[str]:
    terms = []
    for team in _extract_teams_from_query(query):
        terms.append(_normalize(team))
    for term in query.split():
        normalized = _normalize(term)
        if normalized and any(char.isascii() and char.isalnum() for char in normalized):
            terms.append(normalized)
    return terms


def _matches_for_team(matches: List[Dict[str, Any]], team: str) -> List[Dict[str, Any]]:
    normalized_team = _normalize(team)
    found = [
        _format_match(match)
        for match in matches
        if normalized_team in (_normalize(match.get("team1", "")), _normalize(match.get("team2", "")))
    ]
    return sorted(found, key=lambda match: match["kickoff_beijing"])


def _format_match(match: Dict[str, Any]) -> Dict[str, Any]:
    formatted = dict(match)
    kickoff_beijing = _kickoff_beijing(match)
    formatted["match_id"] = _match_id(match)
    formatted["status"] = "finished" if "score" in match else "scheduled"
    formatted["source_date"] = match.get("date")
    formatted["kickoff_beijing"] = kickoff_beijing.isoformat(timespec="minutes")
    formatted["beijing_date"] = kickoff_beijing.strftime("%Y-%m-%d")
    formatted["beijing_time"] = kickoff_beijing.strftime("%H:%M")
    return formatted


def _matches_for_date(matches: List[Dict[str, Any]], date: str) -> List[Dict[str, Any]]:
    target_date = _today_label() if date == "today" else date
    matched = [
        _format_match(match)
        for match in matches
        if _kickoff_beijing(match).strftime("%Y-%m-%d") == target_date
    ]
    return sorted(matched, key=lambda match: match["kickoff_beijing"])


def _matches_for_source_date(matches: List[Dict[str, Any]], date: str) -> List[Dict[str, Any]]:
    matched = [_format_match(match) for match in matches if match.get("date") == date]
    return sorted(matched, key=lambda match: match["kickoff_beijing"])


def _available_source_dates(matches: List[Dict[str, Any]]) -> List[str]:
    return sorted({match["date"] for match in matches})


def _source_date_has_started(matches: List[Dict[str, Any]], date: str, now_bj: datetime) -> bool:
    return any(
        _kickoff_beijing(match) <= now_bj for match in matches if match.get("date") == date
    )


def _source_date_is_upcoming(matches: List[Dict[str, Any]], date: str, now_bj: datetime) -> bool:
    return any(
        _kickoff_beijing(match) > now_bj for match in matches if match.get("date") == date
    )


def _rolling_daily_matches(matches: List[Dict[str, Any]], now_bj: datetime) -> Dict[str, Any]:
    source_dates = _available_source_dates(matches)
    review_date = None
    preview_date = None

    for source_date in source_dates:
        if _source_date_has_started(matches, source_date, now_bj):
            review_date = source_date
        if preview_date is None and _source_date_is_upcoming(matches, source_date, now_bj):
            preview_date = source_date

    review_matches = _matches_for_source_date(matches, review_date) if review_date else []
    preview_matches = _matches_for_source_date(matches, preview_date) if preview_date else []
    return {
        "review_source_date": review_date,
        "preview_source_date": preview_date,
        "review_matches": review_matches,
        "preview_matches": preview_matches,
    }


def _total_goals(matches: List[Dict[str, Any]]) -> int:
    return sum(sum(match.get("score", {}).get("ft", [0, 0])) for match in matches)


def _find_matches(matches: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    teams = _extract_teams_from_query(query)
    if len(teams) == 1:
        return _matches_for_team(matches, teams[0])

    variants = _query_variants(query)
    found = []
    for match in matches:
        haystack = _normalize(
            " ".join(
                [
                    _match_id(match),
                    match.get("date", ""),
                    match.get("team1", ""),
                    match.get("team2", ""),
                    match.get("group", ""),
                    match.get("ground", ""),
                ]
            )
        )
        for variant in variants:
            normalized_query = _normalize(variant)
            query_terms = _query_terms(variant)
            if normalized_query in haystack or (
                query_terms and all(term in haystack for term in query_terms)
            ):
                found.append(_format_match(match))
                break
    return found


def _team_summary(matches: List[Dict[str, Any]], team: str) -> Dict[str, Any]:
    played = []
    scheduled = []
    goals_for = 0
    goals_against = 0
    normalized_team = _normalize(team)

    for match in matches:
        team1 = match.get("team1", "")
        team2 = match.get("team2", "")
        if normalized_team not in (_normalize(team1), _normalize(team2)):
            continue

        formatted = _format_match(match)
        if "score" not in match:
            scheduled.append(formatted)
            continue

        score = match["score"]["ft"]
        is_team1 = _normalize(team1) == normalized_team
        team_goals = score[0] if is_team1 else score[1]
        opponent_goals = score[1] if is_team1 else score[0]
        goals_for += team_goals
        goals_against += opponent_goals
        played.append(formatted)

    return {
        "team": team,
        "played_count": len(played),
        "scheduled_count": len(scheduled),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "played_matches": played[-5:],
        "upcoming_matches": scheduled[:3],
    }


@tool
def get_fixtures(date: str = "today") -> str:
    """Get structured 2026 World Cup fixtures and scores for a date, for example 'today' or '2026-06-17'."""
    return get_daily_report.invoke({"date": date})


@tool
def get_daily_report(date: str = "today") -> str:
    """Get 2026 World Cup daily report data in Beijing time: previous matchday review plus next matchday preview."""
    now_bj = _now_beijing()
    target_date = now_bj.strftime("%Y-%m-%d") if date == "today" else date
    try:
        data = _load_worldcup_data()
        all_matches = data["matches"]

        if date == "today":
            daily_matches = _rolling_daily_matches(all_matches, now_bj)
            review_matches = daily_matches["review_matches"]
            preview_matches = daily_matches["preview_matches"]
            matches = review_matches + [
                match
                for match in preview_matches
                if match["match_id"] not in {review["match_id"] for review in review_matches}
            ]
            report_mode = "rolling_beijing_daily_report"
            source_dates = {
                "review_source_date": daily_matches["review_source_date"],
                "preview_source_date": daily_matches["preview_source_date"],
            }
        else:
            matches = _matches_for_date(all_matches, target_date)
            review_matches = [
                match
                for match in matches
                if match["status"] == "finished"
                or datetime.fromisoformat(match["kickoff_beijing"]) <= now_bj
            ]
            preview_matches = [
                match
                for match in matches
                if datetime.fromisoformat(match["kickoff_beijing"]) > now_bj
            ]
            report_mode = "beijing_date_report"
            source_dates = {"beijing_date": target_date}

        finished = [match for match in review_matches if match["status"] == "finished"]
        missing_results = [
            match for match in review_matches if match["status"] != "finished"
        ]

        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": now_bj.isoformat(timespec="seconds"),
                "timezone": "Asia/Shanghai",
                "report_mode": report_mode,
                "beijing_report_date": target_date,
                "source_dates": source_dates,
                "competition": data.get("name", "World Cup 2026"),
                "summary": {
                    "review_match_count": len(review_matches),
                    "finished_review_count": len(finished),
                    "missing_result_count": len(missing_results),
                    "preview_match_count": len(preview_matches),
                    "total_goals": _total_goals(finished),
                },
                "review_matches": review_matches,
                "preview_matches": preview_matches,
                "matches": matches,
                "daily_report_guidance": [
                    "Use review_matches for the previous matchday recap.",
                    "Use preview_matches for the next matchday outlook.",
                    "All displayed times should use beijing_time/kickoff_beijing.",
                    "If a review match has no score, state that the structured data source has not published the result yet.",
                ],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": now_bj.isoformat(timespec="seconds"),
                "timezone": "Asia/Shanghai",
                "date": target_date,
                "matches": [],
                "error": f"Daily report data failed: {exc}",
            },
            ensure_ascii=False,
        )


@tool
def get_match_result(match_id: str) -> str:
    """Get a structured 2026 World Cup match by match_id or by team/date query."""
    return get_match_analysis.invoke({"match_query": match_id})


@tool
def get_team_profile(team_name: str) -> str:
    """Get all 2026 World Cup matches, latest result, and upcoming fixtures for a team. Supports Chinese or English team names."""
    try:
        data = _load_worldcup_data()
        matches = data["matches"]
        teams = _extract_teams_from_query(team_name)
        if not teams:
            teams = [team_name]

        team = teams[0]
        team_matches = _matches_for_team(matches, team)
        if not team_matches:
            return json.dumps(
                {
                    "source": "openfootball_worldcup_2026",
                    "source_url": DATA_URL,
                    "fetched_at": _now_beijing().isoformat(timespec="seconds"),
                    "query": team_name,
                    "team": team,
                    "matches": [],
                    "error": f"No World Cup 2026 matches found for team: {team_name}",
                },
                ensure_ascii=False,
            )

        played = [match for match in team_matches if match["status"] == "finished"]
        upcoming = [match for match in team_matches if match["status"] == "scheduled"]
        latest_match = played[-1] if played else (upcoming[0] if upcoming else team_matches[-1])

        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": _now_beijing().isoformat(timespec="seconds"),
                "timezone": "Asia/Shanghai",
                "query": team_name,
                "team": team,
                "summary": _team_summary(matches, team),
                "latest_match": latest_match,
                "played_matches": played,
                "upcoming_matches": upcoming,
                "all_matches": team_matches,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": _now_beijing().isoformat(timespec="seconds"),
                "query": team_name,
                "error": f"Team profile failed: {exc}",
            },
            ensure_ascii=False,
        )


@tool
def get_match_analysis(match_query: str) -> str:
    """Get structured data for one 2026 World Cup match analysis, including score, goals, team form, and venue."""
    try:
        data = _load_worldcup_data()
        matches = data["matches"]
        found = _find_matches(matches, match_query)
        if not found:
            return json.dumps(
                {
                    "source": "openfootball_worldcup_2026",
                    "source_url": DATA_URL,
                    "fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "query": match_query,
                    "matches": [],
                    "error": "No matching World Cup 2026 match found.",
                },
                ensure_ascii=False,
            )

        if len(found) == 1:
            match = found[0]
            payload = {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": _now_beijing().isoformat(timespec="seconds"),
                "query": match_query,
                "match": match,
                "team1_context": _team_summary(matches, match["team1"]),
                "team2_context": _team_summary(matches, match["team2"]),
                "analysis_note": "This tool provides structured fixture/result context. For tactical news, injuries, or lineups, also call search_web.",
            }
        else:
            teams = _extract_teams_from_query(match_query)
            team = teams[0] if teams else match_query
            played = [match for match in found if match["status"] == "finished"]
            upcoming = [match for match in found if match["status"] == "scheduled"]
            payload = {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": _now_beijing().isoformat(timespec="seconds"),
                "query": match_query,
                "team": team,
                "summary": _team_summary(matches, team),
                "latest_match": played[-1] if played else (upcoming[0] if upcoming else found[-1]),
                "played_matches": played,
                "upcoming_matches": upcoming,
                "analysis_note": "Multiple matches matched this query. Use latest_match for the most recent result.",
            }

        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "query": match_query,
                "error": f"Match analysis data failed: {exc}",
            },
            ensure_ascii=False,
        )


@tool
def get_prediction_context(match_query: str) -> str:
    """Get structured context for a 2026 World Cup match prediction. Use search_web too for injuries and latest news."""
    try:
        data = _load_worldcup_data()
        matches = data["matches"]
        found = _find_matches(matches, match_query)
        if not found:
            return json.dumps(
                {
                    "source": "openfootball_worldcup_2026",
                    "source_url": DATA_URL,
                    "fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "query": match_query,
                    "matches": [],
                    "error": "No matching World Cup 2026 match found for prediction.",
                },
                ensure_ascii=False,
            )

        match = found[0]
        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "query": match_query,
                "match": match,
                "team1_context": _team_summary(matches, match["team1"]),
                "team2_context": _team_summary(matches, match["team2"]),
                "prediction_rules": [
                    "Use tournament form from structured data when available.",
                    "Use search_web for latest injuries, lineup news, and coach comments.",
                    "Return a low/medium/high confidence level.",
                    "Always include uncertainty and do not present as betting advice.",
                ],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "source": "openfootball_worldcup_2026",
                "source_url": DATA_URL,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "query": match_query,
                "error": f"Prediction context failed: {exc}",
            },
            ensure_ascii=False,
        )
