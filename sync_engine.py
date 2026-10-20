import os
import re
import sys
import time
import json
import logging
import threading
import queue
import urllib.parse
import requests
import msvcrt
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from mediafire import MediaFireApi, MediaFireApiError
from mediafire.uploader import MediaFireUploader

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

log_handlers = [
    FlushingFileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_activity.log"), encoding="utf-8")
]
if sys.stdout and hasattr(sys.stdout, "write") and not getattr(sys.stdout, "name", "").endswith("null"):
    log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers
)

class FileInstanceLock:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file_handle = None

    def acquire(self) -> bool:
        try:
            self.file_handle = open(self.filepath, "w")
            msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except (IOError, OSError):
            return False

def should_ignore_file(path: str) -> bool:
    base = os.path.basename(path).lower()
    if base.startswith(".") or base.endswith(".downloading"):
        return True
    if base in ["desktop.ini", "thumbs.db", ".sync_catalog.json", ".sync.lock"] or base.startswith("~$"):
        return True
    return False

class SyncConfiguration:
    def __init__(self, config_filepath: str):
        with open(config_filepath, "r", encoding="utf-8") as stream:
            settings_map = json.load(stream)
        self.account_email = settings_map["email"]
        self.account_password = settings_map["password"]
        self.client_app_id = settings_map.get("app_id", "42511")
        target_path = settings_map["sync_directory"]
        if not os.path.isabs(target_path):
            base_dir = os.path.dirname(os.path.abspath(config_filepath))
            self.local_directory = os.path.normpath(os.path.join(base_dir, target_path))
        else:
            self.local_directory = os.path.normpath(target_path)
        self.cloud_folder_key = settings_map.get("remote_folder_key", "myfiles")
        self.sync_interval_seconds = settings_map.get("poll_interval_seconds", 20)

class CatalogStore:
    def __init__(self, state_filepath: str):
        self.state_filepath = state_filepath
        self._lock = threading.Lock()
        self.records = self._read_state()

    def _read_state(self) -> dict:
        if not os.path.exists(self.state_filepath):
            return {}
        try:
            with open(self.state_filepath, "r", encoding="utf-8") as stream:
                return json.load(stream)
        except Exception:
            return {}

    def commit_record(self, filename: str, quick_key: str, size_bytes: int, timestamp: float):
        with self._lock:
            self.records[filename] = {
                "quick_key": quick_key,
                "size_bytes": size_bytes,
                "timestamp": timestamp
            }
            with open(self.state_filepath, "w", encoding="utf-8") as stream:
                json.dump(self.records, stream, indent=2, ensure_ascii=False)

    def retrieve_record(self, filename: str) -> dict | None:
        with self._lock:
            return self.records.get(filename)

    def find_by_quick_key(self, quick_key: str) -> tuple[str, dict] | tuple[None, None]:
        with self._lock:
            for entry_name, entry_data in self.records.items():
                if entry_data.get("quick_key") == quick_key:
                    return entry_name, entry_data
        return None, None

