from sqlalchemy import inspect, text


def drop_legacy_quiz_sets_is_public(sync_conn) -> None:
    insp = inspect(sync_conn)
    if not insp.has_table("quiz_sets"):
        return
    cols = {column["name"] for column in insp.get_columns("quiz_sets")}
    if "is_public" not in cols:
        return
    if "visibility" in cols:
        sync_conn.execute(
            text(
                "UPDATE quiz_sets SET visibility = 'public' "
                "WHERE is_public IS TRUE AND visibility IS DISTINCT FROM 'public'"
            )
        )
    sync_conn.execute(text("ALTER TABLE quiz_sets DROP COLUMN is_public"))
