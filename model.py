import re
from typing import List
from bs4 import BeautifulSoup, NavigableString

# ---------- PAGE BOILERPLATE FILTERS ----------
SKIP_TAGS = {"header", "footer", "nav", "aside", "script", "style"}
BOILERPLATE_CLASS_OR_ID = re.compile(
    r"(wb-inv|pagedetails|gc-main-footer|gc-sub-footer|gc-contextual|wtrmrk|breadcrumb|"
    r"site-footer|menu|global-nav|mega-menu|skip-link|toolbar|wb-slc|gcweb-menu)",
    re.I,
)

class ChangeSummarizer:
    """
    Summarizes only Canadian immigration-related textual changes from an HTML diff (<ins>/<del> tags).
    Classification of relevance is done by the LLM instead of regex rules.
    """

    def __init__(self, logger, openai_client, model: str = "gpt-4o-mini"):
        self.logger = logger
        self.openai_client = openai_client
        self.model = model

    def summarize_changes(self, diff_text: str) -> str:
        """
        Generate immigration-only summary from an HTML diff string.
        """
        candidate_sentences = self._extract_changed_sentences(diff_text)
        print(candidate_sentences)

        if not candidate_sentences:
            return "No visible immigration-related textual updates found."

        immigration_only = self._classify_with_llm(candidate_sentences)
        print(immigration_only)

        if not immigration_only:
            return "No visible immigration-related textual updates found."

        prompt = (
            "You are an immigration change analyst. Summarize visible textual updates that affect Canadian immigration applicants "
            "If there are no meaningful immigration updates, reply exactly: "
            "'No visible immigration-related textual updates found.'\n\n"
            f"{'\n'.join(immigration_only)}"
        )

        return self._call_openai(prompt, "summary")

    def translate_text(self, text: str, target_language: str = "Chinese") -> str:
        """
        Translate any given text to the target language while preserving formatting.
        """
        prompt = (
            f"Translate the following text to {target_language} while strictly preserving "
            "all original formatting including line breaks, spacing, punctuation, and special characters. "
            "Do not modify or rearrange the structure—only translate the textual content:\n\n"
            f"{text}"
        )
        return self._call_openai(prompt, "translation")

    # ---------- Internals ----------
    def _extract_changed_sentences(self, html: str) -> List[str]:
        """
        Parse the diff, keep text from <ins>/<del> that is NOT in boilerplate regions,
        and split into sentences.
        """
        soup = BeautifulSoup(html, "html.parser")

        changed = soup.find_all(["ins", "del"])
        if not changed:
            return []

        candidate_sentences: List[str] = []
        for node in changed:
            if self._is_boilerplate(node):
                continue
            buf: List[str] = []
            for d in node.descendants:
                if isinstance(d, NavigableString):
                    t = " ".join(str(d).split())
                    if t:
                        buf.append(t)
            if buf:
                text_block = " ".join(buf)
                sentences = re.split(r"(?<=[\.!?])\s+|\n+", text_block)
                for s in sentences:
                    s = s.strip()
                    if s:
                        candidate_sentences.append(s)
        return candidate_sentences

    def _classify_with_llm(self, sentences: List[str]) -> List[str]:
        """
        Ask the LLM to classify each sentence as Canadian immigration-related or not.
        """
        prompt = (
            "Classify each sentence as either 'IMMIGRATION' or 'IGNORE'.\n"
            "IMMIGRATION means the sentence is relevant to Canadian immigration in any way. "
            "This includes, but is not limited to:\n"
            "- Mentions of IRCC (Immigration, Refugees and Citizenship Canada) or its activities\n"
            "- Changes to immigration policies, visa processes, permits, citizenship, or permanent residence\n"
            "- Humanitarian or international announcements from IRCC\n"
            "- Any updates that could affect immigration applicants, refugees, asylum seekers, or travelers to Canada\n"
            "IGNORE means it has no connection to Canadian immigration.\n\n"
            "Return results in the format: <index>. <label> (no extra text).\n\n"
            + "\n".join(f"{i+1}. {sent}" for i, sent in enumerate(sentences))
        )

        result = self._call_openai(prompt, "classification")
        keep = []
        lines = result.splitlines()
        for idx, line in enumerate(lines):
            if "IMMIGRATION" in line.upper():
                keep.append(sentences[idx])
        return keep

    def _is_boilerplate(self, tag) -> bool:
        for anc in [tag] + list(tag.parents):
            if getattr(anc, "name", None) in SKIP_TAGS:
                return True
            classes = anc.get("class")
            if classes and BOILERPLATE_CLASS_OR_ID.search(" ".join(classes)):
                return True
            elem_id = anc.get("id")
            if elem_id and BOILERPLATE_CLASS_OR_ID.search(elem_id):
                return True
        return False

    def _call_openai(self, prompt: str, operation: str) -> str:
        try:
            self.logger.info(f"Requesting {operation} from OpenAI...")
            completion = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Be concise. Follow the user's instructions exactly."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                timeout=20
            )
            content = completion.choices[0].message.content.strip()
            self.logger.info(f"Successfully completed {operation}")
            return content
        except Exception as e:
            self.logger.error(f"OpenAI API failed during {operation}: {str(e)}")
            raise
