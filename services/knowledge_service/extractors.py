"""
文档文本提取。
"""

from __future__ import annotations

from fastapi import HTTPException, status

try:
    import fitz

    PDF_AVAILABLE = True
except ImportError:
    fitz = None
    PDF_AVAILABLE = False


TEXT_MIME_PREFIXES = ("text/",)
TEXT_EXTENSIONS = (".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".log")
TEXT_DECODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16")


def decode_text_bytes(body: bytes) -> str:
    for encoding in TEXT_DECODINGS:
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def extract_text_from_bytes(file_name: str, mime_type: str | None, body: bytes) -> dict[str, str | int]:
    name = file_name.lower()
    content_type = (mime_type or "").lower()

    if name.endswith(".pdf") or content_type == "application/pdf":
        if not PDF_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "PDF_UNAVAILABLE", "message": "PyMuPDF is not installed"},
            )
        document = fitz.open(stream=body, filetype="pdf")
        pages = [page.get_text() for page in document]
        text = "\n".join(pages).strip()
        return {"title": file_name, "contentText": text, "pages": len(pages)}

    if content_type.startswith(TEXT_MIME_PREFIXES) or name.endswith(TEXT_EXTENSIONS):
        text = decode_text_bytes(body).strip()
        return {"title": file_name, "contentText": text, "pages": 0}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "UNSUPPORTED_FILE", "message": "only PDF and text-like documents are supported"},
    )
