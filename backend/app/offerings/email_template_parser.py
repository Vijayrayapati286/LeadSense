"""Parse uploaded email template files into subject + body."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from app.storage.exceptions import FileValidationError

TEMPLATE_EXTENSIONS = {".html", ".htm", ".txt", ".docx"}
DEFAULT_TEMPLATE_NAME = "Introduction Outreach"
DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _split_subject_body(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        raise FileValidationError("Template file is empty")

    subject_match = re.match(r"^subject\s*:\s*(.+?)(?:\n\n|\r\n\r\n|\n)", raw, re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1).strip()
        body = raw[subject_match.end() :].strip()
        return subject or DEFAULT_TEMPLATE_NAME, body

    lines = raw.splitlines()
    if len(lines) >= 2 and lines[0].strip() and len(lines[0]) < 200:
        return lines[0].strip(), "\n".join(lines[1:]).strip()

    return DEFAULT_TEMPLATE_NAME, raw


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise FileValidationError("Invalid Word document") from exc

    root = ElementTree.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for para in root.iter(f"{DOCX_NS}p"):
        parts = [node.text for node in para.iter(f"{DOCX_NS}t") if node.text]
        if parts:
            paragraphs.append("".join(parts))
    text = "\n\n".join(paragraphs).strip()
    if not text:
        raise FileValidationError("Word document has no readable text")
    return text


def _html_to_body(content: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    subject = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else DEFAULT_TEMPLATE_NAME
    body = content.strip()
    return subject or DEFAULT_TEMPLATE_NAME, body


def parse_email_template_file(*, filename: str, content: bytes) -> dict[str, str]:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in TEMPLATE_EXTENSIONS:
        raise FileValidationError(
            f"Invalid template type '{ext or 'unknown'}'. Allowed: {', '.join(sorted(TEMPLATE_EXTENSIONS))}"
        )

    if ext == ".docx":
        text = _extract_docx_text(content)
        subject, body = _split_subject_body(text)
        if subject == DEFAULT_TEMPLATE_NAME and "\n" not in text[:200]:
            subject = DEFAULT_TEMPLATE_NAME
        return {
            "name": DEFAULT_TEMPLATE_NAME,
            "subject": subject,
            "body": body,
            "source_filename": filename,
        }

    decoded = content.decode("utf-8", errors="replace")
    if ext in {".html", ".htm"}:
        subject, body = _html_to_body(decoded)
    else:
        subject, body = _split_subject_body(decoded)

    return {
        "name": DEFAULT_TEMPLATE_NAME,
        "subject": subject,
        "body": body,
        "source_filename": filename,
    }
