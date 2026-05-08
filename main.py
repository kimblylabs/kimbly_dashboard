import os
from datetime import datetime, time, timedelta, timezone
import importlib

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from sqlalchemy import bindparam, create_engine, text

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
socketio_mod = importlib.import_module("flask_socketio")
SocketIO = getattr(socketio_mod, "SocketIO")
socketio = SocketIO(app, cors_allowed_origins="*")

IMPORTANT_MODULES = [
    "daily_login",
    "db_reset",
    "supervisor",
    "websocket",
    "redis",
    "mysql",
]

APP_TIMEZONE_NAME = "Asia/Kolkata"
LIVE_THRESHOLD_SECONDS = 900

try:
    zoneinfo_mod = importlib.import_module("zoneinfo")
    ZoneInfo = getattr(zoneinfo_mod, "ZoneInfo")
    APP_TZ = ZoneInfo(APP_TIMEZONE_NAME)
except Exception:
    APP_TZ = timezone(timedelta(hours=5, minutes=30))


def now_tz():
    return datetime.now(APP_TZ)


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def monitoring_engine():
    host = _env("MONITORING_DB_HOST", "localhost")
    port = int(_env("MONITORING_DB_PORT", "3306"))
    name = _env("MONITORING_DB_NAME", "kimbly_dashboard")
    user = _env("MONITORING_DB_USER", "root")
    pwd = _env("MONITORING_DB_PASSWORD", "")

    return create_engine(
        f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}",
        pool_pre_ping=True,
        pool_recycle=10,
        pool_size=5,
        max_overflow=10,
    )


def external_engine(db_host, db_name, db_user, db_password, db_port, timeout):
    return create_engine(
        f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
        pool_pre_ping=True,
        pool_recycle=10,
        pool_size=5,
        max_overflow=10,
        connect_args={
            "connect_timeout": timeout,
        },
    )


def fetch_apps():
    query = text("""
        SELECT id, app_name, db_host, db_name, db_user, db_password, app_url
        FROM applications
        WHERE active = 1
        ORDER BY id ASC
    """)

    engine = monitoring_engine()

    try:
        with engine.begin() as conn:
            rows = conn.execute(query).mappings().all()
    finally:
        engine.dispose()

    return [dict(r) for r in rows]


