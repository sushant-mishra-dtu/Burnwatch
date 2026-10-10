"""Provisioning regression tests: no AWS credentials or network required."""
import contextlib
import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_common as common
import setup_iot as iot_setup
import setup_device_iam as iam_setup
import mqtt_smoke_test

ACCOUNT = "123456789012"
IDENTITY = {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:user/setup-admin", "UserId": "setup-admin"}
BUCKET = f"burnwatch-frames-{ACCOUNT}-ap-south-1"
CAMERA = "rwa-gate-2"
CERT_ID = "a" * 64
CERT_ARN = f"arn:aws:iot:ap-south-1:{ACCOUNT}:cert/{CERT_ID}"
KEY_ID, KEY_SECRET = "AKIA" + "A" * 16, "a" * 40
NOW = datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc)


def aws_client(name):
    return boto3.client(name, region_name=common.REGION, aws_access_key_id="test", aws_secret_access_key="test")


def fake_session(**clients):
    result = Mock()
    result.client.side_effect = lambda name: clients[name]
    return result


class EnvironmentTests(unittest.TestCase):
    def test_atomic_update_preserves_other_keys_and_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("# keep\nCAMERA_ID=rwa-gate-2\nBUCKET=old\nBUCKET=old\n", encoding="utf-8")
            common.update_env(env, {"BUCKET": BUCKET, "AWS_SECRET_ACCESS_KEY": KEY_SECRET})
            self.assertEqual(common.read_env(env), {"CAMERA_ID": CAMERA, "BUCKET": BUCKET, "AWS_SECRET_ACCESS_KEY": KEY_SECRET})
            self.assertTrue(env.read_text().startswith("# keep\n"))
            self.assertEqual(env.read_text().count("BUCKET="), 1)

    def test_bad_input_cannot_overwrite_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("bad entry\n")
            with self.assertRaises(ValueError):
                common.update_env(env, {"BUCKET": BUCKET})
            self.assertEqual(env.read_text(), "bad entry\n")

    def test_newline_cannot_inject_another_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            with self.assertRaises(ValueError):
                common.update_env(env, {"BUCKET": "safe\nUNEXPECTED=value"})
            self.assertFalse(env.exists())


class IoTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "burnwatch-test")])
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                       .public_key(key.public_key()).serial_number(1)
                       .not_valid_before(NOW - datetime.timedelta(days=1))
                       .not_valid_after(NOW + datetime.timedelta(days=365))
                       .sign(key, hashes.SHA256()))
        cls.pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
        cls.key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()).decode("ascii")

    def test_first_setup_and_rerun_create_one_certificate(self):
        iot, sts = aws_client("iot"), aws_client("sts")
        with Stubber(iot) as stub, Stubber(sts) as identities, tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                identities.add_response("get_caller_identity", IDENTITY, {})
            endpoint, policy = "example-ats.iot.ap-south-1.amazonaws.com", iot_setup.device_policy(ACCOUNT)
            stub.add_response("describe_endpoint", {"endpointAddress": endpoint}, {"endpointType": "iot:Data-ATS"})
            stub.add_client_error("get_policy", "ResourceNotFoundException", expected_params={"policyName": iot_setup.POLICY_NAME})
            stub.add_response("create_policy", {}, {"policyName": iot_setup.POLICY_NAME, "policyDocument": json.dumps(policy)})
            stub.add_client_error("describe_thing", "ResourceNotFoundException", expected_params={"thingName": f"burnwatch-{CAMERA}"})
            stub.add_response("create_thing", {}, {"thingName": f"burnwatch-{CAMERA}"})
            stub.add_response("create_keys_and_certificate", {"certificateArn": CERT_ARN, "certificateId": CERT_ID,
                              "certificatePem": self.pem, "keyPair": {"PrivateKey": self.key}}, {"setAsActive": True})
            stub.add_response("attach_policy", {}, {"policyName": iot_setup.POLICY_NAME, "target": CERT_ARN})
            stub.add_response("attach_thing_principal", {}, {"thingName": f"burnwatch-{CAMERA}", "principal": CERT_ARN})
            stub.add_response("describe_endpoint", {"endpointAddress": endpoint}, {"endpointType": "iot:Data-ATS"})
            stub.add_response("get_policy", {"policyDocument": json.dumps(policy)}, {"policyName": iot_setup.POLICY_NAME})
            stub.add_response("describe_thing", {}, {"thingName": f"burnwatch-{CAMERA}"})
            stub.add_response("describe_certificate", {"certificateDescription": {"certificateArn": CERT_ARN,
                              "certificatePem": self.pem, "status": "ACTIVE"}}, {"certificateId": CERT_ID})
            stub.add_response("attach_policy", {}, {"policyName": iot_setup.POLICY_NAME, "target": CERT_ARN})
            stub.add_response("attach_thing_principal", {}, {"thingName": f"burnwatch-{CAMERA}", "principal": CERT_ARN})
            env, response = Path(directory) / ".env", Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = self.pem.encode("ascii")
            with patch.object(iot_setup.urllib.request, "urlopen", return_value=response) as download, contextlib.redirect_stdout(io.StringIO()) as output:
                aws = fake_session(iot=iot, sts=sts)
                iot_setup.provision(aws, CAMERA, BUCKET, env)
                first = env.read_bytes()
                iot_setup.provision(aws, CAMERA, BUCKET, env)
                self.assertEqual(first, env.read_bytes())
                download.assert_called_once_with(iot_setup.ROOT_CA_URL, timeout=30)
                self.assertNotIn(self.key, output.getvalue())
            stub.assert_no_pending_responses()
            identities.assert_no_pending_responses()

    def test_partial_certificate_refuses_to_create_more(self):
        iot = Mock()
        with tempfile.TemporaryDirectory() as directory:
            cert_dir = Path(directory)
            (cert_dir / "certificate.pem").write_text(self.pem)
            with self.assertRaisesRegex(RuntimeError, "Incomplete"):
                iot_setup.ensure_certificate(iot, cert_dir)
            iot.create_keys_and_certificate.assert_not_called()

    def test_changed_shared_policy_is_not_replaced(self):
        iot = aws_client("iot")
        with Stubber(iot) as stub:
            stub.add_response("get_policy", {"policyDocument": '{"Statement":[]}'}, {"policyName": iot_setup.POLICY_NAME})
            with self.assertRaisesRegex(RuntimeError, "differs"):
                iot_setup.ensure_policy(iot, iot_setup.device_policy(ACCOUNT))
            stub.assert_no_pending_responses()

    def test_another_camera_cannot_overwrite_env(self):
        with tempfile.TemporaryDirectory() as directory:
            env, aws = Path(directory) / ".env", Mock()
            common.update_env(env, {"CAMERA_ID": "another-camera"})
            with self.assertRaisesRegex(ValueError, "another camera"):
                iot_setup.provision(aws, CAMERA, BUCKET, env)
            aws.client.assert_not_called()


