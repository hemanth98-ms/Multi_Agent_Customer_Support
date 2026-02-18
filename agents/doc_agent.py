"""
docAgent.py

Document summarizer + document Q&A agent using Gemini LLM + RAG (FAISS).

SUPPORTED (as requested):
- PDF
- XLSX / XLSM

REMOVED:
- DOCX
- CSV
- TXT

Behavior:
- Summarize document ONCE
- Ask unlimited questions after summary (RAG)
- No re-summarizing unless you load a new doc
"""

# =========================================================
# Silence HuggingFace / Transformers noise (user-facing UX)
# =========================================================
import os
import logging

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)



import io
import re
import requests
import traceback
from urllib.parse import urlparse
from decouple import config

# PDF extraction
import pdfplumber
from pypdf import PdfReader

# XLSX extraction
import openpyxl

# LangChain
from langchain_core.documents import Document as LC_Document
from langchain_community.vectorstores import FAISS

# Embeddings (local; avoids API quota)
from langchain_huggingface import HuggingFaceEmbeddings

# LLMs (keep Gemini related content)
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq


# =========================================================
# Status messaging helper (user requested “please wait…”)
# =========================================================
def status(msg: str) -> None:
    """
    Prints short progress messages so user knows the app is working.

    Why:
    - Summarization and indexing can take time
    - Users need feedback to avoid thinking the program hung

    Note:
    - This is NOT debug logging; it is user-facing progress output.
    """
    print(msg, flush=True)


# =========================================================
# 1) Gemini setup (DO NOT REMOVE)
# =========================================================
GEMINI_API_KEY = config("GEMINI_API_KEY", default=None)

""" def get_gemini_llm():
 

    Why:
    - Avoid startup crash if env misconfigured
    - Keep import/init safer in some environments
   
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing in .env")

    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=GEMINI_API_KEY,
        temperature=0.3,
        max_output_tokens=512,
    ) """

# ---------------------------------------------------------
# 2) Initialize Gemini LLM (COMMENTED - do not remove)
# ---------------------------------------------------------
""" llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.3,
    max_output_tokens=512,
) """

GROQ_API_KEY = config("GROQ_API_KEY", default=None)

# Groq chat model (LLM)  (KEEP THIS BLOCK UNCHANGED)
llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant",
    temperature=0.3,
    max_tokens=2048,
     timeout=60, 
) 


# =========================================================
# 3) Embeddings (HuggingFace) for RAG
# =========================================================
def get_embeddings():
    """
    Purpose:
    - Create a local embedding model used for semantic search in RAG.

    What are embeddings?
    - Embeddings convert text into vectors (numbers) capturing meaning.
    - Similar meanings => vectors close together => retriever finds relevant chunks.

    Why HuggingFaceEmbeddings here?
    - Local (no network, no API quota/cost)
    - Stable for large indexing jobs
    - Works well with FAISS (vector similarity search library)

    Model chosen:
    - sentence-transformers/all-MiniLM-L6-v2
      * small & fast
      * widely used for semantic retrieval
      * good quality for general document Q&A
    """
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


# =========================================================
# 4) Google export URL converter
# =========================================================
def convert_google_url_to_download(url: str) -> str:
    """
    Converts Google URLs into direct downloadable/export URLs.

    Supports:
    - Google Sheets export -> XLSX
    - Google Drive file -> direct download

    NOTE:
    - We keep Docs conversion code out because you requested to only handle PDF + Excel.
      (If you later want Docs back, we can re-add DOCX extraction + allow doc export.)
    """
    sheet_match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if sheet_match:
        file_id = sheet_match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"

    drive_match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if drive_match:
        file_id = drive_match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    open_id_match = re.search(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)", url)
    if open_id_match:
        file_id = open_id_match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    return url


# =========================================================
# 5) Download file with error handling
# =========================================================
def download_file(url: str) -> tuple[str, bytes]:
    """
    Downloads a file from URL and returns (filename, bytes).

    Error handling:
    - 403/404/4xx: clear message
    - HTML response: usually means login/permission page
    """
    url = convert_google_url_to_download(url)

    try:
        response = requests.get(url, timeout=60, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error while downloading file: {str(e)}")

    if response.status_code == 403:
        raise RuntimeError("Access denied (403). File needs permission/login or is not public.")
    if response.status_code == 404:
        raise RuntimeError("File not found (404). The URL may be incorrect or expired.")
    if response.status_code >= 400:
        raise RuntimeError(f"Failed to download file. HTTP Status: {response.status_code}")

    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)

    content_type = (response.headers.get("Content-Type") or "").lower()

    if "text/html" in content_type:
        raise RuntimeError(
            "The provided URL returned an HTML page instead of a file.\n"
            "This usually means the link requires login or is not a direct download/export link.\n"
            "Fix: Make file public OR provide direct export/download URL."
        )

    # If filename missing extension, best-effort guess
    if not filename or "." not in filename:
        if "spreadsheetml.sheet" in content_type:
            filename = "google_sheet.xlsx"
        elif "application/pdf" in content_type:
            filename = "downloaded.pdf"
        else:
            filename = "downloaded_file"

    return filename, response.content


