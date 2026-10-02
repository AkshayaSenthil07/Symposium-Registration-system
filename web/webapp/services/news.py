"""Flash news shown in the rolling banner on the public pages."""
from webapp import db
from webapp.services import audit


def active_ticker() -> list[dict]:
    return db.get().all(
        "SELECT news_id, message, link_url, priority FROM news_item "
        "WHERE is_active AND starts_at <= NOW() AND (ends_at IS NULL OR ends_at > NOW()) "
        "ORDER BY FIELD(priority, 'URGENT', 'IMPORTANT', 'INFO'), starts_at DESC LIMIT 12")


def all_items() -> list[dict]:
    return db.get().all(
        "SELECT n.*, u.full_name AS author, (n.is_active AND n.starts_at <= NOW() AND "
        "(n.ends_at IS NULL OR n.ends_at > NOW())) AS is_live FROM news_item n "
        "LEFT JOIN app_user u ON u.user_id = n.created_by ORDER BY n.news_id DESC")


def get(news_id: int) -> dict | None:
    return db.get().one("SELECT * FROM news_item WHERE news_id = %s", (news_id,))


def save(data: dict, actor_id: int, news_id: int | None = None, cur=None) -> int:
    fields = ("message", "link_url", "priority", "starts_at", "ends_at", "is_active")
    values = tuple(data.get(f) for f in fields)

    def work(c):
        if news_id is None:
            c.execute(f"INSERT INTO news_item ({', '.join(fields)}, created_by) "
                      f"VALUES ({', '.join(['%s'] * len(fields))}, %s)", values + (actor_id,))
            nid = c.lastrowid
            audit.log(actor_id, "NEWS_POSTED", data["message"][:200], cur=c)
            return nid
        c.execute(f"UPDATE news_item SET {', '.join(f + ' = %s' for f in fields)} WHERE news_id = %s",
                  values + (news_id,))
        audit.log(actor_id, "NEWS_UPDATED", f"News #{news_id}", cur=c)
        return news_id

    if cur is not None:
        return work(cur)
    with db.get().transaction() as c:
        return work(c)


def delete(news_id: int, actor_id: int) -> None:
    db.get().run("DELETE FROM news_item WHERE news_id = %s", (news_id,))
    audit.log(actor_id, "NEWS_DELETED", f"News #{news_id}")
