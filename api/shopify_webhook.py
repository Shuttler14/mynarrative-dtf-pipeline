"""
Shopify Webhook Handler
=======================
Receives Shopify webhook events and triggers the DTF automation pipeline.
Supports payment/order completion webhooks.

Webhook Events:
- orders/paid - When payment is successful
- orders/create - When order is created (use this for immediate processing)

Setup in Shopify Admin:
1. Go to Settings → Notifications → Webhooks
2. Click "Create webhook"
3. Set:
   - Event: Order updated (or orders/create)
   - URL: https://your-vercel-url.vercel.app/api/webhook/shopify
   - Format: JSON
   - Webhook API version: Latest stable (e.g., 2024-01)
4. Copy the webhook secret

Author: Claude Code
"""

import os
import json
import hmac
import hashlib
import base64
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, Header, Depends

router = APIRouter(prefix="/api", tags=["shopify"])


def verify_shopify_hmac(body: bytes, hmac_header: str, secret: str) -> bool:
    """
    Verify the Shopify webhook HMAC signature.

    Args:
        body: Raw request body bytes
        hmac_header: X-Shopify-Hmac-SHA256 header value
        secret: Webhook secret from Shopify admin

    Returns:
        True if signature is valid
    """
    if not secret:
        return True  # Skip verification if no secret

    if not hmac_header:
        return False

    # Decode the provided HMAC
    provided_hmac = base64.b64decode(hmac_header)

    # Calculate expected HMAC
    expected_hmac = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).digest()

    # Constant-time comparison
    return hmac.compare_digest(expected_hmac, provided_hmac)


def extract_design_from_line_item(item: Dict) -> Optional[Dict[str, str]]:
    """
    Extract design UUID and product type from Shopify line item properties.

    Expected properties:
    - _design_uuid: The unique design identifier
    - _product_type: "tee" or "hoodie"

    Args:
        item: Shopify line item dict

    Returns:
        Dict with design_uuid and product_type, or None
    """
    properties = item.get("properties", [])

    # Handle both list and dict formats for properties
    if isinstance(properties, dict):
        properties = [{"name": k, "value": v} for k, v in properties.items()]

    design_uuid = None
    product_type = "tee"

    for prop in properties:
        name = prop.get("name", "")
        value = prop.get("value", "")

        if name == "_design_uuid":
            design_uuid = value
        elif name == "_product_type":
            product_type = value if value in ["tee", "hoodie"] else "tee"

    if not design_uuid:
        return None

    return {
        "design_uuid": design_uuid,
        "product_type": product_type
    }


def extract_customer_info(payload: Dict) -> Dict[str, str]:
    """
    Extract customer information from Shopify order payload.
    """
    customer = payload.get("customer", {})
    email = payload.get("email", "unknown")

    if customer:
        email = customer.get("email", email)
        customer_id = customer.get("id", "unknown")
    else:
        customer_id = "unknown"

    return {
        "customer_id": str(customer_id),
        "email": email,
        "first_name": customer.get("first_name", ""),
        "last_name": customer.get("last_name", "")
    }


