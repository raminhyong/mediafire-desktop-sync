import os
import re
import sys
import time
import json
import logging
import urllib.parse
import requests
from mediafire import MediaFireApi
from mediafire.uploader import MediaFireUploader

logging_handlers = [
    logging.FileHandler("sync_activity.log", encoding="utf-8")
]
if sys.stdout is not None:
    logging_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=logging_handlers
)

class SyncSettings:
    def __init__(self, config_filepath: str):
        with open(config_filepath, "r", encoding="utf-8") as config_file:
            loaded_settings = json.load(config_file)
        self.account_email = loaded_settings["email"]
        self.account_password = loaded_settings["password"]
        self.client_app_id = loaded_settings.get("app_id", "42511")
        raw_directory = loaded_settings["sync_directory"]
        if not os.path.isabs(raw_directory):
            config_dir = os.path.dirname(os.path.abspath(config_filepath))
            self.local_directory = os.path.normpath(os.path.join(config_dir, raw_directory))
        else:
            self.local_directory = os.path.normpath(raw_directory)
        self.cloud_folder_key = loaded_settings.get("remote_folder_key", "myfiles")
        self.sync_interval_seconds = loaded_settings.get("poll_interval_seconds", 30)

class SyncCatalog:
    def __init__(self, state_filepath: str):
        self.state_filepath = state_filepath
        self.records = self._read_state()

    def _read_state(self) -> dict:
        if not os.path.exists(self.state_filepath):
            return {}
        try:
            with open(self.state_filepath, "r", encoding="utf-8") as state_file:
                return json.load(state_file)
        except Exception:
            return {}

    def commit_record(self, filename: str, quick_key: str, size_bytes: int, timestamp: float):
        self.records[filename] = {
            "quick_key": quick_key,
            "size_bytes": size_bytes,
            "timestamp": timestamp
        }
        with open(self.state_filepath, "w", encoding="utf-8") as state_file:
            json.dump(self.records, state_file, indent=2, ensure_ascii=False)

    def retrieve_record(self, filename: str) -> dict | None:
        return self.records.get(filename)

class MediaFireGateway:
    def __init__(self, settings: SyncSettings):
        self.settings = settings
        self.api = MediaFireApi()
        self.uploader = None
        self._authenticate()

    def _authenticate(self):
        session_token = self.api.user_get_session_token(
            email=self.settings.account_email,
            password=self.settings.account_password,
            app_id=self.settings.client_app_id
        )
        self.api.session = session_token
        self.uploader = MediaFireUploader(self.api)
        logging.info("Authenticated with MediaFire Cloud successfully.")

    def fetch_cloud_files(self, folder_key: str) -> list[dict]:
        try:
            response = self.api.folder_get_content(folder_key=folder_key, content_type="files")
            return response.get("folder_content", {}).get("files", [])
        except Exception as error_message:
            logging.error("Failed fetching cloud files: %s", error_message)
            return []

    def resolve_direct_download_url(self, quick_key: str) -> tuple[str | None, str | None]:
        links_response = self.api.file_get_links(quick_key=quick_key)
        links_collection = links_response.get("links", [])
        if not links_collection:
            return None, None
        normal_url = links_collection[0].get("normal_download", "")
        if not normal_url:
            return None, None

        extracted_name = None
        url_segments = normal_url.split("/")
        if len(url_segments) > 5:
            extracted_name = urllib.parse.unquote(urllib.parse.unquote(url_segments[5]))

        page_response = requests.get(
            normal_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=15
        )
        url_match = re.search(r'href=["\'](https?://download[^"\']+)["\']', page_response.text)
        if not url_match:
            return None, extracted_name
        return url_match.group(1), extracted_name

    def download_file(self, direct_url: str, destination_path: str) -> bool:
        download_response = requests.get(
            direct_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            stream=True,
            timeout=30
        )
        if download_response.status_code != 200:
            return False
        temp_destination = destination_path + ".downloading"
        with open(temp_destination, "wb") as output_stream:
            for chunk_bytes in download_response.iter_content(chunk_size=65536):
                if chunk_bytes:
                    output_stream.write(chunk_bytes)
        
        for attempt_index in range(10):
            try:
                if os.path.exists(destination_path):
                    os.remove(destination_path)
                os.replace(temp_destination, destination_path)
                return True
            except PermissionError:
                time.sleep(1.0)
            except Exception as replace_error:
                logging.warning("File replace attempt %d failed: %s", attempt_index, replace_error)
                time.sleep(1.0)
        return False

    def upload_file(self, source_path: str, filename: str, folder_key: str) -> str | None:
        with open(source_path, "rb") as file_stream:
            upload_outcome = self.uploader.upload(
                file_stream,
                name=filename,
                folder_key=folder_key,
                action_on_duplicate="replace"
            )
            return getattr(upload_outcome, "quickkey", None)

