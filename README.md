# Router Agent System

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure API key in `.env`:
```
GOOGLE_API_KEY=your_actual_google_api_key
```

## Run

```bash
python main.py
```

## Test Cases

### 1. Test Excel/Document Analysis
```
You: Load C:/path/to/your/file.xlsx
You: Summarize the document
You: What are the key findings?
```

### 2. Test Zoho (Mock)
```
You: Find invoice INV-12345
```

### 3. Test Salesforce (Mock)
```
You: Show me Lead John Doe
```

### 4. Test Router Intelligence
```
You: Hello
You: Check status (should ask for clarification)
```

Type `exit` or `quit` to stop.
