from flask import Flask, request, jsonify, render_template
import json
import paho.mqtt.client as mqtt
import os
import threading
from datetime import datetime
import time

class PID:
    def __init__(self, P=0.1, I=0.0, D=0.0):
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
ac_control_topic = os.environ['AC_CONTROL_TOPIC']
temperature_topic = os.environ['TEMPERATURE_TOPIC']
external_temperature_topic = os.environ['EXTERNAL_TEMPERATURE_TOPIC']
average_temperature_topic = os.environ['AVERAGE_TEMPERATURE_TOPIC']
set_temperature_topic = os.environ['SET_TEMPERATURE_TOPIC']
threshold_percentage = os.environ['TEMP_THRESHOLD']

# Set initial values for temperature and set temperature
current_temperature = 0.0
external_temperature = 0.0
set_temperature = 70
avg_external_temperature = 0.0
fan_start_time = 0

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
    # MQTT topic to subscribe to for hvac_control
    mqtt_client.subscribe(temperature_topic)
    mqtt_client.subscribe(external_temperature_topic)
    mqtt_client.subscribe(average_temperature_topic)
    mqtt_client.subscribe(set_temperature_topic)


def update_hvac_control():
    global fan_state, cooling_state, heating_state, set_temperature, current_temperature, external_temperature, pid, avg_external_temperature, fan_start_time, cooling_start_time, heating_start_time  # Added heating_start_time

    # Process the temperature difference and determine the HVAC control states
    temperature_difference = current_temperature - set_temperature

    pid.SetPoint = set_temperature
    pid.update(current_temperature)
    pid_value = pid.get_pid_value()

    # Set the thresholds based on a percentage of the average external temperature
    threshold_percentage = 0.15 
    cooling_threshold = avg_external_temperature * (1 - threshold_percentage)
    heating_threshold = avg_external_temperature * (1 + threshold_percentage)

    # thresholds for heating
    if pid_value > 0.25 and external_temperature < heating_threshold and current_temperature < set_temperature:
        cooling_state = False
        heating_state = True
        fan_state = True
        heating_start_time = time.time()  # Start counting the heating duration
    # Thresholds for cooling
    elif pid_value < -0.25 and external_temperature > cooling_threshold and current_temperature > set_temperature:
        cooling_state = True
        heating_state = False
        fan_state = True
        fan_start_time = time.time()
        cooling_start_time = time.time()  # Start counting the cooling duration
    elif abs(pid_value) > .5:
        cooling_state = False
        heating_state = False
        fan_state = True
        fan_start_time = time.time()
    else:
        if fan_state and time.time() - fan_start_time < 300:
            pass  # Keep the fan on
        elif cooling_state and time.time() - cooling_start_time < 300:
            pass  # Keep the cooling on
        elif heating_state and time.time() - heating_start_time < 300: 
            pass  # Keep the heating on
        else:
            cooling_state = False
            heating_state = False
            fan_state = False

    publish_control_command()



def on_message(client, userdata, msg):
    global current_temperature, set_temperature, external_temperature, avg_external_temperature
    if msg.topic == temperature_topic:
        # Update current temperature
        try:
            payload = json.loads(msg.payload.decode())
            current_temperature = float(payload)
            print("Current temperature updated:", current_temperature)
            update_hvac_control()
        except (ValueError, TypeError):
            print("Invalid temperature payload received:", msg.payload)
    elif msg.topic == 'set_temperature':
        # Update set temperature
        try:
            set_temperature = float(msg.payload)
            print("Received set temperature from MQTT:", set_temperature)
            update_hvac_control()
        except (ValueError, TypeError):
            print("Invalid set temperature value received from MQTT:", msg.payload)
    elif msg.topic == external_temperature_topic:
        # Update external temperature
        try:
            external_temperature = float(msg.payload)
            print("Received external temperature from MQTT:", external_temperature)
            update_hvac_control()
        except (ValueError, TypeError):
            print("Invalid external temperature value received from MQTT:", msg.payload)
    elif msg.topic == average_temperature_topic:
        # Update average external temperature
        try:
            avg_external_temperature = float(msg.payload)
            print("Received average external temperature from MQTT:", avg_external_temperature)
            update_hvac_control()
        except (ValueError, TypeError):
            print("Invalid average external temperature value received from MQTT:", msg.payload)

def publish_control_command():
    # Publish the control command to the MQTT topic
    command = {
        "fan": FAN_ON if fan_state else FAN_OFF,
        "cooling": COOLING_ON if cooling_state else COOLING_OFF,
        "heating": HEATING_ON if heating_state else HEATING_OFF
    }
    mqtt_client.publish(ac_control_topic, json.dumps(command))
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
                           external_temperature=external_temperature, avg_external_temperature=avg_external_temperature)

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
