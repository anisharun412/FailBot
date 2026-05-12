# FailBot Evaluation Report

## Summary

| Metric | Value |
| --- | ---: |
| category_accuracy | 0.67 |
| severity_accuracy | 0.67 |
| test_keyword_recall | 0.50 |
| confidence_ok | 1.00 |

## Runs

| log_file | status | failure_category | severity | triage_confidence | category_accuracy | severity_accuracy | test_keyword_recall | eval_test_relevance | eval_confidence_ok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ci_failure_001.txt | report_complete | code_bug | medium | 0.97 | 1.00 | 0.50 | 0.50 | 0.50 | True |
| ci_failure_002.txt | report_complete | infra | high | 0.85 | 0.00 | 0.50 | 0.67 | 0.67 | True |
| ci_failure_003.txt | report_complete | infra | high | 0.97 | 1.00 | 1.00 | 0.33 | 0.33 | True |
