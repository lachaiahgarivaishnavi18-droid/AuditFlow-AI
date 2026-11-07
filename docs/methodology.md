# Methodology and configurable rule catalogue

This application checks internal consistency and evidence coverage. It does not determine authenticity, fraud, regulatory compliance or an audit opinion.

| Rule | Preconditions | Calculation/indicator |
| --- | --- | --- |
| Period validation | ISO row date | Audit start <= date <= audit end |
| Invoice required fields | Invoice category | invoice_number,date,currency,amount and vendor/customer presence |
| Invoice amount | amount | Negative amount requires review as possible credit note |
| Invoice tax arithmetic | net,tax,total | abs(net+tax-total) <= tolerance; no statutory tax-rate determination |
| Duplicate invoice | Invoice number/counterparty/currency | Repeated category/counterparty/invoice/currency key |
| Ledger required fields | Ledger/trial balance/journal | account_code,reference,date presence |
| Ledger amount signs | debit and credit | Nonnegative debit and credit |
| Ledger balance | Rows grouped by source document, journal reference and currency | Sum(debit) vs sum(credit) within tolerance |
| Bank reference | Bank rows | reference presence |
| Bank balance arithmetic | opening,closing,debit,credit | opening+credit-debit vs closing; review bank sign convention |
| Payroll net pay | employee_id,salary,deductions,amount | salary-deductions vs amount |
| Duplicate employee payment | employee_id,date,amount,currency | Repeated employee payment key |
| Employee record matching | employee_id and supporting register row | Identifier match requires review; absent register is incomplete |
| Bank amount signs | debit,credit | Nonnegative signs; simultaneous debit/credit requires review |
| Duplicate expense claim | reference,date,amount,currency | Repeated expense claim key |
| Expense receipt amount | expense and referenced receipt amounts | Exact Decimal difference within tolerance |
| Expense receipt | Reference and currency | Matching receipt reference; amount/nature requires further review |
| Structured data availability | Unstructured document | Not Verifiable; financial rows are not invented |

Audit settings accept `tolerance` (0..10,000), `date_window` (0..90 days) and `disabled_rules` (exact names from the catalogue). The UI exposes tolerance and date window. Rule disablement is available through the authenticated settings API and is logged. Currency equality is mandatory for matching; currency conversion is not performed. Financial arithmetic uses Decimal. Anomaly model inputs use floats only for statistical scoring, never monetary reconciliation.

Reconciliation supports bank/cash book, GL/trial balance, purchase register/invoices, sales register/invoices, payroll/payments, expense register/receipts, invoices/payments, PO/invoices and invoices/goods receipt. Reference equality takes precedence; otherwise amount within tolerance and date window may match. Each target is consumed once per comparison pair. Equal-ranked candidates require human review. Many-to-one partial payments are left unmatched for investigation.

Isolation Forest uses amount only, grouped by currency, minimum eight rows, 100 estimators and random_state=42. It is a demonstration baseline, not a fraud classifier. Duplicate transaction keys are also flagged deterministically. No SHAP claim is made for this unsupervised baseline. Model quality is not established by the synthetic fixture.
