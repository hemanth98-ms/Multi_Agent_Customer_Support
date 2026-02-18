import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from agents.response_generator import ai_chain

def test_response(query, data, scenario_name):
    print(f"\n--- Testing Scenario: {scenario_name} ---")
    print(f"Query: {query}")
    print(f"Data Provided: {data}")
    
    # Context is usually chat history or system prompt context
    context = "User is asking for details."
    
    try:
        response = ai_chain.generate_response(context=context, data=data)
        print(f"AI Response: {response}")
        
        # Validation logic
        if "cannot calculate" in response.lower() or "missing" in response.lower() or "could not find" in response.lower():
            print("✅ PASSED: AI refused to hallucinate.")
            return True
        else:
            # Check if it invented a number (e.g., 1000)
            import re
            numbers = re.findall(r'\d+', response)
            if numbers:
                 print(f"⚠️ WARNING: AI might have hallucinated a number: {numbers}")
            else:
                 print("❓ INDETERMINATE: No numbers, but didn't explicitly refuse.")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

# Test Cases
# Case 1: Partial Data
data_partial = "Found 3 invoices. Invoice A is $500. Invoice B and C have no details."
test_response("What is the sum?", data_partial, "Partial Data Hallucination Check")

# Case 2: No Data
data_none = "No records found matching your criteria."
test_response("What is the total amount?", data_none, "No Data Hallucination Check")
