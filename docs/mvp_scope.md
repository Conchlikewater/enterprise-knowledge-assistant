# RAG MVP Scope

## 1. Project Goal

Build a small RAG knowledge-base question-answering system that can:

- import local documents
- split documents into chunks
- generate embeddings
- store and retrieve vectors
- answer questions based on retrieved content
- return source citations

## 2. Document Input

Initial supported document types:

- TXT
- Markdown
- PDF

Initial dataset size:

- 5 to 10 documents
- mainly technical notes, job descriptions, and project materials

## 3. Core Pipeline

The MVP pipeline contains:

1. document loading
2. text cleaning
3. chunking
4. embedding generation
5. vector storage
6. similarity retrieval
7. answer generation
8. source citation output

## 4. API Requirements

Use FastAPI to provide:

- document upload or import endpoint
- question-answering endpoint
- health check endpoint
- clear error responses

## 5. Evaluation

Prepare:

- 20 test questions
- expected source documents
- answer correctness notes
- retrieval failure cases
- bad case log

Evaluation dimensions:

- retrieval relevance
- answer correctness
- citation correctness
- response time
- failure handling

## 6. MVP Acceptance Criteria

The MVP is complete when it can:

- import at least 5 documents
- divide documents into searchable chunks
- retrieve relevant chunks for a question
- generate an answer based on retrieved content
- display source citations
- answer 20 prepared test questions
- record bad cases
- run through FastAPI

## 7. Out of Scope

The MVP will not include:

- Agent workflows
- Docker deployment
- complex frontend
- model fine-tuning
- multi-user system
- login and permission management
- large-scale distributed vector database
- advanced document parsing
