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