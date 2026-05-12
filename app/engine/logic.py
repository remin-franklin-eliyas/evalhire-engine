import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.getenv("MODEL_TOKEN"),
)

def evaluate_cv(cv_text: str, job_description: str):
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
            model="meta-llama-3-70b-instruct",
            temperature=0.1,
            response_format={"type": "json_object"} # Some providers support this explicitly
        )
        
        # Parse the string into a real Python Dictionary
        raw_content = response.choices[0].message.content
        return json.loads(raw_content)
    
    except Exception as e:
        return {
            "score": 0,
            "critique": ["Error connecting to brain"],
            "verdict": f"Technical failure: {str(e)}"
        }