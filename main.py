import os
import re
import json
import traceback
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

try:
    import google.generativeai as genai
except Exception:
    genai = None

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODEL_FALLBACKS = ["gemini-2.5-flash", "gemini-2.0-flash"]

PRODUCT_KEYWORDS = {
    "bag": "Sustainable Accessory",
    "backpack": "Sustainable Accessory",
    "wallet": "Sustainable Accessory",
    "purse": "Sustainable Accessory",
    "tote": "Sustainable Accessory",
    "sling": "Sustainable Accessory",
    "bottle": "Reusable Drinkware",
    "flask": "Reusable Drinkware",
    "cup": "Reusable Drinkware",
    "mug": "Reusable Drinkware",
    "water": "Reusable Drinkware",
    "shirt": "Eco Apparel",
    "t-shirt": "Eco Apparel",
    "clothing": "Eco Apparel",
    "dress": "Eco Apparel",
    "kurti": "Eco Apparel",
    "pants": "Eco Apparel",
    "top": "Eco Apparel",
    "cream": "Organic Skincare",
    "oil": "Organic Skincare",
    "soap": "Organic Skincare",
    "shampoo": "Organic Skincare",
    "serum": "Organic Skincare",
    "lotion": "Organic Skincare",
    "skincare": "Organic Skincare",
    "face": "Organic Skincare",
    "shoe": "Sustainable Footwear",
    "sneaker": "Sustainable Footwear",
    "sandal": "Sustainable Footwear",
    "boot": "Sustainable Footwear",
    "footwear": "Sustainable Footwear",
}

ECO_CLAIM_PATTERNS = [
    "organic", "recycled", "recyclable", "plastic free", "bpa free", "fair trade",
    "carbon neutral", "vegan", "cruelty free", "compostable", "responsibly sourced",
    "sustainably sourced", "biodegradable", "offset", "zero waste", "eco friendly",
    "natural ingredients", "certified", "made from recycled", "low impact"
]

DEFAULT_IMAGES = {
    "Sustainable Accessory": "https://images.unsplash.com/photo-1544816155-12df9643f363?w=500",
    "Reusable Drinkware": "https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=500",
    "Eco Apparel": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=500",
    "Organic Skincare": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=500",
    "Sustainable Footwear": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500",
}


def _normalize_space(text):
    return " ".join((text or "").replace("\xa0", " ").split())


def _get_title_from_url(url):
    try:
        path_segments = [p for p in urlparse(url).path.strip("/").split("/") if p]
        slug = ""
        if "p" in path_segments:
            p_idx = path_segments.index("p")
            if p_idx > 0:
                slug = path_segments[p_idx - 1]
        elif "dp" in path_segments:
            dp_idx = path_segments.index("dp")
            if dp_idx > 0:
                slug = path_segments[dp_idx - 1]
        elif path_segments:
            slug = path_segments[-1]
        if slug and len(slug) > 2:
            extracted = slug.replace("-", " ").replace("_", " ").title()
            if not any(word in extracted.lower() for word in ["access", "maintenance", "error"]):
                return extracted
    except Exception:
        pass
    return "Selected Product"


def _detect_product_type(url, text=""):
    combined = f"{url} {text}".lower()
    for keyword, product_type in PRODUCT_KEYWORDS.items():
        if keyword in combined:
            return product_type
    return "Eco Product"


def _extract_claims(text):
    normalized = (text or "").lower().replace("-", " ").replace("_", " ")
    text_lower = " ".join(normalized.split())
    claims = []

    for phrase in ECO_CLAIM_PATTERNS:
        if phrase in text_lower:
            claims.append(phrase)

    for keyword in ["recycled", "bpa free", "bpa", "organic", "eco", "water bottle", "reusable", "certified", "fair trade", "compostable", "vegan"]:
        if keyword in text_lower and keyword not in claims:
            claims.append(keyword)

    if not claims:
        title_words = [part for part in re.findall(r"[a-zA-Z]+", text_lower) if len(part) > 3]
        claims = list(dict.fromkeys(title_words[:5]))

    return claims[:10]


