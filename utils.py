from bs4 import BeautifulSoup

def extract_ins_elements_only(html_content: str) -> str:
    """
    Extracts and returns only the <ins> elements from the given HTML content.
    Preserves the <ins> tag and its inline styles and content.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract all <ins> elements
    ins_elements = soup.find_all("ins")

    # Create a new soup with only <ins> tags preserved
    new_soup = BeautifulSoup("", "html.parser")
    for ins in ins_elements:
        new_soup.append(ins)

    return str(new_soup)



def extract_plain_text(html_content: str) -> str:
    """Extracts plain text from the body of an HTML string."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Get only <body> content
    body = soup.body
    if not body:
        return ""

    # Remove script, style, footer, header, nav tags inside body
    for tag in body(["script", "style", "footer", "header", "nav"]):
        tag.decompose()

    # Extract text and clean whitespace
    text = body.get_text(separator="\n", strip=True)
    return text

