import os
import requests

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")  # sandbox domain
MAILGUN_BASE_URL = os.getenv("MAILGUN_BASE_URL", "https://api.mailgun.net/v3")


def send_email(to: str, subject: str, text: str):
    """
    Send an email via Mailgun API.

    Returns: requests.Response
    """
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        # Synthesize a Response-like object to propagate error details
        r = requests.Response()
        r.status_code = 500
        r._content = b"Mailgun is not configured: set MAILGUN_API_KEY and MAILGUN_DOMAIN"
        r.url = f"{MAILGUN_BASE_URL}/{MAILGUN_DOMAIN or ''}/messages"
        return r

    url = f"{MAILGUN_BASE_URL}/{MAILGUN_DOMAIN}/messages"

    try:
        response = requests.post(
            url,
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"Mailgun Sandbox <postmaster@{MAILGUN_DOMAIN}>",
                "to": to,
                "subject": subject,
                "text": text,
            },
            timeout=15,
        )
        return response
    except Exception as e:
        r = requests.Response()
        r.status_code = 500
        r._content = str(e).encode("utf-8", errors="ignore")
        r.url = url
        return r