@router.post("/webhook/shopify")
async def handle_shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_shop: Optional[str] = Header(None),
    x_shopify_topic: Optional[str] = Header(None)
):
    """
    Main Shopify webhook endpoint.

    Headers:
    - X-Shopify-Hmac-SHA256: Webhook signature
    - X-Shopify-Shop-Domain: Shop domain (e.g., my-store.myshopify.com)
    - X-Shopify-Topic: Event type (e.g., orders/paid)

    Environment:
    - SHOPIFY_WEBHOOK_SECRET: Webhook secret for signature verification
    - SHOPIFY_API_KEY: (optional) For Shopify Admin API calls
    - SHOPIFY_API_SECRET: (optional) For Shopify Admin API calls
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature
    secret = os.getenv('SHOPIFY_WEBHOOK_SECRET', '')
    if secret and not verify_shopify_hmac(body, x_shopify_hmac_sha256 or "", secret):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )

    # Parse payload
    payload = json.loads(body)

    # Log webhook receipt
    print(f"📦 Shopify webhook received: {x_shopify_topic}")
    print(f"   Shop: {x_shopify_shop}")
    print(f"   Order: {payload.get('order_number', 'N/A')}")

    # Extract all designs from the order
    designs_to_process = []
    line_items = payload.get("line_items", [])

    for item in line_items:
        design_info = extract_design_from_line_item(item)
        if design_info:
            designs_to_process.append({
                **design_info,
                "item_id": item.get("id"),
                "variant_title": item.get("variant_title", ""),
                "quantity": item.get("quantity", 1)
            })

    if not designs_to_process:
        return {
            "status": "ignored",
            "message": "No DTF designs found in order"
        }

    # Extract customer info
    customer_info = extract_customer_info(payload)

    # Process each design
    processed_designs = []
    errors = []

    for design in designs_to_process:
        try:
            # Import here to avoid circular imports
            from dtf_pipeline import process_design_flow

            result = await process_design_flow(
                design_uuid=design["design_uuid"],
                user_id=customer_info["email"],
                design_url=f"https://cdn.mynarrative.store/previews/{design['design_uuid']}.jpg",
                product_type=design["product_type"]
            )

            processed_designs.append({
                "design_uuid": design["design_uuid"],
                "product_type": design["product_type"],
                "status": result.status,
                "steps_completed": result.steps_completed,
                "error": result.error,
                "pdf_url": result.pdf_url
            })

        except Exception as e:
            errors.append({
                "design_uuid": design["design_uuid"],
                "error": str(e)
            })
            print(f"❌ Error processing design {design['design_uuid']}: {e}")

    # Return response
    return {
        "status": "processed" if processed_designs else "error",
        "order_id": payload.get("id"),
        "order_number": payload.get("order_number"),
        "shop": x_shopify_shop,
        "designs_processed": processed_designs,
        "errors": errors,
        "customer": customer_info
    }


@router.get("/webhook/test")
async def test_webhook():
    """
    Test endpoint to verify webhook connectivity.
    Use this during Shopify webhook setup.
    """
    return {
        "status": "ok",
        "message": "DTF Automation webhook endpoint is active",
        "version": "1.0.0"
    }


@router.post("/webhook/shopify/test")
async def test_webhook_with_payload(request: Request):
    """
    Test endpoint that echoes back the received payload.
    Useful for debugging Shopify webhook configuration.
    """
    body = await request.body()
    payload = json.loads(body)

    return {
        "received": True,
        "payload_keys": list(payload.keys()) if payload else [],
        "order_number": payload.get("order_number"),
        "total_price": payload.get("total_price"),
        "line_items_count": len(payload.get("line_items", []))
    }


# Example webhook registration payload for Shopify
WEBHOOK_CONFIG = {
    "webhook": {
        "topic": "orders/updated",
        "address": "https://your-vercel-url.vercel.app/api/webhook/shopify",
        "format": "json",
        "api_version": "2024-01"
    }
}


def get_webhook_setup_instructions() -> str:
    """
    Returns instructions for setting up the webhook in Shopify Admin.
    """
    return """
# Shopify Webhook Setup Instructions

## Step 1: Get your webhook URL
Deploy this project to Vercel, then note your deployment URL:
https://your-project.vercel.app/api/webhook/shopify

## Step 2: Create webhook in Shopify Admin
1. Go to: Settings → Notifications → Webhooks
2. Click "Create webhook"
3. Fill in:
   - **Event**: Orders updated (or Orders create)
   - **URL**: Your Vercel deployment URL
   - **Format**: JSON
   - **API version**: 2024-01 (or latest)
4. Click Save

## Step 3: Copy the webhook secret
After creating the webhook, you'll see a "Webhook API secret key".
Copy it and add to Vercel environment variables:
- Key: SHOPIFY_WEBHOOK_SECRET
- Value: (the secret from Shopify)

## Step 4: Test the webhook
1. In Shopify, click "Send test notification"
2. Check your Vercel logs or use the /api/webhook/test endpoint

## Step 5: Verify the line item properties
Make sure your Shopify product has these properties:
- _design_uuid: The UUID of the generated design
- _product_type: "tee" or "hoodie"

These should be added when the customer customizes their design before checkout.
"""