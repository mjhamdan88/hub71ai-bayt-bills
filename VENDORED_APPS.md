# Application provenance

Unicom and Unibot are unmodified public Git submodules, pinned to compatible
commits on `fix/tool-batch-continuation`:

- Unicom: https://github.com/meena-erian/unicom at `3a9df4a1c367f03cbf8945013674d76d4f8eca7c`
- Unibot: https://github.com/meena-erian/unibot at `c0caf8bdc81f54116bc7afa3f13dffc266e09254`
- Unicrm: retained snapshot `4146d88a153c231bec0bd47445d5c467384626e2`

These branches include Responses support, request retries, tool continuation,
and the existing template's migrations. Default upstream branches do not yet
include those changes. Deployment uses the recorded commits, never moving branch
tips. Review and test both apps together before updating the pins.

The project-level `templates/unibot/default_bot.py` opts into upstream Responses
support using the local Portacode client and configured model. Custom bot code
should pass the same options. Existing stored bot code is not overwritten.
