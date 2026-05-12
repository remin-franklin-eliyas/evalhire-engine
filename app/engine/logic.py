import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.getenv("MODEL_TOKEN") or "not-configured",
)

CV_TEXT_CHAR_LIMIT = 12_000  # ~3000 tokens — well within Llama 3's 8k context


def evaluate_cv(cv_text: str, job_description: str) -> dict:
    cv_text = cv_text[:CV_TEXT_CHAR_LIMIT]
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Founding CTO of a high-growth AI startup. "
                        "Evaluate the candidate with extreme rigor. "
                        "You must return ONLY a JSON object with the following keys: "
                        "'score' (0-100), 'critique' (list of 3 strings), and 'verdict' (one sentence). "
                        "Focus on High Agency, Technical Depth, and Velocity."
                    )
                },
                {
                    "role": "user",
                    "content": f"JD: {job_description}\n\nCV: {cv_text}"
                }
            ],
            model="Llama-3.3-70B-Instruct",
            temperature=0.1,
        )
        
        # Strip markdown code fences if the model wraps its output
        raw_content = response.choices[0].message.content or ""
        raw_content = raw_content.strip()
        if raw_content.startswith("```"):
            # extract content between the fences
            parts = raw_content.split("```")
            raw_content = parts[1].removeprefix("json").strip()

        if not raw_content:
            raise RuntimeError("LLM returned an empty response.")

        return json.loads(raw_content)
    
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {str(e)}") from e