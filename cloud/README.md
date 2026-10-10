# BurnWatch AWS setup (P4)

All resources run in `ap-south-1`, Bedrock included. The verifier is Claude on
Bedrock, with an NVIDIA Nemotron fallback and Rekognition as the last resort.
The Lambda is a P4 stub until Claude Code completes P5.
Uploading a JPEG now raises an explicit error; it does not produce a verdict.

## Review checkpoint

P4 in `../PROMPTS.md` requires approval of `template.yaml` and the IAM policies
before deployment or credential provisioning. The exact policies are in
`template.yaml`, `setup_iot.device_policy()` and `setup_device_iam.upload_policy()`.

| Principal | Allowed actions | Scope |
|---|---|---|
| Verifier Lambda | `s3:GetObject` | Stack bucket's `frames/*` |
| Verifier Lambda | `dynamodb:PutItem` | `burnwatch-events` |
| Verifier Lambda | `sns:Publish` | `burnwatch-alerts` |
| Verifier Lambda | `iot:Publish` | `burnwatch/*/verdict` in this account/region |
| Verifier Lambda | `bedrock-mantle:CreateInference` | `*` (resource-level ARN format not yet verified; tighten after review) |
| Verifier Lambda | `rekognition:DetectLabels` | `*` (the API has no resource-level scope) |
| Verifier Lambda | CloudWatch log creation/writes | SAM's generated basic execution role |
| IoT certificate | `iot:Connect` | `client/burnwatch-*` |
| IoT certificate | `iot:Publish`, `iot:Receive` | `topic/burnwatch/*` |
| IoT certificate | `iot:Subscribe` | `topicfilter/burnwatch/*` |
| IAM user `burnwatch-device` | `s3:PutObject` only | Stack bucket's `frames/*` |

The verifier calls Claude through the anthropic SDK's `AnthropicBedrockMantle`
client, which signs requests to `https://bedrock-mantle.ap-south-1.api.aws/anthropic/v1/messages`.
That endpoint authorizes **`bedrock-mantle:CreateInference`**
([Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock),
[AWS bedrock-mantle permissions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-responses-api.html)).
`ap-south-1` is served with global routing. The default model is
`anthropic.claude-haiku-5-5`; enable it under Bedrock → Model access before
deploying. The Nemotron fallback is plain HTTPS to NVIDIA and needs no IAM; leave
`NvidiaApiKey`/`NvidiaModelId` empty to skip it.

**The saved IAM user key is a hackathon shortcut.** Production should use the
IoT credentials provider with a role alias for temporary upload credentials.

## Local preparation and checks (PowerShell, repository root)

Python on the Codex machine is 3.13.5; the template uses Lambda `python3.13`.
Install AWS CLI v2 for login/inspection and create an isolated tools environment:

```powershell
python -m venv cloud/.venv
.\cloud\.venv\Scripts\Activate.ps1
python -m pip install -r cloud/requirements.txt aws-sam-cli
aws --version
sam --version
python --version
```

If PowerShell activation is disabled, use
`.\cloud\.venv\Scripts\python.exe` and `.\cloud\.venv\Scripts\sam.exe` directly.
Do not alter the system execution policy for this project.

```powershell
$env:SAM_CLI_TELEMETRY = '0'
sam validate --lint --template-file cloud/template.yaml --region ap-south-1
sam build --template-file cloud/template.yaml
python -m unittest discover -s cloud/tests -v
```

SAM resolves `CodeUri` relative to its template: `verify/` here means
`cloud/verify/`. Writing `cloud/verify/` in this template would incorrectly look
under `cloud/cloud/verify/`. The account/region-derived bucket name is repeated
in the Lambda policy and environment to avoid an S3 notification dependency cycle.
SAM generates the filtered notification and S3-to-Lambda invoke permission.

The bucket blocks all public access, uses AES256 encryption and expires
`frames/` objects after seven days. The table is on-demand with `camera` (S)
and `ts` (N) as keys. The bucket/table are retained if the stack is deleted.
Names are fixed for one BurnWatch stack per account/region.

## Deploy after approval

Use your normal setup/admin AWS profile, not the device's upload-only key.
If necessary, authenticate with `aws configure sso` then `aws sso login`.
Credentials are not copied into source files or printed by the setup scripts.

```powershell
aws sts get-caller-identity --region ap-south-1
aws iot describe-endpoint --endpoint-type iot:Data-ATS --region ap-south-1
sam build --template-file cloud/template.yaml
sam deploy --guided --region ap-south-1
```

For guided deployment use stack name `burnwatch`, region `ap-south-1`, your
`AlertEmail`, model ID `anthropic.claude-haiku-5-5`, confidence threshold `0.6`,
and the ATS hostname printed above as `IotEndpoint`. Leave `NvidiaApiKey` empty
in the guided prompt (and decline saving it); pass it only on the command line,
`sam deploy --parameter-overrides NvidiaApiKey=... NvidiaModelId=...`, so it never
lands in `samconfig.toml`. Allow SAM to create the Lambda IAM role
(`CAPABILITY_IAM`), review the changeset, then save configuration for later runs.
Subsequent deployments use `sam build --template-file cloud/template.yaml`
followed by `sam deploy --region ap-south-1`.

```powershell
aws cloudformation describe-stacks --stack-name burnwatch --region ap-south-1 --query 'Stacks[0].Outputs' --output table
```

Copy `BucketName` from these outputs (along with table/topic values for
PROGRESS.md Facts). The next commands prompt for that actual bucket name:

```powershell
$burnwatchBucket = Read-Host 'SAM BucketName output'
python cloud/setup_iot.py --camera rwa-gate-2 --bucket $burnwatchBucket
python cloud/setup_device_iam.py --bucket $burnwatchBucket
```

Both accept `--profile NAME` and `--env-file PATH`; default settings go to
`device/.env`. IoT creates/reuses the thing and active certificate, attaches
the agreed `burnwatch-device` policy, and downloads AmazonRootCA1 over HTTPS.
IAM creates/reuses the upload-only user and saves the access key privately.
Reruns validate/reuse saved credentials. They refuse incomplete local
credential files, unsaved AWS keys, a changed policy, or extra user permissions,
so retries cannot silently rotate credentials or change a shared policy.
If a new IAM key cannot be saved, that new key is removed.

The committed `../device/.env.example` lists all device configuration keys.
Certificate paths generated on Windows are absolute. After copying `.env` and
`certs/` to the PYNQ, change `CERT_PATH`, `KEY_PATH` and `CA_PATH` to their
board paths (for example `/home/xilinx/burnwatch/device/certs/...`).
`device/.env`, `device/certs/`, `.pem` and `.key` are already git-ignored.
The real credentials must never be committed or pasted into logs/chat.

**Confirm the SNS email** using its subscription link. Deployment success
does not mean that email delivery is ready.

## IoT video take and smoke test

1. In the AWS console select Mumbai (`ap-south-1`), open **IoT Core → Test →
   MQTT test client** and subscribe to `burnwatch/#` before running the test.
2. On the laptop, from the repository root:

   ```powershell
   python cloud/mqtt_smoke_test.py --env-file device/.env
   ```

3. Expect `PASS: published and received ... on burnwatch/test`. Check that the
   same JSON token appears in the console. The test uses the certificate and
   a separate `burnwatch-rwa-gate-2-smoketest` client ID, subscribes before
   publishing, and checks the broker echoes the matching payload.
4. For P6, keep the console subscribed to watch `events`, `heartbeat` and
   `verdict`. Only `frames/*.jpg` uploads trigger verification; the MQTT event
   message itself does not invoke Lambda.

The smoke test checks real MQTT delivery. SNS email, Claude/Nemotron verification and
an S3 event are checked after P5/P6, rather than reported as passing from mocks.
