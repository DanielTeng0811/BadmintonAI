"""Interactive local password recovery. Passwords are never command-line arguments."""
import argparse
import getpass
import os

from .store import AuthError, Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "reset-password"])
    parser.add_argument("username", nargs="?", default="admin")
    args = parser.parse_args()
    store = Store(os.environ.get("AUTH_DATABASE", "/data/auth.db"))
    if args.command == "list":
        for user in store.users():
            print(user["username"], user["role"], "disabled" if user["disabled"] else "active")
        return
    password = getpass.getpass("新密碼（至少 12 個字元）：")
    if password != getpass.getpass("再次輸入："):
        raise SystemExit("兩次密碼不一致，沒有變更。")
    try:
        store.reset_password(args.username, password)
    except AuthError as exc:
        raise SystemExit(str(exc)) from None
    print("密碼已更新，原有登入已失效。")


if __name__ == "__main__":
    main()
