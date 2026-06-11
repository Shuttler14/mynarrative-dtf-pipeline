"""
DTF Automation Pipeline - Main Entry Point
==========================================
Handles Shopify webhook triggers and orchestrates the full DTF workflow:
1. Shopify payment webhook → triggers pipeline
2. OpenAI content safety check
3. Image upscaling for print quality
4. Background removal
5. Nesting optimization for CoralDraw sheets
6. PDF generation for DTF print

Environment Variables Required:
- OPENAI_API_KEY: OpenAI API key for content moderation
- AWS_ACCESS_KEY_ID: AWS credentials for S3
- AWS_SECRET_ACCESS_KEY: AWS secret key
- AWS_REGION: AWS region (default: ap-south-1)
- S3_BUCKET_NAME: S3 bucket for designs
- SHOPIFY_WEBHOOK_SECRET: Verify Shopify webhook signature

Author: Claude Code
"""

import os
import json
import hashlib
import hmac
import base64
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Header, Depends
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError

# Import our pipeline stages
from api.content_safety import ContentSafetyChecker
from api.image_upscaler import ImageUpscaler
from api.background_remover import BackgroundRemover
from api.nesting_optimizer import NestingOptimizer
from api.pdf_generator import PDFGenerator

app = FastAPI(title="DTF Automation Pipeline", version="1.0.0")

# Initialize services
content_safety = ContentSafetyChecker()
image_upscaler = ImageUpscaler()
bg_remover = BackgroundRemover()
nesting_optimizer = NestingOptimizer()
pdf_generator = PDFGenerator()

# S3 Client (lazy initialization)
s3_client = None
S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'mynarrative-dtf')


def get_s3_client():
    """Lazy initialize S3 client to avoid import-time errors"""
    global s3_client
    if s3_client is None:
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'ap-south-1')
            )
        except Exception as e:
            print(f"Warning: Could not initialize S3 client: {e}")
            s3_client = None
    return s3_client


class ShopifyWebhookPayload(BaseModel):
    """Schema for Shopify order webhook"""
    order_id: str
    order_number: int
    email: str
    total_price: float
    currency: str
    line_items: List[Dict[str, Any]]
    customer: Optional[Dict[str, Any]] = None
    shipping_address: Optional[Dict[str, Any]] = None
    created_at: str


class DTFProcessRequest(BaseModel):
    """Manual trigger request for testing"""
    design_uuid: str
    user_id: str
    design_url: str
    product_type: str = "tee"  # tee or hoodie


class DTFProcessResponse(BaseModel):
    """Response for DTF processing"""
    order_id: str
    design_uuid: str
    status: str  # pending, processing, safe, unsafe, completed, failed
    steps_completed: List[str]
    pdf_url: Optional[str] = None
    error: Optional[str] = None
    processing_time_seconds: float


def verify_shopify_webhook(
    body: bytes,
    hmac_header: str,
    secret: str
) -> bool:
    """Verify Shopify webhook HMAC signature"""
    if not secret or not hmac_header:
        return True  # Skip verification if no secret configured

    generated_hmac = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).digest()

    # Shopify sends base64-encoded HMAC
    try:
        decoded_hmac = base64.b64decode(hmac_header)
        return hmac.compare_digest(generated_hmac, decoded_hmac)
    except Exception:
        # Fallback: try hex comparison
        return hmac.compare_digest(generated_hmac.hex(), hmac_header)


def download_design_from_s3(design_uuid: str, user_id: str) -> Optional[bytes]:
    """Download design image from S3"""
    client = get_s3_client()
    if not client:
        print("Warning: S3 client not available")
        return None
    try:
        key = f"designs/{user_id}/{design_uuid}.png"
        response = client.get_object(Bucket=S3_BUCKET, Key=key)
        return response['Body'].read()
    except ClientError as e:
        print(f"Error downloading design: {e}")
        return None


def upload_to_s3(data: bytes, key: str, content_type: str = "image/png") -> Optional[str]:
    """Upload processed file to S3"""
    client = get_s3_client()
    if not client:
        print("Warning: S3 client not available")
        return None
    try:
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type
        )
        return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return None


def create_pending_sheet() -> Dict[str, Any]:
    """Initialize or get pending sheet for nesting"""
    # This would interact with your database in production
    return {
        "sheet_id": f"sheet_{int(time.time())}",
        "created_at": datetime.now().isoformat(),
        "designs": [],
        "status": "open"
    }


