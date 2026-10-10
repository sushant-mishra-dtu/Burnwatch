"""Subscribe then publish on burnwatch/test, using device/.env and mutual TLS."""
import datetime
import json
import ssl
import threading
import time

from setup_common import common_arguments, contracts, read_env


def smoke_test(env_file, timeout=30):
    import paho.mqtt.client as mqtt
    config = read_env(env_file)
    for name in ("IOT_ENDPOINT", "CAMERA_ID", "CERT_PATH", "KEY_PATH", "CA_PATH"):
        if not config.get(name):
            raise ValueError(f"Missing {name} in {env_file}; run setup_iot.py first")
    if datetime.datetime.now(datetime.timezone.utc).year < 2026:
        raise RuntimeError("System clock is wrong; sync it before TLS to IoT Core")
    ready, received, errors = threading.Event(), threading.Event(), []
    # burnwatch/test accepts any JSON (contracts section 1); include a unique token.
    payload = contracts.to_json({"camera": config["CAMERA_ID"], "ts": int(time.time()),
                                  "test": "mqtt-smoke", "token": time.time_ns()})
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=contracts.client_id(config["CAMERA_ID"], "smoketest"),
                         protocol=mqtt.MQTTv311)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            errors.append(f"IoT connection rejected: {reason_code}")
            ready.set()
        else:
            result, _ = client.subscribe(contracts.TOPIC_TEST, qos=0)
            if result != mqtt.MQTT_ERR_SUCCESS:
                errors.append("Unable to subscribe to burnwatch/test")
                ready.set()

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            errors.append("IoT subscription rejected")
        ready.set()

    def on_message(client, userdata, message):
        if message.topic == contracts.TOPIC_TEST and message.payload == payload:
            received.set()

    client.on_connect, client.on_subscribe, client.on_message = on_connect, on_subscribe, on_message
    client.tls_set(ca_certs=config["CA_PATH"], certfile=config["CERT_PATH"],
                   keyfile=config["KEY_PATH"], tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.connect(config["IOT_ENDPOINT"], port=8883, keepalive=60)
    client.loop_start()
    try:
        if not ready.wait(timeout):
            raise TimeoutError("Timed out connecting/subscribing to IoT Core")
        if errors:
            raise RuntimeError(errors[0])
        sent = client.publish(contracts.TOPIC_TEST, payload, qos=0)
        if sent.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with code {sent.rc}")
        sent.wait_for_publish(timeout=timeout)
        if not received.wait(timeout):
            raise TimeoutError("Published but did not receive matching JSON on burnwatch/test")
        print(f"PASS: published and received {json.loads(payload)} on {contracts.TOPIC_TEST}")
        print("Confirm the same token appears in the AWS IoT MQTT test client subscribed to burnwatch/#")
    finally:
        client.disconnect()
        client.loop_stop()


def main():
    parser = common_arguments(__doc__)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    smoke_test(args.env_file, args.timeout)


if __name__ == "__main__":
    main()
