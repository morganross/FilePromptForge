# Contributing

FPF accepts focused fixes and provider updates through pull requests.

1. Create a branch from `master`.
2. Preserve provider behavior unless the pull request documents a deliberate
   compatibility change.
3. Add or update tests for changed behavior.
4. Run `python scripts/test.py`.
5. Describe provider, model, configuration, and migration effects in the pull
   request.

Do not commit credentials, generated logs, raw provider responses, build
artifacts, or private deployment configuration.