def extract_product_signals(html_text, url):
    soup = BeautifulSoup(html_text or "", "html.parser")
    title = ""
    for selector in ["meta[property='og:title']", "meta[name='title']", "title"]:
        tag = soup.select_one(selector)
        if tag:
            value = tag.get("content") or tag.get_text(" ", strip=True)
            if value:
                title = value
                break

    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

    meta_desc = ""
    meta_tag = soup.select_one("meta[name='description'], meta[property='og:description']")
    if meta_tag:
        meta_desc = meta_tag.get("content", "")

    body_text = soup.get_text(" ", strip=True)
    clean_text = _normalize_space(body_text)
    short_text = clean_text[:8000]

    claims = _extract_claims(f"{title} {meta_desc} {short_text}")
    if not claims:
        pieces = [title, meta_desc, short_text]
        for piece in pieces:
            if piece and len(piece) > 20:
                claims.append(piece[:80])

    image_candidates = []
    for selector in ["meta[property='og:image']", "meta[name='twitter:image']", "img"]:
        tag = soup.select_one(selector)
        if tag:
            value = tag.get("content") or tag.get("src")
            if value:
                image_candidates.append(value)

    for script in soup.select("script[type='application/ld+json']"):
        try:
            structured_data = json.loads(script.string or script.get_text())
            structured_items = structured_data if isinstance(structured_data, list) else [structured_data]
            for item in structured_items:
                if isinstance(item, dict):
                    image_value = item.get("image")
                    if isinstance(image_value, str):
                        image_candidates.append(image_value)
                    elif isinstance(image_value, list):
                        image_candidates.extend(image_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    product_image = ""
    for candidate in image_candidates:
        if isinstance(candidate, str) and candidate.strip():
            product_image = urljoin(url, candidate.strip())
            break

    return {
        "title": _normalize_space(title) or _get_title_from_url(url),
        "description": _normalize_space(meta_desc),
        "text": short_text,
        "claims": claims,
        "image": product_image,
    }


def _safe_json_loads(raw_value):
    if not raw_value:
        return {}
    cleaned = raw_value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        return json.loads(cleaned)
    except Exception:
        return {}


def _generate_fallback_report(product_type, title, text, url):
    evidence = f"{title} {text}".lower()
    claim_list = _extract_claims(evidence)
    has_material_proof = any(word in evidence for word in ["recycled", "organic", "stainless steel", "cotton", "hemp", "bamboo"])
    has_certification = any(word in evidence for word in ["certified", "gots", "fsc", "fair trade", "oekotex", "cruelty free"])
    has_supply_chain = any(word in evidence for word in ["supply chain", "factory", "fair wage", "artisan", "traceable", "sourcing"])
    has_lifecycle = any(word in evidence for word in ["recyclable", "compostable", "take back", "repair", "refill", "end of life"])
    material_score = 8 if has_material_proof and has_certification else 6 if has_material_proof else 3
    sourcing_score = 8 if has_supply_chain and has_certification else 5 if has_supply_chain else 3
    packaging_score = 8 if has_lifecycle and has_certification else 5 if has_lifecycle else 3
    claim_score = 8 if has_certification else min(7, 2 + len(claim_list)) if claim_list else 2
    score = max(35, min(92, round((material_score + sourcing_score + packaging_score + claim_score) * 2.5)))

    if score >= 78:
        verdict = "Low Greenwashing Risk"
    elif score >= 60:
        verdict = "Moderate Greenwashing Risk"
    else:
        verdict = "High Greenwashing Risk"

    review = (
        f"Bhai, {title} ({product_type}) ke available page evidence me ye claims/keywords mile: {', '.join(claim_list[:5]) or 'koi clear eco-claim nahi'}. "
        f"Material proof {'mila' if has_material_proof else 'nahi mila'}, certification {'mili' if has_certification else 'nahi mili'}, "
        f"sourcing detail {'mili' if has_supply_chain else 'nahi mili'}, aur lifecycle information {'mili' if has_lifecycle else 'nahi mili'}. "
        f"Is evidence ke basis par score {score}/100 hai. Marketing claims aur independently verifiable proof ke beech gap dikh raha hai, "
        f"isliye brand se material documents, certification number, aur supply-chain details maangni chahiye."
    )

    categories = [
        {"name": "Material Sustainability", "score": material_score, "reason": "Material evidence ko page content ke basis par assess kiya gaya."},
        {"name": "Ethical & Fair Sourcing", "score": sourcing_score, "reason": "Supply-chain aur labor transparency ke available evidence ke basis par score diya gaya."},
        {"name": "Packaging & Circularity", "score": packaging_score, "reason": "Lifecycle, reuse, repair, refill ya packaging evidence ke basis par score diya gaya."},
        {"name": "Claim Authenticity", "score": claim_score, "reason": "Claims ko certification ya independent proof ke against assess kiya gaya."},
    ]

    pros = []
    cons = []
    if has_material_proof:
        pros.append("Page me eco-conscious material language dikh rahi hai.")
    else:
        pros.append("Product category ko sustainable positioning ke liye attempt kiya gaya hai.")
    if has_certification:
        pros.append("Claim support ke liye certification mention mil raha hai.")
    else:
        pros.append("Product ko greener positioning ke hisaab se present kiya gaya hai.")

    if has_lifecycle:
        cons.append("Specific performance claims ka proof page par weak lag raha hai.")
    else:
        cons.append("Brand ke eco-claims ki authenticity ko verify karne ke liye zyada evidence chahiye, aur website par proof missing hai.")
    cons.append("Packaging, sourcing, and lifecycle transparency detailed nahi mil rahi, isliye kisi bhi website se genuine proof verify karna mushkil hota hai.")

    alternative = _build_alternative(product_type, title, evidence, score)

    return {
        "product_type": product_type,
        "green_trust_score": round(score),
        "ai_authenticity_score": round(score),
        "verdict": verdict,
        "review": review,
        "categories": categories,
        "pros": pros[:2],
        "cons": cons[:2],
        "alternative_suggestion": alternative,
        "claims_detected": [
            {"phrase": claim} for claim in claim_list[:10]
        ],
        "cert_checks": [],
    }


def _build_alternative(product_type, title, evidence, score):
    alternatives = {
        "Sustainable Accessory": (
            "Backpack ya bag lete waqt recycled polyester/organic cotton ka exact percentage, lining aur hardware material check karein. "
            "Better option wahi hoga jahan GRS, GOTS ya Fair Trade certification number verify ho, factory/supplier information public ho, "
            "aur repair, spare parts ya take-back program diya ho. Sirf 'eco bag' ya 'vegan leather' likha hona enough proof nahi hai."
        ),
        "Reusable Drinkware": (
            "Bottle ke liye food-grade stainless steel ya clearly specified recycled material choose karein. BPA-free claim ke saath food-contact safety, "
            "recycled-content percentage, leakproof parts ka replacement, packaging material aur end-of-life/recycling instructions bhi hone chahiye. "
            "Aisa seller better hai jo material grade, test report aur long-term repair/replacement support openly dikhata ho."
        ),
        "Eco Apparel": (
            "Kapdon me organic cotton ke liye GOTS certificate number, recycled fibre ka percentage, dyeing process aur factory/labour information verify karein. "
            "Best alternative woh hai jisme fabric composition 100% clear ho, low-impact dye ka proof ho, durable stitching ho, aur brand repair, resale ya take-back option deta ho."
        ),
        "Organic Skincare": (
            "Skincare me ingredient list, ingredient origin, batch details, cruelty-free certification aur packaging recyclability compare karein. "
            "'Natural' ya 'chemical-free' jaise vague words se zyada reliable product woh hai jisme full INCI list, responsible sourcing proof, dermatological testing aur refill/recyclable packaging clearly mentioned ho."
        ),
        "Sustainable Footwear": (
            "Shoes ke liye recycled/plant-based material ka exact percentage, adhesive aur sole composition, factory standards aur durability evidence dekhein. "
            "Preferred alternative woh hai jisme credible material certification, repairable construction, replaceable parts aur take-back/recycling program available ho."
        ),
    }
    guidance = alternatives.get(
        product_type,
        "Aisa alternative choose karein jisme material source, exact recycled/organic percentage, third-party certification, factory details, packaging information aur end-of-life plan clearly available ho."
    )
    return (
        f"{title} ke comparison me recommended direction: {guidance} "
        f"Current evidence score {score}/100 hai, isliye purchase se pehle brand se certification link, material breakdown aur sourcing proof maangna zaroori hai."
    )


def _normalize_report_score(report):
    category_scores = []
    for category in report.get("categories") or []:
        try:
            score = float(category.get("score"))
            if 0 <= score <= 10:
                category_scores.append(score)
        except (AttributeError, TypeError, ValueError):
            continue

    if category_scores:
        report["green_trust_score"] = round(sum(category_scores) / len(category_scores) * 10)
    else:
        try:
            report["green_trust_score"] = max(35, min(92, int(report.get("green_trust_score", 62))))
        except (TypeError, ValueError):
            report["green_trust_score"] = 62
    report["ai_authenticity_score"] = report["green_trust_score"]
    return report


def _is_complete_ai_report(report):
    required_text = ["review", "verdict", "alternative_suggestion"]
    if not isinstance(report, dict):
        return False
    if any(not isinstance(report.get(field), str) or not report[field].strip() for field in required_text):
        return False
    categories = report.get("categories")
    return isinstance(categories, list) and len(categories) >= 4


def _call_gemini_report(product_type, title, url, content_text, image_url=""):
    if genai is None:
        return None, "Gemini SDK load nahi hua. requirements.txt se google-generativeai install karein."
    if not GOOGLE_API_KEY:
        return None, "GOOGLE_API_KEY missing hai. backend/.env me valid Gemini API key add karein."

    last_issue = "Gemini ne valid report return nahi ki."
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        prompt = f"""
You are an expert sustainability auditor. Analyze the actual product page content only.

Product Title: {title}
URL: {url}
Product Category: {product_type}

Actual page text extracted from the URL:
{content_text[:7000]}

If a product image is attached, inspect its visible product type, material cues, packaging, labels, and claims. Do not invent details that are not visible in the page or image.

Give a realistic greenwashing assessment in Hinglish and return ONLY valid JSON. Calculate every category score from the supplied product evidence; never copy a sample score. Use this exact structure:
{{
  "product_type": "...",
    "green_trust_score": 0,
  "verdict": "Moderate Greenwashing Risk",
  "review": "Detailed Hinglish review here",
  "categories": [
        {{"name": "Material Sustainability", "score": 7, "reason": "..."}},
        {{"name": "Ethical & Fair Sourcing", "score": 6, "reason": "..."}},
        {{"name": "Packaging & Circularity", "score": 6, "reason": "..."}},
        {{"name": "Claim Authenticity", "score": 5, "reason": "..."}}
  ],
  "pros": ["...", "..."],
  "cons": ["...", "..."],
    "alternative_suggestion": "Detailed category-specific alternative guidance with material, certification, sourcing, packaging, lifecycle and verification steps."
}}
        """
        content_parts = [prompt]
        if image_url:
            image_response = requests.get(
                image_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            image_response.raise_for_status()
            content_type = image_response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]
            if content_type.startswith("image/"):
                content_parts.append({
                    "mime_type": content_type,
                    "data": image_response.content,
                })

        model_names = [GEMINI_MODEL] + [name for name in GEMINI_MODEL_FALLBACKS if name != GEMINI_MODEL]
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(content_parts)
                raw_text = getattr(response, "text", "") or ""
                parsed = _safe_json_loads(raw_text)
                if _is_complete_ai_report(parsed):
                    parsed["analysis_model"] = model_name
                    return _normalize_report_score(parsed), ""
                last_issue = f"Gemini model {model_name} ne incomplete ya invalid JSON report return ki."
                print(last_issue)
            except Exception as model_error:
                last_issue = f"Gemini model {model_name} error: {str(model_error)[:240]}"
                print(last_issue)
    except Exception as e:
        last_issue = f"Gemini setup/request error: {str(e)[:240]}"
        print(last_issue)
    return None, last_issue


def fetch_product_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception:
        return ""


def _analyze(data: dict):
    if not isinstance(data, dict):
        return {"error": "Invalid payload."}

    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "Please provide a valid product URL."}

    html_text = fetch_product_page(url)
    signals = extract_product_signals(html_text, url)
    title = signals["title"] or _get_title_from_url(url)
    product_type = _detect_product_type(url, f"{title} {signals['description']} {signals['text']}")
    product_image = signals["image"] or DEFAULT_IMAGES.get(product_type, DEFAULT_IMAGES["Eco Product"] if "Eco Product" in DEFAULT_IMAGES else "")

    report, analysis_issue = _call_gemini_report(
        product_type,
        title,
        url,
        signals["text"],
        signals["image"],
    )
    analysis_source = "gemini" if report else "fallback"
    if not report:
        report = _generate_fallback_report(product_type, title, signals["text"], url)

    if "green_trust_score" not in report and "ai_authenticity_score" in report:
        report["green_trust_score"] = report["ai_authenticity_score"]
    if "product_type" not in report:
        report["product_type"] = product_type
    if "product_title" not in report:
        report["product_title"] = title
    if "product_image" not in report:
        report["product_image"] = product_image
    if "verdict" not in report:
        report["verdict"] = "Moderate Greenwashing Risk"
    if "claims_detected" not in report:
        report["claims_detected"] = [{"phrase": claim} for claim in signals["claims"]]
    if "cert_checks" not in report:
        report["cert_checks"] = []
    if "review" not in report:
        report["review"] = f"Product {title} ke liye review available nahi tha."

    return {
        "product_type": report.get("product_type", product_type),
        "product_title": report.get("product_title", title),
        "product_image": report.get("product_image", product_image),
        "green_trust_score": report.get("green_trust_score", report.get("ai_authenticity_score", 62)),
        "ai_authenticity_score": report.get("ai_authenticity_score", report.get("green_trust_score", 62)),
        "verdict": report.get("verdict", "Moderate Greenwashing Risk"),
        "review": report.get("review", "No review available."),
        "categories": report.get("categories", []),
        "claims_detected": report.get("claims_detected", [{"phrase": claim} for claim in signals["claims"]]),
        "cert_checks": report.get("cert_checks", []),
        "pros": report.get("pros", []),
        "cons": report.get("cons", []),
        "alternative_suggestion": report.get("alternative_suggestion", "Choose a more transparent option with clear certifications."),
        "analysis_source": analysis_source,
        "analysis_model": report.get("analysis_model", "evidence-fallback"),
        "analysis_issue": analysis_issue,
    }


@app.post("/analyze")
def analyze(data: dict):
    try:
        return _analyze(data)
    except Exception as e:
        print("=== /analyze CRASHED ===")
        traceback.print_exc()
        return {"error": f"Backend execution error: {str(e)}"}


@app.get("/")
def health_check():
    return {"status": "ok"}
