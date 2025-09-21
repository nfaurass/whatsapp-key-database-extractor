#!/usr/bin/env python3
import subprocess
import os
import sys
import shutil
import json
from datetime import datetime
import whatsapp_config as config

# Directories from config
ADB_PATH = os.path.normpath(config.ADB_PATH)
ABE_JAR_PATH = os.path.normpath(config.ABE_JAR_PATH)
TAR_PATH = os.path.normpath(config.TAR_PATH)
LEGACY_WHATSAPP_APK = os.path.normpath(config.LEGACY_WHATSAPP_APK)
DATA_DIR = os.path.normpath(config.DATA_DIR)
LOGS_DIR = os.path.normpath(config.LOGS_DIR)

# Ensure dirs exist
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Unique logfile for this run
LOG_FILE = os.path.join(LOGS_DIR, f"run-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.log")

# Metadata for this run
metadata = {}


def log_console(msg):
    print(msg)


def log_file(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def log_both(msg):
    log_console(msg)
    log_file(msg)


def run(cmd, capture=False):
    log_file(f"$ {' '.join(cmd)}")
    try:
        if capture:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if result.stdout.strip():
                log_file(result.stdout.strip())
            if result.stderr.strip():
                log_file(result.stderr.strip())
            return result.stdout.strip()
        else:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if result.stdout.strip():
                log_file(result.stdout.strip())
            if result.stderr.strip():
                log_file(result.stderr.strip())
            return None
    except subprocess.CalledProcessError as e:
        log_file(f"[✖] Failed: {' '.join(cmd)}")
        log_file(f"STDOUT:\n{e.stdout}")
        log_file(f"STDERR:\n{e.stderr}")
        log_console(f"[✖] Failed: {' '.join(cmd)} (see log file)")
        sys.exit(1)


def ensure_setup():
    if not shutil.which(ADB_PATH):
        sys.exit(f"[!] adb not found at {ADB_PATH}")

    if not os.path.exists(LEGACY_WHATSAPP_APK):
        sys.exit(f"[!] Legacy WhatsApp APK missing at {LEGACY_WHATSAPP_APK}")

    if not os.path.exists(ABE_JAR_PATH):
        sys.exit(f"[!] ABE.jar missing at {ABE_JAR_PATH}")

    if not os.path.exists(TAR_PATH):
        sys.exit(f"[!] tar not found at {TAR_PATH}")


def adb_stop():
    log_both("[*] Stopping ADB server...")
    result = subprocess.run([ADB_PATH, "kill-server"], capture_output=True, text=True)
    if result.returncode == 0:
        log_both("[✔] ADB server stopped")
    else:
        log_both(f"[✖] Failed to stop ADB server: {result.stderr.strip()}")


def adb_init():
    log_both("[*] Initializing ADB...")
    subprocess.run([ADB_PATH, "kill-server"])
    subprocess.run([ADB_PATH, "start-server"])
    subprocess.run([ADB_PATH, "wait-for-device"])
    devices = run([ADB_PATH, "devices"], capture=True).splitlines()[1:]
    if not any("device" in d for d in devices):
        sys.exit("[!] No devices connected")
    log_both("[✔] Device connected")


def get_metadata():
    sdk = run([ADB_PATH, "shell", "getprop", "ro.build.version.sdk"], capture=True)
    apk_path = run([ADB_PATH, "shell", "pm", "path", "com.whatsapp"], capture=True).replace("package:", "")
    version_info = run([ADB_PATH, "shell", "dumpsys", "package", "com.whatsapp"], capture=True)
    version = next((l.split("=")[1] for l in version_info.splitlines() if "versionName=" in l), "unknown")
    sd_path = run([ADB_PATH, "shell", "echo", "$EXTERNAL_STORAGE"], capture=True)

    metadata.update({"sdk": sdk, "apk_path": apk_path, "version": version, "sd_path": sd_path})
    log_both(f"[✔] Metadata collected: SDK={sdk}, Version={version}")
    return metadata


def backup_apk(apk_path, version):
    out = os.path.join(DATA_DIR, f"WhatsApp-backup-{version}.apk")
    log_both("[*] Backing up WhatsApp APK...")
    run([ADB_PATH, "pull", apk_path, out])
    log_both(f"[✔] APK saved -> {out}")


def install_legacy():
    log_both("[*] Installing legacy WhatsApp...")
    run([ADB_PATH, "install", "-r", "-d", LEGACY_WHATSAPP_APK])
    log_both("[✔] Legacy WhatsApp installed")


def backup_data():
    backup_file = os.path.join(DATA_DIR, "whatsapp.ab")
    log_both("[*] Creating WhatsApp backup (confirm on device)... This may take a few minutes.")

    result = subprocess.call([ADB_PATH, "backup", "-f", backup_file, "com.whatsapp"])

    if os.path.exists(backup_file) and os.path.getsize(backup_file) > 2048:
        log_both(f"[✔] Data backup saved -> {backup_file}")
    else:
        sys.exit("[✖] Backup file too small, likely failed")

    return backup_file


def unpack_ab_to_tar(ab_file):
    log_both("[*] Unpacking .ab to .tar using ABE...")
    tar_file = ab_file.replace(".ab", ".tar")

    password = input("Enter backup password (leave empty if none): ").strip()
    if not password:
        password = None

    cmd = ["java", "-jar", ABE_JAR_PATH, "unpack", ab_file, tar_file]
    if password:
        cmd.append(password)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        sys.exit("[✖] Failed to unpack .ab to .tar. Check ABE and Java installation.")

    if not os.path.exists(tar_file) or os.path.getsize(tar_file) == 0:
        sys.exit(f"[✖] TAR file not created or empty: {tar_file}")

    log_both(f"[✔] Unpacked .tar saved -> {tar_file}")

    return tar_file


def extract_whatsapp_files(tar_file):
    files_to_extract = [
        "apps/com.whatsapp/f/key",
        "apps/com.whatsapp/db/msgstore.db",
        "apps/com.whatsapp/db/msgstore.db-shm",
        "apps/com.whatsapp/db/msgstore.db-wal",
        "apps/com.whatsapp/db/wa.db",
        "apps/com.whatsapp/db/wa.db-shm",
        "apps/com.whatsapp/db/wa.db-wal",
        "apps/com.whatsapp/db/axolotl.db",
        "apps/com.whatsapp/db/axolotl.db-shm",
        "apps/com.whatsapp/db/axolotl.db-wal",
        "apps/com.whatsapp/db/chatsettings.db",
        "apps/com.whatsapp/db/chatsettings.db-shm",
        "apps/com.whatsapp/db/chatsettings.db-wal"
    ]

    log_both(f"[*] Extracting {len(files_to_extract)} files from {tar_file} to {DATA_DIR}...")

    safe_data_dir = os.path.relpath(DATA_DIR)
    safe_tar_file = os.path.abspath(tar_file).replace("\\", "/")

    cmd = [TAR_PATH, "xvf", safe_tar_file, "-C", safe_data_dir] + files_to_extract
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log_both(f"[✖] Extraction failed: {result.stderr.strip()}")
        return
    else:
        log_both(f"[✔] Extraction completed.")

    for path in files_to_extract:
        src = os.path.join(DATA_DIR, path)
        if src.startswith(os.path.join(DATA_DIR, "apps")):
            dst = os.path.join(DATA_DIR, path[len("apps/"):])
        else:
            dst = src
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            log_file(f"[→] Moved {src} → {dst}")

    key_path = os.path.join(DATA_DIR, "com.whatsapp/f/key")
    if os.path.exists(key_path):
        key_size = os.path.getsize(key_path)
        log_both(f"[i] Key file found: {key_path} (~{key_size} bytes)")
    else:
        log_both(f"[!] Key file not found: {key_path}")

    db_dir = os.path.join(DATA_DIR, "com.whatsapp/db")
    if os.path.exists(db_dir):
        db_files = os.listdir(db_dir)
        log_both(f"[i] Extracted DB files: {', '.join(db_files)}")
    else:
        log_both("[!] No database files extracted.")

    apps_dir = os.path.join(DATA_DIR, "apps")
    if os.path.exists(apps_dir):
        try:
            shutil.rmtree(apps_dir)
            log_both(f"[i] Removed empty 'apps/' folder: {apps_dir}")
        except Exception as e:
            log_both(f"[!] Could not remove 'apps/' folder: {e}")


def push_key_to_device_again():
    local_key_path = os.path.join(DATA_DIR, "com.whatsapp/f/key")

    if not os.path.exists(local_key_path):
        log_both(f"[!] Key file not found locally: {local_key_path}")
        return

    sd_path = metadata.get("sd_path")
    if not sd_path:
        log_both("[!] Could not detect device storage path")
        return

    log_both(f"[*] Device storage path detected: {sd_path}")

    run([ADB_PATH, "shell", "mkdir", "-p", f"{sd_path}/WhatsApp/Databases"])

    device_target = f"{sd_path}/WhatsApp/Databases/.nomedia"

    run([ADB_PATH, "push", local_key_path, device_target])

    log_both(f"[✔] Key pushed successfully to {device_target}")

    check = run([ADB_PATH, "shell", "ls", "-l", device_target], capture=True)
    log_both(f"[*] Device check:\n{check}")

    if ".nomedia" in check or "key" in check:
        log_both("[✔] Key presence verified on device")
    else:
        log_both("[✖] Key not found on device after push")


def restore_original_apk():
    whatsapp_backup_apk = os.path.join(DATA_DIR, f"WhatsApp-backup-{metadata['version']}.apk")

    if not os.path.exists(whatsapp_backup_apk):
        log_both("[!] No backup APK found. You can reinstall WhatsApp from Play Store manually.")
        return

    log_both(f"[*] Restoring original WhatsApp APK: {whatsapp_backup_apk}")

    output = run([ADB_PATH, "install", "-r", whatsapp_backup_apk], capture=True)
    log_both(f"[✔] Original APK restored successfully")
    if output:
        log_both(output)


def main():
    log_both("=" * 50)
    log_both("=== WhatsApp Key & Database Extractor Started ===")
    log_both("=" * 50)
    ensure_setup()
    adb_init()
    meta = get_metadata()
    backup_apk(meta["apk_path"], meta["version"])
    install_legacy()
    ab_file = backup_data()
    tar_file = unpack_ab_to_tar(ab_file)
    extract_whatsapp_files(tar_file)
    push_key_to_device_again()
    restore_original_apk()
    adb_stop()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n=== Metadata ===\n")
        f.write(json.dumps(metadata, indent=2))

    log_both("=" * 50)
    log_both("========== Run Completed Successfully! ==========")
    log_both("=" * 50)
    log_console(f"[i] Full log saved at: {LOG_FILE}")


if __name__ == "__main__":
    main()
