🌿 SatyaHarit Exposing greenwash with AI precision.

SatyaHarit is an AI-powered sustainability auditing tool designed to evaluate e-commerce product links, expose misleading greenwashing claims, and provide transparent authenticity scores without running into scraping blocks.

🌍 Problem Statement E-commerce platforms are saturated with vague or misleading marketing buzzwords (such as "eco-friendly," "sustainable," or "natural") that make it difficult for consumers to verify true environmental accountability. Furthermore, major e-commerce platforms (like Amazon, Meesho, and Myntra) employ strict anti-bot protections (403 Forbidden / Access Denied), causing standard web scrapers to fail repeatedly.

💡 Proposed Solution & How It Works SatyaHarit introduces a resilient zero-scraping architecture that guarantees 100% uptime and seamless performance:

Smart URL Slug Extraction: Instead of error-prone scraping, the system parses clean product names and categories directly from the URL path.

Dynamic AI Generation: The parsed titles and keywords are routed to Groq AI (Llama-3.3-70b-versatile) to instantly generate realistic greenwashing assessments, trust scores, pros, cons, and tailored reviews.

Category-Specific Visual Mapping: Automatically matches URL keywords to deliver context-aware product imagery and unique variations.

🚀 Key Features Zero-Scraping Reliability: Bypasses anti-bot barriers completely to avoid crashes and "Access Denied" errors.

Groq AI Integration: Powered by Llama-3.3-70b for fast, intelligent, and contextually rich sustainability insights.

Detailed Breakdown Metrics: Evaluates Material Sustainability, Ethical Sourcing, Packaging Circularity, and Claim Authenticity.

Dynamic Visual Previews: Intelligent image mapping for categories like apparel, skincare, accessories, and drinkware.

🛠️ Tech Stack Backend: FastAPI, Python, Uvicorn

AI Engine: Groq API (Llama-3.3-70b-versatile)

Deployment: Render (Backend), Netlify (Frontend)