class IAMTests(unittest.TestCase):
    def setup_clients(self, existing=True):
        iam, sts = Mock(), Mock()
        sts.get_caller_identity.return_value = IDENTITY
        if not existing:
            iam.get_user.side_effect = ClientError({"Error": {"Code": "NoSuchEntity"}}, "GetUser")
        pages = {
            "list_attached_user_policies": [{"AttachedPolicies": []}],
            "list_user_policies": [{"PolicyNames": [iam_setup.POLICY_NAME] if existing else []}],
            "list_groups_for_user": [{"Groups": []}],
            "list_access_keys": [{"AccessKeyMetadata": []}],
        }
        iam.get_paginator.side_effect = lambda name: Mock(paginate=Mock(return_value=pages[name]))
        iam.get_user_policy.return_value = {"PolicyDocument": iam_setup.upload_policy(BUCKET)}
        iam.create_access_key.return_value = {"AccessKey": {"AccessKeyId": KEY_ID, "SecretAccessKey": KEY_SECRET}}
        return iam, sts, pages

    def test_first_setup_then_reuse_one_saved_key_without_printing_secret(self):
        iam, sts, pages = self.setup_clients(existing=False)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as output:
            env, aws = Path(directory) / ".env", fake_session(iam=iam, sts=sts)
            iam_setup.provision(aws, BUCKET, env)
            iam.create_user.assert_called_once_with(UserName=iam_setup.USER_NAME)
            iam.put_user_policy.assert_called_once_with(UserName=iam_setup.USER_NAME, PolicyName=iam_setup.POLICY_NAME,
                                                        PolicyDocument=json.dumps(iam_setup.upload_policy(BUCKET)))
            first = env.read_bytes()
            iam.get_user.side_effect = None
            pages["list_user_policies"] = [{"PolicyNames": [iam_setup.POLICY_NAME]}]
            pages["list_access_keys"] = [{"AccessKeyMetadata": [{"AccessKeyId": KEY_ID, "Status": "Active"}]}]
            probe = Mock()
            probe.get_caller_identity.return_value = {**IDENTITY, "Arn": f"arn:aws:iam::{ACCOUNT}:user/{iam_setup.USER_NAME}"}
            with patch("boto3.client", return_value=probe):
                iam_setup.provision(aws, BUCKET, env)
            self.assertEqual(first, env.read_bytes())
            iam.create_access_key.assert_called_once_with(UserName=iam_setup.USER_NAME)
            self.assertNotIn(KEY_ID, output.getvalue())
            self.assertNotIn(KEY_SECRET, output.getvalue())

    def test_user_with_extra_permissions_cannot_get_new_key(self):
        iam, sts, pages = self.setup_clients()
        pages["list_groups_for_user"] = [{"Groups": [{"GroupName": "Admins"}]}]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "other policies/groups"):
                iam_setup.provision(fake_session(iam=iam, sts=sts), BUCKET, Path(directory) / ".env")
        iam.create_access_key.assert_not_called()
        iam.put_user_policy.assert_not_called()

    def test_unsaved_remote_key_is_not_rotated(self):
        iam, sts, pages = self.setup_clients()
        pages["list_access_keys"] = [{"AccessKeyMetadata": [{"AccessKeyId": KEY_ID, "Status": "Active"}]}]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "secrets are not saved"):
                iam_setup.provision(fake_session(iam=iam, sts=sts), BUCKET, Path(directory) / ".env")
        iam.create_access_key.assert_not_called()
        iam.delete_access_key.assert_not_called()

    def test_failed_local_save_removes_only_the_new_key(self):
        iam, sts, _ = self.setup_clients()
        with tempfile.TemporaryDirectory() as directory, patch.object(iam_setup, "update_env", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                iam_setup.provision(fake_session(iam=iam, sts=sts), BUCKET, Path(directory) / ".env")
        iam.delete_access_key.assert_called_once_with(UserName=iam_setup.USER_NAME, AccessKeyId=KEY_ID)

    def test_partial_saved_credentials_fail_before_aws_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            env, aws = Path(directory) / ".env", Mock()
            common.update_env(env, {"AWS_ACCESS_KEY_ID": KEY_ID})
            with self.assertRaisesRegex(RuntimeError, "Incomplete"):
                iam_setup.provision(aws, BUCKET, env)
            aws.client.assert_not_called()


class MQTTTests(unittest.TestCase):
    def test_publish_waits_for_suback_and_matching_echo(self):
        import paho.mqtt.client as mqtt
        env = {"IOT_ENDPOINT": "example-ats.iot.ap-south-1.amazonaws.com", "CAMERA_ID": CAMERA,
               "CA_PATH": "ca.pem", "CERT_PATH": "cert.pem", "KEY_PATH": "private.key"}
        client, acknowledged = Mock(), {"value": False}
        client.subscribe.return_value = (mqtt.MQTT_ERR_SUCCESS, 1)
        reason = Mock(is_failure=False)

        def start():
            client.on_connect(client, None, None, reason, None)
            client.on_subscribe(client, None, 1, [reason], None)
            acknowledged["value"] = True

        def publish(topic, payload, qos):
            self.assertTrue(acknowledged["value"])
            self.assertEqual(topic, common.contracts.TOPIC_TEST)
            self.assertEqual(qos, 0)
            client.on_message(client, None, Mock(topic=topic, payload=payload))
            return Mock(rc=mqtt.MQTT_ERR_SUCCESS)

        client.loop_start.side_effect, client.publish.side_effect = start, publish
        with patch.object(mqtt_smoke_test, "read_env", return_value=env), patch.object(mqtt, "Client", return_value=client) as factory:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                mqtt_smoke_test.smoke_test(Path("unused/.env"), timeout=1)
            self.assertIn("PASS", output.getvalue())
        self.assertEqual(factory.call_args.kwargs["client_id"], f"burnwatch-{CAMERA}-smoketest")
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_rejected_subscribe_does_not_publish(self):
        import paho.mqtt.client as mqtt
        client = Mock()
        client.loop_start.side_effect = lambda: client.on_subscribe(client, None, 1, [Mock(is_failure=True)], None)
        env = {"IOT_ENDPOINT": "example", "CAMERA_ID": CAMERA, "CA_PATH": "ca", "CERT_PATH": "cert", "KEY_PATH": "key"}
        with patch.object(mqtt_smoke_test, "read_env", return_value=env), patch.object(mqtt, "Client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "subscription rejected"):
                mqtt_smoke_test.smoke_test(Path("unused/.env"), timeout=1)
        client.publish.assert_not_called()
        client.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
