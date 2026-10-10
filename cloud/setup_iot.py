"""Create/reuse an IoT thing and certificate; run only after P4 approval."""
import json
from pathlib import Path
import ssl
import urllib.request

from setup_common import (
    REGION, atomic_write, check_bucket, common_arguments, contracts,
    read_env, session, update_env,
)

POLICY_NAME = "burnwatch-device"
ROOT_CA_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"


def device_policy(account_id, partition="aws"):
    prefix = f"arn:{partition}:iot:{REGION}:{account_id}:"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "iot:Connect", "Resource": prefix + "client/burnwatch-*"},
            {"Effect": "Allow", "Action": ["iot:Publish", "iot:Receive"], "Resource": prefix + "topic/burnwatch/*"},
            {"Effect": "Allow", "Action": "iot:Subscribe", "Resource": prefix + "topicfilter/burnwatch/*"},
        ],
    }


def ensure_policy(iot, document):
    from botocore.exceptions import ClientError
    try:
        existing = iot.get_policy(policyName=POLICY_NAME)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        iot.create_policy(policyName=POLICY_NAME, policyDocument=json.dumps(document))
        return
    if json.loads(existing["policyDocument"]) != document:
        raise RuntimeError("Existing burnwatch-device policy differs; review it before changing a shared policy")


def ensure_certificate(iot, cert_dir):
    paths = [cert_dir / name for name in ("certificate.pem", "private.key", "certificate.arn")]
    present = [path.exists() for path in paths]
    if any(present) and not all(present):
        raise RuntimeError(f"Incomplete certificate files in {cert_dir}; recover them before rerunning")
    if all(present):
        arn = paths[2].read_text(encoding="utf-8").strip()
        description = iot.describe_certificate(certificateId=arn.rsplit("/", 1)[-1])["certificateDescription"]
        if description["certificateArn"] != arn or description["status"] != "ACTIVE":
            raise RuntimeError("Saved IoT certificate is not active in this account")
        if description["certificatePem"].strip() != paths[0].read_text(encoding="utf-8").strip():
            raise RuntimeError("Saved certificate does not match its AWS certificate ARN")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.load_cert_chain(str(paths[0]), str(paths[1]))
        return arn, paths[0], paths[1]
    created = iot.create_keys_and_certificate(setAsActive=True)
    try:
        atomic_write(paths[0], created["certificatePem"])
        atomic_write(paths[1], created["keyPair"]["PrivateKey"])
        atomic_write(paths[2], created["certificateArn"] + "\n")
    except BaseException:
        print(f"Certificate created but local save failed: {created['certificateArn']}; recover before rerunning")
        raise
    return created["certificateArn"], paths[0], paths[1]


def provision(aws_session, camera, bucket, env_file):
    camera, bucket = contracts.check_camera(camera), check_bucket(bucket)
    existing = read_env(env_file)
    if existing.get("CAMERA_ID", camera) != camera:
        raise ValueError("This .env belongs to another camera; use that camera or a separate --env-file")
    if existing.get("BUCKET", bucket) != bucket and existing.get("AWS_ACCESS_KEY_ID"):
        raise ValueError("Saved S3 credentials target another bucket; resolve them before changing BUCKET")
    iot = aws_session.client("iot")
    identity = aws_session.client("sts").get_caller_identity()
    endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    print(f"IOT_ENDPOINT={endpoint}")
    cert_dir = Path(env_file).parent / "certs" / camera
    root_ca = cert_dir.parent / "AmazonRootCA1.pem"
    if not root_ca.exists():
        with urllib.request.urlopen(ROOT_CA_URL, timeout=30) as response:
            pem = response.read().decode("ascii")
        ssl.PEM_cert_to_DER_cert(pem)
        atomic_write(root_ca, pem)
    else:
        ssl.PEM_cert_to_DER_cert(root_ca.read_text(encoding="ascii"))
    ensure_policy(iot, device_policy(identity["Account"], identity["Arn"].split(":")[1]))
    thing_name = contracts.client_id(camera)
    from botocore.exceptions import ClientError
    try:
        iot.describe_thing(thingName=thing_name)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        iot.create_thing(thingName=thing_name)
    arn, certificate, private_key = ensure_certificate(iot, cert_dir)
    iot.attach_policy(policyName=POLICY_NAME, target=arn)
    iot.attach_thing_principal(thingName=thing_name, principal=arn)
    update_env(env_file, {
        "IOT_ENDPOINT": endpoint, "CAMERA_ID": camera, "CLIENT_ID": thing_name,
        "CERT_PATH": certificate.resolve().as_posix(),
        "KEY_PATH": private_key.resolve().as_posix(),
        "CA_PATH": root_ca.resolve().as_posix(), "BUCKET": bucket, "AWS_REGION": REGION,
    })
    print(f"Thing {thing_name} ready; settings saved to {env_file} (credentials omitted)")


def main():
    parser = common_arguments(__doc__)
    parser.add_argument("--camera", default="rwa-gate-2")
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args()
    provision(session(args.profile), args.camera, args.bucket, args.env_file)


if __name__ == "__main__":
    main()