async def process_design_flow(
    design_uuid: str,
    user_id: str,
    design_url: str,
    product_type: str
) -> DTFProcessResponse:
    """
    Full DTF processing pipeline:
    1. Download design from S3
    2. Content safety check (OpenAI)
    3. Image upscaling
    4. Background removal
    5. Add to nesting queue
    6. Generate PDF when sheet is full
    """
    start_time = time.time()
    steps_completed = []
    error_message = None

    try:
        # Step 1: Download design from S3
        print(f"📥 Step 1: Downloading design {design_uuid}")
        design_bytes = download_design_from_s3(design_uuid, user_id)
        if not design_bytes:
            raise Exception("Failed to download design from S3")
        steps_completed.append("download")

        # Step 2: Content Safety Check (OpenAI)
        print(f"🛡️ Step 2: Running content safety check")
        safety_result = await content_safety.check_image(design_bytes)

        if not safety_result["is_safe"]:
            return DTFProcessResponse(
                order_id=design_uuid,
                design_uuid=design_uuid,
                status="unsafe",
                steps_completed=steps_completed,
                error=f"Content flagged: {safety_result.get('flags', [])}"
            )
        steps_completed.append("content_safety")

        # Step 3: Image Upscaling
        print(f"📈 Step 3: Upscaling image for print quality")
        upscaled_bytes = await image_upscaler.upscale(
            design_bytes,
            target_dpi=300,
            min_width=3000,
            min_height=3000
        )

        # Upload upscaled version
        upscaled_key = f"processed/upscaled/{user_id}/{design_uuid}.png"
        upload_to_s3(upscaled_bytes, upscaled_key)
        steps_completed.append("upscaled")

        # Step 4: Background Removal
        print(f"✂️ Step 4: Removing background")
        no_bg_bytes = await bg_remover.remove_background(upscaled_bytes)

        # Upload transparent version
        transparent_key = f"processed/transparent/{user_id}/{design_uuid}.png"
        upload_to_s3(no_bg_bytes, transparent_key)
        steps_completed.append("background_removed")

        # Step 5: Add to nesting queue
        print(f"📐 Step 5: Adding to nesting optimizer")
        nesting_result = await nesting_optimizer.add_design(
            design_uuid=design_uuid,
            design_image=no_bg_bytes,
            user_id=user_id,
            product_type=product_type
        )

        steps_completed.append("nesting_queued")

        # Step 6: Check if sheet is ready for PDF generation
        if nesting_result.get("sheet_ready"):
            print(f"📄 Step 6: Generating CoralDraw PDF")
            pdf_bytes = await pdf_generator.generate_coraldraw_sheet(
                sheet_id=nesting_result["sheet_id"]
            )

            # Upload PDF
            pdf_key = f"print-ready/{nesting_result['sheet_id']}.pdf"
            pdf_url = upload_to_s3(pdf_bytes, pdf_key, "application/pdf")
            steps_completed.append("pdf_generated")

            return DTFProcessResponse(
                order_id=design_uuid,
                design_uuid=design_uuid,
                status="completed",
                steps_completed=steps_completed,
                pdf_url=pdf_url,
                processing_time_seconds=time.time() - start_time
            )

        # Design added to queue, awaiting more designs
        return DTFProcessResponse(
            order_id=design_uuid,
            design_uuid=design_uuid,
            status="processing",
            steps_completed=steps_completed,
            processing_time_seconds=time.time() - start_time
        )

    except Exception as e:
        error_message = str(e)
        print(f"❌ Pipeline error: {error_message}")

        return DTFProcessResponse(
            order_id=design_uuid,
            design_uuid=design_uuid,
            status="failed",
            steps_completed=steps_completed,
            error=error_message,
            processing_time_seconds=time.time() - start_time
        )


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "DTF Automation Pipeline",
        "version": "1.0.0"
    }


@app.post("/webhook/shopify")
async def shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None)
):
    """
    Shopify webhook endpoint - triggers on payment
    Configure in Shopify: Settings → Notifications → Webhooks
    """
    body = await request.body()

    # Verify webhook (optional - set SHOPIFY_WEBHOOK_SECRET env var)
    secret = os.getenv('SHOPIFY_WEBHOOK_SECRET', '')
    if secret and not verify_shopify_webhook(body, x_shopify_hmac_sha256 or "", secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse webhook payload
    payload = json.loads(body)

    # Find designs in order (look for _design_uuid in line item properties)
    processed_orders = []

    for item in payload.get("line_items", []):
        properties = item.get("properties", [])
        design_uuid = None
        product_type = "tee"

        for prop in properties:
            if prop.get("name") == "_design_uuid":
                design_uuid = prop.get("value")
            if prop.get("name") == "_product_type":
                product_type = prop.get("value", "tee")

        if design_uuid:
            # Get customer info for user_id
            user_id = payload.get("email", "unknown")

            # Process this design
            result = await process_design_flow(
                design_uuid=design_uuid,
                user_id=user_id,
                design_url=f"https://cdn.mynarrative.store/previews/{design_uuid}.jpg",
                product_type=product_type
            )

            processed_orders.append({
                "design_uuid": design_uuid,
                "status": result.status,
                "steps": result.steps_completed
            })

    return {
        "received": True,
        "orders_processed": processed_orders
    }


@app.post("/process-design")
async def process_design_endpoint(
    request: DTFProcessRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Manual design processing endpoint (for testing)
    Use: curl -X POST /process-design -d '{"design_uuid": "...", ...}'
    """
    # Simple API key check
    api_key = os.getenv('DTF_API_KEY', '')
    if api_key and authorization != f"Bearer {api_key}":
        raise HTTPException(status_code=401, detail="Invalid API key")

    result = await process_design_flow(
        design_uuid=request.design_uuid,
        user_id=request.user_id,
        design_url=request.design_url,
        product_type=request.product_type
    )

    return result


@app.get("/status/{design_uuid}")
async def get_status(design_uuid: str):
    """
    Check processing status of a design
    """
    # In production, this would query your database
    # For now, return a placeholder
    return {
        "design_uuid": design_uuid,
        "status": "processing",  # Would be fetched from DB
        "steps": [],
        "last_updated": datetime.now().isoformat()
    }


@app.post("/trigger-sheet")
async def trigger_sheet_generation():
    """
    Manually trigger sheet PDF generation even if not full
    Useful for end of day processing
    """
    result = await pdf_generator.generate_coraldraw_sheet(sheet_id="manual")

    pdf_key = f"print-ready/manual_{int(time.time())}.pdf"
    pdf_url = upload_to_s3(result, pdf_key, "application/pdf")

    return {"pdf_url": pdf_url}


# For Vercel serverless deployment
handler = app