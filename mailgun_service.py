import os
import requests

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")  # wirucombatacademy.ee
MAILGUN_BASE_URL = os.getenv("MAILGUN_BASE_URL", "https://api.eu.mailgun.net/v3")

DEFAULT_FROM = "Wiru Combat Academy <contact@wirucombatacademy.ee>"

def send_email(to: str, subject: str, text: str) -> requests.Response:
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        r = requests.Response()
        r.status_code = 500
        r._content = b"Mailgun is not configured properly"
        return r

    url = f"{MAILGUN_BASE_URL}/{MAILGUN_DOMAIN}/messages"

    try:
        response = requests.post(
            url,
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": DEFAULT_FROM,
                "to": to,
                "subject": subject,
                "text": text,
            },
            timeout=15,
        )
        print("MAILGUN STATUS:", response.status_code)
        print("MAILGUN RESPONSE:", response.text)
        return response
    except Exception as e:
        r = requests.Response()
        r.status_code = 500
        r._content = str(e).encode()
        return r
