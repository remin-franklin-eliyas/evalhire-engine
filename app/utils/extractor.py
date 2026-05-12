import pdfplumber

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
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"