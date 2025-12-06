import paho.mqtt.client as mqtt
import uuid
import time
import logging
import threading


MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 30
MQTT_RECONNECT_DELAY_MIN = 1
MQTT_RECONNECT_DELAY_MAX = 30
MQTT_CLIENT_ID = f"SWSC_Flask_{uuid.uuid4().hex[:8]}_{int(time.time())}"

# MQTT Topics (Untuk di-import file lain)
TOPIC_CONFIG_DURATION = "swsc/config/duration"
TOPIC_CONFIG_BREAK_INTERVAL = "swsc/config/break_interval"
TOPIC_CONFIG_BREAK_LENGTH = "swsc/config/break_length"
TOPIC_CONFIG_WATER_REMINDER = "swsc/config/water_reminder"

TOPIC_CONTROL_START = "swsc/control/start"
TOPIC_CONTROL_STOP = "swsc/control/stop"
TOPIC_CONTROL_RESET = "swsc/control/reset"

TOPIC_ALERT_BREAK = "swsc/alert/break"
TOPIC_ALERT_WATER = "swsc/alert/water"

TOPIC_STATUS = "swsc/status/#"
TOPIC_DATA = "swsc/data/#"
TOPIC_ALERT = "swsc/alert/#"

logger = logging.getLogger(__name__)

class MQTTService:
    def __init__(self):
        self.client = None
        self.connected_event = threading.Event()
        self.connection_count = 0
        
        self.sensor_lock = threading.Lock()
        self.sensor_data = {
            "temperature": "-",
            "humidity": "-",
            "light": "-"
        }
        self.system_status = "Disconnected"

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False):
        if self.client is None:
            logger.warning(f"MQTT client not initialized")
            return False
        
        if not self.connected_event.wait(timeout=2):
            logger.warning(f"MQTT not connected, cannot publish: {topic}")
            return False
        
        try:
            result = self.client.publish(topic, payload, qos=qos, retain=retain)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Published: {topic} = {payload}")
                return True
            else:
                logger.error(f"Publish failed: {topic}, rc={result.rc}")
                return False
        except Exception as e:
            logger.error(f"Publish exception: {topic} | {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        self.connection_count += 1
        
        if rc == 0:
            logger.info(f"MQTT connected successfully (connection #{self.connection_count})")
            self.connected_event.set()

            try:
                client.subscribe(TOPIC_STATUS, qos=1)
                client.subscribe(TOPIC_DATA, qos=1)
                client.subscribe(TOPIC_ALERT, qos=1)
                logger.info("Subscribed to:")
                logger.info(f"  - {TOPIC_STATUS}")
                logger.info(f"  - {TOPIC_DATA}")
                logger.info(f"  - {TOPIC_ALERT}")
            except Exception as e:
                logger.error(f"Subscription failed: {e}")
        else:
            error_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized",
                7: "Network error or broker rate limit"
            }
            logger.error(f"MQTT connection failed: {error_messages.get(rc, f'Unknown error {rc}')}")
            self.connected_event.clear()

    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"MQTT disconnected (rc={rc})")
        self.connected_event.clear()
        
        if rc == 0:
            logger.info("Clean disconnect")
        elif rc == 7:
            logger.warning("Network error or broker rate limit - will retry with backoff")
        else:
            logger.info(f"Unexpected disconnect (rc={rc}) - will auto-reconnect")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="ignore")
        
        logger.debug(f"Received: {topic} = {payload}")
        
        if topic == "swsc/data/temperature":
            with self.sensor_lock:
                self.sensor_data["temperature"] = payload
        elif topic == "swsc/data/humidity":
            with self.sensor_lock:
                self.sensor_data["humidity"] = payload
        elif topic == "swsc/data/light":
            with self.sensor_lock:
                self.sensor_data["light"] = payload
        elif topic == "swsc/status/system":
            self.system_status = payload
            logger.info(f"System status: {self.system_status}")


    def _loop_logic(self):
        logger.info("Starting MQTT thread...")
        logger.info(f"Client ID: {MQTT_CLIENT_ID}")
        
        retry_delay = MQTT_RECONNECT_DELAY_MIN
        
        while True:
            try:
                self.client = mqtt.Client(
                    client_id=MQTT_CLIENT_ID,
                    clean_session=True,
                    protocol=mqtt.MQTTv311
                )
                
                self.client.on_connect = self._on_connect
                self.client.on_disconnect = self._on_disconnect
                self.client.on_message = self._on_message
                self.client._keepalive = MQTT_KEEPALIVE
                
                logger.info(f"Connecting to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
                self.client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
                retry_delay = MQTT_RECONNECT_DELAY_MIN
                
                self.client.loop_forever()
                
            except KeyboardInterrupt:
                logger.info("MQTT loop interrupted by user")
                break
                
            except Exception as e:
                logger.error(f"MQTT loop error: {e}")
                self.connected_event.clear()
                
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                
                retry_delay = min(retry_delay * 2, MQTT_RECONNECT_DELAY_MAX)

    def start(self):
        t = threading.Thread(target=self._loop_logic, daemon=True)
        t.start()

    def stop(self):
        if self.client:
            self.client.disconnect()