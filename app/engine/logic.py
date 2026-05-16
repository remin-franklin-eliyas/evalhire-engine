import os
import json
from dotenv import load_dotenv

load_dotenv()

CV_TEXT_CHAR_LIMIT = 12_000  # ~3000 tokens — well within Llama 3's 8k context

DEFAULT_PERSONA = (
    "You are a Founding CTO of a high-growth AI startup. "
    "Evaluate the candidate with extreme rigor. "
    "Focus on High Agency, Technical Depth, and Velocity."
)

# ── Provider selection ─────────────────────────────────────────────────────────
# Set MODEL_PROVIDER to "openai" or "anthropic" to switch away from the default.
# GitHub Models is the zero-config default — no billing required during development.
#
#   MODEL_PROVIDER=github   → GitHub Models (Llama-3.3-70B), requires MODEL_TOKEN
#   MODEL_PROVIDER=openai   → OpenAI API, requires OPENAI_API_KEY
#   MODEL_PROVIDER=anthropic → Anthropic API, requires ANTHROPIC_API_KEY
#   MODEL_NAME              → optional override for the model name on any provider
_PROVIDER = (os.getenv("MODEL_PROVIDER") or "github").lower()
_MODEL_NAME = os.getenv("MODEL_NAME")  # optional per-provider model override

if _PROVIDER == "openai":
    from openai import OpenAI as _OpenAI
    _client = _OpenAI(api_key=os.getenv("OPENAI_API_KEY") or "not-configured")
    _model = _MODEL_NAME or "gpt-4o-mini"
    _provider_type = "openai"
elif _PROVIDER == "anthropic":
    try:
        import anthropic as _anthropic_sdk
    except ImportError as exc:
        raise ImportError(
            "The 'anthropic' package is required for MODEL_PROVIDER=anthropic. "
            "Install it with: pip install anthropic"
        ) from exc
    _client = _anthropic_sdk.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or "not-configured")
    _model = _MODEL_NAME or "claude-3-5-haiku-20241022"
    _provider_type = "anthropic"
else:  # "github" (default)
    from openai import OpenAI as _OpenAI
    _client = _OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=os.getenv("MODEL_TOKEN") or "not-configured",
    )
    _model = _MODEL_NAME or "Llama-3.3-70B-Instruct"
    _provider_type = "github"


def _build_system_prompt(persona: str) -> str:
    return (
        f"{persona.strip()} "
        "You must return ONLY a JSON object with the following keys: "
        "'score' (0-100), 'critique' (list of 3 strings), and 'verdict' (one sentence). "
        "The score should reflect how well the candidate fits the role described."
    )


def _parse_llm_json(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].removeprefix("json").strip()
    if not raw:
        raise RuntimeError("LLM returned an empty response.")
    return json.loads(raw)


def evaluate_cv(cv_text: str, job_description: str, persona: str = DEFAULT_PERSONA) -> dict:
    cv_text = cv_text[:CV_TEXT_CHAR_LIMIT]
    system_prompt = _build_system_prompt(persona)
    user_message = f"JD: {job_description}\n\nCV: {cv_text}"
    try:
        if _provider_type == "anthropic":
            response = _client.messages.create(
                model=_model,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_content = response.content[0].text or ""
        else:  # openai / github — both use the OpenAI-compatible chat completions API
            response = _client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                model=_model,
                temperature=0.1,
            )
            raw_content = response.choices[0].message.content or ""

        return _parse_llm_json(raw_content)
    
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {str(e)}") from e