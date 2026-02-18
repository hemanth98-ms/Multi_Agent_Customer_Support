
import sys
import os
from unittest.mock import patch
import builtins
import io

# Force UTF-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.append(os.getcwd())

# Mock input to simulate user interaction
# 1. "Summarize it" -> triggers use_doc_agent if file path is available? No, file path needs to be provided first if not loaded.
# But start_chat asks for input immediately.
# Flow:
# 1. "Summarize it" 
# 2. Router asks for file path? No, router asks "How can I assist you?"
# Wait, router agent loop:
# user_query = input("👉 You: ")
# If query is "Summarize it", router might say "which file?" or assume a context.
# Let's provide a file path first.

# Mock inputs:
# 1. "Here is a file: C:\Users\cube0\Downloads\Jagatheswari S Resume  (1).pdf" (Assuming router handles this or extracts entities)
# Actually, the user's prompt was "Summarize it" and then provided path.
# Let's simulate:
# 1. "Summarize C:\Users\cube0\Downloads\Jagatheswari S Resume  (1).pdf"
# 2. "exit"

mock_inputs = [
    "Check Salesforce for Lead XYZ",
    "Is the total amount greater than 4000?",
    "exit"
]

def run_router_test():
    print("Starting Router Agent Simulation...")
    with patch('builtins.input', side_effect=mock_inputs):
        try:
            from agents.router_agent import start_chat
            print("\n--- Interaction Start ---")
            while True:
                response = start_chat()
                if response is None:
                    break
                print(f"Agent Response: {response}")
            print("\n--- Interaction End ---")
        except StopIteration:
            print("Interaction finished (StopIteration)")
        except Exception as e:
            print(f"Error during simulation: {e}")

if __name__ == "__main__":
    run_router_test()
