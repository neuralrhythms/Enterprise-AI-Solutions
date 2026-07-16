"""
Prompt templates for the RAG pipeline.

Defines RAG_PROMPT_TEMPLATE, which is used by rag.py to construct the
prompt sent to the LLM. The template expects two variables: `context`
(the concatenated retrieved chunk text) and `question` (the user's query).
"""

from langchain.prompts import PromptTemplate

_TEMPLATE = """You are an assistant that answers questions based only on the provided context.
If the answer cannot be determined from the context, say "I don't know based on the provided context."

Context:
{context}

Question:
{question}

Answer:"""

RAG_PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["context", "question"],
    template=_TEMPLATE,
)
