"""
Interactive CLI Chat with Database-Only Zoho Books Agent
No Zoho OAuth required - uses database only!
"""

from zoho_books_db_only import DatabaseOnlyAgent

def main():
    print("=" * 60)
    print("🤖 Zoho Books Agent - Database-Only (No OAuth!)")
    print("=" * 60)
    print("Type your questions and press Enter.")
    print("Type 'exit' or 'quit' to end the session.\n")
    
    # Initialize agent
    try:
        agent = DatabaseOnlyAgent()
        print("✅ Agent initialized successfully!")
        print("📊 Using database for invoice queries\n")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        return
    
    # Chat loop
    history = []
    
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Run agent
            print("🤔 Thinking...", end="\r")
            context = {"history": history}
            result = agent.run(user_input, context)
            
            # Display response
            print(f"Agent: {result.text}")
            
            # Display token usage
            if result.token_usage:
                t = result.token_usage
                print(f"📊 Tokens — Prompt: {t['prompt']} | Completion: {t['completion']} | Total: {t['total']} / 6000\n")
            else:
                print()
            
            # Update history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": result.text})
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

if __name__ == "__main__":
    main()
