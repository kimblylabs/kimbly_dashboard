import os
from datetime import datetime, time, timedelta, timezone
import importlib
from urllib.parse import urlparse

import bcrypt
import psutil
import requests

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import bindparam, create_engine, text
from telegram_notifier import check_and_notify

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
LIVE_THRESHOLD_SECONDS = 300  # 5 minutes
MAC_DISK_PATH = "/"
LOW_DISK_THRESHOLD_GB = 5

try:
    zoneinfo_mod = importlib.import_module("zoneinfo")
    ZoneInfo = getattr(zoneinfo_mod, "ZoneInfo")
    APP_TZ = ZoneInfo(APP_TIMEZONE_NAME)
except Exception:
    APP_TZ = timezone(timedelta(hours=5, minutes=30))


def now_tz():
    return datetime.now(APP_TZ)


def bytes_to_gb(value):
    return round(value / (1024**3), 2)


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _win_api_base_url():
    return _env("WIN_API_BASE_URL", "").strip().rstrip("/")


def _win_api_timeout_seconds():
    try:
        timeout = int(_env("WIN_API_TIMEOUT_SECONDS", "3"))
    except Exception:
        timeout = 3

    return timeout if timeout > 0 else 3


def _fetch_win_json(path):
    base = _win_api_base_url()
    if not base:
        return None

    if not str(path).startswith("/"):
        path = f"/{path}"

    url = f"{base}{path}"

    try:
        response = requests.get(url, timeout=_win_api_timeout_seconds())
    except Exception:
        return None

    if not response.ok:
        return None

    try:
        return response.json()
    except Exception:
        return None


def mac_storage_payload():
    disk = psutil.disk_usage(MAC_DISK_PATH)
    total_gb = bytes_to_gb(disk.total)
    used_gb = bytes_to_gb(disk.used)
    free_gb = bytes_to_gb(disk.free)
    used_percent = round(disk.percent, 2)
    low_disk = free_gb < LOW_DISK_THRESHOLD_GB

    return {
        "platform": "MAC",
        "drive": MAC_DISK_PATH,
        "timestamp": now_tz().isoformat(),
        "storage": {
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "used_percent": used_percent,
            "low_disk": low_disk,
        },
    }


def combined_storage_payload():
    mac_data = None
    win_data = None

    try:
        mac_data = mac_storage_payload()
    except Exception as exc:
        mac_data = {"platform": "MAC", "success": False, "error": str(exc)}

    win_data = _fetch_win_json("/win/storage")
    if not isinstance(win_data, dict):
        win_data = {
            "platform": "WIN",
            "success": False,
            "error": "Windows storage unavailable",
        }

    return {
        "mac": mac_data,
        "win": win_data,
    }


app.config["SECRET_KEY"] = _env("FLASK_SECRET_KEY", "kimbly-dashboard-dev-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def _safe_next_url(target):
    if not target:
        return url_for("home")

    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return url_for("home")

    if not target.startswith("/"):
        return url_for("home")

    return target


def _bcrypt_hash_value(value):
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)

    return str(value).encode("utf-8")


def _verify_password(stored_hash, password):
    hashed = _bcrypt_hash_value(stored_hash)
    if not hashed or not hashed.startswith(b"$2"):
        return False

    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    except Exception:
        return False


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


def fetch_user_auth_record(username):
    engine = monitoring_engine()

    try:
        with engine.begin() as conn:
            table_exists = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                    AND table_name = 'user'
                    """),
            ).scalar()

            if not table_exists:
                return None

            row = (
                conn.execute(
                    text("""
                    SELECT id, `username` AS username, `password` AS password
                    FROM `user`
                    WHERE `username` = :username
                    LIMIT 1
                    """),
                    {"username": username},
                )
                .mappings()
                .first()
            )

            if row:
                return dict(row)
    finally:
        engine.dispose()

    return None


def is_logged_in():
    return bool(session.get("user_id"))


@app.before_request
def require_login():
    allowed_endpoints = {"login", "logout", "static"}

    if request.endpoint in allowed_endpoints or request.endpoint is None:
        return None

    if is_logged_in():
        return None

    if request.path.startswith("/api/"):
        return jsonify({"error": "Unauthorized"}), 401

    return redirect(
        url_for("login", next=request.full_path if request.method == "GET" else None)
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


def fetch_app_by_id(app_id):
    query = text("""
        SELECT id, app_name, db_host, db_name, db_user, db_password, app_url
        FROM applications
        WHERE active = 1 AND id = :app_id
        LIMIT 1
        """)

    engine = monitoring_engine()

    try:
        with engine.begin() as conn:
            row = conn.execute(query, {"app_id": app_id}).mappings().first()
    finally:
        engine.dispose()

    return dict(row) if row else None


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

    process_exists_query = text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = 'processes_status'
    """)

    logs_query = text("""
        SELECT module, activity, priority, timestamp
        FROM trade_logs
        WHERE module IN :modules
        ORDER BY timestamp DESC
        LIMIT :log_limit
    """).bindparams(bindparam("modules", expanding=True))

    latest_log_query = text("""
        SELECT timestamp AS last_live_timestamp
        FROM trade_logs
        ORDER BY timestamp DESC
        LIMIT 1
    """)

    try:
        with engine.begin() as conn:

            settings_exists = conn.execute(settings_exists_query).scalar()

            process_exists = conn.execute(process_exists_query).scalar()

            # Priority:
            # 1. settings table
            # 2. processes_status table
            # 3. latest trade_logs timestamp

            if settings_exists:

                setting = conn.execute(text("""
                    SELECT last_live_timestamp
                    FROM settings
                    WHERE id = 1
                    LIMIT 1
                """)).mappings().first()

            elif process_exists:

                setting = conn.execute(text("""
                    SELECT bot AS last_live_timestamp
                    FROM processes_status
                    WHERE id = 1
                    LIMIT 1
                """)).mappings().first()

            else:

                setting = conn.execute(latest_log_query).mappings().first()

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

        status["source"] = "MAC"
        rows.append(status)

    win_payload = _fetch_win_json("/win/dashboard")
    win_rows = win_payload.get("applications") if isinstance(win_payload, dict) else []

    if isinstance(win_rows, list):
        for row in win_rows:
            if not isinstance(row, dict):
                continue

            merged = {
                "app_id": row.get("app_id"),
                "app_name": row.get("app_name"),
                "daily_login": bool(row.get("daily_login")),
                "db_reset": bool(row.get("db_reset")),
                "redirect_link": row.get("redirect_link"),
                "insert_mode": row.get("insert_mode", "UNKNOWN"),
                "low_priority_logs": row.get("low_priority_logs", "UNKNOWN"),
                "status": row.get("status", "OFFLINE"),
                "online": bool(row.get("online")),
                "last_activity_seconds": row.get("last_activity_seconds"),
                "error": row.get("error"),
                "source": "WIN",
            }
            rows.append(merged)

    rows.sort(key=lambda x: ((x.get("app_name") or "").lower(), x.get("source") or ""))

    return rows


