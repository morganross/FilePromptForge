# Providers

FPF contains adapters for OpenAI Responses, Anthropic Messages, Google Gemini,
Google Deep Research, OpenRouter, Perplexity Sonar, Tavily Research, and OpenAI
Deep Research.

The provider and model are selected independently. FPF does not promise that
every model exposed by a provider supports web search, reasoning, or the same
request parameters. Provider adapters construct their native payloads and
surface provider errors when a selected combination is unavailable.

The packaged configuration uses public API endpoints. Deployment-specific
gateways can be selected by supplying another configuration file. The public
default configuration does not route requests through APICostX infrastructure.

Provider catalogs and lifecycle status change independently of FPF releases.
Consult the selected provider's current API documentation when choosing a
model for production work.