# =========================================================
# 6) Text extraction (PDF + Excel only)
# =========================================================
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF.

    Strategy:
    - Try pdfplumber first:
        better on layout/table PDFs.
    - Fallback to pypdf:
        works on many PDFs where pdfplumber fails.

    Output:
    - Plain text string.
    """
    parts = []

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    parts.append(txt)
        out = "\n".join(parts).strip()
        if out:
            return out
    except Exception:
        # Fall back to pypdf
        pass

    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages_text).strip()


def extract_text_from_xlsx_structured(file_bytes: bytes, max_rows: int = 100) -> str:
    """
    Convert Excel into compact structured text.

    Why structured conversion?
    - LLMs do better with key:value representations than raw spreadsheet tables.
    - Improves retrieval accuracy for accounting-style Q&A.

    Strategy:
    - First row => headers
    - Each subsequent row => dict(header -> value)
    - Skip empty cells
    - Cap rows to avoid huge prompts and memory growth
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    output = []

    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue

        headers = [str(h).strip() for h in rows[0] if h]

        output.append(f"Sheet: {sheet.title}")
        output.append(f"Columns: {headers}")

        count = 0
        for row in rows[1:]:
            if count >= max_rows:
                output.append("... remaining rows omitted")
                break

            record = {}
            for idx, value in enumerate(row):
                if idx < len(headers) and value not in (None, ""):
                    record[headers[idx]] = str(value)

            if record:
                output.append(str(record))
                count += 1

    return "\n".join(output).strip()


def extract_text(filename: str, file_bytes: bytes) -> str:
    """
    Detect file type based on extension and extract text.

    Allowed:
    - .pdf
    - .xlsx
    - .xlsm
    """
    name = filename.lower()

    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)

    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return extract_text_from_xlsx_structured(file_bytes)

    raise ValueError("Unsupported file type. Use PDF, XLSX, XLSM only.")


# =========================================================
# 7) Chunking for summarization (generator)
# =========================================================
def chunk_text_generator(text: str, max_chars: int = 12000, overlap: int = 400):
    """
    Generator chunking for summarization.

    Why chunking is required:
    - LLMs have context/token limits.
    - Large PDFs/Excels may exceed those limits.
    - Chunking lets us summarize piece-by-piece safely.

    Why overlap:
    - Prevents losing information at chunk boundaries.
    - Especially important for tables or paragraphs split between chunks.
    """
    start = 0
    n = len(text)

    while start < n:
        end = min(start + max_chars, n)
        yield text[start:end]
        start = end - overlap
        if start < 0:
            start = 0


# =========================================================
# 8) Summarization (rolling summary)
# =========================================================
def summarize_text_with_gemini(text: str) -> str:
    """
    Summarize text using the active LLM (Gemini here).

    Output format is structured for business/accounting documents.
    """
    prompt = f"""
You are a professional document summarizer.

Summarize the document in this format:

1) Executive Summary (5-8 lines)
2) Key Points (bullets)
3) Entities (people/orgs/accounts), Dates, Amounts (if present)
4) Risks / Issues / Open Questions
5) Recommended Next Actions

Document:
\"\"\"{text}\"\"\"
"""
    print("DEBUG: about to call summarize_text_with_gemini", flush=True)
    response = llm.invoke(prompt)
    return response.content.strip()


def summarize_large_text(text: str) -> str:
    """
    Rolling summary approach.

    Guarantees:
    - Final output ALWAYS goes through the structured summary prompt
    - Output format remains unchanged
    - Rolling summary is skipped for structured/tabular content
    """

    # Heuristic: structured/tabular content (Excel-like) should NOT use rolling summary
    is_structured = text.count("{") > 5 and text.count("}") > 5

    # Fast path: small or structured documents
    if len(text) <= 6000 or is_structured:
        return summarize_text_with_gemini(text)

    # Rolling summary for long narrative documents (PDFs, reports)
    running_summary = ""
    chunk_count = 0
    MAX_CHUNKS = 3  # safety cap, not document-specific

    for chunk in chunk_text_generator(text, max_chars=6000, overlap=300):
        chunk_count += 1

        status(f"Please wait... summarizing part {chunk_count}.")
        prompt = f"""
You are summarizing a long document in parts.

CURRENT SUMMARY (keep it concise, max ~200 words):
{running_summary}

NEW CHUNK:
\"\"\"{chunk}\"\"\"

TASK:
Update the summary with any new important information from the new chunk.
Return ONLY the updated summary (max ~200 words).
"""
        response = llm.invoke(prompt)
        running_summary = response.content.strip()

        if chunk_count >= MAX_CHUNKS:
            break

    # 🔴 IMPORTANT: final formatting prompt is ALWAYS applied
    final_prompt = f"""
Convert this into a structured final summary format:

1) Executive Summary (5-8 lines)
2) Key Points (bullets)
3) Entities (people/orgs/accounts), Dates, Amounts (if present)
4) Risks / Issues / Open Questions
5) Recommended Next Actions

SUMMARY TEXT:
\"\"\"{running_summary}\"\"\"
"""
    final_response = llm.invoke(final_prompt)
    return final_response.content.strip()



