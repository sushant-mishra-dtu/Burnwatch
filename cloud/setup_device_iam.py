"""Provision the upload-only hackathon key; run only after P4 approval."""
import json

from setup_common import REGION, check_bucket, common_arguments, read_env, session, update_env

USER_NAME = "burnwatch-device"
POLICY_NAME = "burnwatch-frame-upload"
SHORTCUT_WARNING = (
    "WARNING: a saved IAM user key is a hackathon shortcut. "
    "Production should use the IoT credentials provider with a role alias."
)


def upload_policy(bucket, partition="aws"):
    return {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "s3:PutObject",
                       "Resource": f"arn:{partition}:s3:::{check_bucket(bucket)}/frames/*"}],
    }


def provision(aws_session, bucket, env_file):
    from botocore.exceptions import ClientError
    bucket = check_bucket(bucket)
    existing = read_env(env_file)
    if existing.get("BUCKET", bucket) != bucket:
        raise ValueError(".env BUCKET differs from --bucket; do not silently retarget a shared device user")
    key_id, secret = existing.get("AWS_ACCESS_KEY_ID"), existing.get("AWS_SECRET_ACCESS_KEY")
    if bool(key_id) != bool(secret):
        raise RuntimeError("Incomplete saved AWS key; recover or remove the pair before rerunning")
    identity = aws_session.client("sts").get_caller_identity()
    document = upload_policy(bucket, identity["Arn"].split(":")[1])
    iam = aws_session.client("iam")
    try:
        iam.get_user(UserName=USER_NAME)
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchEntity":
            raise
        iam.create_user(UserName=USER_NAME)
    # Refuse extra permissions rather than removing existing policies implicitly.
    managed = list(iam.get_paginator("list_attached_user_policies").paginate(UserName=USER_NAME))
    inline = list(iam.get_paginator("list_user_policies").paginate(UserName=USER_NAME))
    groups = list(iam.get_paginator("list_groups_for_user").paginate(UserName=USER_NAME))
    if any(page["AttachedPolicies"] for page in managed) or any(page["Groups"] for page in groups):
        raise RuntimeError("Existing burnwatch-device has other policies/groups; review before provisioning")
    names = {name for page in inline for name in page["PolicyNames"]}
    if names - {POLICY_NAME}:
        raise RuntimeError("Existing burnwatch-device has other inline policies; review before provisioning")
    if POLICY_NAME in names:
        saved = iam.get_user_policy(UserName=USER_NAME, PolicyName=POLICY_NAME)["PolicyDocument"]
        if saved != document:
            raise RuntimeError("Existing upload policy differs; review before replacing it")
    else:
        iam.put_user_policy(UserName=USER_NAME, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(document))
    pages = iam.get_paginator("list_access_keys").paginate(UserName=USER_NAME)
    keys = [key for page in pages for key in page["AccessKeyMetadata"]]
    if key_id:
        if not any(key["AccessKeyId"] == key_id and key["Status"] == "Active" for key in keys):
            raise RuntimeError("Saved key is not active on burnwatch-device; recover before rerunning")
        # Verify the saved secret too; never print either credential or signing errors.
        import boto3
        try:
            owner = boto3.client("sts", region_name=REGION, aws_access_key_id=key_id,
                                 aws_secret_access_key=secret).get_caller_identity()
        except Exception:
            raise RuntimeError("Saved device credentials could not be authenticated; recover before rerunning") from None
        if owner["Arn"] != f"arn:{identity['Arn'].split(':')[1]}:iam::{identity['Account']}:user/{USER_NAME}":
            raise RuntimeError("Saved credentials do not belong to the expected device user")
        print("Reused the saved active device key")
    else:
        if keys:
            raise RuntimeError("AWS already has device keys whose secrets are not saved here; recover them before creating more")
        created = iam.create_access_key(UserName=USER_NAME)["AccessKey"]
        try:
            update_env(env_file, {"AWS_ACCESS_KEY_ID": created["AccessKeyId"],
                                  "AWS_SECRET_ACCESS_KEY": created["SecretAccessKey"],
                                  "BUCKET": bucket, "AWS_REGION": REGION})
        except BaseException:
            iam.delete_access_key(UserName=USER_NAME, AccessKeyId=created["AccessKeyId"])
            raise
        print(f"Device upload key saved to {env_file} (credentials omitted)")
    print(SHORTCUT_WARNING)


def main():
    parser = common_arguments(__doc__)
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args()
    provision(session(args.profile), args.bucket, args.env_file)


if __name__ == "__main__":
    main()
