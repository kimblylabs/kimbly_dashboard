import time
from datetime import datetime

from main import fetch_status_rows


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def print_notification(message):

    print("\n" + "=" * 70)

    print(f"[{now_str()}] NOTIFICATION")

    print("-" * 70)

    print(message)

    print("=" * 70 + "\n")


def check_conditions(rows):

    for row in rows:

        app_name = row.get(
            "app_name",
            "Unknown App",
        )

        online = row.get(
            "online",
            False,
        )

        daily_login = row.get(
            "daily_login",
            False,
        )

        db_reset = row.get(
            "db_reset",
            False,
        )

        print(
            f"{app_name:<30} | "
            f"ONLINE={online} | "
            f"DAILY_LOGIN={daily_login} | "
            f"DB_RESET={db_reset}"
        )

        # OFFLINE

        if not online:

            print_notification(
                f"🚨 {app_name} is OFFLINE"
            )

        # DAILY LOGIN

        if not daily_login:

            print_notification(
                f"⚠️ Daily Login NOT done for {app_name}"
            )

        # DB RESET

        if not db_reset:

            print_notification(
                f"⚠️ DB Reset NOT done for {app_name}"
            )


def main():

    print("\n")
    print("=" * 70)
    print(
        "KIMBLY LABS REAL NOTIFICATION TEST"
    )
    print("=" * 70)

    while True:

        try:

            print(
                f"\n[{now_str()}] "
                f"Fetching real dashboard data..."
            )

            rows = fetch_status_rows()

            print(
                f"Applications fetched: {len(rows)}\n"
            )

            check_conditions(rows)

            sleep_time = 15

            print(
                f"\n[{now_str()}] "
                f"Next cycle in {sleep_time} sec..."
            )

            time.sleep(sleep_time)

        except KeyboardInterrupt:

            print("\nStopped by user")

            break

        except Exception as exc:

            print(f"\nError: {exc}")

            time.sleep(5)


if __name__ == "__main__":
    main()