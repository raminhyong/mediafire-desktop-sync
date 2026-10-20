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

def should_ignore_path(target_path: str) -> bool:
    segment_names = [part.lower() for part in re.split(r'[\\/]', target_path)]
    for segment in segment_names:
        if not segment:
            continue
        if segment.startswith(".") or segment.endswith(".downloading"):
            return True
        if segment in ["desktop.ini", "thumbs.db", ".sync_catalog.json", ".sync.lock"]:
            return True
        if segment.startswith("~$"):
            return True
    return False

def sanitize_entry_name(original_name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", original_name).strip()

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
        self.records = {"folders": {"": "myfiles"}, "files": {}}
        self._load_state()

    def _normalize_key(self, raw_path: str) -> str:
        return raw_path.replace("\\", "/").strip("/")

    def _load_state(self):
        if not os.path.exists(self.state_filepath):
            return
        try:
            with open(self.state_filepath, "r", encoding="utf-8") as stream:
                content = json.load(stream)
            if "files" in content or "folders" in content:
                self.records["files"] = content.get("files", {})
                self.records["folders"] = content.get("folders", {"": "myfiles"})
            else:
                self.records["files"] = content
                self.records["folders"] = {"": "myfiles"}
        except Exception as load_error:
            logging.warning("Catalog read failed, resetting state: %s", load_error)

    def _persist(self):
        with open(self.state_filepath, "w", encoding="utf-8") as stream:
            json.dump(self.records, stream, indent=2, ensure_ascii=False)

    def get_folder_key(self, relative_dir: str) -> str | None:
        normalized = self._normalize_key(relative_dir)
        with self._lock:
            return self.records["folders"].get(normalized)

    def set_folder_key(self, relative_dir: str, folder_key: str):
        normalized = self._normalize_key(relative_dir)
        with self._lock:
            self.records["folders"][normalized] = folder_key
            self._persist()

    def remove_folder(self, relative_dir: str):
        normalized = self._normalize_key(relative_dir)
        with self._lock:
            if normalized in self.records["folders"]:
                del self.records["folders"][normalized]
                self._persist()

    def find_folder_by_key(self, folder_key: str) -> str | None:
        with self._lock:
            for path_key, stored_key in self.records["folders"].items():
                if stored_key == folder_key:
                    return path_key
        return None

    def commit_file(self, relative_path: str, quick_key: str, size_bytes: int, timestamp: float):
        normalized = self._normalize_key(relative_path)
        with self._lock:
            self.records["files"][normalized] = {
                "quick_key": quick_key,
                "size_bytes": size_bytes,
                "timestamp": timestamp
            }
            self._persist()

    def retrieve_file(self, relative_path: str) -> dict | None:
        normalized = self._normalize_key(relative_path)
        with self._lock:
            return self.records["files"].get(normalized)

    def remove_file(self, relative_path: str):
        normalized = self._normalize_key(relative_path)
        with self._lock:
            if normalized in self.records["files"]:
                del self.records["files"][normalized]
                self._persist()

    def find_file_by_quick_key(self, quick_key: str) -> tuple[str, dict] | tuple[None, None]:
        with self._lock:
            for path_key, file_metadata in self.records["files"].items():
                if file_metadata.get("quick_key") == quick_key:
                    return path_key, file_metadata
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

    def fetch_cloud_folders(self, folder_key: str) -> list[dict]:
        for attempt_index in range(3):
            try:
                response = self.api.folder_get_content(folder_key=folder_key, content_type="folders")
                return response.get("folder_content", {}).get("folders", [])
            except MediaFireApiError as api_error:
                logging.warning("API error fetching folders, re-authenticating: %s", api_error)
                self.authenticate()
            except Exception as connection_error:
                logging.warning("Connection error fetching folders (attempt %d): %s", attempt_index, connection_error)
                time.sleep(2.0)
        return []

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

    def create_remote_folder(self, folder_name: str, parent_key: str) -> str | None:
        try:
            outcome = self.api.folder_create(foldername=folder_name, parent_key=parent_key)
            return outcome.get("folder_key")
        except MediaFireApiError as api_error:
            logging.warning("Failed creating folder %s: %s", folder_name, api_error)
            return None

    def delete_remote_folder(self, folder_key: str) -> bool:
        try:
            outcome = self.api.folder_delete(folder_key=folder_key)
            return outcome.get("result") == "Success"
        except Exception as delete_error:
            logging.error("Failed to delete remote folder %s: %s", folder_key, delete_error)
            return False

    def delete_remote_file(self, quick_key: str) -> bool:
        try:
            outcome = self.api.file_delete(quick_key=quick_key)
            return outcome.get("result") == "Success"
        except Exception as delete_error:
            logging.error("Failed to delete remote file %s: %s", quick_key, delete_error)
            return False

    def resolve_download_url(self, quick_key: str) -> str | None:
        try:
            links_response = self.api.file_get_links(quick_key=quick_key)
            links_collection = links_response.get("links", [])
            if not links_collection:
                return None
            normal_url = links_collection[0].get("normal_download", "")
            if not normal_url:
                return None

            page_response = requests.get(
                normal_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=15
            )
            match = re.search(r'href=["\'](https?://download[^"\']+)["\']', page_response.text)
            return match.group(1) if match else None
        except Exception as link_error:
            logging.error("Failed resolving download link for %s: %s", quick_key, link_error)
            return None

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
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
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

class LocalTreeWatcher(FileSystemEventHandler):
    def __init__(self, upload_queue: queue.Queue, delete_queue: queue.Queue, local_directory: str):
        super().__init__()
        self.upload_queue = upload_queue
        self.delete_queue = delete_queue
        self.local_directory = local_directory

    def on_created(self, event):
        if should_ignore_path(event.src_path):
            return
        self.upload_queue.put({"action": "upsert", "path": event.src_path, "is_directory": event.is_directory})

    def on_modified(self, event):
        if event.is_directory or should_ignore_path(event.src_path):
            return
        self.upload_queue.put({"action": "upsert", "path": event.src_path, "is_directory": False})

    def on_moved(self, event):
        if should_ignore_path(event.dest_path):
            return
        if not should_ignore_path(event.src_path):
            self.delete_queue.put({"path": event.src_path, "is_directory": event.is_directory})
        self.upload_queue.put({"action": "upsert", "path": event.dest_path, "is_directory": event.is_directory})

    def on_deleted(self, event):
        if should_ignore_path(event.src_path):
            return
        self.delete_queue.put({"path": event.src_path, "is_directory": event.is_directory})

class TwoWaySyncService:
    def __init__(self, config_filepath: str):
        self.config = SyncConfiguration(config_filepath)
        self.client = MediaFireClient(self.config)
        base_dir = os.path.dirname(os.path.abspath(config_filepath))
        state_file = os.path.join(base_dir, ".sync_catalog.json")
        self.catalog = CatalogStore(state_file)
        self.upload_queue = queue.Queue()
        self.delete_queue = queue.Queue()
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

    def _resolve_remote_folder_key(self, relative_dir: str) -> str:
        clean_dir = relative_dir.replace("\\", "/").strip("/")
        if not clean_dir:
            return self.config.cloud_folder_key

        cached_key = self.catalog.get_folder_key(clean_dir)
        if cached_key:
            return cached_key

        parent_dir, current_name = os.path.split(clean_dir)
        parent_folder_key = self._resolve_remote_folder_key(parent_dir)

        existing_folders = self.client.fetch_cloud_folders(parent_folder_key)
        for folder_node in existing_folders:
            if sanitize_entry_name(folder_node["name"]).lower() == current_name.lower():
                assigned_key = folder_node["folderkey"]
                self.catalog.set_folder_key(clean_dir, assigned_key)
                return assigned_key

        created_key = self.client.create_remote_folder(current_name, parent_folder_key)
        if created_key:
            self.catalog.set_folder_key(clean_dir, created_key)
            logging.info("[FOLDER CREATED] Remote folder created: %s (Key: %s)", clean_dir, created_key)
            return created_key
        return parent_folder_key

    def _process_single_upload(self, full_path: str, is_directory: bool):
        relative_path = os.path.relpath(full_path, self.config.local_directory)
        if is_directory:
            self._resolve_remote_folder_key(relative_path)
            return

        if not self._is_file_ready(full_path):
            return

        size_bytes = os.path.getsize(full_path)
        timestamp = os.path.getmtime(full_path)
        record = self.catalog.retrieve_file(relative_path)
        if record and record.get("size_bytes") == size_bytes:
            if abs(record.get("timestamp", 0) - timestamp) < 1.0:
                return

        parent_dir = os.path.dirname(relative_path)
        file_name = os.path.basename(full_path)
        target_folder_key = self._resolve_remote_folder_key(parent_dir)

        logging.info("[REALTIME UPLOAD] Uploading: %s (%d bytes)", relative_path, size_bytes)
        quick_key = self.client.upload_file(full_path, file_name, target_folder_key)
        if quick_key:
            self.catalog.commit_file(relative_path, quick_key, size_bytes, timestamp)
            logging.info("[REALTIME UPLOAD SUCCESS] Completed: %s (QuickKey: %s)", relative_path, quick_key)

    def _process_single_delete(self, full_path: str, is_directory: bool):
        relative_path = os.path.relpath(full_path, self.config.local_directory)
        if is_directory:
            folder_key = self.catalog.get_folder_key(relative_path)
            if folder_key and folder_key != self.config.cloud_folder_key:
                logging.info("[REMOTE DELETE] Deleting cloud folder: %s", relative_path)
                if self.client.delete_remote_folder(folder_key):
                    self.catalog.remove_folder(relative_path)
            return

        record = self.catalog.retrieve_file(relative_path)
        if record:
            quick_key = record.get("quick_key")
            logging.info("[REMOTE DELETE] Deleting cloud file: %s (QuickKey: %s)", relative_path, quick_key)
            if self.client.delete_remote_file(quick_key):
                self.catalog.remove_file(relative_path)

    def _worker_loop(self):
        while not self._shutdown_event.is_set():
            try:
                task_event = self.upload_queue.get(timeout=0.5)
                self._process_single_upload(task_event["path"], task_event["is_directory"])
                self.upload_queue.task_done()
            except queue.Empty:
                pass
            except Exception as worker_error:
                logging.error("Worker error handling upload: %s", worker_error)

            try:
                del_event = self.delete_queue.get_nowait()
                self._process_single_delete(del_event["path"], del_event["is_directory"])
                self.delete_queue.task_done()
            except queue.Empty:
                pass
            except Exception as del_error:
                logging.error("Worker error handling delete: %s", del_error)

    def _sync_cloud_tree(self, cloud_folder_key: str, relative_dir: str):
        local_dir_path = os.path.normpath(os.path.join(self.config.local_directory, relative_dir))
        os.makedirs(local_dir_path, exist_ok=True)
        self.catalog.set_folder_key(relative_dir, cloud_folder_key)

        cloud_subfolders = self.client.fetch_cloud_folders(cloud_folder_key)
        for folder_node in cloud_subfolders:
            subfolder_name = sanitize_entry_name(folder_node["name"])
            subfolder_key = folder_node["folderkey"]
            sub_relative_dir = os.path.normpath(os.path.join(relative_dir, subfolder_name))
            self._sync_cloud_tree(subfolder_key, sub_relative_dir)

        cloud_files = self.client.fetch_cloud_files(cloud_folder_key)
        for file_node in cloud_files:
            quick_key = file_node["quickkey"]
            file_name = sanitize_entry_name(file_node.get("filename", ""))
            declared_size = int(file_node.get("size", 0))

            relative_file_path = os.path.normpath(os.path.join(relative_dir, file_name))
            matched_path, record = self.catalog.find_file_by_quick_key(quick_key)
            target_rel_path = matched_path if matched_path else relative_file_path
            target_local_path = os.path.join(self.config.local_directory, target_rel_path)

            if os.path.exists(target_local_path) and os.path.getsize(target_local_path) == declared_size:
                if not record:
                    self.catalog.commit_file(target_rel_path, quick_key, declared_size, os.path.getmtime(target_local_path))
                continue

            if not os.path.exists(target_local_path):
                alt_name = target_rel_path + ".mp4"
                alt_path = os.path.join(self.config.local_directory, alt_name)
                if os.path.exists(alt_path) and os.path.getsize(alt_path) == declared_size:
                    self.catalog.commit_file(alt_name, quick_key, declared_size, os.path.getmtime(alt_path))
                    continue

            direct_url = self.client.resolve_download_url(quick_key)
            if not direct_url:
                continue

            logging.info("[CLOUD DOWNLOAD] Downloading: %s", target_rel_path)
            if self.client.download_file(direct_url, target_local_path):
                self.catalog.commit_file(target_rel_path, quick_key, declared_size, os.path.getmtime(target_local_path))
                logging.info("[CLOUD DOWNLOAD SUCCESS] Completed: %s", target_rel_path)

    def _enqueue_initial_local_tree(self, current_dir: str):
        for root_path, dirnames, filenames in os.walk(current_dir):
            for dirname in dirnames:
                dirpath = os.path.join(root_path, dirname)
                if not should_ignore_path(dirpath):
                    self.upload_queue.put({"action": "upsert", "path": dirpath, "is_directory": True})
            for filename in filenames:
                filepath = os.path.join(root_path, filename)
                if not should_ignore_path(filepath):
                    self.upload_queue.put({"action": "upsert", "path": filepath, "is_directory": False})

    def start_service(self):
        logging.info("MediaFire Full Two-Way Recursive Sync Service started.")
        logging.info("Directory: %s", self.config.local_directory)

        worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        worker_thread.start()

        event_handler = LocalTreeWatcher(self.upload_queue, self.delete_queue, self.config.local_directory)
        observer = Observer()
        observer.schedule(event_handler, self.config.local_directory, recursive=True)
        observer.start()

        self._enqueue_initial_local_tree(self.config.local_directory)

        try:
            while not self._shutdown_event.is_set():
                try:
                    self._sync_cloud_tree(self.config.cloud_folder_key, "")
                except Exception as tree_error:
                    logging.error("Cloud synchronization tree error: %s", tree_error)
                time.sleep(self.config.sync_interval_seconds)
        except BaseException as exit_signal:
            logging.exception("Fatal service loop interrupted: %s", exit_signal)
        finally:
            logging.info("Shutting down recursive service observer...")
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
