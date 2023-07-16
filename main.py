from flask import Flask, request, jsonify, render_template
import json
import paho.mqtt.client as mqtt
import os
import threading
from datetime import datetime

app = Flask(__name__)
mqtt_broker = os.environ.get('MQTT_BROKER', '10.0.0.105')
mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
mqtt_user = os.environ['MQTT_USER']
mqtt_password = os.environ['MQTT_PASSWORD']
mqtt_topic = os.environ['MQTT_TOPIC']
temperature_topic = os.environ['TEMPERATURE_TOPIC']

# Set initial values for temperature and set temperature
current_temperature = 0.0
set_temperature = 68

def is_nighttime():
    now = datetime.now().time()
    # Define the nighttime range (e.g., from 10 PM to 6 AM)
    start_time = datetime.strptime("22:00", "%H:%M").time()
    end_time = datetime.strptime("06:00", "%H:%M").time()
    return start_time <= now or now <= end_time

def is_daytime():
    now = datetime.now().time()
    # Define the daytime range (e.g., from 6 AM to 10 PM)
    start_time = datetime.strptime("06:00", "%H:%M").time()
    end_time = datetime.strptime("22:00", "%H:%M").time()
    return start_time <= now <= end_time


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

# Thresholds
nighttime_summer_threshold = 65
daytime_winter_threshold = 75

# MQTT client initialization
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(mqtt_user, mqtt_password)

# Lock for concurrent access to shared variables
data_lock = threading.Lock()


def on_connect(client, userdata, flags, rc):
    # Subscribe to the temperature topic when connected to MQTT broker
    mqtt_client.subscribe(temperature_topic)
    mqtt_client.subscribe('set_temperature')


def update_hvac_control():
    global fan_state, cooling_state, heating_state, set_temperature
    # Process the temperature difference and determine the HVAC control states
    temperature_difference = current_temperature - set_temperature

    # Check if it is summer or winter based on the current month
    now = datetime.now()
    month = now.month
    is_summer = month >= 6 and month <= 8
    is_winter = month >= 12 or month <= 2

    if is_summer:
        # Apply summer control logic with extra temperature allowance
        summer_threshold = set_temperature + nighttime_summer_threshold if is_nighttime() else set_temperature
        if temperature_difference >= 2.0:
            cooling_state = True
            heating_state = False
            fan_state = True
        elif temperature_difference >= 1.0:
            cooling_state = False
            heating_state = False
            fan_state = False
        elif temperature_difference >= 0.0 and current_temperature <= summer_threshold:
            cooling_state = False
            heating_state = False
            fan_state = False
        else:
            cooling_state = False
            heating_state = False
            fan_state = False
    elif is_winter:
        # Apply winter control logic with extra temperature allowance
        winter_threshold = set_temperature - daytime_winter_threshold if is_daytime() else set_temperature
        if temperature_difference <= -2.0:
            cooling_state = False
            heating_state = True
            fan_state = True
        elif temperature_difference <= -1.0:
            cooling_state = False
            heating_state = True
            fan_state = True
        elif temperature_difference <= 0.0 and current_temperature >= winter_threshold:
            cooling_state = False
            heating_state = False
            fan_state = False
        else:
            cooling_state = False
            heating_state = False
            fan_state = False
    else:
        # Apply standard control logic
        if temperature_difference >= 2.0:
            cooling_state = True
            heating_state = False
            fan_state = True
        elif temperature_difference >= 1.0:
            cooling_state = False
            heating_state = False
            fan_state = False
        elif temperature_difference <= -2.0:
            cooling_state = False
            heating_state = True
            fan_state = True
        elif temperature_difference <= -1.0:
            cooling_state = False
            heating_state = True
            fan_state = True
        else:
            cooling_state = False
            heating_state = False
            fan_state = False

    publish_control_command()



def on_message(client, userdata, msg):
    global current_temperature, set_temperature
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
                           heating_state="ON" if heating_state else "OFF",
                           nighttime_summer_threshold=nighttime_summer_threshold,
                           daytime_winter_threshold=daytime_winter_threshold)


@app.route('/get_hvac_state')
def get_hvac_state():
    return jsonify({
        'fan_state': 'ON' if fan_state else 'OFF',
        'cooling_state': 'ON' if cooling_state else 'OFF',
        'heating_state': 'ON' if heating_state else 'OFF'
    })


@app.route('/set_thresholds', methods=['POST'])
def set_thresholds():
    global nighttime_summer_threshold, daytime_winter_threshold
    data = request.form
    nighttime_summer_threshold = float(data.get('nighttime_summer_threshold'))
    daytime_winter_threshold = float(data.get('daytime_winter_threshold'))
    update_hvac_control()
    return jsonify({"message": "Thresholds set successfully"})


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