def dashboard_payload(rows):
    return {
        "applications": rows,
        "storage": combined_storage_payload(),
        "meta": {
            "total": len(rows),
            "generated_at": now_tz().isoformat(),
            "market_status": indian_market_status(),
        },
    }


def _jsonify_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {k: _jsonify_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_jsonify_safe(v) for v in value]

    return value


def app_detail_payload(app_row):
    snapshot = fetch_snapshot(app_row)
    status = derive_status(app_row, snapshot)

    return {
        "application": {
            "app_id": app_row["id"],
            "app_name": app_row.get("app_name"),
            "redirect_link": app_row.get("app_url"),
            "status": status,
            "settings": _jsonify_safe(snapshot.get("settings") or {}),
            "logs": _jsonify_safe(snapshot.get("logs") or []),
        },
        "meta": {
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


@app.route("/login", methods=["GET", "POST"])
def login():
    if is_logged_in():
        return redirect(url_for("home"))

    error = None
    next_target = request.form.get("next") or request.args.get("next") or ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if username and password:
            user = fetch_user_auth_record(username)
            stored_password = user.get("password") if user else None

            if user and _verify_password(stored_password, password):
                session.clear()
                session["user_id"] = user.get("id") or username
                session["username"] = user.get("username") or username
                return redirect(_safe_next_url(next_target))

        error = "Invalid username or password"

    return render_template("login.html", error=error, next_url=next_target)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def home():
    return render_template("dashboard.html")


@app.get("/applications/<int:app_id>")
def application_detail_page(app_id):
    app_row = fetch_app_by_id(app_id)
    if not app_row:
        abort(404)

    return render_template(
        "application_detail.html",
        app_id=app_id,
        app_name=app_row.get("app_name") or "Application",
        app_source="MAC",
    )


@app.get("/applications/win/<int:app_id>")
def application_detail_page_win(app_id):
    return render_template(
        "application_detail.html",
        app_id=app_id,
        app_name=f"Windows App #{app_id}",
        app_source="WIN",
    )


@app.get("/api/dashboard")
def api_dashboard():
    try:
        rows = fetch_status_rows()
        print(f"Fetched dashboard data for {rows} applications")
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


@app.get("/api/applications/<int:app_id>")
def api_application_detail(app_id):
    app_row = fetch_app_by_id(app_id)

    if not app_row:
        return jsonify({"error": "Application not found"}), 404

    try:
        return jsonify(app_detail_payload(app_row))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/win/<path:subpath>")
def api_win_proxy(subpath):
    base = _win_api_base_url()
    if not base:
        return jsonify({"error": "WIN_API_BASE_URL is not configured"}), 503

    path = f"/win/{subpath.lstrip('/')}"
    url = f"{base}{path}"

    try:
        response = requests.get(url, timeout=_win_api_timeout_seconds())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    try:
        payload = response.json()
    except Exception:
        payload = {"error": "Invalid JSON response from windows API"}

    return jsonify(payload), response.status_code


@app.get("/api/storage")
def api_storage_combined():
    return jsonify(combined_storage_payload())


@app.get("/storage")
def storage():
    try:
        return jsonify(mac_storage_payload())
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@socketio.on("connect")
def on_connect():
    if not is_logged_in():
        return False

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
    check_and_notify(rows)

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
        host = _env("FLASK_RUN_HOST", "0.0.0.0")
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
