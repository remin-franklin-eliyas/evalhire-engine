import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# GitHub Models uses an OpenAI-compatible endpoint
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.getenv("MODEL_TOKEN"), # Updated variable name
)

def evaluate_cv(cv_text: str, job_description: str):
    """
    Evaluates a CV against a JD using Llama 3 on GitHub's free tier.
    """
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a Founding CTO. Evaluate the candidate with extreme rigor."
                },
                {
                    "role": "user", 
                    "content": f"JD: {job_description}\n\nCV: {cv_text}"
                }
            ],
            model="meta-llama-3-70b-instruct",
            temperature=0.1, 
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Brain Error: {str(e)}"