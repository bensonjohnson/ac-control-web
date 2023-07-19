from flask import Flask, request, jsonify, render_template
import json
import paho.mqtt.client as mqtt
import os
import threading
from datetime import datetime
import time

class PID:
    def __init__(self, P=0.2, I=0.0, D=0.0):
        self.Kp = P
        self.Ki = I
        self.Kd = D
        self.sample_time = 0.00
        self.current_time = time.time()
        self.last_time = self.current_time
        self.clear()

    def clear(self):
        self.SetPoint = 0.0
        self.PTerm = 0.0
        self.ITerm = 0.0
        self.DTerm = 0.0
        self.last_error = 0.0
        # Windup Guard
        self.int_error = 0.0
        self.windup_guard = 20.0
        self.output = 0.0

    def update(self, feedback_value):
        error = self.SetPoint - feedback_value
        self.current_time = time.time()
        delta_time = self.current_time - self.last_time
        delta_error = error - self.last_error
        if (delta_time >= self.sample_time):
            self.PTerm = self.Kp * error
            self.ITerm += error * delta_time
            if (self.ITerm < -self.windup_guard):
                self.ITerm = -self.windup_guard
            elif (self.ITerm > self.windup_guard):
                self.ITerm = self.windup_guard
            self.DTerm = 0.0
            if delta_time > 0:
                self.DTerm = delta_error / delta_time
            # Remember last time and last error for next calculation
            self.last_time = self.current_time
            self.last_error = error
            self.output = self.PTerm + (self.Ki * self.ITerm) + (self.Kd * self.DTerm)

    def get_pid_value(self):
        return self.output

app = Flask(__name__)
mqtt_broker = os.environ.get('MQTT_BROKER', '10.0.0.105')
mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
mqtt_user = os.environ['MQTT_USER']
mqtt_password = os.environ['MQTT_PASSWORD']
mqtt_topic = os.environ['MQTT_TOPIC']
temperature_topic = os.environ['TEMPERATURE_TOPIC']
external_temperature_topic = os.environ['EXTERNAL_TEMPERATURE_TOPIC']

# Set initial values for temperature and set temperature
current_temperature = 0.0
external_temperature = 0.0
set_temperature = 68

# Relay control command constants
COOLING_ON = "cooling_on"
COOLING_OFF = "cooling_off"
HEATING_ON = "heating_on"
HEATING_OFF = "heating_off"
FAN_ON = "fan_on"
FAN_OFF = "fan_off"

# HVAC control variables
fan_state = False
cooling_state = False
heating_state = False

# MQTT client initialization
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(mqtt_user, mqtt_password)

# Lock for concurrent access to shared variables
data_lock = threading.Lock()

# PID controller initialization
pid = PID()

def on_connect(client, userdata, flags, rc):
    # Subscribe to the temperature topic when connected to MQTT broker
    mqtt_client.subscribe(temperature_topic)
    mqtt_client.subscribe(external_temperature_topic)
    mqtt_client.subscribe('set_temperature')

def update_hvac_control():
    global fan_state, cooling_state, heating_state, set_temperature
    # Process the temperature difference and determine the HVAC control states
    temperature_difference = current_temperature - set_temperature

    pid.SetPoint = set_temperature
    pid.update(current_temperature)
    pid_value = pid.get_pid_value()

    if pid_value > 0:
        cooling_state = False
        heating_state = True
        fan_state = True
    elif pid_value < 0:
        cooling_state = True
        heating_state = False
        fan_state = True
    else:
        cooling_state = False
        heating_state = False
        fan_state = False

    publish_control_command()

def on_message(client, userdata, msg):
    global current_temperature, set_temperature, external_temperature
    # Update the current temperature or set temperature when a new message is received
    if msg.topic == temperature_topic:
        try:
            payload = json.loads(msg.payload.decode())
            current_temperature = float(payload)
            print("Current temperature updated:", current_temperature)
            update_hvac_control()  # Trigger the update_hvac_control() function
        except (ValueError, TypeError):
            print("Invalid temperature payload received:", msg.payload)
    elif msg.topic == 'set_temperature':
        try:
            set_temperature = float(msg.payload)
            print("Received set temperature from MQTT:", set_temperature)
            update_hvac_control()
        except (ValueError, TypeError):
            print("Invalid set temperature value received from MQTT:", msg.payload)
    elif msg.topic == external_temperature_topic:
        try:
            external_temperature = float(msg.payload)
            print("Received external temperature from MQTT:", external_temperature)
            update_hvac_control()
        except (ValueError, TypeError):
            print("Invalid external temperature value received from MQTT:", msg.payload)

def publish_control_command():
    # Publish the control command to the MQTT topic
    command = {
        "fan": FAN_ON if fan_state else FAN_OFF,
        "cooling": COOLING_ON if cooling_state else COOLING_OFF,
        "heating": HEATING_ON if heating_state else HEATING_OFF
    }
    mqtt_client.publish(mqtt_topic, json.dumps(command))
    print("Published control command:", command)

@app.route('/set_temperature', methods=['POST'])
def set_temp():
    global set_temperature
    # Set the new set temperature based on the request data
    data = request.form.get('set_temperature')
    try:
        set_temperature = float(data)
        update_hvac_control()
        mqtt_client.publish('set_temperature', str(set_temperature))
        return jsonify({"message": "Temperature set successfully", "set_temperature": set_temperature})
    except (ValueError, TypeError):
        return jsonify({"message": "Invalid temperature value"})

@app.route('/')
def index():
    # Render the index.html template and pass the current and set temperature values
    return render_template('index.html', current_temperature=current_temperature, set_temperature=set_temperature,
                           fan_state="ON" if fan_state else "OFF", cooling_state="ON" if cooling_state else "OFF",
                           heating_state="ON" if heating_state else "OFF", pid_calculation=pid.get_pid_value(),
                           external_temperature=external_temperature)

@app.route('/get_hvac_state')
def get_hvac_state():
    return jsonify({
        'fan_state': 'ON' if fan_state else 'OFF',
        'cooling_state': 'ON' if cooling_state else 'OFF',
        'heating_state': 'ON' if heating_state else 'OFF'
    })

@app.route('/get_pid_calculation')
def get_pid_calculation():
    return jsonify({
        'pid_calculation': pid.get_pid_value()
    })

def mqtt_thread():
    # Start the MQTT client
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(mqtt_broker, mqtt_port, 60)
    mqtt_client.loop_start()

def flask_thread():
    # Start the Flask web API
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    # Start MQTT and Flask in separate threads
    mqtt_thread = threading.Thread(target=mqtt_thread)
    flask_thread = threading.Thread(target=flask_thread)

    mqtt_thread.start()
    flask_thread.start()
