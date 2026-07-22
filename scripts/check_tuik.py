import json
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

TUIK_URL = os.environ.get(
    "TUIK_URL",
    "https://data.tuik.gov.tr/Bulten/Index?p=Yapi-Izin-Istatistikleri",
)

STATE_FILE = Path("state/last.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GitHubActions/1.0; +https://github.com/)"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_latest_signature(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    page_title = normalize(soup.title.get_text(" ", strip=True)) if soup.title else ""

    # Sayfada "En Son Yayımlanan Bülten" veya buna benzer ifadeleri arar.
    body_text = normalize(soup.get_text(" ", strip=True))

    quarter_match = re.search(r"\b([IVX]{1,4})\.\s*Çeyrek\b", body_text, re.IGNORECASE)
    quarter = quarter_match.group(0) if quarter_match else ""

    # İlk anlamlı bülten bağlantısını yakalamaya çalış.
    bulletin_title = ""
    bulletin_href = ""

    for a in soup.find_all("a", href=True):
        text = normalize(a.get_text(" ", strip=True))
        href = a["href"].strip()

        combined = f"{text} {href}"
        if "Yapı İzin İstatistikleri" in combined or re.search(r"\bÇeyrek\b", combined, re.IGNORECASE):
            bulletin_title = text or bulletin_title
            bulletin_href = urljoin(base_url, href)
            break

    # Başlık boşsa sayfa başlığını kullan
    if not bulletin_title:
        bulletin_title = page_title

    signature = normalize(f"{bulletin_title}|{bulletin_href}|{quarter}|{page_title}")

    return {
        "title": bulletin_title,
        "href": bulletin_href,
        "quarter": quarter,
        "page_title": page_title,
        "signature": signature,
    }


def send_mail(subject: str, body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_addr = os.environ["MAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)


def main() -> None:
    state = load_state()
    html = fetch_html(TUIK_URL)
    current = extract_latest_signature(html, TUIK_URL)

    last_signature = state.get("last_signature", "")
    if current["signature"] == last_signature:
        print("Yeni yayın yok.")
        return

    subject = "TÜİK Yapı İzin İstatistikleri Güncellendi"
    body = (
        "Merhaba,\n\n"
        "TÜİK Yapı İzin İstatistikleri için yeni bir bülten yayımlandı.\n\n"
        f"İncelemek için:\n{TUIK_URL}\n\n"
        "İyi çalışmalar.\n"
    )

    send_mail(subject, body)

    save_state(
        {
            "last_signature": current["signature"],
            "last_title": current["title"],
            "last_href": current["href"],
            "last_quarter": current["quarter"],
            "page_title": current["page_title"],
        }
    )

    print("Yeni yayın tespit edildi ve mail gönderildi.")


if __name__ == "__main__":
    main()
