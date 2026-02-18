from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from config.config import Config

class AIChain:
    """AI Response Chain Handler"""
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=Config.MODEL_NAME,
            temperature=Config.TEMPERATURE,
            google_api_key=Config.GOOGLE_API_KEY,
            request_timeout=60
        )
        
        self.prompt = PromptTemplate(
            input_variables=["context", "data", "history"],
            template="""
You are an intelligent assistant.

Conversation History:
{history}

Context (Role):
{context}

Request Data (Source Information):
{data}

Instructions:
- Answer the user's question using ONLY the provided "Request Data" and "Conversation History".
- **Context Resolution**: Use "Conversation History" to understand what "it", "that", "the previous result" refers to.
- **Data Source**: Use "Request Data" for factual answers to the CURRENT question.
- Do NOT use outside knowledge.
- If the answer is found in the data, provide it directly and concisely.
- **ANALYTICAL TASK**: If the user asks for a calculation (sum, average, count, difference) on data shown in "Conversation History" or "Request Data", YOU MUST PERFORM THE CALCULATION.
- **CRITICAL**: PROVE YOUR WORK. If the data retrieval is partial or missing values, DO NOT INVENT THEM. If you cannot calculate the true sum because of missing data, state 'I cannot calculate the exact sum because some invoice amounts are missing in the retrieved data.'
- If the "Request Data" does not contain the answer AND it's not in the "Conversation History", state EXACTLY: "I could not find this information in the current source."
- Do NOT add polite preambles like "Here is the information" or "Based on the data". Just give the answer.
"""
        )
        
        self.chain = self.prompt | self.llm
    
    def generate_response(self, context: str, data: str, history: str = "") -> str:
        """Generate AI response"""
        try:
            response = self.chain.invoke({
                "context": context,
                "data": data,
                "history": history
            })
            return response.content
        except Exception as e:
            raise Exception(f"AI generation failed: {str(e)}")

# Global instance
ai_chain = AIChain()