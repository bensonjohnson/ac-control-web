ac-control-web\
\
A MQTT based web controller to control an ESP32 as a wall thermostat unit.\
A weather broker needs to feed external weather data over a MQTT topic (external_weather).\
This is designed to be used in conjunction with something like an EMQX cluster It also assumes you can either query or supply the average temperature over X days. I have found that that around 3 days is ideal.

