# Security Policy

## Supported Scope

RAG V1 is a local, single-user portfolio application. It is designed to bind to
`127.0.0.1` and process a small trusted document set. It does not claim to be a
public or multi-user enterprise service.

## Security Properties

- credentials are loaded from the environment or ignored `.env` file
- uploaded filenames cannot choose their storage path
- extension and media type must agree
- uploads are size bounded and saved incrementally
- deletion rejects stored paths outside the configured upload directory
- retrieval is filtered to explicitly selected document IDs
- provider errors are mapped to stable messages without raw upstream details
- logs exclude document text, queries, prompts, answers, vectors, keys, and paths
- LLM calls use `store=False` and enable no tools or conversation state

## Deployment Warning

Do not expose this V1 directly to the internet or a shared network. Before any
shared deployment it requires, at minimum, authentication, authorization,
tenant isolation, restrictive CORS, rate limiting, audit retention, managed
secrets, transport security, backups, and a production vector database review.

## Secrets

Never commit `.env` or an API key. If a key is accidentally exposed, revoke it
at the provider immediately, create a replacement, and remove the secret from
Git history before publishing the repository.

## Reporting a Vulnerability

If this project is hosted on GitHub, use the repository's private Security
Advisory feature. Do not include credentials, private documents, or exploit
details in a public Issue.
