# ML Calibration Model Evaluation Report

**Generated:** 2026-09-16 15:25:27 UTC  
**Model Type:** `gradient_boosting`  
**Evaluation Strategy:** Leave-One-Role-Out Cross-Validation (8 Folds)  
**Data Provenance:** Bootstrap AI Recruiter Labels (Perplexity) — replaces with live implicit feedback in production  

---

## 1. Overall Cross-Validation Performance

| Metric | Score |
| --- | --- |
| Accuracy | 0.9489 |
| Macro F1 Score | 0.7724 |
| Weighted F1 Score | 0.9513 |
| Top Match (Label 2) Precision | 0.8000 |
| Top Match (Label 2) Recall | 0.6667 |
| Top Match (Label 2) F1 Score | 0.7273 |

---

## 2. Confusion Matrix (Out-of-Fold Predictions)

Rows: True Ground Truth | Columns: Model Prediction

| Ground Truth \ Prediction | Reject (0) | Possible (1) | Top Match (2) |
| --- | --- | --- | --- |
| **Reject (0)** | 156 | 4 | 0 |
| **Possible (1)** | 2 | 7 | 1 |
| **Top Match (2)** | 0 | 2 | 4 |

---

## 3. Feature Importance Ranking

Features contributing to recruiter match suitability:

| Rank | Feature | Importance / Weight |
| --- | --- | --- |
| 1 | `final_score` | 0.4390 |
| 2 | `stage1_score` | 0.2066 |
| 3 | `years_experience` | 0.1187 |
| 4 | `stage3_score` | 0.0921 |
| 5 | `stage2_score` | 0.0650 |
| 6 | `stage2_met_count` | 0.0648 |
| 7 | `right_to_work_uk` | 0.0107 |
| 8 | `stage2_total_count` | 0.0032 |
| 9 | `stage1_passed` | 0.0000 |

---

## 4. Production Usage & Implicit Feedback Architecture

- **Inference Mode:** The ML calibration model acts as an explainable confidence layer on top of the 3-stage funnel.
- **Continuous Retraining:** Natural platform interactions (Shortlist ⭐ = 1, Interview 📞 = 2, Dismiss ❌ = 0) update ground truth labels in `ai_match_results.recruiter_label`.
- **Scheduled Calibration:** Retraining can be triggered periodically once sufficient human interactions are logged.
