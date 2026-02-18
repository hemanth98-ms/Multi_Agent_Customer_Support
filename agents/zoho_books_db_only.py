"""
Zoho Books Agent - Database-Only Version (No OAuth Required)
Works with invoice data already in the database via RAG
"""

import os
import json
# import psycopg2 (Moved to RAGService)
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_groq import ChatGroq
from langchain.agents import create_agent, AgentState
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import StructuredTool

# ============================================================================
# CONFIGURATION
# ============================================================================

load_dotenv()

class Settings(BaseModel):
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    google_api_key: str | None = os.getenv("GOOGLE_API_KEY")
    llm_model: str = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    embeddings_model: str = os.getenv("EMBEDDINGS_MODEL", "models/gemini-embedding-001")
    database_url: str | None = os.getenv("DATABASE_URL")

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

# ============================================================================
# BASE CLASSES
# ============================================================================

@dataclass
class AgentResult:
    text: str
    steps: List[str]
    confidence: float
    agent_name: str
    token_usage: Dict[str, int] = None  # {prompt, completion, total}

# ============================================================================
# RAG SERVICE (Database-Only)
# ============================================================================

class RAGService:
    def __init__(self):
        self.settings = get_settings()
        if not self.settings.database_url:
            raise ValueError("DATABASE_URL is not set.")
        if not self.settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set.")
        
        genai.configure(api_key=self.settings.google_api_key)
        self.embedding_model = self.settings.embeddings_model
        
        import psycopg2
        self.conn = psycopg2.connect(self.settings.database_url)
        self.conn.autocommit = True

    def embed_query(self, text: str) -> List[float]:
        """Generates embedding for a query."""
        result = genai.embed_content(
            model=self.embedding_model,
            content=text,
            task_type="retrieval_query",
            output_dimensionality=768
        )
        return result["embedding"]

    def search_invoices(self, query: str, limit: int = 1) -> List[Dict]:
        """Searches for similar invoices in the database."""
        if not query or not query.strip():
            return [{"content": "No query provided", "similarity": 0.0}]
        
        query_embedding = self.embed_query(query.strip())
        # Force truncation to 768 dims to match database
        if len(query_embedding) > 768:
            query_embedding = query_embedding[:768]
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT content, metadata, 1 - (embedding <=> %s::vector) as similarity
                FROM invoice_embeddings
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (query_embedding, query_embedding, limit))
            
            results = []
            for row in cur.fetchall():
                content = str(row[0])[:200]  # Hard limit 200 chars
                # Extract only invoice number from metadata
                meta = row[1] if isinstance(row[1], dict) else {}
                small_meta = {"invoice": meta.get("invoice_number", "N/A")}
                results.append({
                    "content": content,
                    "meta": small_meta,
                    "score": round(float(row[2]), 2)
                })
            return results

# ============================================================================
# TOOL SCHEMAS
# ============================================================================

class SearchContentArgs(BaseModel):
    query: str = Field(..., description="Search query for invoices")
    limit: int = Field(1, description="Number of results (max 2)")

# ============================================================================
# DATABASE-ONLY AGENT
# ============================================================================

class DatabaseOnlyAgent:
    name = "billing_db"
    
    def __init__(self):
        self.settings = get_settings()
        
        # Initialize RAG
        try:
            self.rag = RAGService()
        except Exception as e:
            raise ValueError(f"Failed to initialize RAG service: {e}")

        # Verify API key
        if not self.settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        # Initialize LLM
        self.llm = ChatGroq(
            api_key=self.settings.groq_api_key,
            model_name=self.settings.llm_model,
            temperature=0
        )

        # Initialize Tools (RAG only)
        tools = [
            StructuredTool.from_function(
                func=self.rag.search_invoices,
                name="search_invoices",
                description="Search invoice data in the database. Use this for queries about invoices, customers, products, or amounts.",
                args_schema=SearchContentArgs
            )
        ]

        # Initialize Agent
        system_prompt = """You are a helpful assistant with invoice database access.
Use 'search_invoices' tool for invoice questions. Answer general questions directly. Be concise."""

        self.agent = create_agent(
            model=self.llm,
            tools=tools,
            state_schema=AgentState,
            system_prompt=system_prompt
        )

    def run(self, message: str, context: Dict[str, Any]) -> AgentResult:
        # Prepare History (limit to last 2 to prevent rate limits)
        raw_history = context.get("history", [])[-2:]
        chat_history = []
        for msg in raw_history:
            if msg.get("role") == "user":
                chat_history.append(HumanMessage(content=msg.get("content")))
            elif msg.get("role") == "assistant":
                chat_history.append(AIMessage(content=msg.get("content")))

        # Run Agent
        try:
            result = self.agent.invoke({
                "messages": chat_history + [HumanMessage(content=message)]
            })
            
            # Extract token usage from all AI messages
            total_prompt = 0
            total_completion = 0
            if "messages" in result:
                for msg in result["messages"]:
                    usage = getattr(msg, 'usage_metadata', None)
                    if usage:
                        total_prompt += usage.get('input_tokens', 0)
                        total_completion += usage.get('output_tokens', 0)
            
            token_usage = {
                "prompt": total_prompt,
                "completion": total_completion,
                "total": total_prompt + total_completion
            }
            
            if "messages" in result and len(result["messages"]) > 0:
                last_message = result["messages"][-1]
                output_text = last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                output_text = str(result)
            
            return AgentResult(text=output_text, steps=[], confidence=0.9, agent_name=self.name, token_usage=token_usage)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return AgentResult(text=f"I encountered an error: {e}", steps=[], confidence=0.1, agent_name=self.name, token_usage={"prompt": 0, "completion": 0, "total": 0})


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("Zoho Books Agent - Database-Only Version")
    print("=" * 60)
    print("No Zoho OAuth required - uses database only!")
    print("=" * 60)
    
    try:
        agent = DatabaseOnlyAgent()
        print("✅ Agent initialized successfully!\n")
        
        # Example query
        test_message = "Search for invoices"
        test_context = {"history": []}
        
        result = agent.run(test_message, test_context)
        print(f"📝 Query: {test_message}")
        print(f"📤 Response: {result.text}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
