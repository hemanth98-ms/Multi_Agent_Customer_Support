import json
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from utils.groq_client import setup_groq, call_groq
from agents.prompts import ROUTER_PROMPT

client = setup_groq()

def test_query(query, context, last_tool):
    print(f"\n--- Testing Query: '{query}' ---")
    print(f"Context: {last_tool}")
    
    full_prompt = (
        f"{ROUTER_PROMPT}\n\n"
        f"!!! SYSTEM STATUS !!!\n"
        f"Current Context / Last Tool: {last_tool}\n"
        f"Active Document: None\n"
        f"History:\nHuman: Check invoices\nAI: Here are 3 invoices.\n\n"
        f"User Query: {query}\n\n"
        f"Respond ONLY with valid JSON."
    )
    
    try:
        response = call_groq(client, full_prompt, temperature=0.0)
        # Clean JSON
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
            
        print(f"Raw Response: {response}")
        data = json.loads(response)
        print(f"Destination: {data.get('destination')}")
        return data.get('destination')
    except Exception as e:
        print(f"Error: {e}")
        return None

# Test Cases
print("Running Verification...")
dest1 = test_query("What is the sum of these?", "Here are invoices...", "zoho")
dest2 = test_query("That sum is wrong", "The sum is 15000", "zoho")

if dest1 == "zoho" and (dest2 == "zoho" or dest2 == "chat"):
    print("\n✅ PASSED: Logic handles context and feedback correctly.")
else:
    print("\n❌ FAILED: Misrouting detected.")
    print(f"Expected 'zoho' & 'zoho/chat', Got '{dest1}' & '{dest2}'")