class TwoWaySyncOrchestrator:
    def __init__(self, config_filepath: str):
        self.settings = SyncSettings(config_filepath)
        self.gateway = MediaFireGateway(self.settings)
        state_path = os.path.join(self.settings.local_directory, ".sync_catalog.json")
        self.catalog = SyncCatalog(state_path)
        os.makedirs(self.settings.local_directory, exist_ok=True)

    def _sanitize_filename(self, candidate_name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "_", candidate_name)

    def synchronize_cloud_to_local(self):
        cloud_files = self.gateway.fetch_cloud_files(self.settings.cloud_folder_key)
        for cloud_record in cloud_files:
            quick_key = cloud_record["quickkey"]
            raw_filename = cloud_record.get("filename", "")
            declared_size = int(cloud_record.get("size", 0))

            direct_link, parsed_name = self.gateway.resolve_direct_download_url(quick_key)
            final_name = self._sanitize_filename(parsed_name or raw_filename)
            local_target_path = os.path.join(self.settings.local_directory, final_name)

            catalog_entry = self.catalog.retrieve_record(final_name)
            if catalog_entry and catalog_entry.get("quick_key") != quick_key:
                name_root, ext = os.path.splitext(final_name)
                final_name = f"{name_root}_{quick_key[:6]}{ext}"
                local_target_path = os.path.join(self.settings.local_directory, final_name)
                catalog_entry = self.catalog.retrieve_record(final_name)

            if os.path.exists(local_target_path) and catalog_entry:
                if catalog_entry.get("quick_key") == quick_key and catalog_entry.get("size_bytes") == declared_size:
                    continue

            if not direct_link:
                continue

            logging.info("Downloading from Cloud -> Local: %s", final_name)
            success = self.gateway.download_file(direct_link, local_target_path)
            if success:
                local_mtime = os.path.getmtime(local_target_path)
                self.catalog.commit_record(final_name, quick_key, declared_size, local_mtime)
                logging.info("Download completed: %s", final_name)

    def synchronize_local_to_cloud(self):
        for local_entry in os.listdir(self.settings.local_directory):
            if local_entry.startswith("."):
                continue
            full_local_path = os.path.join(self.settings.local_directory, local_entry)
            if not os.path.isfile(full_local_path) or local_entry.endswith(".downloading"):
                continue

            current_mtime = os.path.getmtime(full_local_path)
            current_size = os.path.getsize(full_local_path)
            catalog_entry = self.catalog.retrieve_record(local_entry)

            if catalog_entry:
                if catalog_entry.get("size_bytes") == current_size and abs(catalog_entry.get("timestamp", 0) - current_mtime) < 1.0:
                    continue

            logging.info("Uploading Local -> Cloud: %s", local_entry)
            assigned_quick_key = self.gateway.upload_file(
                full_local_path,
                local_entry,
                self.settings.cloud_folder_key
            )
            if assigned_quick_key:
                self.catalog.commit_record(local_entry, assigned_quick_key, current_size, current_mtime)
                logging.info("Upload completed: %s (QuickKey: %s)", local_entry, assigned_quick_key)

    def run_continuous_daemon(self):
        logging.info("MediaFire Two-Way Sync Daemon started.")
        logging.info("Local Folder: %s", self.settings.local_directory)
        logging.info("Polling Interval: %d seconds", self.settings.sync_interval_seconds)

        while True:
            try:
                self.synchronize_cloud_to_local()
                self.synchronize_local_to_cloud()
            except Exception as iteration_error:
                logging.error("Error during sync cycle: %s", iteration_error)
            time.sleep(self.settings.sync_interval_seconds)

if __name__ == "__main__":
    try:
        current_directory = os.path.dirname(os.path.abspath(__file__))
        config_location = os.path.join(current_directory, "config.json")
        orchestrator = TwoWaySyncOrchestrator(config_location)
        orchestrator.run_continuous_daemon()
    except Exception as fatal_error:
        logging.exception("Fatal error in sync engine: %s", fatal_error)
