"""
Module for generating personalized outbound confirmation / telesales system prompts based on Google Sheets lead data and Product Configuration.
"""

from typing import Any, Mapping
from app.products import product_knowledge_text


def build_outbound_sheet_prompt(
    lead_info: Mapping[str, Any],
    product: Mapping[str, Any] | None = None,
) -> str:
    """
    Generates a personalized system instruction for an outbound confirmation call
    using lead metadata (Name, Product, Quantity, Address, Notes) and Product Knowledge.
    """
    customer_name = str(lead_info.get("name") or "").strip()
    customer_phone = str(lead_info.get("phone") or "").strip()
    sheet_product = str(lead_info.get("product") or "").strip()
    quantity = str(lead_info.get("quantity") or "1").strip()
    address = str(lead_info.get("address") or "").strip()
    notes = str(lead_info.get("notes") or "").strip()

    active_product_name = (
        sheet_product
        or (str(product.get("name")) if product and product.get("name") else "Venus BigOne")
    )

    customer_context_lines = []
    if customer_name:
        customer_context_lines.append(f"- Customer Name: {customer_name}")
    if customer_phone:
        customer_context_lines.append(f"- Phone Number: {customer_phone}")
    if active_product_name:
        customer_context_lines.append(f"- Product of Interest: {active_product_name}")
    if quantity and quantity != "1":
        customer_context_lines.append(f"- Quantity: {quantity}")
    if address:
        customer_context_lines.append(f"- Stated Address: {address}")
    if notes:
        customer_context_lines.append(f"- Customer Notes: {notes}")

    customer_context_str = "\n".join(customer_context_lines) if customer_context_lines else "- No prior details recorded."

    greeting_guidance = (
        f'Greet {customer_name} warmly by name ("မင်္ဂလာပါရှင် {customer_name}...")'
        if customer_name
        else 'Greet the customer warmly ("မင်္ဂလာပါရှင်...")'
    )

    # Ingest Product-specific System Prompt & Knowledge Base if present
    product_sections = []
    if product:
        if product.get("system_prompt"):
            product_sections.append(f"Product Guidelines & System Prompt:\n{product['system_prompt'].strip()}")
        pk = product_knowledge_text(product)
        if pk:
            product_sections.append(f"Product Knowledge & Authorized Prices:\n{pk}")

    product_knowledge_str = "\n\n".join(product_sections) if product_sections else ""

    return f"""Role and Call Objective:
You are a friendly, professional telesales and order confirmation representative calling out to a customer for {active_product_name}.
Your objective is to proactively introduce yourself, confirm the customer's interest in {active_product_name}, answer any questions, confirm recipient name, phone, and delivery address, and close the order.

Customer File Context (from Google Sheet):
{customer_context_str}

{product_knowledge_str}

Voice call rules:
- Always answer in natural Burmese. Product names such as {active_product_name} may stay in English.
- Each turn should be only 1 to 2 short sentences and ask at most 1 next question.
- {greeting_guidance} and mention you are calling to consult/confirm their order for {active_product_name}.
- If the customer asks questions about price or usage, answer strictly according to authorized product prices and knowledge.
- Proactively guide the customer to complete the order confirmation: confirm quantity, confirm recipient name, confirm phone number, and confirm delivery address.
- Short acknowledgements such as "ဟုတ်ကဲ့", "အင်း", "ရပါတယ်", "ok" mean agreement/permission to proceed.
- Do not use aggressive pressure selling. Keep a polite, helpful, and reassuring tone at all times.
""".strip()
