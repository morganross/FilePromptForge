# Configuration

The packaged `FilePromptForge/fpf_config.yaml` contains public defaults.
Supply another YAML file with `--config` to override a route, timeout, model,
retry policy, reasoning effort, token limit, or web-search option.

Configuration precedence is:

1. Explicit function or CLI arguments
2. The selected YAML configuration
3. Packaged public defaults

The `provider_urls` mapping selects an endpoint for each provider. Private,
OpenAI-compatible, or self-hosted gateways belong in deployment-specific
configuration rather than the packaged default file.

Environment variables supply API credentials. OpenAI Deep Research uses the
OpenAI credential, and Google Deep Research uses the Google credential when
their provider-specific variable is absent.

Mutable runtime files are stored in operating-system user locations unless an
explicit path or environment override is supplied. Installed package files are
treated as read-only.
