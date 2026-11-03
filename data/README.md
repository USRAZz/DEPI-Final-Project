# data/ (owner: M4 Ziad)
Raw datasets are NOT committed. Run the download scripts; files land in `data/raw/` (git-ignored).

| Dataset | Use | Script |
|---|---|---|
| PaySim | fraud model | `scripts/download_paysim.py` (Kaggle API) |
| IEEE-CIS Fraud | fraud model | `scripts/download_ieee.py` |
| Credit Card Fraud (ULB) | fraud model | `scripts/download_ulb.py` |
| SROIE, CORD | OCR F1 | `scripts/download_ocr.py` |
| Synthetic invoices/vendors | duplicates, IBAN changes, demo seed | `scripts/generate_synthetic.py` |
