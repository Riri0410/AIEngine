# CreativeOps AI — Run Instructions

This guide explains how to set up and run the CreativeOps AI backend and frontend locally.

## Prerequisites
- **Python 3.10+**
- **OpenAI API Key**

## 1. Setup

### Clone and Navigate
```bash
git clone <repository-url>
cd AIEngine/creativeops
```

### Environment Variables
Create a `.env` file in the `creativeops/` directory:
```bash
cp .env.example .env
```
Open `.env` and add your OpenAI API key:
```env
OPENAI_API_KEY=sk-....
```

### Virtual Environment & Dependencies
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 2. Running the Application

### Start the Backend (FastAPI)
From the `creativeops/` directory:
```bash
source venv/bin/activate
python3 main.py
```
The backend will be available at [http://localhost:8000](http://localhost:8000). </br>
Backend: [http://localhost:8000](http://localhost:8000) </br>
Swagger: [http://localhost:8000/docs](http://localhost:8000/docs) </br>

### Start the Frontend
In a new terminal, from the `creativeops/` directory:
```bash
python3 -m http.server 3000
```
The frontend will be available at [http://localhost:3000](http://localhost:3000).

---

## API Documentation
Once the backend is running, you can access the interactive API docs:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Health Check
Verify the backend is running:
```bash
curl http://localhost:8000/health
```
