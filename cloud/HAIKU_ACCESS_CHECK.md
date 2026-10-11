# Haiku 5.5 account access check

Checked on 11 October 2026 using the authenticated local AWS profile `burnwatch`
in `ap-south-1`. No successful model response was obtained.

## Results

- CLI login is valid: STS `GetCallerIdentity` succeeds.
- `ListFoundationModels` and `GetFoundationModel` list
  `anthropic.claude-haiku-5-5` as ACTIVE, with TEXT and IMAGE input, TEXT output,
  and `INFERENCE_PROFILE` inference support.
- `GetFoundationModelAvailability` returns:
  `regionAvailability=AVAILABLE`, `entitlementAvailability=AVAILABLE`,
  `authorizationStatus=NOT_AUTHORIZED`, and
  `agreementAvailability.status=NOT_AVAILABLE`.
- The configured Anthropic SDK Mantle request returned HTTP 404:
  `The model 'anthropic.claude-haiku-5-5' does not exist`.
  This is an endpoint result, not evidence that the model is absent from AWS.
  Request ID: `req_rzvjopxadrt5kdanlhntuzt7cpp7kbpf5bc6buor52ycfhd5cx6a`.
- `GetUseCaseForModelAccess` says the first-use form has not been filled out.
- After the user explicitly approved the exact BurnWatch student project details,
  `PutUseCaseForModelAccess` returned `ValidationException`:
  `Your account is not authorized to perform this action. Please create a support case (https://console.aws.amazon.com/support/home) with details about your use case and we will get back to you.`
- `GetInferenceProfile` confirms the ACTIVE global route
  `global.anthropic.claude-haiku-5-5` in Mumbai. A small `InvokeModel` test through
  that route returned HTTP 400 / `ValidationException`: `Operation not allowed`.
  Request ID: `9132373e-59a8-4519-969f-5a497a11a7bd`.
- The free-tier account-plan lookup returned `ResourceNotFoundException` /
  `Missing data for account`. This does not establish whether the account is on
  a free or paid plan, or whether any credits apply to inference.

## Test settings

The test asked for `{"ok":true}`. It used `max_tokens=2048`,
`output_config.effort=low`, and no temperature/top-p/top-k settings. The Mantle
test used Anthropic SDK 1.13.0, timeout 20 seconds, and one SDK retry. The native
Bedrock test used boto3 1.43.108, a 20-second read timeout, and no retries.

No AWS stack was deployed, no device credentials were created, and no model or
account plan was switched. The model test and first-use form are separate from
P4's still-pending template/IAM deployment approval.

## Next action

Open an [AWS Support case](https://console.aws.amazon.com/support/home) with the
above failed operations and request IDs. Ask AWS why this account cannot submit
the Anthropic first-use form or invoke Haiku 5.5. A case has not been sent by the
agent. Retry model availability and the test after AWS resolves access.

Reference documentation:

- [AWS Haiku 5.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html)
- [AWS model access requirements](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [Anthropic's Mantle integration](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)

The AWS model card documents global native Bedrock inference for Mumbai, while
the project currently configures Mantle. Validate a working route before changing
the verifier implementation or its IAM policy.
