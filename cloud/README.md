# cloud/

The AWS side, region `ap-south-1` (Bedrock region set separately via `BEDROCK_REGION`):

- `template.yaml`: SAM stack (S3 bucket, DynamoDB table, SNS topic, verifier Lambda).
- `verify/`: the S3-triggered Lambda that checks each suspect frame with Claude on Bedrock. `verify/cameras.json` lists the camera names and addresses.
- `setup_iot.py`, `setup_device_iam.py`: IoT thing, certificate, policy and the device's scoped S3 key.

Deploy commands are added in P4.