# =========================================================
# 9) Chunking for RAG + FAISS build (generator)
# =========================================================
def chunk_for_rag_generator(text: str, chunk_size: int = 1500, overlap: int = 200):
    """
    Chunking specifically for RAG retrieval.

    Why smaller chunks than summarization?
    - Retrieval precision improves when chunks are not too large.
    - The retriever can grab only the relevant fragment instead of huge blocks.

    Overlap helps preserve context across chunk boundaries.
    """
    text = text.replace("\x00", " ").strip()
    n = len(text)
    start = 0

    while start < n:
        end = min(start + chunk_size, n)
        yield text[start:end]
        start = end - overlap
        if start < 0:
            start = 0


def build_vectorstore_incremental(text: str) -> FAISS:
    """
    Build FAISS index incrementally in batches (memory-safe).

    Why embeddings + FAISS:
    - Embeddings map chunks to vectors.
    - FAISS stores vectors and supports fast similarity search.
    - At question time, we retrieve the top-k similar chunks as context.

    Why incremental/batching:
    - Prevents memory spikes on large documents.
    - Avoids building huge lists at once.
    """
    embeddings = get_embeddings()

    vectorstore = None
    batch_docs = []
    batch_size = 100
    chunk_index = 0
    MAX_CHUNKS = 500  # safety cap

    for chunk in chunk_for_rag_generator(text, chunk_size=12000, overlap=400):
        chunk_index += 1
        batch_docs.append(LC_Document(page_content=chunk, metadata={"chunk": chunk_index}))

        if len(batch_docs) >= batch_size:
            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch_docs, embeddings)
            else:
                vectorstore.add_documents(batch_docs)
            batch_docs = []

        if chunk_index >= MAX_CHUNKS:
            break

    if batch_docs:
        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch_docs, embeddings)
        else:
            vectorstore.add_documents(batch_docs)

    return vectorstore


def answer_with_rag(vectorstore: FAISS, question: str, summary_hint: str = "") -> str:
    """
    RAG Q&A

    Flow:
    1) Retrieve top-k semantically relevant chunks using FAISS
    2) Provide ONLY retrieved text as context to the LLM
    3) LLM performs post-retrieval filtering + reasoning

    Key Design Principles:
    - Retrieval is approximate (semantic)
    - Filtering is exact (done by LLM using instructions)
    - Presentation (summary vs details) is controlled by prompt
    """
    retriever = vectorstore.as_retriever(search_kwargs={"k": 20})
    docs = retriever.invoke(question)
    # Step 1: Semantic retrieval (approximate by design)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 20})
    docs = retriever.invoke(question)

    # Combine retrieved chunks
    context_chunks = [d.page_content for d in docs]
    context = "\n\n".join(context_chunks)

    # Step 2: Prompt with Summary + Context
    prompt = f"""
You are an intelligent assistant analyzing a document.

DOCUMENT SUMMARY:
{summary_hint}

RETRIEVED DOCUMENT CHUNKS:
\"\"\"{context}\"\"\"

QUESTION:
{question}

INSTRUCTIONS:
- Use the DOCUMENT SUMMARY and RETRIEVED CHUNKS to answer.
- If the answer is in the summary, USE IT.
- If the answer is not present, say: "Not found in the document."
- Answer the specific question asked.
- Do NOT split the answer into sections unless asked.
- Keep the tone professional and direct.
"""

    # Step 3: LLM grounded answer
    return llm.invoke(prompt).content.strip()



# =========================================================
# Module-level state (PERSISTS between calls)
# =========================================================



def start_chat():
    """
    Asks for document URL or local file path once,
    loads the document,
    extracts full raw text,
    and returns it as a single response.
    """

    try:
        source = input("Enter document URL or local file path: ").strip()

        if not source:
            return "No document source provided"

        # Load file
        if os.path.exists(source):
            filename = os.path.basename(source)
            with open(source, "rb") as f:
                file_bytes = f.read()

        elif source.startswith("http"):
            filename, file_bytes = download_file(source)

        else:
            return "Invalid file path or URL"

        # Extract raw text (no modification)
        extracted_text = extract_text(filename, file_bytes)

        if not extracted_text:
            return "No content extracted from document"

        # Return raw content exactly as-is
        return extracted_text

    except Exception as e:
        return str(e)








# =========================================================
# 11) Run
# =========================================================
if __name__ == "__main__":
    start_chat()
