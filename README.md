# ACL IntelliRAG v2.0

On-premise AI knowledge assistant — zero data leakage, enterprise-grade RAG platform.

## Project Structure

```
intellirag/
├── backend/                        # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/                 # Versioned API endpoints
│   │   │   ├── auth.py             # JWT authentication & RBAC
│   │   │   ├── query.py            # RAG query endpoint
│   │   │   ├── ingest.py           # Document upload & ingestion
│   │   │   ├── connectors.py       # Google Drive connector
│   │   │   ├── m365.py             # Microsoft 365 connector
│   │   │   ├── localfs.py          # Local file system connector
│   │   │   ├── analytics.py        # Usage analytics
│   │   │   └── router.py           # Route aggregator
│   │   ├── core/
│   │   │   ├── config.py           # App settings (pydantic-settings)
│   │   │   ├── database.py         # PostgreSQL async connection
│   │   │   ├── vector_store.py     # Qdrant client
│   │   │   ├── security.py         # JWT utilities
│   │   │   └── exceptions.py       # Custom exception handlers
│   │   ├── middleware/
│   │   │   └── logging.py          # Request/response logging
│   │   ├── models/                 # SQLAlchemy models (future)
│   │   ├── schemas/
│   │   │   ├── auth.py             # Auth request/response schemas
│   │   │   ├── query.py            # Query schemas
│   │   │   └── document.py         # Document schemas
│   │   ├── services/
│   │   │   ├── rag/
│   │   │   │   ├── pipeline.py     # Main RAG orchestration
│   │   │   │   ├── retrieval.py    # Hybrid vector+BM25 search
│   │   │   │   ├── generation.py   # Groq/Ollama LLM generation
│   │   │   │   └── date_filter.py  # Natural language date parsing
│   │   │   ├── connectors/
│   │   │   │   ├── gdrive.py       # Google Drive sync service
│   │   │   │   └── m365.py         # Microsoft 365 sync service
│   │   │   ├── embedding.py        # Ollama embedding service
│   │   │   ├── ingestion.py        # Document chunking & indexing
│   │   │   ├── memory.py           # Conversation session storage
│   │   │   ├── analytics.py        # Query logging
│   │   │   └── storage.py          # MinIO file storage
│   │   └── main.py                 # FastAPI app entry point
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                       # Next.js 14 TypeScript frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx          # Root layout
│   │   │   └── page.tsx            # Main dashboard page
│   │   ├── components/
│   │   │   ├── ui/                 # Reusable primitives
│   │   │   │   └── index.tsx       # Card, Badge, Input, StatusDot, ProgressBar
│   │   │   ├── ui/Button.tsx       # Button component
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx      # App header with user info
│   │   │   │   └── TabNav.tsx      # Navigation tabs
│   │   │   ├── auth/
│   │   │   │   └── LoginForm.tsx   # Login form component
│   │   │   ├── chat/
│   │   │   │   ├── ChatWidget.tsx  # Main chat widget (<200 lines)
│   │   │   │   ├── ChatMessage.tsx # Individual message bubble
│   │   │   │   ├── ChatInput.tsx   # Message input area
│   │   │   │   └── SourcePills.tsx # Source selection pills
│   │   │   ├── charts/
│   │   │   │   ├── BarChart.tsx    # SVG bar chart with PNG export
│   │   │   │   └── PieChart.tsx    # SVG pie chart with PNG export
│   │   │   ├── connectors/
│   │   │   │   └── ConnectorsPanel.tsx
│   │   │   └── upload/
│   │   │       └── DocumentsTable.tsx
│   │   ├── hooks/
│   │   │   ├── useAuth.ts          # Authentication hook
│   │   │   └── useChat.ts          # Chat state & session management
│   │   ├── lib/
│   │   │   ├── api/
│   │   │   │   ├── client.ts       # Base fetch client
│   │   │   │   ├── auth.ts         # Auth API calls
│   │   │   │   ├── query.ts        # Query API calls
│   │   │   │   └── documents.ts    # Document API calls
│   │   │   ├── utils/
│   │   │   │   └── chartDetection.ts # Chart data extraction utility
│   │   │   └── constants.ts        # App-wide constants & source configs
│   │   ├── store/
│   │   │   └── authStore.ts        # Zustand auth state store
│   │   └── types/
│   │       ├── auth.ts             # Auth types
│   │       ├── chat.ts             # Chat/query types
│   │       └── connector.ts        # Connector types
│   ├── public/
│   │   └── acl-logo.png
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── docker/
│   └── init.sql                    # PostgreSQL initialization
├── docker-compose.yml              # Full stack orchestration
├── .env                            # Environment variables
└── README.md
```

## Quick Start

### Prerequisites
- Docker Desktop / Colima (Mac)
- Node.js 20+ (for frontend dev)
- Python 3.12+ (for backend dev)

### Production (Docker)
```bash
# Start all services
colima start --cpu 4 --memory 8 --disk 80 --dns 8.8.8.8
docker compose up -d

# Pull embedding model
docker exec intellirag-ollama ollama pull nomic-embed-text

# Register first admin user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@acldigital.com","name":"Admin","password":"your-password"}'
```

### Development

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev       # Development server
npm run build     # Production build
npm run start     # Start production server
```

## API Documentation
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| State Management | Zustand |
| Backend | FastAPI + Python 3.12 |
| Vector Database | Qdrant |
| Embeddings | Ollama + nomic-embed-text |
| LLM | Groq + Llama 3.3-70B |
| Relational DB | PostgreSQL |
| Object Storage | MinIO |
| Containerization | Docker Compose |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key | required |
| `GROQ_MODEL` | LLM model name | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | PostgreSQL connection string | see .env.example |
| `SECRET_KEY` | JWT signing secret | change in production |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |
