# smutscrape/stash.py

class StashClient:
    def __init__(self, url: str, api_key: str = ""):
        self.url = url.rstrip("/") + "/graphql"
        self.session = requests.Session()
        if api_key:
            self.session.headers["ApiKey"] = api_key

    def _query(self, query: str, variables: dict = None) -> dict: ...

    # ── Scan ──
    def metadata_scan(self, paths: list[str]) -> str | None:
        """Trigger a library scan, return job ID."""

    def wait_for_job(self, job_id: str, timeout: float = 180) -> bool:
        """Poll until job completes."""

    # ── Scene lookup ──
    def find_scene_by_path(self, path: str) -> int | None:
        """Return scene ID for a file path, or None if not yet indexed."""

    # ── Metadata push ──
    def update_scene(self, scene_id: int, *,
                     title: str = None, details: str = None,
                     date: str = None, url: str = None,
                     cover_image: str = None) -> bool: ...

    def apply_tags(self, scene_id: int, tag_names: list[str]) -> bool:
        """Resolve tag names → IDs (create missing), apply to scene."""

    def apply_performers(self, scene_id: int, performer_names: list[str]) -> bool: ...

    def apply_studios(self, scene_id: int, studio_names: list[str]) -> bool: ...

    # ── Generation ──
    def generate(self, scene_ids: list[int]) -> bool:
        """Fire cover/preview/sprite generation."""