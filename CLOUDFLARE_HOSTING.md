# Hosting on Cloudflare Guide

You can host both the frontend and the backend of CreativeOps AI on Cloudflare for free.

## 1. Frontend: Cloudflare Pages

Cloudflare Pages is the best place for your `index.html`.

1.  **Prepare for Deploy**: Ensure your `index.html` is in a folder (e.g., `creativeops/`).
2.  **Deploy**:
    -   Log in to the [Cloudflare Dashboard](https://dash.cloudflare.com).
    -   Go to **Workers & Pages** > **Create application** > **Pages** > **Upload assets**.
    -   Drag and drop the `creativeops/` folder.
3.  **Note**: Once deployed, you will get a URL like `https://creative-ops.pages.dev`.

## 2. Backend: Cloudflare Workers (Python)

Cloudflare now supports Python natively in Workers!

### Setup Wrangler
If you haven't yet, install the Cloudflare CLI:
```bash
npm install -g wrangler
```

### Configuration
I've already created a `wrangler.toml` file in `creativeops/`. 

### Deploying the Backend
1.  **Login**:
    ```bash
    wrangler login
    ```
2.  **Add your OpenAI Key** (Secret):
    ```bash
    wrangler secret put OPENAI_API_KEY
    ```
    (Enter your key when prompted)
3.  **Deploy**:
    ```bash
    cd creativeops
    wrangler deploy
    ```
4.  **Backend URL**: You will get a URL like `https://creative-ops-api.your-subdomain.workers.dev`.

---

## 3. Connecting Frontend to Backend

After deploying both, you need to tell the frontend where the backend is.

1.  Open `index.html`.
2.  Find line 118:
    ```javascript
    const API_BASE = 'http://localhost:8000';
    ```
3.  Change it to your Worker URL:
    ```javascript
    const API_BASE = 'https://creative-ops-api.your-subdomain.workers.dev';
    ```
4.  Re-upload `index.html` to Cloudflare Pages.

---

## Troubleshooting
- **CORS**: The backend (`main.py`) already has `allow_origins=["*"]`, so it should work from any domain.
- **Python Compatibility**: Cloudflare's Python Worker runtime is still evolving. If some libraries in `requirements.txt` fail to install, you might need to use a simpler `httpx` based worker instead of full `FastAPI`.
