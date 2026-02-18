
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from config.config import Config
from agents.response_agent import router

def test_response_generator():
    print(f"Testing with Model: {Config.MODEL_NAME}")
    print(f"API Key present: {bool(Config.GOOGLE_API_KEY)}")
    
    test_data = {
        "type": "technical",
        "data": "User asked for a summary of a python script. The script contains a function 'multiply' that takes a and b and returns a*b."
    }
    
    print("\nSending request to router...")
    try:
        result = router.process_request(test_data)
        print("\nResult:")
        print(result)
        
        if result["status"] == "success":
            print("\n✅ Verification Successful: Response generated.")
        else:
            print(f"\n❌ Verification Failed: {result.get('message')}")
            
    except Exception as e:
        print(f"\n❌ Verification Error: {str(e)}")

if __name__ == "__main__":
    test_response_generator()
