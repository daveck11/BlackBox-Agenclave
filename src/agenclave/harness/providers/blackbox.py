# Gateway adapter: the OpenAI SDK pointed at an OpenAI-compatible base URL.
# Started as the BlackBox adapter; OpenRouter speaks the same protocol with
# the same provider/model ids, so one class covers both. AGENCLAVE_PROVIDER
# picks which, and the key + base come from config (BLACKBOX_API_KEY /
# OPENROUTER_API_KEY, AGENCLAVE_<PROVIDER>_API_BASE).
#
# Same error contract as DirectAgent: propose_patch puts failures in
# PatchResult.error instead of raising.

from __future__ import annotations

from ...config import settings
from ..interfaces import Agent, PatchResult, Task
from .base import AGENT_SYSTEM_PROMPT, build_task_prompt, extract_diff


class BlackBoxAgent(Agent):
    # api_key / api_base default to settings for `provider`; they're constructor
    # args so tests can point at a mock endpoint. The client is built lazily, so
    # constructing an agent needs no key.

    def __init__(
        self,
        model: str,
        *,
        provider: str = "blackbox",
        api_key: str | None = None,
        api_base: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.provider = provider
        self.name = f"{provider}:{model}"  # unique within a dispatch; flags the source
        self._api_key = (
            api_key if api_key is not None else settings.gateway_api_key(provider)
        )
        self._api_base = (api_base or settings.gateway_api_base(provider)).rstrip("/")
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        # Build (once) an OpenAI Async client pointed at the gateway. Only reached
        # when a key is present (propose_patch guards first), so api_key is set.
        if self._client is None:
            import openai  # lazy: avoid import cost / key lookup at module load

            self._client = openai.AsyncOpenAI(
                api_key=self._api_key or "",
                base_url=self._api_base,
            )
        return self._client

    async def propose_patch(self, task: Task) -> PatchResult:
        if not self._api_key:
            return PatchResult(
                agent_name=self.name,
                instance_id=task.instance_id,
                patch="",
                error=(
                    f"{self.provider.upper()}_API_KEY not set; cannot call the "
                    f"{self.provider} API"
                ),
            )
        try:
            client = self._get_client()
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": build_task_prompt(task)},
                ],
            )
            text = resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - capture, never crash dispatch
            return PatchResult(
                agent_name=self.name,
                instance_id=task.instance_id,
                patch="",
                error=f"{type(exc).__name__}: {exc}",
            )
        return PatchResult(
            agent_name=self.name,
            instance_id=task.instance_id,
            patch=extract_diff(text),
            raw_response=text,
        )
