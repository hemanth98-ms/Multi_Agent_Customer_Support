from agents.router_agent import start_chat

if __name__ == "__main__":
    print("--- ROUTER SYSTEM STARTED ---")
    
    while True:
        result = start_chat()

        if result is None:
            print("\nConversation ended.")
            break

        print("\n--- RESPONSE RECEIVED ---")
        print(result)
