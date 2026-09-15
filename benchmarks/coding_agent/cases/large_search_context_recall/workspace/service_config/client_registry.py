"""Explicit downstream-client configuration registry."""

from service_config.timeouts import DEFAULT_REQUEST_TIMEOUT_SECONDS

CLIENT_REQUEST_TIMEOUTS = {
    "accounting-ledger": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "anti-fraud-screening": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "bank-transfer-gateway": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "billing-invoice": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "card-authorization": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "cash-application": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "chargeback-management": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "compliance-audit": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "contract-entitlement": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "credit-risk-profile": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "currency-conversion": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "customer-notification": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "data-export": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "document-archive": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "invoice-delivery": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "merchant-settlement": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "payment-reconciliation": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "payout-orchestration": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "pricing-catalog": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "refund-processing": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "report-generation": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "revenue-recognition": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "tax-calculation": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "tenant-configuration": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "transaction-journal": DEFAULT_REQUEST_TIMEOUT_SECONDS,
}