def fetch_snapshot(app_row):
    db_port = int(_env("APP_DB_PORT", "3306"))
    timeout = int(_env("APP_DB_CONNECT_TIMEOUT_SECONDS", "3"))
    limit = int(_env("APP_DB_LOG_LIMIT", "120"))

    engine = external_engine(
        app_row["db_host"],
        app_row["db_name"],
        app_row["db_user"],
        app_row["db_password"],
        db_port,
        timeout,
    )

    settings_exists_query = text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = 'settings'
    """)

    logs_query = text("""
        SELECT module, activity, priority, timestamp
        FROM trade_logs
        WHERE module IN :modules
        ORDER BY timestamp DESC
        LIMIT :log_limit
    """).bindparams(bindparam("modules", expanding=True))

    try:
        with engine.begin() as conn:

            settings_exists = conn.execute(settings_exists_query).scalar()

            if settings_exists:
                setting = conn.execute(text("""
                        SELECT last_live_timestamp
                        FROM settings
                        WHERE id = 1
                        LIMIT 1
                    """)).mappings().first()

            else:
                setting = conn.execute(text("""
                        SELECT bot AS last_live_timestamp
                        FROM processes_status
                        WHERE id = 1
                        LIMIT 1
                    """)).mappings().first()

            logs = (
                conn.execute(
                    logs_query,
                    {
                        "modules": tuple(IMPORTANT_MODULES),
                        "log_limit": limit,
                    },
                )
                .mappings()
                .all()
            )

    finally:
        engine.dispose()

    return {
        "settings": dict(setting) if setting else {},
        "logs": [dict(l) for l in logs],
    }


def semantic_priority(activity, priority):
    if priority is not None:
        try:
            return int(priority)
        except (TypeError, ValueError):
            pass

    text_val = (activity or "").lower()

    if "fail" in text_val or "error" in text_val:
        return 5

    if "skip" in text_val or "missed" in text_val:
        return 3

    if "success" in text_val or "completed" in text_val:
        return 4

    return 1


def indian_market_status(now_ist=None):
    if now_ist is None:
        now_ist = now_tz()

    if now_ist.weekday() >= 5:
        return "CLOSED"

    start = time(9, 15)
    end = time(15, 15)

    current = now_ist.time()

    return "OPEN" if start <= current <= end else "CLOSED"


def derive_status(app_row, snapshot):
    logs = snapshot.get("logs") or []
    settings = snapshot.get("settings") or {}
    has_settings_row = bool(settings)

    now = now_tz()

    def parse_dt(v):
        if v is None:
            return None

        if isinstance(v, datetime):
            return v.astimezone(APP_TZ) if v.tzinfo else v.replace(tzinfo=APP_TZ)

        try:
            d = datetime.fromisoformat(str(v))
            return d.astimezone(APP_TZ) if d.tzinfo else d.replace(tzinfo=APP_TZ)
        except Exception:
            return None

    last_live_ts = parse_dt(settings.get("last_live_timestamp"))

    last_live_sec = (
        abs(int((now - last_live_ts).total_seconds())) if last_live_ts else None
    )

    online = last_live_sec is not None and last_live_sec <= LIVE_THRESHOLD_SECONDS

    status = "ONLINE" if online else "OFFLINE"

    def latest_for(module_name):
        module_name = (module_name or "").lower()

        for row in logs:
            if str(row.get("module") or "").lower() == module_name:
                return row

        return None

    daily = latest_for("daily_login")
    reset = latest_for("db_reset")

    redis_or_mysql_raw = settings.get("redis_or_mysql")
    low_priority_raw = settings.get("low_priority_logs")

    if not has_settings_row:
        insert_mode = "UNKNOWN"
        low_priority_logs = "UNKNOWN"

    else:
        if redis_or_mysql_raw is None:
            insert_mode = "UNKNOWN"

        elif str(redis_or_mysql_raw) == "0":
            insert_mode = "REDIS"

        elif str(redis_or_mysql_raw) == "1":
            insert_mode = "MYSQL"

        else:
            insert_mode = "UNKNOWN"

        if low_priority_raw is None:
            low_priority_logs = "UNKNOWN"

        elif str(low_priority_raw) == "0":
            low_priority_logs = "DISABLED"

        elif str(low_priority_raw) == "1":
            low_priority_logs = "ENABLED"

        else:
            low_priority_logs = "UNKNOWN"

    return {
        "app_id": app_row["id"],
        "app_name": app_row["app_name"],
        "daily_login": bool(
            daily
            and semantic_priority(
                daily.get("activity"),
                daily.get("priority"),
            )
            >= 4
        ),
        "db_reset": bool(
            reset
            and semantic_priority(
                reset.get("activity"),
                reset.get("priority"),
            )
            >= 4
        ),
        "redirect_link": app_row.get("app_url"),
        "insert_mode": insert_mode,
        "low_priority_logs": low_priority_logs,
        "status": status,
        "online": online,
        "last_activity_seconds": last_live_sec,
    }


def fetch_status_rows():
    rows = []

    for app_row in fetch_apps():
        try:
            status = derive_status(
                app_row,
                fetch_snapshot(app_row),
            )

            status["error"] = None

        except Exception as exc:
            status = {
                "app_id": app_row["id"],
                "app_name": app_row["app_name"],
                "daily_login": False,
                "db_reset": False,
                "redirect_link": app_row.get("app_url"),
                "insert_mode": "UNKNOWN",
                "low_priority_logs": "UNKNOWN",
                "status": "OFFLINE",
                "online": False,
                "last_activity_seconds": None,
                "error": str(exc),
            }

        rows.append(status)

    rows.sort(key=lambda x: (x.get("app_name") or "").lower())

    return rows


def dashboard_payload(rows):
    return {
        "applications": rows,
        "meta": {
            "total": len(rows),
            "generated_at": now_tz().isoformat(),
            "market_status": indian_market_status(),
        },
    }


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@app.get("/")
def home():
    return render_template("dashboard.html")


@app.get("/api/dashboard")
def api_dashboard():
    try:
        rows = fetch_status_rows()

        return jsonify(dashboard_payload(rows))

    except Exception as exc:
        print(f"Error in /api/dashboard: {exc}")

        return (
            jsonify(
                {
                    "applications": [],
                    "meta": {"total": 0},
                    "errors": [{"error": str(exc)}],
                }
            ),
            500,
        )


@socketio.on("connect")
def on_connect():
    rows = fetch_status_rows()
    socketio.emit(
        "dashboard:update",
        dashboard_payload(rows),
    )


@socketio.on("dashboard:subscribe")
def on_subscribe(_data=None):
    rows = fetch_status_rows()

    socketio.emit(
        "dashboard:update",
        dashboard_payload(rows),
    )


def poll_and_broadcast():
    rows = fetch_status_rows()

    socketio.emit(
        "dashboard:update",
        dashboard_payload(rows),
    )


def start_scheduler():
    scheduler_mod = importlib.import_module("apscheduler.schedulers.background")

    BackgroundScheduler = getattr(
        scheduler_mod,
        "BackgroundScheduler",
    )

    interval = int(
        _env(
            "MONITORING_POLL_INTERVAL_SECONDS",
            "15",
        )
    )

    if interval < 5:
        interval = 5

    if interval > 30:
        interval = 30

    scheduler = BackgroundScheduler(timezone=APP_TIMEZONE_NAME)
    scheduler.add_job(
        poll_and_broadcast,
        "interval",
        seconds=interval,
        id="poll",
        replace_existing=True,
    )
    scheduler.start()

    return scheduler


if __name__ == "__main__":
    fetch_status_rows()

    scheduler = start_scheduler()

    try:
        host = _env("FLASK_RUN_HOST", "127.0.0.1")
        port = int(_env("FLASK_RUN_PORT", "5000"))
        debug = _env("FLASK_DEBUG", "0") == "1"

        socketio.run(
            app,
            host=host,
            port=port,
            debug=debug,
        )
    finally:
        scheduler.shutdown(wait=False)
