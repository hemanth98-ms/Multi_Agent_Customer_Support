from groq import Groq
from config.config import Config

def setup_groq():
    """Initialize Groq client"""
    return Groq(api_key=Config.GROQ_API_KEY)

def call_groq(client, prompt, temperature=1, max_tokens=2048):
    """Call Groq with the given prompt"""
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_completion_tokens=max_tokens,
            top_p=1,
            stream=False
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling Groq: {e}")
        return None
