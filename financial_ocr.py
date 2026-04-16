import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

from groq import Groq
from dotenv import load_dotenv
import fitz  # PyMuPDF

load_dotenv()
GROQ_API_KEY="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"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class ChartReadyNormalizer:
    @staticmethod
    def to_numeric(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if not value or str(value).strip() in ["-", "null", "None", ""]:
            return 0.0
        s = str(value).strip()

        # Detect negativity BEFORE stripping characters
        is_negative = (
            ("(" in s and ")" in s) or          # accounting: (1,000)
            re.search(r"\$\s*-", s) is not None or  # dollar-negative: $-1,289
            s.startswith("-")                    # plain leading minus
        )

        # Strip everything except digits and decimal point
        s = re.sub(r"[^\d.]", "", s)
        try:
            result = float(s) if s else 0.0
            return -result if is_negative else result
        except ValueError:
            return 0.0


class FinancialPDFExtractor:
    """
    Extracts financial line items from a PDF using Groq LLM.
    Returns a dict in the standard 'financials' format consumed by app.py.
    """

    FINANCIAL_KEYWORDS = ["assets", "liabilities", "revenue", "expenses", "statement", "balance"]

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        api_key = GROQ_API_KEY
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from environment.")
        self.client = Groq(api_key=api_key)
        self.model = model
        self.normalizer = ChartReadyNormalizer()

    def _extraction_prompt(self, text: str) -> str:
        return f"""
You are a specialized financial OCR engine. Extract financial line items from the text below into structured JSON suitable for charting.

DOCUMENT TEXT:
{text}

CRITICAL INSTRUCTIONS:

1. YEAR DETECTION: Identify all fiscal years from column headers (e.g. 2020, 2019, "31 December 2020").
   Map each value to its correct year column.

2. NEGATIVE NUMBERS:
   - Brackets like (1,000) → NEGATIVE: -1000
   - Dollar-negative like $-1,289 → NEGATIVE: -1289
   - Plain minus like -500 → NEGATIVE: -500

3. MULTI-COLUMN MOVEMENT TABLES (e.g. Opening Balance / Increase / Reduction / Closing Balance):
   - These tables show ONE item with FOUR columns.
   - Extract ONLY the Closing Balance column as the item's value.
   - DO NOT create separate rows for Opening/Increase/Reduction.
   - Example: "Fuel and Materials | 30,457 | (1,289) | 0 | 29,168" → extract ONLY 29,168 as "Fuel and Materials"

4. ASSET DISPOSAL TABLES (Net Book Value / Proceeds / Profit / Loss columns):
   - Extract ONLY the Net Book Value and the Profit or Loss as separate items.
   - Name them: "[Asset name] - Net Book Value" and "[Asset name] - Profit/Loss"
   - DO NOT create rows for Proceeds separately.

5. CATEGORIZE each item: Revenue, Expenses, Assets, Liabilities, or Equity.

6. CURRENCY: Use the currency stated in the document header. If not visible on this page,
   default to AUD for Australian government/council documents.


OUTPUT FORMAT – strict JSON, NO markdown fences:
{{
    "metadata": {{
        "company_name": "Shire of Jerramungup",
        "currency": "AUD",
        "report_type": "Statement of Financial Activity"
    }},
    "line_items": [
        {{
            "category": "Assets",
            "item": "Cash and cash equivalents",
            "year": "2020",
            "raw_value": "6,174,704",
            "normalized_value": 6174704.0
        }},
        {{
            "category": "Liabilities",
            "item": "Contract liabilities",
            "year": "2020",
            "raw_value": "(2,089,231)",
            "normalized_value": -2089231.0
        }}
    ]
}}

RULES:
- "normalized_value" must be a JSON Number (not a string).
- Output raw JSON only — no explanation, no markdown.
- One row per item per year. Never duplicate the same item for the same year.
"""

    def _is_financial_page(self, text: str) -> bool:
        return any(kw in text.lower() for kw in self.FINANCIAL_KEYWORDS)

    def _clean_json(self, content: str) -> str:
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        return content.strip()

    def extract_from_bytes(self, pdf_bytes: bytes, filename: str = "upload.pdf", progress_callback=None) -> Dict:
        """
        Extract financial data from raw PDF bytes.
        progress_callback(current, total, message) is optional — used by Streamlit.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)

        result: Dict = {
            "file_info": {"filename": filename},
            "financials": [],
        }

        for page_idx, page in enumerate(doc):
            if progress_callback:
                progress_callback(page_idx + 1, total_pages, f"Processing page {page_idx + 1}/{total_pages}…")

            text = page.get_text("text")

            if not self._is_financial_page(text):
                logger.info(f"Page {page_idx + 1} skipped (no financial keywords)")
                continue

            logger.info(f"Extracting page {page_idx + 1}…")
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a precise financial data extraction API. Output strict JSON only."},
                        {"role": "user", "content": self._extraction_prompt(text)},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )

                raw = self._clean_json(response.choices[0].message.content)
                page_data = json.loads(raw)

                # Re-normalise with Python for reliability
                for item in page_data.get("line_items", []):
                    item["normalized_value"] = self.normalizer.to_numeric(item.get("raw_value"))

                result["financials"].append({"page": page_idx + 1, "content": page_data})

            except json.JSONDecodeError:
                logger.error(f"JSON parse failed on page {page_idx + 1}")
            except Exception as exc:
                logger.error(f"API error on page {page_idx + 1}: {exc}")

        doc.close()
        return result

    def extract_from_path(self, pdf_path: str) -> Dict:
        """Convenience wrapper for CLI / script usage."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        return self.extract_from_bytes(path.read_bytes(), filename=path.name)


# ── CLI entry point (python financial_ocr.py input.pdf output.json) ──────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python financial_ocr.py <input.pdf> <output.json>")
        sys.exit(1)

    extractor = FinancialPDFExtractor()
    data = extractor.extract_from_path(sys.argv[1])

    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved to {sys.argv[2]}")
