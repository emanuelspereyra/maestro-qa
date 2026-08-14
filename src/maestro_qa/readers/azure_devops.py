import re
from dataclasses import dataclass

import httpx

from .base import FetchedTicket, ReaderError

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    return _WHITESPACE_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()


@dataclass
class AzureDevOpsReader:
    org: str
    project: str
    pat: str

    def fetch(self, external_id: str) -> FetchedTicket:
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/wit/workitems/{external_id}?api-version=7.1"
        response = httpx.get(url, auth=("", self.pat), timeout=30)
        if response.status_code >= 400:
            raise ReaderError(f"Azure DevOps API respondió {response.status_code}: {response.text[:300]}")

        fields = response.json().get("fields") or {}
        title = str(fields.get("System.Title") or f"Work item {external_id}")
        description_html = str(fields.get("System.Description") or fields.get("Microsoft.VSTS.TCM.ReproSteps") or "")
        description = _strip_html(description_html)

        text = f"{title}\n\n{description}" if description else title
        return FetchedTicket(external_id=str(external_id), title=title, text=text)
