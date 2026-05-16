import re
import pdfplumber
from app.models import ContactInfo


def extract_text_from_pdf(file_bytes):
    """
    Extracts text from a PDF file while maintaining basic structural flow.
    """
    text = ""
    try:
        with pdfplumber.open(file_bytes) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(layout=True)
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to extract PDF text: {exc}") from exc


def extract_contact_info(text: str) -> ContactInfo:
    email_match = re.search(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text
    )
    phone_match = re.search(
        r'(\+?\d[\d\s\-().]{7,}\d)', text
    )
    linkedin_match = re.search(
        r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)', text, re.IGNORECASE
    )

    linkedin_url = None
    if linkedin_match:
        handle = linkedin_match.group(1)
        linkedin_url = f"https://linkedin.com/in/{handle}"

    return ContactInfo(
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(1).strip() if phone_match else None,
        linkedin=linkedin_url,
    )