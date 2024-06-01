from flask import Flask, render_template, request, jsonify
import logging

app = Flask(__name__)

# log_file_path = server_config.server_log_path
# logging.basicConfig(filename=server_config.manager_log_path, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_log')
def get_log():
    from server_manager import server_config
    log_file_path = server_config.server_log_path
    with open(log_file_path, "r") as log_file:
        log_lines = log_file.readlines()
    return jsonify(log_lines[-20:])  # Return the last 20 lines of the log

@app.route('/send_command', methods=['POST'])
def send_command():
    from server_manager import server_config, send_server_command
    logging.basicConfig(filename=server_config.manager_log_path, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    
    command = request.form['command']
    logging.info(f"Received and executing command: {command}")
    send_server_command(command)
    return jsonify(status="success", command=command)
