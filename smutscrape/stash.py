# smutscrape/stash.py
"""Stash GraphQL client for direct metadata push after download."""

import time
import requests
from loguru import logger


class StashClient:
    def __init__(self, url: str, api_key: str = ""):
        self.url = url.rstrip("/") + "/graphql"
        self.session = requests.Session()
        if api_key:
            self.session.headers["ApiKey"] = api_key

    def _query(self, query: str, variables: dict | None = None) -> dict:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self.session.post(self.url, json=payload, timeout=30)
        if not resp.ok:
            logger.error(f"Stash HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.error(f"Stash GraphQL errors: {data['errors']}")
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})

    # ── Scan ──
    def metadata_scan(self, paths: list[str]) -> str | None:
        result = self._query("""
            mutation($input: ScanMetadataInput!) {
                metadataScan(input: $input)
            }
        """, {"input": {"paths": paths}})
        return result.get("metadataScan")

    def wait_for_job(self, job_id: str, timeout: float = 180) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self._query("""
                query($id: ID!) { jobStatus(id: $id) { status } }
            """, {"id": job_id})
            status = result.get("jobStatus", {}).get("status", "")
            if status in ("FINISHED", "CANCELLED"):
                return status == "FINISHED"
            time.sleep(1)
        return False

    # ── Scene lookup ──
    def find_scene_by_path(self, path: str) -> int | None:
        result = self._query("""
            query($filter: FindFilterType!, $scene_filter: SceneFilterType!) {
                findScenes(filter: $filter, scene_filter: $scene_filter) {
                    scenes { id }
                }
            }
        """, {
            "filter": {"per_page": 1},
            "scene_filter": {"path": {"value": path, "modifier": "EQUALS"}}
        })
        scenes = result.get("findScenes", {}).get("scenes", [])
        return scenes[0]["id"] if scenes else None

    # ── Metadata push ──
    def update_scene(self, scene_id: int, *,
                     title: str = None, details: str = None,
                     date: str = None, url: str = None,
                     cover_image: str = None) -> bool:
        inp = {"id": str(scene_id)}
        if title:       inp["title"] = title
        if details:     inp["details"] = details
        if date:        inp["date"] = date
        if url:         inp["url"] = url
        if cover_image: inp["cover_image"] = cover_image
        try:
            self._query("""
                mutation($input: SceneUpdateInput!) {
                    sceneUpdate(input: $input) { id }
                }
            """, {"input": inp})
            return True
        except Exception as e:
            logger.warning(f"Stash: sceneUpdate failed for {scene_id}: {e}")
            return False



    def _find_or_create_ids(self, query_name: str, create_mutation: str,
                            names: list[str], input_key: str) -> list[str]:
        """Generic find-or-create for tags/performers/studios."""
        # Stash uses different field names in the result type than the query name
        result_field = {
            "findTags": "tags",
            "findPerformers": "performers",
            "findStudios": "studios",
        }.get(query_name, query_name)
    
        ids = []
        for name in names:
            result = self._query(f"""
                query($filter: FindFilterType!) {{
                    {query_name}(filter: $filter) {{
                        {result_field} {{ id name }}
                    }}
                }}
            """, {"filter": {"q": name, "per_page": 1}})
            items = result.get(query_name, {}).get(result_field, [])
            if items:
                ids.append(items[0]["id"])
            else:
                result = self._query(f"""
                    mutation($input: {create_mutation}!) {{
                        {create_mutation}(input: $input) {{ id }}
                    }}
                """, {"input": {input_key: name}})
                new_id = result.get(create_mutation, {}).get("id")
                if new_id:
                    ids.append(new_id)
        return ids

    def apply_tags(self, scene_id: int, tag_names: list[str]) -> bool:
        tag_ids = self._find_or_create_ids(
            "findTags", "tagCreate", tag_names, "name")
        if not tag_ids:
            return False
        try:
            self._query("""
                mutation($input: BulkSceneUpdateInput!) {
                    bulkSceneUpdate(input: $input) { id }
                }
            """, {"input": {"ids": [str(scene_id)], "tag_ids": {
                "ids": tag_ids, "mode": "ADD"}}})
            return True
        except Exception as e:
            logger.warning(f"Stash: apply_tags failed: {e}")
            return False

    def apply_performers(self, scene_id: int, performer_names: list[str]) -> bool:
        performer_ids = self._find_or_create_ids(
            "findPerformers", "performerCreate", performer_names, "name")
        if not performer_ids:
            return False
        try:
            self._query("""
                mutation($input: BulkSceneUpdateInput!) {
                    bulkSceneUpdate(input: $input) { id }
                }
            """, {"input": {"ids": [str(scene_id)], "performer_ids": {
                "ids": performer_ids, "mode": "ADD"}}})
            return True
        except Exception as e:
            logger.warning(f"Stash: apply_performers failed: {e}")
            return False

    def apply_studios(self, scene_id: int, studio_names: list[str]) -> bool:
        # Studios: only one per scene in Stash, use the first
        studio_ids = self._find_or_create_ids(
            "findStudios", "studioCreate", studio_names[:1], "name")
        if not studio_ids:
            return False
        try:
            self._query("""
                mutation($input: SceneUpdateInput!) {
                    sceneUpdate(input: $input) { id }
                }
            """, {"input": {"id": str(scene_id), "studio_id": studio_ids[0]}})
            return True
        except Exception as e:
            logger.warning(f"Stash: apply_studios failed: {e}")
            return False

    # ── Generation ──
    def generate(self, scene_ids: list[int]) -> bool:
        try:
            self._query("""
                mutation($input: GenerateMetadataInput!) {
                    metadataGenerate(input: $input)
                }
            """, {"input": {"sceneIds": [str(sid) for sid in scene_ids]}})
            return True
        except Exception as e:
            logger.warning(f"Stash: generate failed: {e}")
            return False