import subprocess
import threading
import logging
import os
import shutil
import signal
from time import sleep

JAR_PATH = "C:\\Users\\colli\\fakeServer\\server.jar"
LOG_PATH = "C:\\Users\\colli\\serverService\\server_manager.log"
SERVER_PATH = "C:\\Users\\colli\\fakeServer"
BACKUP_DIR = "C:\\Users\\colli\\backupFakeServer"
SAVE_INTERVAL_SEC = 600 # 10 minutes
BACKUP_INTERVAL_SEC = 60 * 60 * 24 # 1 day
STOP_THREADS_FLAG = threading.Event()

def start_server_jar(jar_path: str) -> subprocess.Popen:
    """
    Function that initially kicks off server, and returns the subprocess obj
    """
    logging.info('starting server jar...')
    server_process = subprocess.Popen(['java', '-jar', jar_path, '--nogui'],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,
                                      universal_newlines=True,
                                      cwd=SERVER_PATH)
    return server_process

def send_server_command(server_process: subprocess.Popen, command: str):
    """
    Wrapper function for sending commands to the server jar
    """
    logging.debug(f'sending command: {command}')
    server_process.stdin.write(command + '\r')
    server_process.stdin.flush()

def periodic_save(server_process: subprocess.Popen, interval_sec: int) -> None:
    # modular sleeps into seconds to check for the stop threads flag
    logging.debug("Running initial wait on periodic save thread")
    for _ in range(interval_sec):
        if not STOP_THREADS_FLAG.is_set():
            sleep(1)
        else:
            break
    while True and not STOP_THREADS_FLAG.is_set():
        # Send the save command to the server process
        logging.info('saving the server...')
        send_server_command(server_process, "save-all")
        
        logging.debug("Running periodic wait on save thread")
        for _ in range(interval_sec):
            if not STOP_THREADS_FLAG.is_set():
                sleep(1)
            else:
                break

def copy_files(src_dir: str, dest_dir: str):
    """
    Generic function to copy all files and subdirectories to a new dir
    Creates the dir if it's not already there
    """
    try:
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            logging.debug(f"Created backup dir at: {dest_dir}")
        else:
            logging.debug(f"Backup dir {dest_dir} already exists")
    except OSError as exc:
        logging.error(f"Error creating backup dir: {dest_dir}: {exc}")
        raise exc

    try:
        # shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
        # Copy all files and directories recursively from src_dir to dest_dir
        for root, dirs, files in os.walk(src_dir):
            for dir in dirs:
                src_subdir = os.path.join(root, dir)
                dest_subdir = os.path.join(dest_dir, os.path.relpath(src_subdir, src_dir))
                try:
                    os.makedirs(dest_subdir)
                except FileExistsError:
                    pass
            for file in files:
                # skip server filelocks - this will fail and halt the copy
                if ".lock" in file:
                    pass
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, os.path.relpath(src_file, src_dir))
                try:
                    shutil.copy2(src_file, dest_file)
                    # logging.info(f"File '{src_file}' copied to '{dest_file}' successfully.")
                except Exception as e:
                    logging.error(f"Failed to copy '{src_file}' to '{dest_file}': {e}")

    except Exception as exc:
        logging.error(f"Couldn't copy src {src_dir} to dest {dest_dir}: {exc}")
        raise exc
    
    logging.debug("All files copied successfully.")

def periodic_backup(interval_sec: int, backup_dir: str) -> None:
    """
    Wrapper func for a periodic backup of all files to a specified directory
    Do not fail and kill process if we cannot backup files - just create a strong critical
    entry
    """
    while True and not STOP_THREADS_FLAG.is_set():
        try:
            logging.info(f"Backing up server files to {backup_dir}")
            copy_files(src_dir=SERVER_PATH, dest_dir=backup_dir)
        except Exception as exc:
            logging.critical(f"Could not backup files to {backup_dir}: {exc}")
        
        # modular sleeps into seconds to check for the stop threads flag
        logging.info("Running periodic wait on backup thread")
        for _ in range(interval_sec):
            if not STOP_THREADS_FLAG.is_set():
                sleep(1)
            else:
                break

def main():
    """
    Main func to create and handle the server jar process
    """
    # initialize the log
    logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    # Initialize the server
    server_process = start_server_jar(JAR_PATH)

    # Create threads to manage the server saves and backups
    try:
        save_task = threading.Thread(target=periodic_save, args=(server_process, SAVE_INTERVAL_SEC,))
        save_task.start()

        backup_task = threading.Thread(target=periodic_backup, args=(BACKUP_INTERVAL_SEC, BACKUP_DIR,))
        backup_task.start()

        server_process.wait()
    except KeyboardInterrupt:
        logging.critical("program exited, killing server process and sub processes")
        STOP_THREADS_FLAG.set()
        server_process.terminate()

if __name__ == "__main__":
    main()