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
    "https://veriportali.tuik.gov.tr/Bulten/Index?dil=1&p=Yap%C4%B1-%C4%B0zin-%C4%B0statistikleri-I.-%C3%87eyrek%3A-Ocak-Mart-2026-58303",
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

    bulletin_title = ""
    bulletin_href = ""

    # "Yapı İzin İstatistikleri" bültenini bul
    for a in soup.find_all("a", href=True):
        text = normalize(a.get_text(" ", strip=True))

        if "Yapı İzin İstatistikleri" in text:
            bulletin_title = text
            bulletin_href = urljoin(base_url, a["href"])
            break

    if not bulletin_href:
        raise Exception("Yapı İzin İstatistikleri bülteni bulunamadı.")

    # Asıl bülten sayfasını indir
    bulletin_html = fetch_html(bulletin_href)
    bulletin = BeautifulSoup(bulletin_html, "html.parser")

    excel_link = ""

    # Excel / XLS / XLSX bağlantısını ara
    for a in bulletin.find_all("a", href=True):
        href = a["href"]

        if (
            ".xlsx" in href.lower()
            or ".xls" in href.lower()
            or "excel" in href.lower()
        ):
            excel_link = urljoin(bulletin_href, href)
            break

    signature = bulletin_href

    return {
        "title": bulletin_title,
        "href": bulletin_href,
        "excel": excel_link,
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
    "Yeni TÜİK Yapı İzin İstatistikleri yayımlandı.\n\n"
    f"Bülten : {current['title']}\n\n"
    f"Link : {current['href']}\n\n"
    "İyi çalışmalar."
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