class MediaFireClient:
    def __init__(self, config: SyncConfiguration):
        self.config = config
        self.api = MediaFireApi()
        self.uploader = None
        self._auth_lock = threading.Lock()
        self.authenticate()

    def authenticate(self):
        with self._auth_lock:
            token = self.api.user_get_session_token(
                email=self.config.account_email,
                password=self.config.account_password,
                app_id=self.config.client_app_id
            )
            self.api.session = token
            self.uploader = MediaFireUploader(self.api)
            logging.info("Authenticated with MediaFire Cloud successfully.")

    def fetch_cloud_files(self, folder_key: str) -> list[dict]:
        for attempt_index in range(3):
            try:
                response = self.api.folder_get_content(folder_key=folder_key, content_type="files")
                return response.get("folder_content", {}).get("files", [])
            except MediaFireApiError as api_error:
                logging.warning("API error fetching files, re-authenticating: %s", api_error)
                self.authenticate()
            except Exception as connection_error:
                logging.warning("Connection failure fetching files (attempt %d): %s", attempt_index, connection_error)
                time.sleep(2.0)
        return []

    def resolve_download_url(self, quick_key: str) -> tuple[str | None, str | None]:
        try:
            links_response = self.api.file_get_links(quick_key=quick_key)
            links_collection = links_response.get("links", [])
            if not links_collection:
                return None, None
            normal_url = links_collection[0].get("normal_download", "")
            if not normal_url:
                return None, None

            page_response = requests.get(
                normal_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=15
            )
            match = re.search(r'href=["\'](https?://download[^"\']+)["\']', page_response.text)
            direct_url = match.group(1) if match else None
            return direct_url, None
        except Exception as link_error:
            logging.error("Failed resolving download link for %s: %s", quick_key, link_error)
            return None, None

    def download_file(self, direct_url: str, destination_path: str) -> bool:
        temp_destination = destination_path + ".downloading"
        try:
            download_response = requests.get(
                direct_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                stream=True,
                timeout=45
            )
            if download_response.status_code != 200:
                return False
            with open(temp_destination, "wb") as output_stream:
                for chunk in download_response.iter_content(chunk_size=65536):
                    if chunk:
                        output_stream.write(chunk)

            if os.path.exists(destination_path):
                os.remove(destination_path)
            os.replace(temp_destination, destination_path)
            return True
        except Exception as transfer_error:
            logging.error("Download failed for %s: %s", destination_path, transfer_error)
            if os.path.exists(temp_destination):
                try:
                    os.remove(temp_destination)
                except OSError:
                    pass
            return False

    def upload_file(self, source_path: str, filename: str, folder_key: str) -> str | None:
        for attempt_index in range(3):
            try:
                with open(source_path, "rb") as file_stream:
                    outcome = self.uploader.upload(
                        file_stream,
                        name=filename,
                        folder_key=folder_key,
                        action_on_duplicate="replace"
                    )
                    return getattr(outcome, "quickkey", None)
            except MediaFireApiError as api_error:
                logging.warning("Upload API error, re-authenticating: %s", api_error)
                self.authenticate()
            except Exception as upload_error:
                logging.warning("Upload attempt %d failed: %s", attempt_index, upload_error)
                time.sleep(2.0)
        return None

def should_ignore_file(path: str) -> bool:
    base = os.path.basename(path).lower()
    if base.startswith(".") or base.endswith(".downloading"):
        return True
    if base in ["desktop.ini", "thumbs.db", ".sync_catalog.json"] or base.startswith("~$"):
        return True
    return False

class LocalFileWatcher(FileSystemEventHandler):
    def __init__(self, upload_queue: queue.Queue, local_directory: str):
        super().__init__()
        self.upload_queue = upload_queue
        self.local_directory = local_directory

    def on_created(self, event):
        if event.is_directory or should_ignore_file(event.src_path):
            return
        self.upload_queue.put(event.src_path)

    def on_modified(self, event):
        if event.is_directory or should_ignore_file(event.src_path):
            return
        self.upload_queue.put(event.src_path)

    def on_moved(self, event):
        if event.is_directory or should_ignore_file(event.dest_path):
            return
        self.upload_queue.put(event.dest_path)

