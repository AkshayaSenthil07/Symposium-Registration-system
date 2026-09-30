"""Judges' scores, results publication, leaderboard, certificates and verification codes."""
from flask import current_app

from webapp import db
from webapp.security import sign
from webapp.services import audit


def published_winners() -> list[dict]:
    return db.get().all(
        "SELECT er.event_id, er.position, e.event_name, e.event_date, u.full_name, r.team_name, c.college_name "
        "FROM event_result er JOIN event e ON e.event_id = er.event_id "
        "JOIN registration r ON r.reg_id = er.reg_id JOIN app_user u ON u.user_id = r.user_id "
        "LEFT JOIN participant_profile pp ON pp.user_id = u.user_id "
        "LEFT JOIN college c ON c.college_id = pp.college_id "
        "WHERE e.results_published ORDER BY e.event_date, e.event_name, er.position")


def college_leaderboard() -> list[dict]:
    return db.get().all("SELECT * FROM v_college_leaderboard WHERE points > 0 OR registrations > 0 "
                        "ORDER BY points DESC, gold DESC, registrations DESC LIMIT 15")


# ------------------------------------------------------------------ scoring
def score_board(event_id: int) -> list[dict]:
    return db.get().all("SELECT sb.*, er.position FROM v_score_board sb "
                        "LEFT JOIN event_result er ON er.reg_id = sb.reg_id "
                        "WHERE sb.event_id = %s ORDER BY sb.avg_score IS NULL, sb.avg_score DESC, sb.full_name",
                        (event_id,))


def my_scores(event_id: int, judge_id: int) -> dict:
    rows = db.get().all("SELECT js.reg_id, js.score, js.remarks FROM judge_score js "
                        "JOIN registration r ON r.reg_id = js.reg_id WHERE r.event_id = %s AND js.judge_id = %s",
                        (event_id, judge_id))
    return {r["reg_id"]: r for r in rows}


def save_scores(event_id: int, judge_id: int, scores: dict) -> int:
    """scores: {reg_id: (score or None, remarks)}. Only attended, confirmed registrations are scored."""
    saved = 0
    with db.get().transaction() as cur:
        cur.execute("SELECT reg_id FROM registration WHERE event_id = %s AND status = 'CONFIRMED' AND attended",
                    (event_id,))
        allowed = {r["reg_id"] for r in cur.fetchall()}
        for reg_id, (score, remarks) in scores.items():
            if reg_id not in allowed:
                continue
            if score is None:
                cur.execute("DELETE FROM judge_score WHERE reg_id = %s AND judge_id = %s", (reg_id, judge_id))
                continue
            cur.execute("INSERT INTO judge_score (reg_id, judge_id, score, remarks) VALUES (%s, %s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE score = VALUES(score), remarks = VALUES(remarks)",
                        (reg_id, judge_id, score, remarks or None))
            saved += 1
        audit.log(judge_id, "SCORES_SAVED", f"Event #{event_id}: {saved} score(s)", cur=cur)
    return saved


def set_winners(event_id: int, positions: dict, actor_id: int) -> None:
    """positions: {1: reg_id, 2: reg_id, 3: reg_id} (missing = not awarded)."""
    regs = [r for r in positions.values() if r]
    if len(regs) != len(set(regs)):
        raise db.DatabaseError("The same participant cannot win two positions.")
    with db.get().transaction() as cur:
        for reg_id in regs:
            cur.execute("SELECT 1 FROM registration WHERE reg_id = %s AND event_id = %s AND status = 'CONFIRMED' "
                        "AND attended", (reg_id, event_id))
            if not cur.fetchone():
                raise db.DatabaseError("Only confirmed participants who attended can win.")
        cur.execute("DELETE FROM event_result WHERE event_id = %s", (event_id,))
        for pos, reg_id in positions.items():
            if reg_id:
                cur.execute("INSERT INTO event_result (event_id, position, reg_id) VALUES (%s, %s, %s)",
                            (event_id, pos, reg_id))
        audit.log(actor_id, "RESULTS_SET", f"Event #{event_id}: {len(regs)} winner(s)", cur=cur)


def auto_rank(event_id: int) -> dict:
    """Top three by average judge score (ties broken by earlier registration)."""
    rows = db.get().all("SELECT sb.reg_id FROM v_score_board sb JOIN registration r ON r.reg_id = sb.reg_id "
                        "WHERE sb.event_id = %s AND sb.avg_score IS NOT NULL "
                        "ORDER BY sb.avg_score DESC, r.registered_at LIMIT 3", (event_id,))
    return {i + 1: r["reg_id"] for i, r in enumerate(rows)}


def publish(event_id: int, published: bool, actor_id: int) -> None:
    db.get().run("UPDATE event SET results_published = %s, status = IF(%s, 'COMPLETED', status) "
                 "WHERE event_id = %s", (published, published, event_id))
    audit.log(actor_id, "RESULTS_PUBLISHED" if published else "RESULTS_HIDDEN", f"Event #{event_id}")


# ------------------------------------------------------------------ certificates
def certificate_code(reg_id: int) -> str:
    secret = current_app.config["SECRET_KEY"]
    return f"{reg_id}-{sign(f'cert:{reg_id}', secret)[:10].upper()}"


def certificate_lookup(code: str) -> dict | None:
    try:
        reg_part, _sig = code.split("-", 1)
        reg_id = int(reg_part)
    except ValueError:
        return None
    if certificate_code(reg_id) != code.upper():
        return None
    row = db.get().one("SELECT * FROM v_registration_details WHERE reg_id = %s AND status = 'CONFIRMED' "
                       "AND attended", (reg_id,))
    if row and row["result_position"] and not row["results_published"]:
        row["result_position"] = None
    return row
