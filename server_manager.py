import subprocess
import threading
import logging
import os
import shutil
import argparse
import json 
from time import sleep
from flask import Flask, render_template, request, jsonify

STOP_THREADS_FLAG = threading.Event()
app = Flask(__name__)
logger_name = "ServerManagerLogger"
flask_log = "werkzeug"

class ServerManagerConfig:
    """
    Object for the server config to load configured values into
    """
    def __init__(self, configFilePath: str):
        """
        Load in the values from the config file to fields in the object
        """
        with open(configFilePath, 'r') as config_file:
            config = json.load(config_file)
        self.jar_path = config['JarPath']
        self.manager_log_path = config['ManagerLogPath']
        self.web_log_path = config['WebLogPath']
        self.update_log_path = config['UpdateLogPath']
        self.server_log_path = config['ServerLogPath']
        self.server_path = config['ServerPath']
        self.backup_path = config['BackupPath']
        self.save_interval_sec = config['SaveIntervalSec']
        self.backup_interval_sec = config['BackupIntervalSec']

def start_server_jar(jar_path: str, server_path: str) -> subprocess.Popen:
    """
    Function that initially kicks off server, and returns the subprocess obj
    """
    manager_logger.info('starting server jar...')
    server_process = subprocess.Popen(['java', '-jar', jar_path, '--nogui'],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,
                                      universal_newlines=True,
                                      cwd=server_path)
    return server_process

def send_server_command(command: str):
    """
    Wrapper function for sending commands to the server jar
    """
    manager_logger.debug(f'sending command: {command}')
    server_process.stdin.write(command + '\r')
    server_process.stdin.flush()

def periodic_save(interval_sec: int) -> None:
    # modular sleeps into seconds to check for the stop threads flag
    manager_logger.debug("Running initial wait on periodic save thread")
    for _ in range(interval_sec):
        if not STOP_THREADS_FLAG.is_set():
            sleep(1)
        else:
            break
    while True and not STOP_THREADS_FLAG.is_set():
        # Send the save command to the server process
        manager_logger.info('saving the server...')
        send_server_command("save-all")
        
        manager_logger.debug("Running periodic wait on save thread")
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
            manager_logger.debug(f"Created backup dir at: {dest_dir}")
        else:
            manager_logger.debug(f"Backup dir {dest_dir} already exists")
    except OSError as exc:
        manager_logger.error(f"Error creating backup dir: {dest_dir}: {exc}")
        raise exc

    try:
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
                    continue
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, os.path.relpath(src_file, src_dir))
                try:
                    shutil.copy2(src_file, dest_file)
                except Exception as e:
                    manager_logger.error(f"Failed to copy '{src_file}' to '{dest_file}': {e}")

    except Exception as exc:
        manager_logger.error(f"Couldn't copy src {src_dir} to dest {dest_dir}: {exc}")
        raise exc
    
    manager_logger.debug("All files copied successfully.")

def periodic_backup(interval_sec: int, backup_dir: str, server_path: str) -> None:
    """
    Wrapper func for a periodic backup of all files to a specified directory
    Do not fail and kill process if we cannot backup files - just create a strong critical
    entry
    """
    # TODO: Add a naming scheme to backups so multiple copies of backups can be held
    # TODO: Zip the backups for space efficiency
    while True and not STOP_THREADS_FLAG.is_set():
        try:
            manager_logger.info(f"Backing up server files to {backup_dir}")
            copy_files(src_dir=server_path, dest_dir=backup_dir)
        except Exception as exc:
            manager_logger.critical(f"Could not backup files to {backup_dir}: {exc}")
        
        # modular sleeps into seconds to check for the stop threads flag
        manager_logger.info("Running periodic wait on backup thread")
        for _ in range(interval_sec):
            if not STOP_THREADS_FLAG.is_set():
                sleep(1)
            else:
                break

def configure_manager_log(filepath: str):
    """
    Custom log desired for the management portion needs a separate config,
    don't want to be mixed with flask logging
    """
    global manager_logger
    manager_logger = logging.getLogger('manager_logger')
    manager_logger.setLevel(logging.DEBUG)
    # create a file handler for the manager log
    manager_handler = logging.FileHandler(filepath)
    manager_handler.setLevel(logging.DEBUG)
    # create the formatter
    manager_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    manager_handler.setFormatter(manager_formatter)
    # add handler to logger
    manager_logger.addHandler(manager_handler)

def configure_flask_log(filepath: str):
    """
    Necessary steps to separate the flask application from writing to the root log,
    and to our own desired UI based log
    """
    # Get the Flask logger
    flask_logger = logging.getLogger(flask_log)

    # Remove the default Flask (werkzeug) handlers
    flask_logger.handlers = []

    # Create a file handler for the Flask logger
    flask_handler = logging.FileHandler(filepath)
    flask_handler.setLevel(logging.DEBUG)

    # Create a formatter and set it for the Flask handler
    flask_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    flask_handler.setFormatter(flask_formatter)

    # Add the handler to the Flask logger
    flask_logger.addHandler(flask_handler)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_log')
def get_log():
    log_file_path = server_config.server_log_path
    with open(log_file_path, "r") as log_file:
        log_lines = log_file.readlines()
    return jsonify(log_lines[-20:])  # Return the last 20 lines of the log

@app.route('/send_command', methods=['POST'])
def send_command():    
    command = request.form['command']
    logging.info(f"Received and executing command: {command}")
    send_server_command(command)
    return jsonify(status="success", command=command)

def main():
    """
    Main func to create and handle the server jar process
    """
    # TODO: add the web server interface so users can still interact with the server and send
    # administrative commands - perhaps also see the live logs up there too?

    # TODO: add checks for the thread kill flag to the flask app

    # take in argument for config file
    parser = argparse.ArgumentParser(
        prog="MC Server manager wrapper",
        description="Full time multithreaded manager for mc server jar",
    )
    parser.add_argument("-c", "--config", help="The configuration file", required=True)
    args = parser.parse_args()
    config_name = args.config

    # load the config file values with the config class - will be used by flask application
    global server_config
    server_config = ServerManagerConfig(config_name)

    # call the function to configure the custom logs to have separate files
    configure_manager_log(server_config.manager_log_path)
    configure_flask_log(server_config.web_log_path)

    # Initialize the server
    global server_process
    server_process = start_server_jar(server_config.jar_path, server_config.server_path)

    # Create threads to manage the server saves and backups
    try:
        save_task = threading.Thread(target=periodic_save, args=(server_config.save_interval_sec,))
        save_task.start()

        backup_task = threading.Thread(target=periodic_backup, args=(server_config.backup_interval_sec, server_config.backup_path, server_config.server_path))
        backup_task.start()

        flask_task = threading.Thread(target=app.run(host='0.0.0.0', port=5000))
        flask_task.start()

        server_process.wait()
        STOP_THREADS_FLAG.set()
        server_process.terminate()
    except KeyboardInterrupt:
        manager_logger.critical("program exited, killing server process and sub processes")
        STOP_THREADS_FLAG.set()
        server_process.terminate()

if __name__ == "__main__":
    main()