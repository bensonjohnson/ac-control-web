from flask import Flask, request, jsonify, render_template
import json
import paho.mqtt.client as mqtt

app = Flask(__name__)
mqtt_broker = "10.0.0.105"
mqtt_port = 1883  
mqtt_user = "tempctrl"  
mqtt_password = "tempctrl"  
mqtt_topic = "ac_control"  
temperature_topic = "temperature"  

# Set initial values for temperature and set temperature
current_temperature = 0.0
set_temperature = None

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


def on_connect(client, userdata, flags, rc):
    # Subscribe to the temperature topic when connected to MQTT broker
    mqtt_client.subscribe(temperature_topic)


def on_message(client, userdata, msg):
    global current_temperature
    # Update the current temperature when a new temperature reading is received
    if msg.topic == temperature_topic:
        try:
            payload = json.loads(msg.payload.decode())
            current_temperature = float(payload)
        except (ValueError, TypeError):
            print("Invalid temperature payload received:", msg.payload)
        else:
            # Ignore the value if it is not a valid float
            print("Current temperature updated:", current_temperature)
            update_hvac_control()


def update_hvac_control():
    global fan_state, cooling_state, heating_state
    # Process the temperature difference and determine the HVAC control states
    if set_temperature is not None:
        temperature_difference = current_temperature - set_temperature

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
            fan_state = False
        else:
            cooling_state = False
            heating_state = False
            fan_state = False

    publish_control_command()


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
        return jsonify({"message": "Temperature set successfully", "set_temperature": set_temperature})
    except (ValueError, TypeError):
        return jsonify({"message": "Invalid temperature value"})

@app.route('/')
def index():
    # Render the index.html template and pass the current and set temperature values
    return render_template('index.html', current_temperature=current_temperature, set_temperature=set_temperature,
                           fan_state="ON" if fan_state else "OFF", cooling_state="ON" if cooling_state else "OFF",
                           heating_state="ON" if heating_state else "OFF")


if __name__ == '__main__':
    # Start the MQTT client and Flask web API
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(mqtt_broker, mqtt_port, 60)
    mqtt_client.loop_start()
    app.run(host='0.0.0.0', port=5000)