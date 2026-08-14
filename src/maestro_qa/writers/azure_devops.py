from dataclasses import dataclass

import httpx

from .base import WorkItem, WriterError, WriteResult


@dataclass
class AzureDevOpsWriter:
    org: str
    project: str
    pat: str
    work_item_type: str = "Task"

    def create(self, item: WorkItem) -> WriteResult:
        url = (
            f"https://dev.azure.com/{self.org}/{self.project}/_apis/wit/workitems/"
            f"${self.work_item_type}?api-version=7.1"
        )
        patch = [
            {"op": "add", "path": "/fields/System.Title", "value": item.title},
            {"op": "add", "path": "/fields/System.Description", "value": item.description},
        ]
        response = httpx.post(
            url,
            auth=("", self.pat),
            headers={"Content-Type": "application/json-patch+json"},
            json=patch,
            timeout=30,
        )
        if response.status_code >= 400:
            raise WriterError(f"Azure DevOps API respondió {response.status_code}: {response.text[:300]}")

        data = response.json()
        try:
            return WriteResult(external_id=str(data["id"]), url=data["_links"]["html"]["href"])
        except KeyError as exc:
            raise WriterError(f"Respuesta inesperada de Azure DevOps, falta {exc}") from exc
