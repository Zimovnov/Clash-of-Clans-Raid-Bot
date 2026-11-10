"""Read-only provider checks; credentials arrive over stdin, never in argv/logs."""

import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    values = json.load(sys.stdin)
    token = values["BOT_TOKEN"]
    checks = [
        ("telegram_getMe", f"https://api.telegram.org/bot{token}/getMe", {}),
        ("telegram_webhook", f"https://api.telegram.org/bot{token}/getWebhookInfo", {}),
        (
            "clash_locations",
            "https://api.clashofclans.com/v1/locations?limit=1",
            {"Authorization": f"Bearer {values['CLASH_API_TOKEN']}"},
        ),
    ]
    failed = False
    for label, url, headers in checks:
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                payload = json.load(error)
            except ValueError:
                payload = {}
        except (urllib.error.URLError, TimeoutError):
            print(json.dumps({"check": label, "status": "network_error"}))
            failed = True
            continue

        result = {"check": label, "status": status}
        if label == "telegram_getMe":
            result["ok"] = payload.get("ok")
            result["username"] = payload.get("result", {}).get("username")
        elif label == "telegram_webhook":
            webhook = payload.get("result", {})
            result["has_webhook"] = bool(webhook.get("url"))
            result["pending_update_count"] = webhook.get("pending_update_count")
        else:
            result["reason"] = payload.get("reason")
            result["items"] = len(payload.get("items", []))
        print(json.dumps(result))
        failed = failed or status != 200
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
