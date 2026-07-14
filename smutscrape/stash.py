# smutscrape/stash.py
"""Stash GraphQL client — modeled after Sharestream's backends/stash.py.

All queries match the real Stash GraphQL schema. Sync (requests), not async
(httpx), because smutscrape is a CLI tool, not a web server.
"""
from __future__ import annotations

import time
import requests
from loguru import logger


class StashClient:
    def __init__(self, url: str, api_key: str = ""):
        self.url = url.rstrip("/") + "/graphql"
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
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
        """Trigger a Stash metadata scan. Returns job id or None."""
        result = self._query(
            "mutation MetadataScan($input: ScanMetadataInput!) { metadataScan(input: $input) }",
            {"input": {"paths": paths}},
        )
        job_id = result.get("metadataScan")
        if job_id:
            logger.info(f"Stash: metadata scan started, job={job_id}")
        return job_id

    def wait_for_job(self, job_id: str, timeout: float = 180.0) -> str:
        """Poll findJob until terminal state or timeout. Returns status string."""
        deadline = time.time() + timeout
        terminal = {"FINISHED", "CANCELLED", "FAILED"}
        while time.time() < deadline:
            try:
                result = self._query(
                    "query FindJob($input: FindJobInput!) { findJob(input: $input) { status } }",
                    {"input": {"id": job_id}},
                )
                job = (result or {}).get("findJob")
                if job is None:          # aged out of queue → done
                    return "FINISHED"
                status = job.get("status")
                if status in terminal:
                    return status
            except Exception as e:
                logger.warning(f"Stash: error polling job {job_id}: {e}")
            time.sleep(1)
        logger.warning(f"Stash: timed out waiting for job {job_id}")
        return "TIMEOUT"

    # ── Scene lookup ──
    def find_scene_by_path(self, path: str) -> int | None:
        """Return scene id whose file path equals ``path``, else None."""
        result = self._query(
            """
            query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType) {
                findScenes(filter: $filter, scene_filter: $scene_filter) {
                    scenes { id }
                }
            }
            """,
            {
                "filter": {"page": 1, "per_page": 1, "sort": "created_at", "direction": "DESC"},
                "scene_filter": {"path": {"value": path, "modifier": "EQUALS"}},
            },
        )
        scenes = result.get("findScenes", {}).get("scenes", [])
        return int(scenes[0]["id"]) if scenes else None

    # ── Metadata push ──
    def update_scene(self, scene_id: int, *,
                     title: str = None, details: str = None,
                     date: str = None, url: str = None,
                     cover_image: str = None) -> bool:
        """Set a scene's title/details/date/url. Omitted/blank fields left as-is."""
        fields = {"id": str(scene_id)}
        if title:
            fields["title"] = title
        if details:
            fields["details"] = details
        if date:
            fields["date"] = date
        if url:
            fields["url"] = url
        if cover_image:
            fields["cover_image"] = cover_image
        if len(fields) == 1:  # nothing beyond id
            return True
        try:
            self._query(
                "mutation SceneUpdate($input: SceneUpdateInput!) { sceneUpdate(input: $input) { id } }",
                {"input": fields},
            )
            logger.info(f"Stash: updated metadata for scene {scene_id}")
            return True
        except Exception as e:
            logger.warning(f"Stash: sceneUpdate failed for {scene_id}: {e}")
            return False

    # ── Tags ──
    def add_tags_to_scene(self, scene_id: int, tag_ids: list[str]) -> bool:
        """Union ``tag_ids`` into a scene's existing tags (never clobbers others).

        Reads current tags, unions with new ids, writes back in one SceneUpdate.
        Mirrors Sharestream's add_tags_to_scene exactly.
        """
        wanted = {str(t) for t in tag_ids if t not in (None, "")}
        if not wanted:
            return True
        try:
            # 1. Read current tag ids
            result = self._query(
                "query FindScene($id: ID!) { findScene(id: $id) { tags { id } } }",
                {"id": str(scene_id)},
            )
            scene = (result or {}).get("findScene") or {}
            merged = {str(t["id"]) for t in scene.get("tags", [])}
            merged |= wanted

            # 2. Write back the union
            self._query(
                "mutation SceneUpdate($input: SceneUpdateInput!) { sceneUpdate(input: $input) { id } }",
                {"input": {"id": str(scene_id), "tag_ids": sorted(merged)}},
            )
            logger.info(f"Stash: tagged scene {scene_id} with {sorted(wanted)}")
            return True
        except Exception as e:
            logger.warning(f"Stash: add_tags_to_scene failed for {scene_id}: {e}")
            return False

    def _find_or_create_tag_ids(self, tag_names: list[str]) -> list[str]:
        """Find existing tags by name, creating any that don't exist. Returns ids."""
        ids = []
        for name in tag_names:
            result = self._query(
                """
                query FindTags($filter: FindFilterType, $tag_filter: TagFilterType) {
                    findTags(filter: $filter, tag_filter: $tag_filter) {
                        tags { id name }
                    }
                }
                """,
                {"filter": {"q": name, "per_page": 1}, "tag_filter": {}},
            )
            tags = result.get("findTags", {}).get("tags", [])
            if tags:
                ids.append(tags[0]["id"])
            else:
                # Create
                result = self._query(
                    "mutation TagCreate($input: TagCreateInput!) { tagCreate(input: $input) { id } }",
                    {"input": {"name": name}},
                )
                new_id = (result.get("tagCreate") or {}).get("id")
                if new_id:
                    ids.append(new_id)
        return ids

    def apply_tags(self, scene_id: int, tag_names: list[str]) -> bool:
        """Find-or-create tags by name, then add them to the scene."""
        tag_ids = self._find_or_create_tag_ids(tag_names)
        if not tag_ids:
            return False
        return self.add_tags_to_scene(scene_id, tag_ids)

    # ── Performers ──
    def _find_or_create_performer_ids(self, performer_names: list[str]) -> list[str]:
        ids = []
        for name in performer_names:
            result = self._query(
                """
                query FindPerformers($filter: FindFilterType) {
                    findPerformers(filter: $filter) {
                        performers { id name }
                    }
                }
                """,
                {"filter": {"q": name, "per_page": 1}},
            )
            performers = result.get("findPerformers", {}).get("performers", [])
            if performers:
                ids.append(performers[0]["id"])
            else:
                result = self._query(
                    "mutation PerformerCreate($input: PerformerCreateInput!) { performerCreate(input: $input) { id } }",
                    {"input": {"name": name}},
                )
                new_id = (result.get("performerCreate") or {}).get("id")
                if new_id:
                    ids.append(new_id)
        return ids

    def apply_performers(self, scene_id: int, performer_names: list[str]) -> bool:
        """Find-or-create performers by name, then add them to the scene."""
        performer_ids = self._find_or_create_performer_ids(performer_names)
        if not performer_ids:
            return False
        try:
            self._query(
                "mutation SceneUpdate($input: SceneUpdateInput!) { sceneUpdate(input: $input) { id } }",
                {"input": {"id": str(scene_id), "performer_ids": performer_ids}},
            )
            logger.info(f"Stash: added performers {performer_names} to scene {scene_id}")
            return True
        except Exception as e:
            logger.warning(f"Stash: apply_performers failed: {e}")
            return False

    # ── Studios ──
    def _find_or_create_studio_id(self, studio_name: str) -> str | None:
        result = self._query(
            """
            query FindStudios($filter: FindFilterType) {
                findStudios(filter: $filter) {
                    studios { id name }
                }
            }
            """,
            {"filter": {"q": studio_name, "per_page": 1}},
        )
        studios = result.get("findStudios", {}).get("studios", [])
        if studios:
            return studios[0]["id"]
        result = self._query(
            "mutation StudioCreate($input: StudioCreateInput!) { studioCreate(input: $input) { id } }",
            {"input": {"name": studio_name}},
        )
        return (result.get("studioCreate") or {}).get("id")

    def apply_studios(self, scene_id: int, studio_names: list[str]) -> bool:
        """Set the scene's studio (Stash only supports one studio per scene)."""
        if not studio_names:
            return False
        studio_id = self._find_or_create_studio_id(studio_names[0])
        if not studio_id:
            return False
        try:
            self._query(
                "mutation SceneUpdate($input: SceneUpdateInput!) { sceneUpdate(input: $input) { id } }",
                {"input": {"id": str(scene_id), "studio_id": studio_id}},
            )
            logger.info(f"Stash: set studio '{studio_names[0]}' on scene {scene_id}")
            return True
        except Exception as e:
            logger.warning(f"Stash: apply_studios failed: {e}")
            return False

    # ── Generation ──
    def generate(self, scene_ids: list[int]) -> str | None:
        """Generate covers, previews, animated WebP, sprites. Returns job id."""
        result = self._query(
            "mutation MetadataGenerate($input: GenerateMetadataInput!) { metadataGenerate(input: $input) }",
            {"input": {
                "sceneIDs": [str(s) for s in scene_ids],
                "covers": True,
                "previews": True,
                "imagePreviews": True,
                "sprites": True,
                "phashes": True,
                "clipPreviews": True,
            }},
        )
        job_id = result.get("metadataGenerate")
        if job_id:
            logger.info(f"Stash: metadata generate started, job={job_id}")
        return job_id