class TwoWaySyncService:
    def __init__(self, config_filepath: str):
        self.config = SyncConfiguration(config_filepath)
        self.client = MediaFireClient(self.config)
        state_file = os.path.join(self.config.local_directory, ".sync_catalog.json")
        self.catalog = CatalogStore(state_file)
        self.upload_queue = queue.Queue()
        os.makedirs(self.config.local_directory, exist_ok=True)
        self._shutdown_event = threading.Event()

    def _is_file_ready(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        try:
            first_size = os.path.getsize(filepath)
            time.sleep(0.8)
            second_size = os.path.getsize(filepath)
            if first_size != second_size:
                return False
            with open(filepath, "rb"):
                return True
        except (PermissionError, OSError):
            return False

    def _process_single_upload(self, filepath: str):
        if not self._is_file_ready(filepath):
            return
        filename = os.path.basename(filepath)
        size_bytes = os.path.getsize(filepath)
        timestamp = os.path.getmtime(filepath)

        record = self.catalog.retrieve_record(filename)
        if record and record.get("size_bytes") == size_bytes:
            if abs(record.get("timestamp", 0) - timestamp) < 1.0:
                return

        logging.info("[REALTIME UPLOAD] Uploading: %s (%d bytes)", filename, size_bytes)
        quick_key = self.client.upload_file(filepath, filename, self.config.cloud_folder_key)
        if quick_key:
            self.catalog.commit_record(filename, quick_key, size_bytes, timestamp)
            logging.info("[REALTIME UPLOAD SUCCESS] Completed: %s (QuickKey: %s)", filename, quick_key)

    def _upload_worker_loop(self):
        while not self._shutdown_event.is_set():
            try:
                filepath = self.upload_queue.get(timeout=1.0)
                self._process_single_upload(filepath)
                self.upload_queue.task_done()
            except queue.Empty:
                continue
            except Exception as worker_error:
                logging.error("Worker error handling upload: %s", worker_error)

    def _sync_cloud_to_local_cycle(self):
        cloud_files = self.client.fetch_cloud_files(self.config.cloud_folder_key)
        for cloud_item in cloud_files:
            quick_key = cloud_item["quickkey"]
            filename = cloud_item.get("filename", "")
            declared_size = int(cloud_item.get("size", 0))

            matched_name, record = self.catalog.find_by_quick_key(quick_key)
            target_name = matched_name if matched_name else filename
            target_path = os.path.join(self.config.local_directory, target_name)

            if os.path.exists(target_path) and os.path.getsize(target_path) == declared_size:
                if not record:
                    self.catalog.commit_record(target_name, quick_key, declared_size, os.path.getmtime(target_path))
                continue

            if not os.path.exists(target_path):
                alt_name = target_name + ".mp4"
                alt_path = os.path.join(self.config.local_directory, alt_name)
                if os.path.exists(alt_path) and os.path.getsize(alt_path) == declared_size:
                    self.catalog.commit_record(alt_name, quick_key, declared_size, os.path.getmtime(alt_path))
                    continue

            direct_url, _ = self.client.resolve_download_url(quick_key)
            if not direct_url:
                continue

            logging.info("[CLOUD DOWNLOAD] Downloading: %s", target_name)
            if self.client.download_file(direct_url, target_path):
                self.catalog.commit_record(target_name, quick_key, declared_size, os.path.getmtime(target_path))
                logging.info("[CLOUD DOWNLOAD SUCCESS] Completed: %s", target_name)

    def start_service(self):
        logging.info("MediaFire Real-Time Two-Way Sync Service started.")
        logging.info("Directory: %s", self.config.local_directory)

        worker_thread = threading.Thread(target=self._upload_worker_loop, daemon=True)
        worker_thread.start()

        event_handler = LocalFileWatcher(self.upload_queue, self.config.local_directory)
        observer = Observer()
        observer.schedule(event_handler, self.config.local_directory, recursive=False)
        observer.start()

        for initial_name in os.listdir(self.config.local_directory):
            initial_path = os.path.join(self.config.local_directory, initial_name)
            if os.path.isfile(initial_path) and not should_ignore_file(initial_path):
                self.upload_queue.put(initial_path)

        try:
            while not self._shutdown_event.is_set():
                try:
                    self._sync_cloud_to_local_cycle()
                except Exception as cycle_error:
                    logging.error("Cloud download cycle error: %s", cycle_error)
                time.sleep(self.config.sync_interval_seconds)
        except BaseException as outer_error:
            logging.exception("Fatal unhandled exception in main loop: %s", outer_error)
        finally:
            logging.info("Shutting down service and stopping observer...")
            self._shutdown_event.set()
            observer.stop()
            observer.join()
            logging.info("Service shutdown completed.")

if __name__ == "__main__":
    base_directory = os.path.dirname(os.path.abspath(__file__))
    lock_path = os.path.join(base_directory, ".sync.lock")
    instance_lock = FileInstanceLock(lock_path)
    if not instance_lock.acquire():
        logging.warning("Another instance of MediaFire sync engine is already active. Exiting.")
        sys.exit(0)

    try:
        config_path = os.path.join(base_directory, "config.json")
        sync_service = TwoWaySyncService(config_path)
        sync_service.start_service()
    except Exception as fatal_exception:
        logging.exception("Fatal unhandled exception in sync engine: %s", fatal_exception)
