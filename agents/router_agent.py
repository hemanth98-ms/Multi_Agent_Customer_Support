import sys
import os
import json
import google.generativeai as genai
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from agents.zoho_books_db_only import DatabaseOnlyAgent

# --- IMPORT YOUR DOC AGENT (Unchanged) ---
# Assumes docAgent.py is in the same directory or python path

# --- IMPORT YOUR DOC AGENT HELPERS ---
# We import the stateless helper functions to build the logic here
from agents.doc_agent import (
    download_file,
    extract_text,
    summarize_large_text,
    build_vectorstore_incremental,
    answer_with_rag,
    status
)

# --- RESPONSE AGENT ---
from agents.response_agent import router as response_router

# --- GROQ SETUP (Using your existing utils) ---
from utils.groq_client import setup_groq, call_groq 

router_client = setup_groq()
chat_history = []

# --- ROUTER SCHEMA ---
class RouterDecision(BaseModel):
    destination: Literal["zoho", "salesforce", "excel", "chat", "ask_user"] = Field(
        description="The tool to use."
    )
    entities: List[str] = Field(
        default=[], 
        description="For Zoho/Salesforce: The IDs/Names. For Excel: Leave empty or add context."
    )
    missing_info: Optional[str] = Field(default=None)
    response_message: str = Field(description="Message to the user.")

# --- ROUTER PROMPT ---
from agents.prompts import ROUTER_PROMPT

# --- TOOL FUNCTIONS ---

def use_zoho(entities, query): 
    """
    Hands over control to the Database-Only Zoho Agent.
    """
    # print("\n[🔄 Switching to Zoho Database Agent...]")
    
    try:
        # Initialize the DB agent
        agent = DatabaseOnlyAgent()
        
        # Convert router history (LangChain Messages) to list of dicts for DB agent
        db_agent_history = []
        for msg in chat_history:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            db_agent_history.append({"role": role, "content": msg.content})
            
        # Run the agent
        context = {"history": db_agent_history}
        result = agent.run(query, context)
        raw_output = result.text.strip()
        
        # --- RESPONSE GENERATOR INTEGRATION ---
        # Analyze the result: Does it answer the question?
        
        # Prepare history string
        history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in chat_history[-5:]])

        api_response = response_router.process_request({
            "type": "sales",
            "data": f"User Query: {query}\nDatabase Result: {raw_output}",
            "history": history_str
        })
        
        if api_response["status"] == "success":
            final_response = api_response["response"]
            
            # Simple check for failure/missing info in the AI response
            failure_keywords = ["could not find this information", "no specific records", "not found", "no records found"]
            if any(k in final_response.lower() for k in failure_keywords):
                 return f"{final_response}\n\n⚠️ Would you like me to check Salesforce instead?"
            
            return final_response
        else:
            return raw_output
        
    except Exception as e:
        return f"❌ Zoho Agent Error: {str(e)}"

def use_salesforce(entities, query): 
    """
    Mock Salesforce Agent with 'Ask Permission' Logic
    """
    # print("\n[🔄 Switching to Salesforce Agent...]")
    
    # Placeholder: Simulate a "Not Found" or "Partial Info" scenario for demonstration
    # In a real app, you'd call the Salesforce API here.
    # Placeholder: Simulate a list of opportunities with values
    raw_output = "Found 3 Opportunities for Lead XYZ: \n1. Op A: $1000\n2. Op B: $2000\n3. Op C: $1500"
    
    # --- RESPONSE GENERATOR INTEGRATION ---
    history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in chat_history[-5:]])
    
    api_response = response_router.process_request({
        "type": "sales",
        "data": f"User Query: {query}\nSalesforce Result: {raw_output}",
        "history": history_str
    })
    
    if api_response["status"] == "success":
        final_response = api_response["response"]
        
        # Logic: If the answer implies missing info, ask to check Zoho
        failure_keywords = ["could not find this information", "no specific records", "not found", "no records found"]
        if any(k in final_response.lower() for k in failure_keywords):
            return f"{final_response}\n\n🕵️ I couldn't find this in Salesforce. Would you like me to check Zoho Books?"
            
        return final_response
    else:
        return raw_output


# --- LOCAL DOC STATE (Router manages this now) ---
DOC_STATE = {
    "vectorstore": None,
    "summary": None,
    "raw_text": None
}

