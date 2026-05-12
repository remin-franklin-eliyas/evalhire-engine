import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# We use the OpenAI client because most free providers (GitHub/HF) follow this spec
client = OpenAI(
    base_url=os.getenv("MODEL_ENDPOINT"),
    api_key=os.getenv("MODEL_API_KEY"),
)

def evaluate_cv(cv_text, job_description):
    prompt = f"""
    You are a Founding CTO of a high-growth AI startup. 
    Analyze this CV against the Job Description. 
    Look for: High Agency, Technical Depth, and Velocity.
    
    JD: {job_description}
    CV: {cv_text}
    
    Provide a 'Startup Fit' score (0-100) and a 3-bullet point critique.
    """
    
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="meta-llama-3-70b-instruct", # Or whichever free model is available
        temperature=0.7,
    )
    
    return response.choices[0].message.content