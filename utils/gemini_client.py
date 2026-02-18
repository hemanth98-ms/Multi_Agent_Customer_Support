from langchain_google_genai import ChatGoogleGenerativeAI
from config.config import Config

def setup_gemini():
    """Initialize Google Gemini client"""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=Config.GOOGLE_API_KEY,
        temperature=Config.TEMPERATURE,
        max_tokens=Config.MAX_TOKENS
    )
