from .storage import invoice_by_key


def find_invoice(db, payment):
    """Return the id of the invoice this payment belongs to, or None.

    A payment attaches only to an invoice with the same customer_id AND
    invoice_number (BUSINESS_RULES, "Records and identity"). A matching amount
    alone does not establish identity, so it is never used to pick an invoice.
    """
    exact = invoice_by_key(db, payment['customer_id'], payment['invoice_number'])
    return exact['id'] if exact else None
