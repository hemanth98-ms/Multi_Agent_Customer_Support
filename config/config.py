from decouple import config

class Config:
    # Groq Configuration
    GROQ_API_KEY = config("GROQ_API_KEY", default="your_groq_api_key")
    
    # Agent Settings
    MAX_TOKENS = config("MAX_TOKENS", default=1024, cast=int)
    TEMPERATURE = config("TEMPERATURE", default=1.0, cast=float)
    DEBUG = config("DEBUG", default=False, cast=bool)

    # Gemini Configuration
    GOOGLE_API_KEY = config("GOOGLE_API_KEY", default=None) 
    MODEL_NAME = "gemini-1.5-flash"