def use_doc_agent(entities, query):
    """
    Hands over control to the Document Agent Logic (hosted here).
    """
    # print("\n[🔄 Switching to Document Agent...]")
    global DOC_STATE

    try:
        # --- 1. LOAD DOCUMENT (IF NEEDED) ---
        if DOC_STATE["vectorstore"] is None:
            # entities[0] is expected to be the file path from the router
            file_path = entities[0] if entities else ""
            
            if not file_path or file_path == "Active Document":
                 return "❌ Doc Agent Error: No file loaded. Please provide a file path."
            
            print(f"[🤖 Auto-filling file path]: {file_path}")
            
            # Load file bytes
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
            elif file_path.startswith("http"):
                filename, file_bytes = download_file(file_path)
            else:
                try:
                    # Try to handle it as a raw string if it's not a valid path but maybe a URL-like
                    filename, file_bytes = download_file(file_path)
                except:
                     return "❌ Doc Agent Error: Invalid file path or URL."

            # Extract Text
            status("[DocAgent] Extracting text...")
            extracted_text = extract_text(filename, file_bytes)
            
            if not extracted_text:
                 return "❌ Doc Agent Error: No content extracted from document."
            
            DOC_STATE["raw_text"] = extracted_text

            # Summarize
            status("[DocAgent] Generating summary...")
            summary = summarize_large_text(extracted_text)
            DOC_STATE["summary"] = summary

            # Build Vector Store
            status("[DocAgent] Building search index (RAG)...")
            vectorstore = build_vectorstore_incremental(extracted_text)
            DOC_STATE["vectorstore"] = vectorstore
            
            status("[DocAgent] Ready!")

        # --- 2. HANDLE QUESTION ---
        # Prioritize the task description (entities[1]) if the user query is just a confirmation
        task_description = entities[1] if len(entities) > 1 else ""
        is_confirmation = query.lower().strip() in ["yes", "y", "proceed", "ok", "confirm", "sure", "summarize it"]
        
        if is_confirmation and task_description:
            final_query = task_description
            print(f"[🤖 Using inferred task]: {final_query}")
        else:
            # If the user just pasted the file path as the query, default to "Summarize this"
            # Logic: If query matches the file path entity, or looks like a path
            cleaned_query = query.strip('"').strip("'").strip()
            cleaned_path = entities[0].strip('"').strip("'").strip() if entities else ""
            
            if cleaned_query == cleaned_path or (os.path.exists(cleaned_query) and " " not in cleaned_query):
                 final_query = "Summarize this document"
                 print(f"[🤖 Using inferred task]: {final_query}")
            else:
                 final_query = query

        # SPECIAL HANDLING FOR SUMMARIES
        if "summar" in final_query.lower() and DOC_STATE["summary"]:
             raw_summary = DOC_STATE['summary']
             # Format Summary
             api_response = response_router.process_request({
                "type": "technical",
                "data": f"Document Summary: {raw_summary}"
             })
             
             final_resp = api_response['response'] if api_response["status"] == "success" else raw_summary
             return final_resp # CLEAN OUTPUT (No prefix)

        status(f"[DocAgent] Thinking about: {final_query}")
        raw_answer = answer_with_rag(DOC_STATE["vectorstore"], final_query, summary_hint=DOC_STATE["summary"])
        
        # Format Answer
        history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in chat_history[-5:]])
        
        api_response = response_router.process_request({
            "type": "technical",
            "data": f"User Question: {final_query}\nAnswer: {raw_answer}",
            "history": history_str
        })
        final_resp = api_response['response'] if api_response["status"] == "success" else raw_answer
        
        return final_resp # CLEAN OUTPUT (No prefix)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ Doc Agent Error: {str(e)}"

# --- MAIN CHAT LOOP ---

def start_chat():
    """Main function called by your main.py"""
    
    # Track context (simple approach)
    last_tool_used = "None"
    
    while True:
        user_query = input("👉 You: ")
        
        if user_query.lower() in ["exit", "quit"]:
            return None
        
        try:
            # Prepare Prompt
            active_doc_status = "None"
            if DOC_STATE["vectorstore"] is not None:
                 active_doc_status = "Loaded (Ready for Q&A)"
            
            history_text = "\n".join([f"{msg.type}: {msg.content}" for msg in chat_history[-4:]])
            
            full_prompt = (
                f"{ROUTER_PROMPT}\n\n"
                f"!!! SYSTEM STATUS !!!\n"
                f"Current Context / Last Tool: {last_tool_used}\n"
                f"Active Document: {active_doc_status}\n"
                f"History:\n{history_text}\n\n"
                f"User Query: {user_query}\n\n"
                f"Respond ONLY with valid JSON."
            )
            
            # Call LLM (Router)
            response_text = call_groq(router_client, full_prompt, temperature=0.0, max_tokens=1024)
            
            if not response_text:
                print("❌ Error: Empty response from router")
                continue
            
            # Clean JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            result = json.loads(response_text)
            
            # --- DECISION HANDLER ---
            output = ""
            
            # CASE 1: ASK USER OR CHAT
            if result["destination"] in ["ask_user", "chat"]:
                chat_history.append(HumanMessage(content=user_query))
                chat_history.append(AIMessage(content=result['response_message']))
                output = f"🤖 AI: {result['response_message']}"
            
            # CASE 2: EXECUTE TOOL
            else:
                if result["destination"] == "zoho":
                    output = use_zoho(result["entities"], user_query)
                elif result["destination"] == "salesforce":
                    output = use_salesforce(result["entities"], user_query)
                    
                elif result["destination"] == "excel":
                    # VALIDATION
                    raw_path = result["entities"][0] if result["entities"] else ""
                    # Clean path: Strip outer quotes
                    raw_path = raw_path.strip('"').strip("'").strip()
                    
                    is_active_doc = DOC_STATE["vectorstore"] is not None and raw_path == "Active Document"
                    
                    if not is_active_doc:
                        suspicious_keywords = ["file_path", "path/to/file", "your_file", "document.pdf", "filename"]
                        if not raw_path or raw_path.lower() in suspicious_keywords or (not os.path.exists(raw_path) and not raw_path.startswith("http")):
                            msg = "I need a valid file path or URL to proceed. Please provide it."
                            chat_history.append(HumanMessage(content=user_query))
                            chat_history.append(AIMessage(content=msg))
                            output = f"🤖 AI: {msg}"
                        else:
                             output = use_doc_agent(result["entities"], user_query)
                    else:
                        output = use_doc_agent(result["entities"], user_query)

                # Update History
                chat_history.append(HumanMessage(content=user_query))
                chat_history.append(AIMessage(content=f"Tool Used: {result['destination']}"))
                
                # Update Context
                last_tool_used = result["destination"]
            
            print(f"\n{output}\n")

        except json.JSONDecodeError:
            print(f"❌ Router Error: Invalid JSON.\nRaw: {response_text}")
        except Exception as e:
            print(f"❌ Error: {e}")

# Allow standalone execution for testing
if __name__ == "__main__":
    print("--- ROUTER AGENT STARTED ---")
    start_chat()