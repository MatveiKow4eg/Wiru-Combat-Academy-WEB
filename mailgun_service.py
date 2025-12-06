import os
import requests

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")  # sandbox domain
MAILGUN_BASE_URL = os.getenv("MAILGUN_BASE_URL", "https://api.mailgun.net/v3")


def send_email(to: str, subject: str, text: str):
    """
    Send an email via Mailgun API.

    Returns a tuple: (ok: bool, status_code: int, message: str)
    """
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        msg = "Mailgun is not configured: set MAILGUN_API_KEY and MAILGUN_DOMAIN"
        print(msg)
        return False, 500, msg

    url = f"{MAILGUN_BASE_URL}/{MAILGUN_DOMAIN}/messages"

    from_addr = f"Mailgun <postmaster@{MAILGUN_DOMAIN}>"
    try:
        response = requests.post(
            url,
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": from_addr,
                "to": to,
                "subject": subject,
                "text": text,
            },
            timeout=15,
        )
        ok = response.status_code == 200
        if ok:
            print("Mailgun: message sent successfully", response.status_code)
            return True, response.status_code, response.text
        else:
            print("Mailgun error:", response.status_code, response.text)
            return False, response.status_code, response.text
    except Exception as e:
        print("Mailgun exception:", e)
        return False, 500, str(e)
